"""PlayerFeedbackAgent — bireysel oyuncu maç-sonu coach feedback.

tactic11'nin en yüksek ürün diferansiyatörü: Opta/Wyscout takım analizi
verir, oyuncu-bazlı aksiyonel feedback vermez.

Context: {"match_external_id": int, "player_external_id": int}
Output: {
  player_id, match_id, summary metrics (xT/xA/VAEP/prog passes,
  press_resistance), top 3 suboptimal pass (frame örnekleri),
  ai_brief: "Bu maçta Y pas seçeneği X yerine olmalıydı" tarzı 200 kelime
}

Backward compatible: events tablosu boşsa stub brief.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.base import Agent, AgentResult
from app.ai import AnthropicClient, ClaudeCommentator
from app.data.loaders import load_match_events
from app.db import models
from app.engine.overperformance import compute_overperformance
from app.engine.pass_alternatives import (
    compute_player_pass_alternatives_summary,
)
from app.engine.press_resistance import compute_press_resistance
from app.engine.progressive_passes import compute_progressive_passes
from app.engine.vaep import compute_vaep
from app.engine.xa import compute_player_xa
from app.engine.xt import compute_player_xt
from app.sports import football


class PlayerFeedbackAgent(Agent):
    """Maç-sonu bireysel oyuncu feedback raporu."""

    name = "player_feedback"
    version = "1"

    def __init__(self, *, commentator: ClaudeCommentator | None = None):
        self._commentator = commentator or ClaudeCommentator(AnthropicClient())

    def run(self, session: Session, *, context: dict[str, Any]) -> AgentResult:
        match_id = context.get("match_external_id")
        player_id = context.get("player_external_id")
        if match_id is None or player_id is None:
            raise ValueError(
                "context.match_external_id + player_external_id zorunlu",
            )
        match_id = int(match_id)
        player_id = int(player_id)

        match = session.execute(
            select(models.Match).where(
                models.Match.sport == football.SPORT_NAME,
                models.Match.external_id == match_id,
            )
        ).scalar_one_or_none()
        if match is None:
            raise ValueError(f"match {match_id} yok")

        loaded = load_match_events(session, match_id)
        if loaded.total == 0:
            return AgentResult(
                output_json={
                    "match_external_id": match_id,
                    "player_external_id": player_id,
                    "events_loaded": 0,
                    "note": "Bu maç için event ingest yok",
                    "ai_brief": (
                        f"[stub:player_feedback] match {match_id} player "
                        f"{player_id} — events yok."
                    ),
                },
                summary=f"player feedback: events yok (player={player_id})",
                subject_type="player", subject_id=player_id,
            )

        # PlayerAppearance — minutes_played için
        appearance = session.execute(
            select(models.PlayerAppearance).where(
                models.PlayerAppearance.sport == football.SPORT_NAME,
                models.PlayerAppearance.match_external_id == match_id,
                models.PlayerAppearance.player_external_id == player_id,
            )
        ).scalar_one_or_none()
        minutes_played = float(appearance.minutes if appearance else 90)

        # Engineler
        xt = compute_player_xt(player_id, loaded.passes, loaded.carries).value
        xa = compute_player_xa(
            player_id, loaded.passes, loaded.shots,
            minutes_played=int(minutes_played),
        ).value
        vaep = compute_vaep(
            player_external_id=player_id, all_passes=loaded.passes,
            all_carries=loaded.carries, all_shots=loaded.shots,
            minutes_played=minutes_played,
        ).value
        prog = compute_progressive_passes(
            player_external_id=player_id, all_passes=loaded.passes,
            player_minutes_played=minutes_played,
        ).value
        press = compute_press_resistance(
            player_external_id=player_id, all_passes=loaded.passes,
            all_def_actions=loaded.defensive_actions,
        ).value
        overperf = compute_overperformance(
            player_external_id=player_id, all_passes=loaded.passes,
            all_shots=loaded.shots,
        ).value

        # Pas alternatives — frame örnekleri
        alt_summary = compute_player_pass_alternatives_summary(
            player_id, loaded.passes, top_n_suboptimal=3,
        )

        ai_brief = _build_feedback_brief(
            commentator=self._commentator,
            player_id=player_id, match_id=match_id,
            minutes_played=minutes_played,
            xt=xt, xa=xa, vaep=vaep, prog=prog, press=press, overperf=overperf,
            alt_summary=alt_summary,
        )

        output = {
            "match_external_id": match_id,
            "player_external_id": player_id,
            "minutes_played": minutes_played,
            "events_loaded": loaded.total,
            "metrics": {
                "xt_per_90": xt.xt_per_90,
                "xa_per_90": xa.xa_per_90,
                "vaep_per_90": vaep.vaep_per_90,
                "progressive_per_90": prog.progressive_per_90,
                "press_resistance_under_press": press.completion_rate_under_press,
                "overperformance_total": overperf.total_overperformance,
                "overperformance_label": overperf.label,
            },
            "pass_alternatives_summary": alt_summary,
            "ai_brief": ai_brief,
        }
        summary = (
            f"player feedback — player {player_id} match {match_id}: "
            f"xT/90={xt.xt_per_90}, VAEP/90={vaep.vaep_per_90}, "
            f"suboptimal_share={alt_summary['suboptimal_share']}"
        )
        return AgentResult(
            output_json=output, summary=summary,
            subject_type="player", subject_id=player_id,
        )


def _build_feedback_brief(
    *, commentator: ClaudeCommentator,
    player_id: int, match_id: int, minutes_played: float,
    xt, xa, vaep, prog, press, overperf,
    alt_summary: dict[str, Any],
) -> str:
    if commentator._client.is_stub():
        n_sub = len(alt_summary.get("top_suboptimal", []))
        return (
            f"[stub:player_feedback] player {player_id} match {match_id}: "
            f"{minutes_played:.0f} dk · xT/90 {xt.xt_per_90} · "
            f"VAEP/90 {vaep.vaep_per_90} · "
            f"prog/90 {prog.progressive_per_90} · "
            f"press_resistance {press.completion_rate_under_press} · "
            f"overperf {overperf.label}. "
            f"{n_sub} alt-optimal pas tespit edildi. ANTHROPIC_API_KEY yok."
        )
    system = (
        "Sen futbol oyuncusuna maç sonrası kişisel performans feedback "
        "veren teknik analiz koçusun. 200-220 kelime, samimi ama doğrudan ton. "
        "Yapı:\n"
        "1) Maç içinde iyi yapılan 1-2 nokta (xT/VAEP üzerinden)\n"
        "2) İyileştirilebilecek 2-3 spesifik durum (alt-optimal pas örnekleri)\n"
        "3) Bir sonraki maç için odak (1 madde)\n"
        "Sayıları tekrar etme; ÇIKARIM ve spesifik aksiyon öner."
    )
    top_subopt = alt_summary.get("top_suboptimal", [])
    examples = ""
    for i, p in enumerate(top_subopt[:3], 1):
        actual = p["actual_end"]
        best = p["best_alternative"]
        examples += (
            f"\n{i}. {p['minute']:.0f}. dk: ({p['start'][0]:.0f},{p['start'][1]:.0f}) "
            f"→ ({actual[0]:.0f},{actual[1]:.0f}) "
            f"yerine ({best['x']:.0f},{best['y']:.0f}) "
            f"daha iyiydi (xT Δ +{best['delta']:.2f})"
        )
    user = (
        f"Oyuncu {player_id} — Match {match_id}\n"
        f"Süre: {minutes_played:.0f} dk\n\n"
        f"Metrikler:\n"
        f"- xT/90: {xt.xt_per_90} (yaratılan tehdit)\n"
        f"- xA/90: {xa.xa_per_90}\n"
        f"- VAEP/90: {vaep.vaep_per_90} (possession value)\n"
        f"- Progressive paslar/90: {prog.progressive_per_90}\n"
        f"- Pres altında pas tamamlama: "
        f"{press.completion_rate_under_press:.2f} "
        f"(pres dışı: {press.completion_rate_unpressed:.2f})\n"
        f"- Overperformance: {overperf.label} "
        f"(toplam {overperf.total_overperformance:+.2f})\n\n"
        f"Alt-optimal pas oranı: {alt_summary['suboptimal_share']:.0%}\n"
        f"En öne çıkan {len(top_subopt)} alternatif örnek:{examples}"
    )
    return commentator._call(system, user, max_tokens=600)
