"""Press Resistance — pres altında pas tamamlama oranı.

Tanım: bir oyuncunun (veya takımın) **pressure** eventiyle aynı dakikada
ve <= 5 birim mesafede yaptığı pasların başarı oranı.

De Bruyne, Modric, Verratti gibi "press-proof" oyuncuların ayırt edilmesi
için temel. Takım seviyesinde: deep_playmaker'ların hayatta kalma oranı.

Saf hesap. PassEvent + DefensiveAction (pressure) → PressResistanceReport.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

from app.audit import AuditRecord, EngineResult
from app.domain import DefensiveAction, PassEvent

ENGINE_NAME = "engine.press_resistance"
ENGINE_VERSION = "1"

# Pres mesafesi (Euclidean 100×100 saha): rakip pressure eventi <= 8 birim
PRESS_RADIUS = 8.0
# Zaman penceresi: pressure ile pas aynı dakika içinde
PRESS_TIME_WINDOW_MIN = 1.0


@dataclass(frozen=True)
class PressResistanceReport:
    team_external_id: int | None
    player_external_id: int | None
    matches_analyzed: int
    passes_under_press: int
    completed_under_press: int
    completion_rate_under_press: float   # 0-1
    completion_rate_unpressed: float     # 0-1 (karşılaştırma)
    press_resistance_delta: float        # under_press - unpressed; ≥0 iyi


def _is_under_press(p: PassEvent, opponent_pressures: list[DefensiveAction]) -> bool:
    """Pas başlangıç noktasından <=PRESS_RADIUS uzaklıkta rakip pressure var mı?"""
    for pr in opponent_pressures:
        if pr.period != p.period:
            continue
        if abs(pr.minute - p.minute) > PRESS_TIME_WINDOW_MIN:
            continue
        dx = pr.x - p.start_x
        dy = pr.y - p.start_y
        if math.hypot(dx, dy) <= PRESS_RADIUS:
            return True
    return False


def compute_press_resistance(
    *,
    team_external_id: int | None = None,
    player_external_id: int | None = None,
    all_passes: Iterable[PassEvent],
    all_def_actions: Iterable[DefensiveAction],
    matches_analyzed: int = 1,
) -> EngineResult[PressResistanceReport]:
    """Bir takım VEYA oyuncu için press resistance.

    Subject seçimi: `player_external_id` set'liyse o oyuncuya filtre;
    yoksa `team_external_id` ile takım geneline.
    """
    if team_external_id is None and player_external_id is None:
        raise ValueError("team_external_id veya player_external_id verilmeli")

    # Subject pasları
    subj_team: int | None
    if player_external_id is not None:
        subject_passes = [p for p in all_passes if p.player_external_id == player_external_id]
        # Rakip pressureları: subject'in takımı dışındaki pressureları
        subj_team = subject_passes[0].team_external_id if subject_passes else team_external_id
    else:
        subj_team = team_external_id
        subject_passes = [p for p in all_passes if p.team_external_id == team_external_id]

    opponent_pressures = [
        d for d in all_def_actions
        if d.team_external_id != subj_team and d.action_type == "pressure"
    ]

    under_press = 0
    under_press_completed = 0
    unpressed = 0
    unpressed_completed = 0

    for p in subject_passes:
        if _is_under_press(p, opponent_pressures):
            under_press += 1
            if p.completed:
                under_press_completed += 1
        else:
            unpressed += 1
            if p.completed:
                unpressed_completed += 1

    rate_press = under_press_completed / under_press if under_press > 0 else 0.0
    rate_unp = unpressed_completed / unpressed if unpressed > 0 else 0.0

    report = PressResistanceReport(
        team_external_id=team_external_id,
        player_external_id=player_external_id,
        matches_analyzed=matches_analyzed,
        passes_under_press=under_press,
        completed_under_press=under_press_completed,
        completion_rate_under_press=round(rate_press, 3),
        completion_rate_unpressed=round(rate_unp, 3),
        press_resistance_delta=round(rate_press - rate_unp, 3),
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="player" if player_external_id else "team",
        subject_id=player_external_id or team_external_id or 0,
        metric="press_resistance",
        value={
            "passes_under_press": under_press,
            "completion_rate_under_press": report.completion_rate_under_press,
            "completion_rate_unpressed": report.completion_rate_unpressed,
            "delta": report.press_resistance_delta,
        },
        inputs={
            "press_radius": PRESS_RADIUS,
            "press_time_window_min": PRESS_TIME_WINDOW_MIN,
            "matches_analyzed": matches_analyzed,
        },
        formula="completed / total for passes near opponent pressure event",
    )
    return EngineResult(value=report, audit=audit)
