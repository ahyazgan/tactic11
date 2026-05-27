"""OpponentScoutAgent — bir takımın sıradaki rakibi için scout raporu.

PreMatch'ten farklı: PreMatch iki takımı eşit ağırlıkta inceler;
Scout sadece RAKİP'i derinlemesine inceler (ev vs dep ayrımı, h2h trend,
güç/zayıflık çıkarımı).

Context: {"team_external_id": int}  # benim takımım
Output: {
  team_external_id, next_match: {match_id, opponent_id, kickoff, side},
  opponent_form: ..., opponent_rating: ..., h2h: ...,
  ai_brief: "Rakip son N maçta..., zayıf yönü..., maç planı önerisi..."
}
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.agents.base import Agent, AgentResult
from app.ai import AnthropicClient, ClaudeCommentator
from app.api.serialize import engine_result_to_dict
from app.db import models
from app.engine.form import compute_form
from app.engine.opponent import compute_head_to_head
from app.engine.rating import compute_team_rating
from app.sports import football


class NoUpcomingMatch(Exception):
    """Takımın önümüzdeki maçı yok — scout yapılamaz."""


class OpponentScoutAgent(Agent):
    """Sıradaki rakibe odaklı scout raporu."""

    name = "opponent_scout"
    version = "1"

    def __init__(self, *, commentator: ClaudeCommentator | None = None, last_n: int = 5):
        self._commentator = commentator or ClaudeCommentator(AnthropicClient())
        self._last_n = last_n

    def run(self, session: Session, *, context: dict[str, Any]) -> AgentResult:
        team_id = context.get("team_external_id")
        if team_id is None:
            raise ValueError("context.team_external_id zorunlu")
        team_id = int(team_id)

        # Bir maç bul → ref_tz al, sonra "future + NS" filtreyle sıradaki rakip
        sample = session.execute(
            select(models.Match).where(
                models.Match.sport == football.SPORT_NAME,
                or_(
                    models.Match.home_team_external_id == team_id,
                    models.Match.away_team_external_id == team_id,
                ),
            ).limit(1)
        ).scalar_one_or_none()
        if sample is None:
            raise NoUpcomingMatch(f"team {team_id} için hiç maç yok")
        ref_tz = sample.kickoff.tzinfo
        now = datetime.now(ref_tz)

        next_match = session.execute(
            select(models.Match).where(
                models.Match.sport == football.SPORT_NAME,
                or_(
                    models.Match.home_team_external_id == team_id,
                    models.Match.away_team_external_id == team_id,
                ),
                models.Match.kickoff > now,
                ~models.Match.status.in_(football.FINISHED_STATUSES),
            ).order_by(models.Match.kickoff)
        ).scalars().first()
        if next_match is None:
            raise NoUpcomingMatch(f"team {team_id} için yaklaşan maç yok")

        is_home = next_match.home_team_external_id == team_id
        opponent_id = (
            next_match.away_team_external_id if is_home
            else next_match.home_team_external_id
        )

        # Rakibin geçmişi (kickoff'tan ÖNCE — leakage guard)
        opp_prior = list(
            session.execute(
                select(models.Match).where(
                    models.Match.sport == football.SPORT_NAME,
                    models.Match.kickoff < next_match.kickoff,
                    or_(
                        models.Match.home_team_external_id == opponent_id,
                        models.Match.away_team_external_id == opponent_id,
                    ),
                )
            ).scalars()
        )
        opp_form = compute_form(opponent_id, opp_prior, last_n=self._last_n)
        opp_rating = compute_team_rating(opponent_id, opp_prior, last_n=10)

        # H2H
        h2h_prior = [
            m for m in opp_prior
            if (m.home_team_external_id == team_id and m.away_team_external_id == opponent_id)
            or (m.home_team_external_id == opponent_id and m.away_team_external_id == team_id)
        ]
        h2h = compute_head_to_head(team_id, opponent_id, h2h_prior)

        ai_brief = _build_scout_brief(
            commentator=self._commentator,
            my_team_id=team_id, opponent_id=opponent_id,
            is_home_for_me=is_home,
            opp_form=opp_form, opp_rating=opp_rating, h2h=h2h,
            kickoff_iso=next_match.kickoff.isoformat(),
        )

        output = {
            "team_external_id": team_id,
            "next_match": {
                "match_id": next_match.external_id,
                "opponent_id": opponent_id,
                "kickoff": next_match.kickoff.isoformat(),
                "my_side": "home" if is_home else "away",
            },
            "opponent_form": engine_result_to_dict(opp_form),
            "opponent_rating": engine_result_to_dict(opp_rating),
            "h2h": engine_result_to_dict(h2h),
            "ai_brief": ai_brief,
        }
        of = opp_form.value
        summary = (
            f"Team {team_id} sıradaki: opp {opponent_id} "
            f"({'ev' if is_home else 'dep'}) — opp form "
            f"{of.wins}-{of.draws}-{of.losses}, "
            f"rating {opp_rating.value.rating}"
        )
        return AgentResult(
            output_json=output, summary=summary,
            subject_type="team", subject_id=team_id,
        )


def _build_scout_brief(
    *, commentator: ClaudeCommentator,
    my_team_id: int, opponent_id: int, is_home_for_me: bool,
    opp_form, opp_rating, h2h, kickoff_iso: str,
) -> str:
    of = opp_form.value
    or_ = opp_rating.value
    hv = h2h.value
    if commentator._client.is_stub():
        return (
            f"[stub:opponent_scout] benim takım {my_team_id} vs rakip {opponent_id} "
            f"({'ev' if is_home_for_me else 'dep'}): rakip form "
            f"{of.wins}-{of.draws}-{of.losses}, rating {or_.rating}, "
            f"H2H {hv.team_a_wins}-{hv.draws}-{hv.team_b_wins}. ANTHROPIC_API_KEY yok."
        )
    system = (
        "Sen futbol teknik direktörüne rakip scout raporu sunan analiz asistanısın. "
        "150-200 kelime. Yapı: (1) rakibin son form trendi + en güçlü yön, "
        "(2) hangi durumda zorlandığı (ev/dep/gol yedi/gol attı), "
        "(3) bizimle önceki maç paterni, (4) somut maç planı önerisi (1-2 madde)."
    )
    user = (
        f"Benim takım: {my_team_id} ({'ev' if is_home_for_me else 'dep'} oynayacağız)\n"
        f"Rakip: {opponent_id}\n"
        f"Kickoff: {kickoff_iso}\n\n"
        f"Rakip son form (W-D-L): {of.wins}-{of.draws}-{of.losses}, "
        f"ppg {of.points_per_game}, gd/maç {of.goal_diff_per_match}\n"
        f"Rakip rating: kompozit {or_.rating}; "
        f"ev_rating={or_.home_rating}, dep_rating={or_.away_rating}\n"
        f"H2H (geçmiş): {hv.matches_played} maç, "
        f"benim={hv.team_a_wins} beraberlik={hv.draws} rakip={hv.team_b_wins}, "
        f"goller benim={hv.team_a_goals} rakip={hv.team_b_goals}\n"
    )
    return commentator._call(system, user, max_tokens=500)
