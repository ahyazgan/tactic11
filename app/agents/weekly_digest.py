"""WeeklyDigestAgent — bir lig için haftalık özet.

5 bölümlü tek sayfa: form liderleri, fixture difficulty zirvedeki takımlar,
ML kalibrasyon güncellemesi, dikkat çeken yaklaşan maçlar, accuracy snapshot.

Context: {"league_external_id": int, "lookback_days": int (default 7)}
Output: {
  league_external_id, generated_at,
  form_leaders: [{team_id, ppg, gd_per_match}, ...],
  difficulty_leaders: [{team_id, weighted_difficulty}, ...],
  ml_status: {status, best_rho|null, sample_count|null},
  accuracy: {brier_score|null, log_loss|null, sample_count|null},
  upcoming_matches: [{match_id, home, away, kickoff}, ...],
  ai_brief: str
}
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.agents.base import Agent, AgentResult
from app.ai import AnthropicClient, ClaudeCommentator
from app.data.cache.store import cache_get
from app.db import models
from app.engine.fixture_difficulty import OpponentRating, compute_fixture_difficulty
from app.engine.form import compute_form
from app.engine.predict_ml import CACHE_KEY as ML_CACHE_KEY
from app.engine.predict_ml import CACHE_SOURCE as ML_CACHE_SOURCE
from app.engine.rating import compute_team_rating
from app.sports import football


def _team_matches(session: Session, team_id: int) -> list[models.Match]:
    return list(
        session.execute(
            select(models.Match).where(
                models.Match.sport == football.SPORT_NAME,
                or_(
                    models.Match.home_team_external_id == team_id,
                    models.Match.away_team_external_id == team_id,
                ),
            ).order_by(models.Match.kickoff.desc())
        ).scalars()
    )


class WeeklyDigestAgent(Agent):
    """Haftalık lig özeti — birden çok engine'in sentezi."""

    name = "weekly_digest"
    version = "1"

    def __init__(self, *, commentator: ClaudeCommentator | None = None, top_n: int = 5):
        self._commentator = commentator or ClaudeCommentator(AnthropicClient())
        self._top_n = top_n

    def run(self, session: Session, *, context: dict[str, Any]) -> AgentResult:
        league_id = context.get("league_external_id")
        if league_id is None:
            raise ValueError("context.league_external_id zorunlu")
        lookback_days = int(context.get("lookback_days", 7))

        teams = list(
            session.execute(
                select(models.Team).where(models.Team.sport == football.SPORT_NAME)
            ).scalars()
        )

        # form leaders: tüm takımlar için form hesapla, ppg'ye göre sırala
        form_rows: list[tuple[int, float, float]] = []
        for t in teams:
            ms = _team_matches(session, t.external_id)
            if not ms:
                continue
            f = compute_form(t.external_id, ms, last_n=5).value
            if f.matches_played == 0:
                continue
            gdpm = f.goals_for_per_match - f.goals_against_per_match
            form_rows.append((t.external_id, f.points_per_game, gdpm))
        form_rows.sort(key=lambda x: (x[1], x[2]), reverse=True)
        form_leaders = [
            {"team_id": tid, "ppg": round(ppg, 3), "gd_per_match": round(gdpm, 3)}
            for tid, ppg, gdpm in form_rows[: self._top_n]
        ]

        # difficulty leaders: önümüzdeki 30 günde en zor rakipleri olan
        difficulty_rows: list[tuple[int, float]] = []
        ratings: dict[int, OpponentRating] = {}
        for t in teams:
            ms = _team_matches(session, t.external_id)
            if not ms:
                continue
            rr = compute_team_rating(t.external_id, ms, last_n=10).value
            if rr.matches_considered:
                ratings[t.external_id] = OpponentRating(
                    home_rating=rr.home_rating if rr.home_matches else None,
                    away_rating=rr.away_rating if rr.away_matches else None,
                    overall_rating=rr.rating,
                )
        # ratings dict hazır; tek-pas geç ve zorluk hesapla
        for t in teams:
            ms = _team_matches(session, t.external_id)
            if not ms:
                continue
            ref_tz = ms[0].kickoff.tzinfo
            now = datetime.now(ref_tz)
            horizon = now + timedelta(days=30)
            scoped = [m for m in ms if m.kickoff <= horizon]
            fd = compute_fixture_difficulty(t.external_id, scoped, ratings, now=now).value
            if fd.matches_considered > 0:
                difficulty_rows.append((t.external_id, fd.weighted_difficulty))
        difficulty_rows.sort(key=lambda x: x[1], reverse=True)
        difficulty_leaders = [
            {"team_id": tid, "weighted_difficulty": round(d, 3)}
            for tid, d in difficulty_rows[: self._top_n]
        ]

        # ML model durumu
        ml_cache = cache_get(session, source=ML_CACHE_SOURCE, key=ML_CACHE_KEY)
        if ml_cache and ml_cache.get("best_rho") is not None:
            ml_status = {
                "status": "fresh",
                "best_rho": ml_cache.get("best_rho"),
                "sample_count": ml_cache.get("sample_count"),
            }
        else:
            ml_status = {"status": "untrained", "best_rho": None, "sample_count": None}

        # Accuracy snapshot — reconciled predictions üstünden hızlı Brier
        accuracy = _quick_accuracy(session, days=lookback_days * 4)  # ~ son ay

        # Upcoming matches — bu lig, ilk lookback_days
        upcoming = list(
            session.execute(
                select(models.Match).where(
                    models.Match.sport == football.SPORT_NAME,
                    models.Match.league_external_id == int(league_id),
                    ~models.Match.status.in_(football.FINISHED_STATUSES),
                ).order_by(models.Match.kickoff)
            ).scalars()
        )
        if upcoming:
            ref_tz = upcoming[0].kickoff.tzinfo
            now = datetime.now(ref_tz)
            horizon = now + timedelta(days=lookback_days)
            upcoming = [m for m in upcoming if now < m.kickoff <= horizon]
        upcoming_matches = [
            {
                "match_id": m.external_id,
                "home": m.home_team_external_id,
                "away": m.away_team_external_id,
                "kickoff": m.kickoff.isoformat(),
            }
            for m in upcoming[: self._top_n * 2]
        ]

        ai_brief = _build_digest_brief(
            commentator=self._commentator,
            league_id=int(league_id),
            form_leaders=form_leaders, difficulty_leaders=difficulty_leaders,
            ml_status=ml_status, accuracy=accuracy,
            upcoming_count=len(upcoming_matches),
        )

        output = {
            "league_external_id": int(league_id),
            "generated_at": datetime.now(UTC).isoformat(),
            "lookback_days": lookback_days,
            "form_leaders": form_leaders,
            "difficulty_leaders": difficulty_leaders,
            "ml_status": ml_status,
            "accuracy": accuracy,
            "upcoming_matches": upcoming_matches,
            "ai_brief": ai_brief,
        }
        summary = (
            f"League {league_id} haftalık: "
            f"form lider {form_leaders[0]['team_id'] if form_leaders else '—'}, "
            f"en zor fikstür {difficulty_leaders[0]['team_id'] if difficulty_leaders else '—'}, "
            f"ML {ml_status['status']}, yaklaşan maç={len(upcoming_matches)}"
        )
        return AgentResult(
            output_json=output, summary=summary,
            subject_type="league", subject_id=int(league_id),
        )


