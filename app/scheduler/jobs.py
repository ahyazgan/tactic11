"""Kayıtlı iş tanımları.

Yeni iş ekleme: handler yaz + dosya sonunda `register(JobSpec(...))` çağır.
Bu modül `app.scheduler.__init__` tarafından otomatik import edilir, böylece
kayıt side effect'i tetiklenir.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select

from app.agents import PreMatchReportAgent, save_agent_output
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
