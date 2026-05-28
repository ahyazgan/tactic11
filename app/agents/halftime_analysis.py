"""HalftimeAnalysisAgent — devre arası takım analizi + 2. yarı önerileri.

Profesyonel futbol analitiğinin BİRİNCİL canlı kullanım senaryosu:
- Klopp/Brentford/Brighton devre arasında "ne yaradı / ne yaramadı / 2. yarı
  için 3 somut öneri" raporu alır
- 30+ engine'i 1. yarı event filtresiyle çalıştır
- AI commentator 200-250 kelime brief üretir

Context: {"match_external_id": int, "my_team_external_id": int}
Output: {
  match info, 1H stats (xT, PPDA, field_tilt, dominance),
  fatigue_signals (per player), opponent_weakness (channel),
  ai_brief (3 bölüm)
}

Backward compatible: events tablosu boşsa boş report.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.base import Agent, AgentResult
from app.ai import AnthropicClient, ClaudeCommentator
from app.api.serialize import engine_result_to_dict
from app.data.loaders import load_match_events, load_team_events
from app.db import models
from app.engine.fatigue_signal import compute_fatigue_signal
from app.engine.field_tilt import compute_field_tilt
from app.engine.live_sub_recommendation import compute_live_sub_recommendation
from app.engine.match_dominance import compute_match_dominance
from app.engine.opponent_weakness import compute_opponent_weakness
from app.engine.ppda import compute_ppda
from app.engine.pressing_trigger import compute_pressing_trigger
from app.engine.set_piece_pattern_history import compute_set_piece_pattern_history
from app.engine.xt import compute_team_xt
from app.sports import football

# Devre arası penceresi
HALFTIME_MAX_MINUTE = 45.0
# Çok az event'le çalışan oyuncuyu fatigue_signal'dan çıkar
MIN_PLAYER_ACTIONS_FOR_FATIGUE = 8


class HalftimeAnalysisAgent(Agent):
    """Devre arası analiz — 1. yarı event'leri üzerinde 30+ engine."""

    name = "halftime_analysis"
    version = "2"  # v2: set-piece pattern + sub_recommendation eklendi

    def __init__(self, *, commentator: ClaudeCommentator | None = None):
        self._commentator = commentator or ClaudeCommentator(AnthropicClient())

    def run(self, session: Session, *, context: dict[str, Any]) -> AgentResult:
        match_id = context.get("match_external_id")
        my_team_id = context.get("my_team_external_id")
        if match_id is None or my_team_id is None:
            raise ValueError(
                "context.match_external_id + my_team_external_id zorunlu",
            )
        match_id = int(match_id)
        my_team_id = int(my_team_id)

        match = session.execute(
            select(models.Match).where(
                models.Match.sport == football.SPORT_NAME,
                models.Match.external_id == match_id,
            )
        ).scalar_one_or_none()
        if match is None:
            raise ValueError(f"match {match_id} bulunamadı")

        home_id = match.home_team_external_id
        away_id = match.away_team_external_id
        if my_team_id not in (home_id, away_id):
            raise ValueError(
                f"my_team {my_team_id} bu maçta yok (ev={home_id} dep={away_id})",
            )
        opponent_id = away_id if my_team_id == home_id else home_id
        is_home = my_team_id == home_id

        # Events: sadece 1. yarı (minute <= 45)
        loaded = load_match_events(session, match_id)
        first_half_passes = [p for p in loaded.passes if p.minute <= HALFTIME_MAX_MINUTE]
        first_half_carries = [c for c in loaded.carries if c.minute <= HALFTIME_MAX_MINUTE]
        first_half_defs = [d for d in loaded.defensive_actions
                           if d.minute <= HALFTIME_MAX_MINUTE]
        first_half_shots = [s for s in loaded.shots if s.minute <= HALFTIME_MAX_MINUTE]

        events_loaded = (len(first_half_passes) + len(first_half_carries)
                          + len(first_half_defs) + len(first_half_shots))

        if events_loaded == 0:
            return AgentResult(
                output_json={
                    "match_external_id": match_id,
                    "my_team_external_id": my_team_id,
                    "events_loaded": 0,
                    "note": "events tablosunda bu maç için kayıt yok",
                    "ai_brief": (
                        f"[stub:halftime] Match {match_id} için event ingest "
                        f"yapılmamış."
                    ),
                },
                summary="halftime: events yok",
                subject_type="match", subject_id=match_id,
            )

        # Engine çalıştır
        ppda = compute_ppda(my_team_id, first_half_passes, first_half_defs).value
        pres = compute_pressing_trigger(
            my_team_id, first_half_passes, first_half_defs,
        ).value
        tilt = compute_field_tilt(my_team_id, opponent_id, first_half_passes).value
        my_xt = compute_team_xt(my_team_id, first_half_passes, first_half_carries).value
        dominance = compute_match_dominance(
            team_external_id=my_team_id, opponent_team_external_id=opponent_id,
            team_shots=first_half_shots, opponent_shots=first_half_shots,
            all_passes=first_half_passes, team_carries=first_half_carries,
            opponent_carries=first_half_carries,
        ).value
        weakness = compute_opponent_weakness(
            my_team_external_id=my_team_id,
            opponent_team_external_id=opponent_id,
            all_passes=first_half_passes, all_carries=first_half_carries,
            all_def_actions=first_half_defs,
        ).value

        # Rakibin set-piece pattern'i (geçmiş 5 maçtan)
        opp_history = load_team_events(session, opponent_id, last_n=5)
        set_piece_pattern: dict[str, Any] | None = None
        if opp_history.total > 0:
            try:
                sp = compute_set_piece_pattern_history(
                    opponent_id, opp_history.shots,
                    matches_analyzed=len(opp_history.match_ids),
                )
                set_piece_pattern = engine_result_to_dict(sp)["value"]
            except (ValueError, ZeroDivisionError, TypeError, KeyError):
                pass

        # Sub recommendation @ 45. dk
        try:
            sub_rec = compute_live_sub_recommendation(
                my_team_id, first_half_passes, first_half_defs,
                current_minute=HALFTIME_MAX_MINUTE,
                my_score=(match.home_score if is_home else match.away_score) or 0,
                opponent_score=(match.away_score if is_home else match.home_score) or 0,
            )
            sub_recommendations = engine_result_to_dict(sub_rec)["value"]
        except (ValueError, ZeroDivisionError, TypeError, KeyError):
            sub_recommendations = None

        # Fatigue per player (sadece bizim oyuncular)
        my_player_ids = {
            p.player_external_id for p in first_half_passes
            if p.team_external_id == my_team_id
        } | {
            d.player_external_id for d in first_half_defs
            if d.team_external_id == my_team_id
        }
        fatigue_alerts: list[dict[str, Any]] = []
        for pid in my_player_ids:
            f = compute_fatigue_signal(
                pid, first_half_passes, first_half_defs,
                minutes_window=(0.0, HALFTIME_MAX_MINUTE),
            ).value
            if (f.early_actions + f.late_actions) < MIN_PLAYER_ACTIONS_FOR_FATIGUE:
                continue
            if f.recommendation in ("consider_sub", "urgent_sub"):
                fatigue_alerts.append({
                    "player_id": pid,
                    "fatigue_score": f.fatigue_score,
                    "recommendation": f.recommendation,
                    "pass_completion_drop": f.pass_completion_drop,
                })
        fatigue_alerts.sort(key=lambda x: -x["fatigue_score"])

        # AI brief
        ai_brief = _build_halftime_brief(
            commentator=self._commentator,
            my_team_id=my_team_id, opponent_id=opponent_id, is_home=is_home,
            ppda=ppda, pres=pres, tilt=tilt, dominance=dominance,
            weakness=weakness, fatigue_alerts=fatigue_alerts,
            score=f"{match.home_score}-{match.away_score}",
        )

        output = {
            "match_external_id": match_id,
            "my_team_external_id": my_team_id,
            "opponent_team_external_id": opponent_id,
            "my_side": "home" if is_home else "away",
            "halftime_score": f"{match.home_score}-{match.away_score}",
            "events_loaded": events_loaded,
            "first_half_event_counts": {
                "passes": len(first_half_passes),
                "carries": len(first_half_carries),
                "defensive_actions": len(first_half_defs),
                "shots": len(first_half_shots),
            },
            "stats": {
                "ppda": ppda.ppda,
                "pressing_style": pres.style_label,
                "field_tilt_my_share": tilt.team_a_tilt,
                "team_xt_total": my_xt.total_xt,
                "match_dominance_score": dominance.dominance_score,
                "match_dominance_label": dominance.label,
            },
            "opponent_weakness": {
                "most_vulnerable_channel": weakness.most_vulnerable_channel,
                "recommendation": weakness.recommendation,
                "by_channel": [
                    {"channel": c.channel, "score": c.vulnerability_score,
                     "our_attacks": c.our_attacks,
                     "opp_def_actions": c.opp_def_actions}
                    for c in weakness.by_channel
                ],
            },
            "fatigue_alerts": fatigue_alerts,
            "opponent_set_piece_pattern": set_piece_pattern,
            "sub_recommendations": sub_recommendations,
            "ai_brief": ai_brief,
            "audit": {
                "ppda": engine_result_to_dict(
                    compute_ppda(my_team_id, first_half_passes, first_half_defs)
                )["audit"],
                "dominance": engine_result_to_dict(
                    compute_match_dominance(
                        team_external_id=my_team_id,
                        opponent_team_external_id=opponent_id,
                        team_shots=first_half_shots, opponent_shots=first_half_shots,
                        all_passes=first_half_passes, team_carries=first_half_carries,
                        opponent_carries=first_half_carries,
                    )
                )["audit"],
            },
        }
        summary = (
            f"halftime brief — team {my_team_id} vs {opponent_id}: "
            f"dom={dominance.label} ({dominance.dominance_score}), "
            f"zayıf={weakness.most_vulnerable_channel}, "
            f"{len(fatigue_alerts)} yorgun"
        )
        return AgentResult(
            output_json=output, summary=summary,
            subject_type="match", subject_id=match_id,
        )


