"""LiveDecisionDigestAgent — maç-içi snapshot → 2-3 cümlelik TR brief.

Live-decision panel çıktısını (10+ engine + context_engine primary) tüketir;
ANTHROPIC_API_KEY varsa Claude'a yollar, yoksa stub döner. TD `/decisions/live`
sayfasında veya WebSocket push'unda bu paragrafı tek bakışta okur.

Context: {"match_external_id": int, "my_team_id": int,
          "current_minute": float, "star_player_id"?: int}

Output: {
  match_external_id, my_team_id, current_minute, score,
  primary_headline, ai_brief
}
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.base import Agent, AgentResult
from app.ai import AnthropicClient, ClaudeCommentator
from app.db import models
from app.sports import football


class LiveDecisionDigestAgent(Agent):
    """Live snapshot → 1 paragraf TR AI brief."""

    name = "live_decision_digest"
    version = "1"

    def __init__(self, *, commentator: ClaudeCommentator | None = None) -> None:
        self._commentator = commentator or ClaudeCommentator(AnthropicClient())

    def run(self, session: Session, *, context: dict[str, Any]) -> AgentResult:
        match_id = int(context["match_external_id"])
        my_team_id = int(context["my_team_id"])
        current_minute = float(context["current_minute"])
        star_player_id = context.get("star_player_id")

        match = session.execute(
            select(models.Match).where(
                models.Match.sport == football.SPORT_NAME,
                models.Match.external_id == match_id,
            )
        ).scalar_one_or_none()
        if match is None:
            raise ValueError(f"match {match_id} bulunamadı")

        score = f"{match.home_score or 0}-{match.away_score or 0}"

        # Live-decision endpoint mantığını içeride çalıştır (DB session direct)
        # — gereksiz HTTP roundtrip yok. context_pipeline modülü API katmanına
        # bağlı ama session.info["tenant_id"] caller'da set olduğu için doğrudan
        # çalışır.
        from app.api.admin import live_decision_endpoint
        snapshot = live_decision_endpoint(
            match_id=match_id, my_team_id=my_team_id,
            current_minute=current_minute,
            star_player_id=star_player_id,
            draw_is_enough=False, must_win=False,
            session=session,
        )

        ai_brief = self._commentator.explain_live_digest(
            snapshot, match_id=match_id,
            current_minute=current_minute, score=score,
        )

        primary = (snapshot.get("context") or {}).get("primary") or {}
        primary_headline = primary.get("headline") if isinstance(primary, dict) else None

        output = {
            "match_external_id": match_id,
            "my_team_id": my_team_id,
            "current_minute": current_minute,
            "score": score,
            "primary_headline": primary_headline,
            "ai_brief": ai_brief,
            # Karar takip / debug için snapshot ham özet (engine'ler kısa)
            "snapshot_keys": sorted(snapshot.keys()),
        }
        summary = (
            f"{match_id} · {current_minute:.0f}' · {score} → "
            f"{(primary_headline or 'izleme')[:80]}"
        )
        return AgentResult(
            output_json=output,
            summary=summary,
            subject_type="match",
            subject_id=match_id,
        )
