"""Final Third Entries — son üçe giriş yolları (pas vs carry) + tipik zone.

Tanım: takımın hücum üçüne (x ≥ 66.7) geçiş event'leri. Tip ayrımı:
- pass entries: PassEvent.start_x < 66.7 AND end_x ≥ 66.7
- carry entries: Carry.start_x < 66.7 AND end_x ≥ 66.7

Tipik giriş kanalı: pass.end_y dağılımı (sol/orta/sağ).

Saf hesap.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.audit import AuditRecord, EngineResult
from app.domain import Carry, PassEvent

ENGINE_NAME = "engine.final_third_entries"
ENGINE_VERSION = "1"

FINAL_THIRD_X = 66.7


@dataclass(frozen=True)
class FinalThirdEntriesReport:
    team_external_id: int
    matches_analyzed: int
    pass_entries: int
    carry_entries: int
    total_entries: int
    pass_share: float                # pass_entries / total
    left_entries: int                # end_y < 33
    central_entries: int             # 33 ≤ end_y ≤ 67
    right_entries: int               # end_y > 67
    dominant_entry_channel: str      # "left" | "central" | "right" | "balanced"


def _channel(y: float) -> str:
    if y < 33.3:
        return "left"
    if y > 66.7:
        return "right"
    return "central"


def compute_final_third_entries(
    team_external_id: int,
    all_passes: Iterable[PassEvent],
    all_carries: Iterable[Carry],
    *,
    matches_analyzed: int = 1,
) -> EngineResult[FinalThirdEntriesReport]:
    channel_counts = {"left": 0, "central": 0, "right": 0}

    pass_entries = 0
    for p in all_passes:
        if p.team_external_id != team_external_id:
            continue
        if p.start_x >= FINAL_THIRD_X or p.end_x < FINAL_THIRD_X:
            continue
        pass_entries += 1
        channel_counts[_channel(p.end_y)] += 1

    carry_entries = 0
    for c in all_carries:
        if c.team_external_id != team_external_id:
            continue
        if c.start_x >= FINAL_THIRD_X or c.end_x < FINAL_THIRD_X:
            continue
        carry_entries += 1
        channel_counts[_channel(c.end_y)] += 1

    total = pass_entries + carry_entries
    if total == 0:
        dominant = "insufficient_data"
    else:
        maxc = max(channel_counts.values())
        # %40 dominance
        if maxc / total < 0.40:
            dominant = "balanced"
        else:
            dominant = max(channel_counts, key=lambda k: channel_counts[k])

    report = FinalThirdEntriesReport(
        team_external_id=team_external_id,
        matches_analyzed=matches_analyzed,
        pass_entries=pass_entries,
        carry_entries=carry_entries,
        total_entries=total,
        pass_share=round(pass_entries / total, 3) if total else 0.0,
        left_entries=channel_counts["left"],
        central_entries=channel_counts["central"],
        right_entries=channel_counts["right"],
        dominant_entry_channel=dominant,
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="team", subject_id=team_external_id,
        metric="final_third_entries",
        value={
            "pass_entries": pass_entries,
            "carry_entries": carry_entries,
            "total_entries": total,
            "dominant_entry_channel": dominant,
        },
        inputs={"final_third_x": FINAL_THIRD_X, "matches_analyzed": matches_analyzed},
        formula="passes/carries crossing x=66.7 from below; bin end_y per channel",
    )
    return EngineResult(value=report, audit=audit)
