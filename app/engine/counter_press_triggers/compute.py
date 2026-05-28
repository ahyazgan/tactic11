"""Counter-press Trigger Types — top kaybı sonrası ilk reaksiyon tipi.

Tanım: bizim takım pas kaybedince (PassEvent.completed=False), takımdan
gelen İLK defansif aksiyonun (≤TRIGGER_WINDOW dk içinde) tipini sayar:
- pressure
- tackle
- interception
- ball_recovery
- (none — pencere içinde reaksiyon yok)

Klopp "counter-press" : %50+ pressure (yoğun yaklaşma).
Mourinho "drop-back"  : %50+ none (geriye çekilme).

Saf hesap.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.audit import AuditRecord, EngineResult
from app.domain import DefensiveAction, PassEvent

ENGINE_NAME = "engine.counter_press_triggers"
ENGINE_VERSION = "1"

# Top kaybı → ilk reaksiyon penceresi
TRIGGER_WINDOW_MIN = 0.10  # 6 saniye


@dataclass(frozen=True)
class CounterPressTriggersReport:
    team_external_id: int
    matches_analyzed: int
    losses_analyzed: int
    pressure_responses: int
    tackle_responses: int
    interception_responses: int
    recovery_responses: int
    no_response: int
    dominant_trigger: str   # "pressure" | "tackle" | "interception" | "recovery" | "drop_back"


def compute_counter_press_triggers(
    team_external_id: int,
    all_passes: Iterable[PassEvent],
    all_def_actions: Iterable[DefensiveAction],
    *,
    matches_analyzed: int = 1,
) -> EngineResult[CounterPressTriggersReport]:
    losses = sorted(
        ((p.period * 1000 + p.minute) for p in all_passes
         if p.team_external_id == team_external_id and not p.completed),
    )
    # Sadece bizim takımın aksiyonları
    own_actions = sorted(
        ((d.period * 1000 + d.minute, d.action_type) for d in all_def_actions
         if d.team_external_id == team_external_id),
        key=lambda x: x[0],
    )

    counts = {
        "pressure": 0, "tackle": 0, "interception": 0,
        "ball_recovery": 0, "none": 0,
    }
    for loss_t in losses:
        # İlk own action ≤ window
        first: str | None = None
        for at, atype in own_actions:
            if at < loss_t:
                continue
            if at - loss_t > TRIGGER_WINDOW_MIN:
                break
            first = atype
            break
        if first is None:
            counts["none"] += 1
        elif first in counts:
            counts[first] += 1
        else:
            counts["none"] += 1  # unknown action_type → drop_back say

    total = sum(counts.values())
    if total == 0:
        dominant = "insufficient_data"
    else:
        # Dominant: en yüksek pay
        biggest = max(counts.values())
        if counts["none"] == biggest:
            dominant = "drop_back"
        else:
            tag = max((k for k, v in counts.items() if k != "none"),
                      key=lambda k: counts[k])
            dominant = tag.replace("ball_recovery", "recovery")

    report = CounterPressTriggersReport(
        team_external_id=team_external_id,
        matches_analyzed=matches_analyzed,
        losses_analyzed=total,
        pressure_responses=counts["pressure"],
        tackle_responses=counts["tackle"],
        interception_responses=counts["interception"],
        recovery_responses=counts["ball_recovery"],
        no_response=counts["none"],
        dominant_trigger=dominant,
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="team", subject_id=team_external_id,
        metric="counter_press_triggers",
        value={
            "pressure_responses": counts["pressure"],
            "tackle_responses": counts["tackle"],
            "interception_responses": counts["interception"],
            "recovery_responses": counts["ball_recovery"],
            "no_response": counts["none"],
            "dominant_trigger": dominant,
        },
        inputs={"trigger_window_min": TRIGGER_WINDOW_MIN,
                "matches_analyzed": matches_analyzed},
        formula="first own def_action within TRIGGER_WINDOW after own pass loss",
    )
    return EngineResult(value=report, audit=audit)