def _quick_accuracy(session: Session, *, days: int) -> dict[str, Any]:
    cutoff = datetime.now(UTC) - timedelta(days=days)
    rows = list(
        session.execute(
            select(models.Prediction).where(
                models.Prediction.engine == "engine.predict",
                models.Prediction.actual_outcome.is_not(None),
                models.Prediction.reconciled_at.is_not(None),
                models.Prediction.reconciled_at >= cutoff,
            )
        ).scalars()
    )
    if not rows:
        return {"brier_score": None, "log_loss": None, "sample_count": 0}

    import json as _json
    from math import log as _log
    brier_sum = 0.0
    ll_sum = 0.0
    n = 0
    for r in rows:
        try:
            p = _json.loads(r.predicted_value_json)
        except _json.JSONDecodeError:
            continue
        if r.actual_outcome is None:
            continue  # gerçek sonuç yoksa Brier hesaplanamaz
        prob_actual = {
            "home": float(p.get("prob_home_win", 0.0)),
            "draw": float(p.get("prob_draw", 0.0)),
            "away": float(p.get("prob_away_win", 0.0)),
        }.get(r.actual_outcome, 0.0)
        # 3-class Brier: sum_i (p_i - y_i)^2
        y = {"home": 0.0, "draw": 0.0, "away": 0.0}
        y[r.actual_outcome] = 1.0
        brier_sum += (
            (float(p.get("prob_home_win", 0.0)) - y["home"]) ** 2
            + (float(p.get("prob_draw", 0.0)) - y["draw"]) ** 2
            + (float(p.get("prob_away_win", 0.0)) - y["away"]) ** 2
        )
        ll_sum += -_log(max(prob_actual, 1e-9))
        n += 1
    if n == 0:
        return {"brier_score": None, "log_loss": None, "sample_count": 0}
    return {
        "brier_score": round(brier_sum / n, 4),
        "log_loss": round(ll_sum / n, 4),
        "sample_count": n,
    }


def _build_digest_brief(
    *, commentator: ClaudeCommentator, league_id: int,
    form_leaders: list[dict], difficulty_leaders: list[dict],
    ml_status: dict, accuracy: dict, upcoming_count: int,
) -> str:
    if commentator._client.is_stub():
        return (
            f"[stub:weekly_digest] league={league_id}: "
            f"{len(form_leaders)} form lideri, {len(difficulty_leaders)} zorlu fikstür, "
            f"ML {ml_status['status']}, {upcoming_count} yaklaşan maç. "
            "ANTHROPIC_API_KEY yok."
        )
    system = (
        "Sen futbol teknik ekibine haftalık özet yazan analiz asistanısın. "
        "Tek paragraf, 120-160 kelime. Sayıyı tekrar etme; çıkarımı yaz: "
        "form trendi, fikstür darboğazı, model güveni, dikkat edilmesi gereken maç."
    )
    user = (
        f"Lig {league_id} haftalık veri:\n"
        f"Form liderleri: {form_leaders[:3]}\n"
        f"En zor fikstür: {difficulty_leaders[:3]}\n"
        f"ML durumu: {ml_status}\n"
        f"Doğruluk (son 30 gün): {accuracy}\n"
        f"Yaklaşan maç sayısı: {upcoming_count}\n\n"
        "Brief'te 4 cümle: (1) form trendi, (2) fikstür darboğazı, "
        "(3) model güveni, (4) kritik yaklaşan maç vurgusu."
    )
    return commentator._call(system, user, max_tokens=350)