def _build_halftime_brief(
    *, commentator: ClaudeCommentator,
    my_team_id: int, opponent_id: int, is_home: bool,
    ppda, pres, tilt, dominance, weakness,
    fatigue_alerts: list[dict[str, Any]], score: str,
) -> str:
    side = "ev" if is_home else "dep"
    side_label = "ev sahibi" if is_home else "deplasman"
    n_fatigue = len(fatigue_alerts)
    if commentator._client.is_stub():
        return (
            f"[stub:halftime] {side_label} team {my_team_id} vs {opponent_id}, "
            f"İY skor {score}. Dominance {dominance.label} "
            f"({dominance.dominance_score}). PPDA {ppda.ppda}. Field tilt "
            f"%{int(tilt.team_a_tilt * 100)}. Zayıf kanal: "
            f"{weakness.most_vulnerable_channel}. {n_fatigue} yorgun oyuncu. "
            f"ANTHROPIC_API_KEY yok."
        )
    system = (
        "Sen Türk futbolu teknik direktörünün devre arası analiz asistanısın. "
        "Tam 200-220 kelime. Yapı:\n"
        "(1) 1. yarı özeti — ne yaradı (1-2 cümle, somut sayı)\n"
        "(2) Ne yaramadı — eksik yön (1-2 cümle)\n"
        "(3) 2. yarı için 3 somut öneri (madde madde):\n"
        "    - taktiksel ayar (kanal/pres)\n"
        "    - oyuncu değişikliği (varsa yorgun)\n"
        "    - skor durumuna göre risk (öndeyse koruma, geride atak)\n"
        "Sayılarda iki ondalık kullan; sadece anlamlıyı seç."
    )
    fatigue_line = ""
    if fatigue_alerts:
        top = fatigue_alerts[:3]
        fatigue_line = (
            "\nYorgun oyuncular: " + ", ".join(
                f"player {a['player_id']} (skor {a['fatigue_score']}, "
                f"{a['recommendation']})"
                for a in top
            )
        )
    user = (
        f"Maç: takım {my_team_id} ({side}) vs rakip {opponent_id}\n"
        f"İY skor: {score}\n\n"
        f"1. yarı sayılar:\n"
        f"- PPDA: {ppda.ppda} ({ppda.opp_passes_in_press_zone} rakip pas / "
        f"{ppda.team_def_actions_in_press_zone} defansif)\n"
        f"- Pressing tarzı: {pres.style_label} (avg recovery "
        f"{pres.avg_recovery_time_min} dk)\n"
        f"- Field tilt: bizim %{int(tilt.team_a_tilt * 100)}, "
        f"rakip %{int(tilt.team_b_tilt * 100)}\n"
        f"- Match dominance: {dominance.dominance_score} ({dominance.label})\n"
        f"- xG farkı: {dominance.xg_diff}; possession %"
        f"{int(dominance.possession_share * 100)}\n\n"
        f"Rakibin zayıf kanalı: {weakness.most_vulnerable_channel}. "
        f"Öneri: {weakness.recommendation}"
        f"{fatigue_line}\n"
    )
    return commentator._call(system, user, max_tokens=600)
