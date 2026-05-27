"""PreMatchReportAgent — bir maç için ön bakış brief'i.

Engine'leri (form, opponent) tüketir + AI commentator'ı match preview için
çağırır. Çıktı dashboard'da gösterilebilir tek bir AgentResult.

Context: {"match_external_id": int}
Output: {
  "match_external_id": int,
  "home_team_external_id": int,
  "away_team_external_id": int,
  "kickoff": ISO datetime,
  "home_form": {value, audit},
  "away_form": {value, audit},
  "head_to_head": {value, audit},
  "ai_brief": str  (AI yorumu; ANTHROPIC_API_KEY yoksa stub)
}
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.agents.base import Agent, AgentResult
from app.ai import AnthropicClient, ClaudeCommentator
from app.api.serialize import engine_result_to_dict
from app.db import models
from app.engine.form import compute_form
from app.engine.opponent import compute_head_to_head
from app.sports import football


class PreMatchReportAgent(Agent):
    """Maç öncesi brief üretir: form (her iki takım) + h2h + AI sentezi."""

    name = "pre_match_report"
    version = "1"

    def __init__(self, *, commentator: ClaudeCommentator | None = None, last_n: int = 5):
        # commentator opsiyonel — testte stub injekte edilebilir
        self._commentator = commentator or ClaudeCommentator(AnthropicClient())
        self._last_n = last_n

    def run(self, session: Session, *, context: dict[str, Any]) -> AgentResult:
        match_id = context.get("match_external_id")
        if match_id is None:
            raise ValueError("context.match_external_id zorunlu")

        match = session.execute(
            select(models.Match).where(
                models.Match.sport == football.SPORT_NAME,
                models.Match.external_id == int(match_id),
            )
        ).scalar_one_or_none()
        if match is None:
            raise ValueError(f"match {match_id} bulunamadı")

        home_id = match.home_team_external_id
        away_id = match.away_team_external_id

        # Leakage guard: form/h2h kickoff'tan ÖNCE
        def _prior_for_team(tid: int):
            return list(
                session.execute(
                    select(models.Match).where(
                        models.Match.sport == football.SPORT_NAME,
                        models.Match.kickoff < match.kickoff,
                        or_(
                            models.Match.home_team_external_id == tid,
                            models.Match.away_team_external_id == tid,
                        ),
                    )
                ).scalars()
            )

        home_form = compute_form(home_id, _prior_for_team(home_id), last_n=self._last_n)
        away_form = compute_form(away_id, _prior_for_team(away_id), last_n=self._last_n)

        # H2H — kickoff öncesi karşılaşmalar
        h2h_matches = list(
            session.execute(
                select(models.Match).where(
                    models.Match.sport == football.SPORT_NAME,
                    models.Match.kickoff < match.kickoff,
                    or_(
                        (models.Match.home_team_external_id == home_id)
                        & (models.Match.away_team_external_id == away_id),
                        (models.Match.home_team_external_id == away_id)
                        & (models.Match.away_team_external_id == home_id),
                    ),
                )
            ).scalars()
        )
        h2h = compute_head_to_head(home_id, away_id, h2h_matches)

        # AI brief — ANTHROPIC_API_KEY yoksa stub döner (commentator.explain_match_preview)
        ai_brief = self._commentator.explain_match_preview(
            home_form=home_form,
            away_form=away_form,
            h2h=h2h,
            home_team_id=home_id,
            away_team_id=away_id,
            kickoff_iso=match.kickoff.isoformat(),
        )

        output = {
            "match_external_id": int(match_id),
            "home_team_external_id": home_id,
            "away_team_external_id": away_id,
            "kickoff": match.kickoff.isoformat(),
            "home_form": engine_result_to_dict(home_form),
            "away_form": engine_result_to_dict(away_form),
            "head_to_head": engine_result_to_dict(h2h),
            "ai_brief": ai_brief,
        }
        # Summary — kısa metin (dashboard/Slack için)
        h2h_v = h2h.value
        summary = (
            f"{home_id} vs {away_id} @ {match.kickoff.date()}: "
            f"ev form {home_form.value.wins}-{home_form.value.draws}-{home_form.value.losses}, "
            f"dep form {away_form.value.wins}-{away_form.value.draws}-{away_form.value.losses}, "
            f"H2H {h2h_v.team_a_wins}-{h2h_v.draws}-{h2h_v.team_b_wins}"
        )

        return AgentResult(
            output_json=output,
            summary=summary,
            subject_type="match",
            subject_id=int(match_id),
        )
