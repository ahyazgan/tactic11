"""Kayıtlı iş tanımları.

Yeni iş ekleme: handler yaz + dosya sonunda `register(JobSpec(...))` çağır.
Bu modül `app.scheduler.__init__` tarafından otomatik import edilir, böylece
kayıt side effect'i tetiklenir.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select

from app.agents import (
    InjuryLoadAgent,
    MegaMatchAgent,
    NoUpcomingMatch,
    OpponentScoutAgent,
    PostMatchReportAgent,
    PreMatchReportAgent,
    WeeklyDigestAgent,
    save_agent_output,
)
from app.core.logging import get_logger
from app.data.ingest import sync_league
from app.data.predictions import reconcile_pending_predictions
from app.data.sources.api_football import APIFootball
from app.db import models
from app.db.session import SessionLocal
from app.scheduler.registry import JobSpec, register
from app.sports import football

log = get_logger(__name__)


def sync_league_handler(*, league_id: int, season: int, last: int = 10) -> None:
    """Bir lig + sezon için adapter'dan çek ve DB'ye yaz (CLI ile aynı yol)."""
    source = APIFootball()
    with SessionLocal() as session:
        report = sync_league(
            session,
            source,
            league_id=league_id,
            season=season,
            matches_per_team=last,
        )
    log.info(
        "job sync_league: leagues=%d teams=%d matches=%d snapshot=%d",
        report.leagues_written,
        report.teams_written,
        report.matches_written,
        report.snapshot_id,
    )


def reconcile_predictions_handler(*, sport: str = football.SPORT_NAME) -> None:
    """Bitmiş maçların actual sonucunu predictions tablosuna yaz."""
    with SessionLocal() as session:
        report = reconcile_pending_predictions(session, sport=sport)
        session.commit()
    log.info(
        "job reconcile_predictions: scanned=%d updated=%d match_not_finished=%d",
        report.scanned, report.updated, report.match_not_finished,
    )


register(
    JobSpec(
        name="sync_league",
        handler=sync_league_handler,
        description="Bir lig + sezon için adapter'dan veri çek, doğrula, DB'ye yaz, snapshot al.",
    )
)

register(
    JobSpec(
        name="reconcile_predictions",
        handler=reconcile_predictions_handler,
        description="Bitmiş maçların actual sonucunu predictions tablosuna yaz (kalibrasyon).",
    )
)


def run_pre_match_reports_handler(*, horizon_days: int = 7) -> None:
    """Önümüzdeki N gündeki NS maçlar için PreMatchReportAgent çalıştır.

    Idempotent: save_agent_output upsert — aynı maç için tekrar çalışırsa
    output_json refresh edilir (yeni veri / yeni form penceresi yansır).
    """
    agent = PreMatchReportAgent()
    processed = 0
    failed = 0
    upcoming_count = 0
    with SessionLocal() as session:
        # SQLite tz-strip; engine.schedule ile aynı pattern (PR #14)
        sample = session.execute(
            select(models.Match)
            .where(models.Match.sport == football.SPORT_NAME)
            .limit(1)
        ).scalar_one_or_none()
        ref_tz = sample.kickoff.tzinfo if sample is not None else None
        now_local = datetime.now(ref_tz)
        horizon_local = now_local + timedelta(days=horizon_days)

        upcoming = list(
            session.execute(
                select(models.Match)
                .where(
                    models.Match.sport == football.SPORT_NAME,
                    models.Match.kickoff > now_local,
                    models.Match.kickoff <= horizon_local,
                    ~models.Match.status.in_(football.FINISHED_STATUSES),
                )
                .order_by(models.Match.kickoff)
            ).scalars()
        )
        upcoming_count = len(upcoming)
        for match in upcoming:
            try:
                result = agent.run(session, context={"match_external_id": match.external_id})
                save_agent_output(
                    session, result=result,
                    agent_name=agent.name, agent_version=agent.version,
                )
                processed += 1
            except Exception as e:  # noqa: BLE001 — agent loop bir maçta düşmesin
                log.warning(
                    "pre_match_report match=%d başarısız: %s", match.external_id, e
                )
                failed += 1
        session.commit()
    log.info(
        "job run_pre_match_reports: upcoming=%d processed=%d failed=%d horizon_days=%d",
        upcoming_count, processed, failed, horizon_days,
    )


register(
    JobSpec(
        name="run_pre_match_reports",
        handler=run_pre_match_reports_handler,
        description="Önümüzdeki N gündeki NS maçlar için PreMatchReportAgent çalıştır.",
    )
)


def train_predict_ml_handler(*, min_samples: int = 20) -> None:
    """engine.predict_ml — predictions tablosundan best ρ öğren.

    Sonucu cache_entries(source='ml_predict_model', key='best_rho_v1')'e
    JSON olarak yazar. TTL 30 gün — yeniden train'e kadar geçerli.
    Yetersiz veri → NotEnoughTrainingData → log + skip (job fail değil).
    """
    from dataclasses import asdict as _asdict

    from app.data.cache.store import cache_set
    from app.engine.predict_ml import (
        CACHE_KEY,
        CACHE_SOURCE,
        NotEnoughTrainingData,
        train_best_rho,
    )

    with SessionLocal() as session:
        try:
            report = train_best_rho(session, min_samples=min_samples)
        except NotEnoughTrainingData as e:
            log.info("predict_ml train atlandı: %s", e)
            return
        cache_set(
            session,
            source=CACHE_SOURCE,
            key=CACHE_KEY,
            value=_asdict(report),
            ttl_seconds=30 * 86_400,
        )
        session.commit()
    log.info(
        "job train_predict_ml: samples=%d best_rho=%.2f best_log_loss=%.4f",
        report.sample_count, report.best_rho, report.best_log_loss,
    )


register(
    JobSpec(
        name="train_predict_ml",
        handler=train_predict_ml_handler,
        description="engine.predict_ml: predictions tablosundan best ρ öğren.",
    )
)


def ingest_tracking_match_handler(*, match_external_id: int, replace: bool = False) -> None:
    """Bir maç için tracking frame'lerini DB'ye yaz.

    Default `FixtureTrackingSource` — repo'daki tests/fixtures/tracking_<id>.json
    okur. Gerçek vendor adapter eklendiğinde bu handler'a `source_name` arg'ı
    eklenip dispatch edilir.
    """
    from app.data.ingest import (
        delete_match_frames as _delete,
    )
    from app.data.ingest import (
        ingest_tracking_match as _ingest,
    )
    from app.data.sources.fixture_tracking import FixtureTrackingSource

    source = FixtureTrackingSource()
    if not source.has_fixture(match_external_id):
        log.info("tracking ingest atlandı: match=%d fixture yok", match_external_id)
        return
    with SessionLocal() as session:
        if replace:
            removed = _delete(session, sport="football", match_external_id=match_external_id)
            log.info("tracking replace: match=%d silindi=%d", match_external_id, removed)
        report = _ingest(
            session, source, match_external_id=match_external_id,
        )
        session.commit()
    log.info(
        "job ingest_tracking_match: match=%d written=%d updated=%d",
        report.match_external_id, report.frames_written, report.frames_updated,
    )


register(
    JobSpec(
        name="ingest_tracking_match",
        handler=ingest_tracking_match_handler,
        description=(
            "Bir maçın tracking frame'lerini adapter'dan oku, DB'ye yaz. "
            "Varsayılan FixtureTrackingSource (tests/fixtures/tracking_<id>.json)."
        ),
    )
)


def run_post_match_reports_handler(*, lookback_days: int = 3) -> None:
    """Son N günde reconciled olan tahminler için PostMatchReport üret."""
    from datetime import datetime as _dt
    from datetime import timedelta as _td

    agent = PostMatchReportAgent()
    processed = failed = 0
    cutoff = _dt.now(tz=_dt.now().astimezone().tzinfo) - _td(days=lookback_days)
    with SessionLocal() as session:
        rows = list(
            session.execute(
                select(models.Prediction).where(
                    models.Prediction.engine == "engine.predict",
                    models.Prediction.reconciled_at.is_not(None),
                    models.Prediction.reconciled_at >= cutoff,
                )
            ).scalars()
        )
        match_ids = sorted({r.match_external_id for r in rows})
        for mid in match_ids:
            try:
                result = agent.run(session, context={"match_external_id": mid})
                save_agent_output(
                    session, result=result,
                    agent_name=agent.name, agent_version=agent.version,
                )
                processed += 1
            except Exception as e:  # noqa: BLE001
                log.warning("post_match match=%d başarısız: %s", mid, e)
                failed += 1
        session.commit()
    log.info(
        "job run_post_match_reports: candidates=%d processed=%d failed=%d",
        len(match_ids), processed, failed,
    )


register(JobSpec(
    name="run_post_match_reports",
    handler=run_post_match_reports_handler,
    description="Son N günde reconciled tahminler için PostMatchReportAgent.",
))


def run_weekly_digest_handler(*, league_external_id: int, lookback_days: int = 7) -> None:
    """Verilen lig için haftalık özet."""
    agent = WeeklyDigestAgent()
    with SessionLocal() as session:
        result = agent.run(session, context={
            "league_external_id": league_external_id,
            "lookback_days": lookback_days,
        })
        save_agent_output(
            session, result=result,
            agent_name=agent.name, agent_version=agent.version,
        )
        session.commit()
    log.info(
        "job run_weekly_digest: league=%d summary=%s",
        league_external_id, result.summary,
    )


register(JobSpec(
    name="run_weekly_digest",
    handler=run_weekly_digest_handler,
    description="Bir lig için haftalık özet (WeeklyDigestAgent).",
))


def run_opponent_scouts_handler() -> None:
    """Tüm takımlar için sıradaki rakip scout raporu."""
    agent = OpponentScoutAgent()
    processed = skipped = failed = 0
    with SessionLocal() as session:
        teams = list(
            session.execute(
                select(models.Team).where(models.Team.sport == football.SPORT_NAME)
            ).scalars()
        )
        for t in teams:
            try:
                result = agent.run(session, context={"team_external_id": t.external_id})
                save_agent_output(
                    session, result=result,
                    agent_name=agent.name, agent_version=agent.version,
                )
                processed += 1
            except NoUpcomingMatch:
                skipped += 1
            except Exception as e:  # noqa: BLE001
                log.warning("opponent_scout team=%d başarısız: %s", t.external_id, e)
                failed += 1
        session.commit()
    log.info(
        "job run_opponent_scouts: teams=%d processed=%d skipped=%d failed=%d",
        len(teams), processed, skipped, failed,
    )


register(JobSpec(
    name="run_opponent_scouts",
    handler=run_opponent_scouts_handler,
    description="Tüm takımlar için sıradaki rakip scout raporu.",
))


def run_injury_load_handler(*, player_external_ids: list[int], subject_id: int = 0,
                            window_days: int = 14) -> None:
    """Verilen oyuncu listesi için yük raporu."""
    agent = InjuryLoadAgent()
    with SessionLocal() as session:
        result = agent.run(session, context={
            "player_external_ids": player_external_ids,
            "subject_id": subject_id,
            "window_days": window_days,
        })
        save_agent_output(
            session, result=result,
            agent_name=agent.name, agent_version=agent.version,
        )
        session.commit()
    log.info("job run_injury_load: %s", result.summary)


register(JobSpec(
    name="run_injury_load",
    handler=run_injury_load_handler,
    description="Verilen oyuncu listesi için yük + rotasyon raporu.",
))


def run_mega_match_handler(*, match_external_id: int) -> None:
    """Bir maç için kapsamlı MegaMatch brief."""
    agent = MegaMatchAgent()
    with SessionLocal() as session:
        result = agent.run(session, context={"match_external_id": match_external_id})
        save_agent_output(
            session, result=result,
            agent_name=agent.name, agent_version=agent.version,
        )
        session.commit()
    log.info("job run_mega_match: %s", result.summary)


register(JobSpec(
    name="run_mega_match",
    handler=run_mega_match_handler,
    description="Bir maç için kapsamlı MegaMatchAgent brief'i.",
))


# --------------------------------------------------------------------------- #
# Karar agent'ları (lineup / sub / tactical) — manuel match+team başına job
# --------------------------------------------------------------------------- #


def run_lineup_recommendation_handler(*, match_external_id: int, team_external_id: int) -> None:
    """Bir maç+takım için lineup öneri üret + sakla."""
    from app.agents import LineupRecommendationAgent
    agent = LineupRecommendationAgent()
    with SessionLocal() as session:
        result = agent.run(session, context={
            "match_external_id": match_external_id,
            "team_external_id": team_external_id,
        })
        save_agent_output(
            session, result=result,
            agent_name=agent.name, agent_version=agent.version,
        )
        session.commit()
    log.info("job run_lineup_recommendation: %s", result.summary)


register(JobSpec(
    name="run_lineup_recommendation",
    handler=run_lineup_recommendation_handler,
    description="Bir maç+takım için LineupRecommendationAgent.",
))


def run_tactical_adjustment_handler(*, match_external_id: int, team_external_id: int,
                                    preferred_formation: str = "4-3-3") -> None:
    """Bir maç+takım için taktiksel ayarlama önerisi."""
    from app.agents import TacticalAdjustmentAgent
    agent = TacticalAdjustmentAgent()
    with SessionLocal() as session:
        result = agent.run(session, context={
            "match_external_id": match_external_id,
            "team_external_id": team_external_id,
            "preferred_formation": preferred_formation,
        })
        save_agent_output(
            session, result=result,
            agent_name=agent.name, agent_version=agent.version,
        )
        session.commit()
    log.info("job run_tactical_adjustment: %s", result.summary)


register(JobSpec(
    name="run_tactical_adjustment",
    handler=run_tactical_adjustment_handler,
    description="Bir maç+takım için TacticalAdjustmentAgent.",
))


def run_lineup_for_upcoming_handler(
    *, team_external_id: int, horizon_days: int = 7,
) -> None:
    """Bir takımın önümüzdeki N gündeki maçları için lineup önerileri.

    Maç günü asistanın hazır 11 önerisini push'lamasını sağlar.
    """
    from app.agents import LineupRecommendationAgent
    agent = LineupRecommendationAgent()
    processed = failed = 0
    with SessionLocal() as session:
        sample = session.execute(
            select(models.Match).where(
                models.Match.sport == football.SPORT_NAME,
            ).limit(1)
        ).scalar_one_or_none()
        ref_tz = sample.kickoff.tzinfo if sample is not None else None
        now_local = datetime.now(ref_tz)
        horizon_local = now_local + timedelta(days=horizon_days)
        upcoming = list(
            session.execute(
                select(models.Match).where(
                    models.Match.sport == football.SPORT_NAME,
                    models.Match.kickoff > now_local,
                    models.Match.kickoff <= horizon_local,
                    ~models.Match.status.in_(football.FINISHED_STATUSES),
                    (models.Match.home_team_external_id == team_external_id)
                    | (models.Match.away_team_external_id == team_external_id),
                ).order_by(models.Match.kickoff)
            ).scalars()
        )
        for match in upcoming:
            try:
                result = agent.run(session, context={
                    "match_external_id": match.external_id,
                    "team_external_id": team_external_id,
                })
                save_agent_output(
                    session, result=result,
                    agent_name=agent.name, agent_version=agent.version,
                )
                processed += 1
            except Exception as e:  # noqa: BLE001
                log.warning(
                    "lineup match=%d başarısız: %s", match.external_id, e,
                )
                failed += 1
        session.commit()
    log.info(
        "job run_lineup_for_upcoming: team=%d upcoming=%d processed=%d failed=%d",
        team_external_id, len(upcoming), processed, failed,
    )


register(JobSpec(
    name="run_lineup_for_upcoming",
    handler=run_lineup_for_upcoming_handler,
    description="Takımın önümüzdeki N gündeki maçları için lineup önerileri.",
))
