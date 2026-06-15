"""TacticalAdjustmentAgent — rakibe karşı formasyon/baskı önerisi.

Context: {
  "match_external_id": int,
  "team_external_id": int,    # benim takım
  "preferred_formation"?: str  # default "4-3-3"
}

Çıktı: rakibin profil özetine göre 2-3 taktiksel ayarlama önerisi.
- Rakip form + rating + h2h → "hangi formasyona meyilli, nereden zorlanıyor"
- engine.formation_matcher: bizim/rakip historical formasyon × formasyon agregat
- AI sentez: somut baskı bölgesi + formasyon önerisi

v2: engine.formation_matcher entegre. player_appearances'tan formation_played
çekilir → her geçmiş maç için (my_formation, opp_formation) çıkar → tarihsel
agregat. "Rakip 4-2-3-1 karşısında 3-5-2 son N maçta %58 win" tarzı çıkarım.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.agents.base import Agent, AgentResult
from app.ai import AnthropicClient, ClaudeCommentator
from app.db import models
from app.engine.form import compute_form
from app.engine.formation_matcher import (
    FormationMatchupRecord,
    best_formations_against,
    compute_formation_matchup,
)
from app.engine.match_plan_builder import MatchPlanContext, compute_match_plan
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
    version = "3"  # v2 → v3: engine.match_plan_builder (H+I+K kompozit) entegre

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

        # v2: formation_matcher — tarihsel formasyon × formasyon agregat
        formation_records = _extract_formation_records(
            session, team_external_id=team_id, opp_external_id=opp_id,
        )
        formation_insight: dict[str, Any] = {"records_total": len(formation_records)}
        if formation_records:
            # Rakibin son maçtaki formasyonu (varsa) — taktiksel agent için ipucu
            opp_recent_formation = _last_formation_for_team(
                session, opp_id, before=match.kickoff,
            )
            if opp_recent_formation:
                formation_insight["opp_recent_formation"] = opp_recent_formation
                # Bu formasyon karşısında bizim için en iyi formasyon
                best = best_formations_against(
                    opp_recent_formation, formation_records,
                    min_matches=2, top_n=3,
                )
                formation_insight["best_against_opp"] = [
                    {
                        "my_formation": r.my_formation,
                        "matches": r.matches_played,
                        "win_rate": r.win_rate,
                        "avg_goal_diff": r.avg_goal_diff,
                    }
                    for r in best
                ]
                if best:
                    top = best[0]
                    signals.append(
                        f"Tarihsel: '{top.my_formation}' formasyonu "
                        f"'{opp_recent_formation}' karşısında "
                        f"%{int(top.win_rate * 100)} win "
                        f"({top.matches_played} maç, +{top.avg_goal_diff:.1f} gd)"
                    )
            # Tercih edilen formasyon ile rakip son formasyonu kıyas
            if opp_recent_formation and preferred_formation:
                pref_vs_opp = compute_formation_matchup(
                    preferred_formation, opp_recent_formation, formation_records,
                ).value
                formation_insight["preferred_vs_opp"] = {
                    "matches": pref_vs_opp.matches_played,
                    "win_rate": pref_vs_opp.win_rate,
                    "avg_goal_diff": pref_vs_opp.avg_goal_diff,
                }

        # v3: Match Plan kompoziti (H formation_matchup + I set_piece + K threat)
        opp_recent_formation = formation_insight.get("opp_recent_formation")
        opponent_style = _infer_opponent_style(opp_form, opp_rating)
        plan_ctx = MatchPlanContext(
            our_formation=preferred_formation,
            opp_formation=opp_recent_formation or "4-3-3",
            opponent_style=opponent_style,
            set_piece_type="corner",
            set_piece_side="long",
            our_attributes={"aerial": 0.7, "set_piece": 0.65, "technique": 0.7},
        )
        match_plan_result = compute_match_plan(plan_ctx)
        match_plan = match_plan_result.value
        # Plan'dan en kritik advice'i signals'a ekle
        if match_plan.matchup_advice:
            signals.append(
                f"Plan: {match_plan.matchup_advice[0]}",
            )
        if match_plan.set_piece_top:
            top_sp = match_plan.set_piece_top[0]
            signals.append(
                f"Set-piece önerisi: {top_sp['label']} (score {top_sp['score']})",
            )

        ai_brief = _build_tactical_brief(
            commentator=self._commentator,
            match_id=match_id, my_team_id=team_id, opp_id=opp_id, is_home=is_home,
            preferred_formation=preferred_formation, signals=signals,
            opp_form=opp_form, opp_rating=opp_rating, h2h=h2h,
            formation_insight=formation_insight,
            match_plan=match_plan,
        )

        output = {
            "match_external_id": match_id,
            "team_external_id": team_id,
            "formation_insight": formation_insight,
            "match_plan": {
                "headline": match_plan.headline,
                "matchup_vector": match_plan.matchup_vector,
                "matchup_advice": list(match_plan.matchup_advice),
                "set_piece_top": list(match_plan.set_piece_top),
                "plan_lines": list(match_plan.plan_lines),
                "opponent_style_inferred": opponent_style,
            },
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


def _extract_formation_records(
    session: Session, *, team_external_id: int, opp_external_id: int,
) -> list[FormationMatchupRecord]:
    """player_appearances.formation_played'den FormationMatchupRecord listesi üret.

    Akış:
    1. team_external_id'nin oynadığı tüm maçları al (FT, skor dolu)
    2. Her maç için: bu takımın formation_played'i + rakibin formation_played'i çek
       (player_appearances'tan herhangi bir oyuncunun kaydı yeter — formation maç+takım için tek)
    3. (my_formation, opp_formation, my_goals, opp_goals) tuple → FormationMatchupRecord

    Rakip belirtilmemiş olsa bile tarihsel agregat için tüm rakipleri sayar.
    Sadece "team_external_id'nin formation × her rakip formation".
    """
    # FT maçlar — team_external_id'nin oynadıkları
    matches = list(
        session.execute(
            select(models.Match).where(
                models.Match.sport == football.SPORT_NAME,
                or_(
                    models.Match.home_team_external_id == team_external_id,
                    models.Match.away_team_external_id == team_external_id,
                ),
                models.Match.status.in_(football.FINISHED_STATUSES),
                models.Match.home_score.is_not(None),
                models.Match.away_score.is_not(None),
            )
        ).scalars()
    )
    records: list[FormationMatchupRecord] = []
    for m in matches:
        my_form = _formation_for_team_in_match(
            session, m.external_id, team_external_id,
        )
        if my_form is None:
            continue
        # Rakip ID'sini bul
        if m.home_team_external_id == team_external_id:
            opp_in_match = m.away_team_external_id
            my_goals = m.home_score or 0
            opp_goals = m.away_score or 0
        else:
            opp_in_match = m.home_team_external_id
            my_goals = m.away_score or 0
            opp_goals = m.home_score or 0
        opp_form = _formation_for_team_in_match(
            session, m.external_id, opp_in_match,
        )
        if opp_form is None:
            continue
        records.append(FormationMatchupRecord(
            match_external_id=m.external_id,
            my_formation=my_form,
            opp_formation=opp_form,
            my_goals=my_goals,
            opp_goals=opp_goals,
        ))
    return records


def _formation_for_team_in_match(
    session: Session, match_id: int, team_id: int,
) -> str | None:
    """Bir maçta bir takımın formasyonunu player_appearances'tan çek.

    Formation aynı maç+takım için sabit — ilk eşleşeni döner.
    """
    row = session.execute(
        select(models.PlayerAppearance.formation_played).where(
            models.PlayerAppearance.match_external_id == match_id,
            models.PlayerAppearance.team_external_id == team_id,
            models.PlayerAppearance.formation_played.is_not(None),
        ).limit(1)
    ).scalar_one_or_none()
    return row


def _last_formation_for_team(
    session: Session, team_id: int, *, before,
) -> str | None:
    """Bir takımın son maçta oynadığı formasyon (FT + before kickoff)."""
    row = session.execute(
        select(models.PlayerAppearance.formation_played)
        .join(
            models.Match,
            models.Match.external_id == models.PlayerAppearance.match_external_id,
        )
        .where(
            models.PlayerAppearance.team_external_id == team_id,
            models.PlayerAppearance.formation_played.is_not(None),
            models.Match.kickoff < before,
            models.Match.sport == football.SPORT_NAME,
        )
        .order_by(models.Match.kickoff.desc())
        .limit(1)
    ).scalar_one_or_none()
    return row


def _infer_opponent_style(opp_form, opp_rating) -> str | None:
    """opp_form + opp_rating'den basit kural-tabanlı stil etiketi."""
    ga = opp_form.goals_against
    gf = opp_form.goals_for
    mp = opp_form.matches_played
    if mp < 3:
        return None
    if ga <= 3 and mp >= 3:
        return "italian_catenaccio"
    if gf >= 10 and mp >= 5:
        return "gegenpress"
    if opp_form.draws >= mp // 2 and mp >= 4:
        return "atletico_compact"
    return None


def _build_tactical_brief(
    *, commentator: ClaudeCommentator, match_id: int, my_team_id: int,
    opp_id: int, is_home: bool, preferred_formation: str, signals: list[str],
    opp_form, opp_rating, h2h,
    formation_insight: dict | None = None,
    match_plan=None,
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
    formation_block = ""
    if formation_insight and formation_insight.get("records_total", 0) > 0:
        opp_recent = formation_insight.get("opp_recent_formation", "?")
        best = formation_insight.get("best_against_opp", [])
        formation_block = (
            f"\nTarihsel formasyon (toplam {formation_insight['records_total']} maç):\n"
            f"  Rakibin son formasyonu: {opp_recent}\n"
        )
        if best:
            for r in best[:2]:
                formation_block += (
                    f"  - {r['my_formation']}: %{int(r['win_rate']*100)} win "
                    f"({r['matches']} maç, gd {r['avg_goal_diff']:+.1f})\n"
                )

    plan_block = ""
    if match_plan is not None:
        plan_block = f"\nMatch Plan (kompozit): {match_plan.headline}\n"
        for line in match_plan.plan_lines[:4]:
            plan_block += f"  • {line}\n"

    user = (
        f"Maç {match_id}, ben={my_team_id} ({'ev' if is_home else 'dep'}) vs rakip {opp_id}\n"
        f"Tercih ettiğim formasyon: {preferred_formation}\n"
        f"Rakip form (W-D-L): {opp_form.wins}-{opp_form.draws}-{opp_form.losses}, "
        f"ppg {opp_form.points_per_game}, GF/GA {opp_form.goals_for}/{opp_form.goals_against}\n"
        f"Rakip rating: kompozit {opp_rating.rating}, "
        f"ev={opp_rating.home_rating}, dep={opp_rating.away_rating}\n"
        f"H2H: {h2h.matches_played} maç (ben={h2h.team_a_wins} X={h2h.draws} rakip={h2h.team_b_wins})\n"
        f"Sinyaller: {signals if signals else 'belirgin sinyal yok'}"
        + formation_block
        + plan_block
    )
    return commentator._call(system, user, max_tokens=400)
