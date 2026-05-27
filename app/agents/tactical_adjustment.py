"""TacticalAdjustmentAgent — rakibe karşı formasyon/baskı önerisi.

Context: {
  "match_external_id": int,
  "team_external_id": int,    # benim takım
  "preferred_formation"?: str  # default "4-3-3"
}

Çıktı: rakibin profil özetine göre 2-3 taktiksel ayarlama önerisi.
- Rakip form + rating + h2h → "hangi formasyona meyilli, nereden zorlanıyor"
- AI sentez: somut baskı bölgesi + formasyon önerisi
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.agents.base import Agent, AgentResult
from app.ai import AnthropicClient, ClaudeCommentator
from app.db import models
from app.engine.form import compute_form
from app.engine.opponent import compute_head_to_head
from app.engine.rating import compute_team_rating
from app.sports import football

_PRESSING_ZONE_RULES = (
    # (condition_label, suggested_zone) — basit kural; AI gerekçe ile yumuşatır
    ("rakip yüksek skor → orta saha presi", "midfield"),
    ("rakip ev rating yüksek → erken pres", "high"),
    ("rakip dep rating düşük → orta-savunma çizgisi", "midfield"),
    ("rakip son 5'te az gol → düşük pres + counter", "low"),
)


class TacticalAdjustmentAgent(Agent):
    """Rakibe karşı taktiksel ayarlama önerisi."""

    name = "tactical_adjustment"
    version = "1"

    def __init__(self, *, commentator: ClaudeCommentator | None = None):
        self._commentator = commentator or ClaudeCommentator(AnthropicClient())

    def run(self, session: Session, *, context: dict[str, Any]) -> AgentResult:
        match_id = context.get("match_external_id")
        team_id = context.get("team_external_id")
        if match_id is None or team_id is None:
            raise ValueError("match_external_id + team_external_id zorunlu")
        match_id, team_id = int(match_id), int(team_id)
        preferred_formation = context.get("preferred_formation", "4-3-3")

        match = session.execute(
            select(models.Match).where(
                models.Match.sport == football.SPORT_NAME,
                models.Match.external_id == match_id,
            )
        ).scalar_one_or_none()
        if match is None:
            raise ValueError(f"match {match_id} yok")
        if team_id not in (match.home_team_external_id, match.away_team_external_id):
            raise ValueError(f"team {team_id} match {match_id} tarafı değil")

        is_home = team_id == match.home_team_external_id
        opp_id = match.away_team_external_id if is_home else match.home_team_external_id

        # Rakip profil — kickoff öncesi (leakage guard)
        opp_prior = list(
            session.execute(
                select(models.Match).where(
                    models.Match.sport == football.SPORT_NAME,
                    models.Match.kickoff < match.kickoff,
                    or_(
                        models.Match.home_team_external_id == opp_id,
                        models.Match.away_team_external_id == opp_id,
                    ),
                )
            ).scalars()
        )
        opp_form = compute_form(opp_id, opp_prior, last_n=5).value
        opp_rating = compute_team_rating(opp_id, opp_prior, last_n=10).value

        h2h_matches = [
            m for m in opp_prior
            if (m.home_team_external_id == team_id and m.away_team_external_id == opp_id)
            or (m.home_team_external_id == opp_id and m.away_team_external_id == team_id)
        ]
        h2h = compute_head_to_head(team_id, opp_id, h2h_matches).value

        # Basit kural-tabanlı taktiksel sinyaller
        signals: list[str] = []
        if opp_form.goals_for >= 8 and opp_form.matches_played >= 3:
            signals.append("rakip son maçlarda çok gol atıyor → orta sahada baskıyı sıkılaştır")
        if opp_form.goals_against >= 8 and opp_form.matches_played >= 3:
            signals.append("rakip son maçlarda çok gol yiyor → hücumda erken yayılma fırsat verir")
        if opp_rating.home_rating and opp_rating.home_rating > opp_rating.rating + 0.5:
            signals.append("rakip ev sahibi olduğunda güçlü → bu maç dep ise psikolojik avantaj")
        elif opp_rating.away_rating and opp_rating.away_rating < opp_rating.rating - 0.5:
            signals.append("rakip deplasmanda zayıf — ev sahibi isen direkt baskı")
        if h2h.matches_played >= 2 and h2h.team_a_wins > h2h.team_b_wins:
            signals.append(f"H2H'de bizim lehimize ({h2h.team_a_wins}-{h2h.draws}-{h2h.team_b_wins}) — psikolojik üstünlük")

        ai_brief = _build_tactical_brief(
            commentator=self._commentator,
            match_id=match_id, my_team_id=team_id, opp_id=opp_id, is_home=is_home,
            preferred_formation=preferred_formation, signals=signals,
            opp_form=opp_form, opp_rating=opp_rating, h2h=h2h,
        )

        output = {
            "match_external_id": match_id,
            "team_external_id": team_id,
            "opponent_id": opp_id,
            "is_home": is_home,
            "preferred_formation": preferred_formation,
            "signals": signals,
            "opponent_summary": {
                "form_wdl": [opp_form.wins, opp_form.draws, opp_form.losses],
                "ppg": opp_form.points_per_game,
                "rating": opp_rating.rating,
                "home_rating": opp_rating.home_rating,
                "away_rating": opp_rating.away_rating,
                "h2h_played": h2h.matches_played,
            },
            "ai_brief": ai_brief,
        }
        summary = (
            f"Taktiksel öneri match={match_id} team={team_id}: "
            f"{len(signals)} sinyal, formasyon={preferred_formation}"
        )
        return AgentResult(
            output_json=output, summary=summary,
            subject_type="match", subject_id=match_id,
        )


def _build_tactical_brief(
    *, commentator: ClaudeCommentator, match_id: int, my_team_id: int,
    opp_id: int, is_home: bool, preferred_formation: str, signals: list[str],
    opp_form, opp_rating, h2h,
) -> str:
    if commentator._client.is_stub():
        return (
            f"[stub:tactical] match={match_id} team={my_team_id} vs {opp_id} "
            f"({'ev' if is_home else 'dep'}) formasyon={preferred_formation}: "
            f"{len(signals)} sinyal. ANTHROPIC_API_KEY yok."
        )
    system = (
        "Sen futbol teknik direktörüne maç-bazlı taktiksel öneri sunan "
        "asistansın. 120-160 kelime. Yapı: (1) rakibin profili 1 cümle, "
        "(2) somut formasyon önerisi + alternatif, (3) baskı bölgesi (yüksek/orta/düşük), "
        "(4) sabit oyun (set piece) için 1 not."
    )
    user = (
        f"Maç {match_id}, ben={my_team_id} ({'ev' if is_home else 'dep'}) vs rakip {opp_id}\n"
        f"Tercih ettiğim formasyon: {preferred_formation}\n"
        f"Rakip form (W-D-L): {opp_form.wins}-{opp_form.draws}-{opp_form.losses}, "
        f"ppg {opp_form.points_per_game}, GF/GA {opp_form.goals_for}/{opp_form.goals_against}\n"
        f"Rakip rating: kompozit {opp_rating.rating}, "
        f"ev={opp_rating.home_rating}, dep={opp_rating.away_rating}\n"
        f"H2H: {h2h.matches_played} maç (ben={h2h.team_a_wins} X={h2h.draws} rakip={h2h.team_b_wins})\n"
        f"Sinyaller: {signals if signals else 'belirgin sinyal yok'}"
    )
    return commentator._call(system, user, max_tokens=400)
