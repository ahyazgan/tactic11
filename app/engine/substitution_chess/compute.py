"""Substitution Chess — sub yapılırsa önümüzdeki dakikalarda ne olur.

"Substitution chess" çünkü TD farklı sub kombinasyonlarını "satranç hamlesi"
gibi düşünür. Bu engine basit projeksiyon yapar (gerçek Monte Carlo değil):

Her potansiyel sub için:
1. Çıkan oyuncunun mevcut fatigue + recent_completion
2. Giren oyuncunun (varsayılan) fresh state
3. Önümüzdeki kalan dakikalar boyunca takım performans projeksiyonu:
   - fatigue: kalan dakika × declining curve
   - team_performance_delta: sub yapılırsa N dk sonra dominance % değişimi

Heuristic — pilot kulüpte gerçek per-player tracking gelirse Monte Carlo
ile zenginleştirilebilir.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.audit import AuditRecord, EngineResult
from app.domain import DefensiveAction, PassEvent
from app.engine.live_sub_recommendation import compute_live_sub_recommendation

ENGINE_NAME = "engine.substitution_chess"
ENGINE_VERSION = "1"

# Fresh oyuncunun başlangıç fatigue'i — oyuna yeni giren tabula rasa
FRESH_PLAYER_FATIGUE = 0.05
# Fatigue curve: dakika başına artış (~1.5 dk başına 0.01 — 30 dk'da 0.20)
FATIGUE_PER_MINUTE = 0.007
# Sub'ın "fresh boost" katkısı: takım dominance'ına projekt
SUB_BOOST_DOMINANCE_DELTA_PER_MINUTE_REMAINING = 0.015


@dataclass(frozen=True)
class SubScenario:
    """Tek sub senaryosu — çıkan + giren + projeksiyon."""
    out_player_id: int
    out_player_current_fatigue: float
    out_player_projected_fatigue_at_full_time: float  # eğer sub YOKSA
    in_player_id: int | None                          # None = "boş slot" (henüz seçilmedi)
    in_player_projected_fatigue_at_full_time: float
    minutes_remaining: float
    projected_dominance_delta: float                  # sub yaparsa +; yapmazsa 0
    confidence: str                                   # "high" | "medium" | "low"


@dataclass(frozen=True)
class SubChessReport:
    team_external_id: int
    current_minute: float
    minutes_remaining: float
    scenarios: tuple[SubScenario, ...]  # urgency_desc sırada
    best_scenario_index: int            # En yüksek dominance_delta
    no_action_baseline: float            # Sub YAPMAZSA dominance delta


def _project_fatigue(
    current_fatigue: float, minutes_remaining: float,
) -> float:
    return min(1.0, current_fatigue + FATIGUE_PER_MINUTE * minutes_remaining)


def _confidence(out_fatigue: float, minutes_remaining: float) -> str:
    if out_fatigue >= 0.50 and minutes_remaining >= 15:
        return "high"
    if out_fatigue >= 0.30:
        return "medium"
    return "low"


def compute_substitution_chess(
    team_external_id: int,
    all_passes: Iterable[PassEvent],
    all_def_actions: Iterable[DefensiveAction],
    *,
    current_minute: float,
    match_total_minutes: float = 90.0,
    my_score: int = 0,
    opponent_score: int = 0,
    candidate_in_player_ids: list[int] | None = None,
) -> EngineResult[SubChessReport]:
    """Mevcut maç durumundan top sub kombinasyonlarını projekt et.

    `candidate_in_player_ids` verilirse her senaryo için ev sahibi
    yedek seçimi simüle edilir; verilmezse "in_player_id=None" döner
    (TD'nin seçeceği boş slot).
    """
    passes_list = list(all_passes)
    defs_list = list(all_def_actions)
    minutes_remaining = max(0.0, match_total_minutes - current_minute)

    # Mevcut sub recommendations'tan top 3 çıkan oyuncu al
    sub_rec = compute_live_sub_recommendation(
        team_external_id, passes_list, defs_list,
        current_minute=current_minute,
        my_score=my_score, opponent_score=opponent_score,
    ).value

    scenarios: list[SubScenario] = []
    for sub in sub_rec.recommendations[:3]:
        out_pid = sub.player_external_id
        out_fatigue = sub.fatigue_score

        # Sub YAPMAZSA: out oyuncu kalan dakikaları yorgun gider
        projected_out_fatigue_if_no_sub = _project_fatigue(
            out_fatigue, minutes_remaining,
        )

        in_pid = (
            candidate_in_player_ids[0]
            if candidate_in_player_ids else None
        )
        in_projected_fatigue = _project_fatigue(
            FRESH_PLAYER_FATIGUE, minutes_remaining,
        )

        # Projeksiyon: sub yaparsak ne kadar dominance bonus alırız
        # Fresh oyuncu fatigue avantajı: (out_projected - in_projected) × scaling
        fatigue_diff = projected_out_fatigue_if_no_sub - in_projected_fatigue
        projected_dominance_delta = round(
            fatigue_diff * SUB_BOOST_DOMINANCE_DELTA_PER_MINUTE_REMAINING
            * minutes_remaining,
            3,
        )

        scenarios.append(SubScenario(
            out_player_id=out_pid,
            out_player_current_fatigue=round(out_fatigue, 3),
            out_player_projected_fatigue_at_full_time=round(
                projected_out_fatigue_if_no_sub, 3,
            ),
            in_player_id=in_pid,
            in_player_projected_fatigue_at_full_time=round(
                in_projected_fatigue, 3,
            ),
            minutes_remaining=minutes_remaining,
            projected_dominance_delta=projected_dominance_delta,
            confidence=_confidence(out_fatigue, minutes_remaining),
        ))

    scenarios_sorted = tuple(sorted(
        scenarios, key=lambda s: -s.projected_dominance_delta,
    ))
    best_idx = 0 if scenarios_sorted else -1
    # Sub YAPMAZSA baseline (en yorgun oyuncu — eğer çıkarmazsak fatigue artar)
    # Bu, "hiçbir sub yapma" projeksiyonu — dominance Δ ~ 0
    baseline = 0.0

    report = SubChessReport(
        team_external_id=team_external_id,
        current_minute=current_minute,
        minutes_remaining=minutes_remaining,
        scenarios=scenarios_sorted,
        best_scenario_index=best_idx,
        no_action_baseline=baseline,
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="team", subject_id=team_external_id,
        metric="substitution_chess",
        value={
            "minutes_remaining": minutes_remaining,
            "scenarios_count": len(scenarios_sorted),
            "best_scenario_delta": (
                scenarios_sorted[0].projected_dominance_delta
                if scenarios_sorted else 0.0
            ),
            "scenarios": [
                {
                    "out": s.out_player_id,
                    "in": s.in_player_id,
                    "projected_delta": s.projected_dominance_delta,
                    "confidence": s.confidence,
                }
                for s in scenarios_sorted
            ],
        },
        inputs={
            "fresh_player_fatigue": FRESH_PLAYER_FATIGUE,
            "fatigue_per_minute": FATIGUE_PER_MINUTE,
            "sub_boost_scaling": SUB_BOOST_DOMINANCE_DELTA_PER_MINUTE_REMAINING,
            "current_minute": current_minute,
            "match_total_minutes": match_total_minutes,
            "my_score": my_score,
            "opponent_score": opponent_score,
        },
        formula=(
            "live_sub_recommendation top 3 üzerinde forward projection; "
            "out_fatigue_projected vs in_fresh_projected × kalan dakika "
            "× scaling = dominance delta"
        ),
    )
    return EngineResult(value=report, audit=audit)
