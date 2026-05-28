"""Fatigue Signal — devre arası yorulan oyuncu tespiti.

Tanım: bir oyuncunun **erken-yarı** (minute 0-30) vs **geç-yarı**
(minute 30-45 veya 75-90) arasındaki performans düşüşü.

İki sinyal birleştirilir:
- pass_completion_drop = early.complete% − late.complete%
- action_count_drop_ratio = (early_actions − late_actions) / early_actions

Combined fatigue_score: 0..1 — yüksek = oyuncu yorgun
Eşik 0.30+ → "consider substitution"
0.50+ → "high fatigue, urgent"

Saf hesap. Event listesinden PassEvent + DefensiveAction üzerinde çalışır.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.audit import AuditRecord, EngineResult
from app.domain import DefensiveAction, PassEvent

ENGINE_NAME = "engine.fatigue_signal"
ENGINE_VERSION = "1"

# Erken-yarı / Geç-yarı sınırı (dakika)
EARLY_HALF_END = 30.0
LATE_HALF_START = 30.0  # 1. yarıda 30-45; 2. yarıda 75-90 için caller ayarlar

# Subset eşikleri (consider/urgent)
CONSIDER_THRESHOLD = 0.30
URGENT_THRESHOLD = 0.50


@dataclass(frozen=True)
class FatigueReport:
    player_external_id: int
    minutes_analyzed: tuple[float, float]   # (start, end) penceresi
    early_actions: int
    late_actions: int
    early_pass_completion: float
    late_pass_completion: float
    pass_completion_drop: float
    action_count_drop_ratio: float
    fatigue_score: float                      # 0..1
    recommendation: str                       # "fresh" | "consider_sub" | "urgent_sub"


def _recommendation(score: float, sample: int) -> str:
    if sample < 5:
        return "insufficient_data"
    if score >= URGENT_THRESHOLD:
        return "urgent_sub"
    if score >= CONSIDER_THRESHOLD:
        return "consider_sub"
    return "fresh"


def compute_fatigue_signal(
    player_external_id: int,
    all_passes: Iterable[PassEvent],
    all_def_actions: Iterable[DefensiveAction],
    *,
    early_end: float = EARLY_HALF_END,
    late_start: float = LATE_HALF_START,
    minutes_window: tuple[float, float] = (0.0, 45.0),
) -> EngineResult[FatigueReport]:
    """Bir oyuncunun erken vs geç dakika performans düşüşü.

    Default pencere 1. yarı (0-45). 2. yarı için caller `minutes_window=(45,90)`
    + `early_end=75, late_start=75`.
    """
    window_start, window_end = minutes_window
    pass_list = [
        p for p in all_passes
        if p.player_external_id == player_external_id
        and window_start <= p.minute <= window_end
    ]
    def_list = [
        d for d in all_def_actions
        if d.player_external_id == player_external_id
        and window_start <= d.minute <= window_end
    ]

    # Erken-yarı / Geç-yarı ayrımı
    early_passes = [p for p in pass_list if p.minute < early_end]
    late_passes = [p for p in pass_list if p.minute >= late_start]
    early_defs = [d for d in def_list if d.minute < early_end]
    late_defs = [d for d in def_list if d.minute >= late_start]

    early_actions = len(early_passes) + len(early_defs)
    late_actions = len(late_passes) + len(late_defs)

    early_comp = (
        sum(1 for p in early_passes if p.completed) / len(early_passes)
        if early_passes else 0.0
    )
    late_comp = (
        sum(1 for p in late_passes if p.completed) / len(late_passes)
        if late_passes else 0.0
    )

    pass_drop = max(0.0, early_comp - late_comp)
    # Action drop normalize: %50+ azalma → 1.0
    if early_actions == 0:
        action_drop = 0.0
    else:
        raw_drop = (early_actions - late_actions) / early_actions
        action_drop = max(0.0, min(1.0, raw_drop / 0.5))

    fatigue_score = round(0.5 * pass_drop + 0.5 * action_drop, 3)
    rec = _recommendation(fatigue_score, early_actions + late_actions)

    report = FatigueReport(
        player_external_id=player_external_id,
        minutes_analyzed=minutes_window,
        early_actions=early_actions,
        late_actions=late_actions,
        early_pass_completion=round(early_comp, 3),
        late_pass_completion=round(late_comp, 3),
        pass_completion_drop=round(pass_drop, 3),
        action_count_drop_ratio=round(action_drop, 3),
        fatigue_score=fatigue_score,
        recommendation=rec,
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="player", subject_id=player_external_id,
        metric="fatigue_signal",
        value={
            "fatigue_score": fatigue_score,
            "pass_completion_drop": report.pass_completion_drop,
            "action_count_drop_ratio": report.action_count_drop_ratio,
            "recommendation": rec,
        },
        inputs={
            "early_end": early_end, "late_start": late_start,
            "window": list(minutes_window),
            "consider_threshold": CONSIDER_THRESHOLD,
            "urgent_threshold": URGENT_THRESHOLD,
        },
        formula="0.5 × pass_completion_drop + 0.5 × min(1, action_drop/0.5)",
    )
    return EngineResult(value=report, audit=audit)
