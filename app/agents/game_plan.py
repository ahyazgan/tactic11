"""GamePlanAgent — birleşik maç-hazırlık dokümanı (Faz 5 #22, #25, #27, #29).

Maç öncesi tek sayfada: rakip zaaf + bizim güç eşleşmesi + duran top
hazırlık + senaryo planı (Plan B-C) + müsait kadro özeti + AI sentez.

Bu agent diğer engine/agent'ları compose eder; yeni motor yazmaz.

Context: {
    "my_team_external_id": int,
    "opponent_external_id": int,
    "match_external_id"?: int,
    "squad"?: [{player_id, injured?, suspended?, risk_level?}],
}

Output: matchup grid + set-piece routine + scenario plan + available squad
+ ai_brief (game plan dokümanı).
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.agents.base import Agent, AgentResult
from app.ai import AnthropicClient, ClaudeCommentator
from app.data.loaders import load_team_events
from app.engine.available_squad import compute_available_squad
from app.engine.matchup_grid import compute_matchup_grid
from app.engine.set_piece_routine import compute_set_piece_routine

# Senaryo planı — skor durumuna göre taktiksel reçete (heuristic).
# `formation_hint` statik (yaygın TR/EU pratiği); `dynamic_focus`
# matchup_grid sonucundan runtime'da `enrich_scenarios()` ile eklenir.
SCENARIOS = {
    "leading": {
        "label": "Öndeyiz",
        "approach": "Kontrollü blok + hızlı geçiş; pres yüksekliğini düşür",
        "risk": "Çok geri çekilme → momentum kaybı",
        "formation_hint": "5-3-2 veya 4-4-2 (kompakt)",
    },
    "level": {
        "label": "Beraberlik",
        "approach": "Plan A devam; en iyi eşleşme kanadını zorla",
        "risk": "Sabırsızlaşıp dengeyi bozma",
        "formation_hint": "4-3-3 dengeli",
    },
    "trailing": {
        "label": "Geride",
        "approach": "Hat yükselt + ekstra hücum oyuncusu + duran top yoğunluğu",
        "risk": "Arkada açık alan → kontra yeme",
        "formation_hint": "4-2-4 veya 3-4-3 (hücum yoğunluğu)",
    },
}


def enrich_scenarios(
    base: dict[str, dict[str, Any]],
    *,
    matchup: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    """Senaryoları matchup_grid'den çıkan kanal bilgisi ile zenginleştir.

    Backward-compat: yeni alanlar eklenir (`dynamic_focus`); mevcut anahtarlar
    aynı kalır. matchup yoksa base'i kopyalar.
    """
    enriched: dict[str, dict[str, Any]] = {k: dict(v) for k, v in base.items()}
    if not matchup:
        return enriched
    best = matchup.get("best_channel")
    worst = matchup.get("worst_channel")
    if best:
        enriched["level"]["dynamic_focus"] = (
            f"En iyi eşleşme {best} kanadından zorla — matchup tavsiyesi"
        )
        enriched["trailing"]["dynamic_focus"] = (
            f"Hücum kütlesini {best} kanadına kaydır; o tarafta sayısal üstünlük kur"
        )
    if worst:
        enriched["leading"]["dynamic_focus"] = (
            f"Rakip {worst} kanadında güçlü — top kaybetme, top dolaşımı orta-{best or 'kanat'}"
            if best else
            f"Rakip {worst} kanadında güçlü — top dolaşımını oradan kaçır"
        )
    return enriched


class GamePlanAgent(Agent):
    """Birleşik maç-hazırlık (game-plan) dokümanı."""

    name = "game_plan"
    version = "1"

    def __init__(self, *, commentator: ClaudeCommentator | None = None):
        self._commentator = commentator or ClaudeCommentator(AnthropicClient())

    def run(self, session: Session, *, context: dict[str, Any]) -> AgentResult:
        my_team = context.get("my_team_external_id")
        opp_team = context.get("opponent_external_id")
        if my_team is None or opp_team is None:
            raise ValueError(
                "context.my_team_external_id + opponent_external_id zorunlu",
            )
        my_team = int(my_team)
        opp_team = int(opp_team)
        squad = context.get("squad", [])

        my_events = load_team_events(session, my_team, last_n=5)
        opp_events = load_team_events(session, opp_team, last_n=5)

        # 1. Matchup grid (rakip zaaf × bizim güç)
        matchup: dict[str, Any] | None = None
        if my_events.total > 0 and opp_events.total > 0:
            try:
                mg = compute_matchup_grid(
                    my_team_external_id=my_team,
                    opponent_team_external_id=opp_team,
                    our_passes=my_events.passes,
                    our_carries=my_events.carries,
                    opponent_def_actions=opp_events.defensive_actions,
                    matches_analyzed=len(my_events.match_ids),
                ).value
                matchup = {
                    "best_channel": mg.best_channel,
                    "worst_channel": mg.worst_channel,
                    "recommendation": mg.recommendation,
                    "by_channel": [
                        {"channel": c.channel, "score": c.matchup_score,
                         "verdict": c.verdict}
                        for c in mg.by_channel
                    ],
                }
            except (ValueError, ZeroDivisionError, KeyError, TypeError):
                matchup = None

        # 2. Set-piece routine
        set_piece: dict[str, Any] | None = None
        if my_events.total > 0 and opp_events.total > 0:
            try:
                sp = compute_set_piece_routine(
                    my_team_external_id=my_team,
                    opponent_team_external_id=opp_team,
                    my_offensive_shots=my_events.shots,
                    opponent_defensive_shots=opp_events.shots,
                    opponent_offensive_shots=opp_events.shots,
                    matches_analyzed=min(
                        len(my_events.match_ids), len(opp_events.match_ids),
                    ),
                ).value
                set_piece = {
                    "avoid_zone": sp.avoid_zone,
                    "top_recommendations": [
                        {"zone": r.target_zone, "technique": r.technique,
                         "rationale": r.rationale}
                        for r in sp.top_recommendations
                    ],
                }
            except (ValueError, ZeroDivisionError, KeyError, TypeError):
                set_piece = None

        # 3. Müsait kadro (squad verilirse)
        squad_report: dict[str, Any] | None = None
        if squad:
            sr = compute_available_squad(my_team, squad).value
            squad_report = {
                "available_count": sr.available_count,
                "doubtful_count": sr.doubtful_count,
                "unavailable_count": sr.unavailable_count,
                "players": [
                    {"player_id": p.player_external_id, "status": p.status,
                     "reason": p.reason}
                    for p in sr.players
                ],
            }

        # 4. Senaryo planı — base heuristic + matchup_grid runtime enrich
        scenario_plan = enrich_scenarios(SCENARIOS, matchup=matchup)

        ai_brief = _build_game_plan_brief(
            commentator=self._commentator,
            my_team=my_team, opp_team=opp_team,
            matchup=matchup, set_piece=set_piece,
            squad_report=squad_report, scenario_plan=scenario_plan,
        )

        output = {
            "my_team_external_id": my_team,
            "opponent_external_id": opp_team,
            "match_external_id": context.get("match_external_id"),
            "matchup_grid": matchup,
            "set_piece_plan": set_piece,
            "available_squad": squad_report,
            "scenario_plan": scenario_plan,
            "ai_brief": ai_brief,
        }
        best = matchup["best_channel"] if matchup else "—"
        summary = (
            f"game plan {my_team} vs {opp_team}: "
            f"en iyi kanal {best}, "
            f"{len(scenario_plan)} senaryo"
        )
        return AgentResult(
            output_json=output, summary=summary,
            subject_type="team", subject_id=my_team,
        )


def _build_game_plan_brief(
    *, commentator: ClaudeCommentator,
    my_team: int, opp_team: int,
    matchup: dict[str, Any] | None,
    set_piece: dict[str, Any] | None,
    squad_report: dict[str, Any] | None,
    scenario_plan: dict[str, Any],
) -> str:
    if commentator._client.is_stub():
        parts = [f"[stub:game_plan] takım {my_team} vs rakip {opp_team}"]
        if matchup:
            parts.append(f"en iyi kanal {matchup['best_channel']}")
        if set_piece:
            parts.append(f"set-piece avoid {set_piece['avoid_zone']}")
        if squad_report:
            parts.append(f"{squad_report['available_count']} müsait oyuncu")
        parts.append(f"{len(scenario_plan)} senaryo. ANTHROPIC_API_KEY yok.")
        return " · ".join(parts)
    system = (
        "Sen futbol teknik direktörünün maç-öncesi game-plan dokümanını "
        "hazırlayan baş analistsin. 250-300 kelime. Yapı:\n"
        "1) Anahtar eşleşme — hangi kanaldan saldır, hangiden kaçın\n"
        "2) Duran top planı (hedef zone + teknik + kaçınılacak)\n"
        "3) Kadro durumu (müsait/şüpheli)\n"
        "4) Senaryo reçeteleri (önde/berabere/geride)\n"
        "Somut, sahada uygulanabilir; sayı tekrar etme, çıkarım ver."
    )
    user_parts: list[str] = [f"Maç: takım {my_team} vs rakip {opp_team}\n"]
    if matchup:
        user_parts.append(
            f"Matchup grid: en iyi kanal {matchup['best_channel']}, "
            f"rakip güçlü {matchup['worst_channel']}. "
            f"{matchup['recommendation']}\n"
        )
    if set_piece:
        recs = "; ".join(
            f"{r['zone']} ({r['technique']})"
            for r in set_piece["top_recommendations"][:2]
        )
        user_parts.append(
            f"Set-piece: hedef {recs}; avoid {set_piece['avoid_zone']}\n"
        )
    if squad_report:
        user_parts.append(
            f"Kadro: {squad_report['available_count']} müsait, "
            f"{squad_report['doubtful_count']} şüpheli, "
            f"{squad_report['unavailable_count']} yok\n"
        )
    user_parts.append(
        "Senaryolar: " + "; ".join(
            f"{v['label']} → {v['approach']}"
            for v in scenario_plan.values()
        )
    )
    return commentator._call(system, "".join(user_parts), max_tokens=800)
