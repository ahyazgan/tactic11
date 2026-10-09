"""Combine existing appearance consensus and short-gap palette evidence.

Development only. Both boundary rules require a stable, independently tracked
identity change. Baseline source teams and the complete baseline coverage are
retained; neither color cue alone can split a person.
"""

from __future__ import annotations

from collections import defaultdict

from app.tracking.identity_split import appearance_phases
from scripts.soccertrack_v2.candidates.identity_consensus_palette_v2 import palette_support
from scripts.soccertrack_v2.candidates.palette_motion_partitions_v1 import (
    _observations,
    _source_index,
)
from scripts.soccertrack_v2.candidates.palette_motion_partitions_v1 import (
    partition as palette_partition,
)
from scripts.soccertrack_v2.candidates.short_gap_motion_v1 import valid_color


def partition(
    raw, primary, secondary, baseline, palette_anchors, *, baseline_centers, appearance_only=False
):
    # This call also validates all source observations and chooses the entire
    # baseline clip when the motion stream has lost any existing observation.
    output, _ = palette_partition(raw, primary, dict(samples=[]), baseline, palette_anchors)
    source, timeline = _source_index(raw)
    support = _observations(secondary, source, timeline)
    _, palette_events = palette_partition(raw, primary, secondary, baseline, palette_anchors)
    events = (
        {}
        if appearance_only
        else {
            (event["continuity_id"], event["raw_id"], event["first_order"]): {
                **event,
                "evidence": ["palette_crossover"],
            }
            for event in palette_events
        }
    )
    grouped = defaultdict(list)
    for sample in output["samples"]:
        continuity = sample.get("continuity_id", 0)
        for index, row in enumerate(sample["persons"]):
            key = (continuity, sample["frame_idx"], tuple(row[1:5]))
            grouped[continuity, row[0]].append(
                (
                    sample,
                    index,
                    valid_color(source[key]["color"]),
                    support.get(key, (None, None))[0],
                )
            )
    fps = float(raw["stats"]["effective_track_fps"])
    for (continuity, identity), rows in grouped.items():
        _, boundaries = appearance_phases(
            [row[2] for row in rows],
            seconds=[row[0]["seconds"] for row in rows],
            max_gap_seconds=1.5 / fps,
        )
        for boundary in boundaries:
            start, end = boundary.first_index, boundary.confirmed_index
            before, after = rows[max(0, start - 3) : start], rows[start : end + 1]
            old, new = [row[3] for row in before], [row[3] for row in after]
            if not (
                len(old) == 3
                and len(new) >= 3
                and None not in old + new
                and len(set(old)) == len(set(new)) == 1
                and old[0] != new[0]
                and palette_support(
                    [row[2] for row in before], [row[2] for row in after], baseline_centers
                )
            ):
                continue
            key = (continuity, identity, rows[start][0]["order"])
            if key in events:
                events[key]["evidence"].append("appearance_consensus")
                continue
            events[key] = dict(
                continuity_id=continuity,
                raw_id=identity,
                first_order=rows[start][0]["order"],
                confirmed_order=rows[end][0]["order"],
                old_support=old[0],
                new_support=new[0],
                evidence=["appearance_consensus"],
            )
    next_id = (
        max((row[0] for sample in output["samples"] for row in sample["persons"]), default=0) + 1
    )
    audit = []
    for (continuity, original), rows in grouped.items():
        identity = original
        for sample, index, _, _ in rows:
            event = events.get((continuity, original, sample["order"]))
            if event:
                identity = next_id
                next_id += 1
                audit.append({**event, "new_id": identity})
            row = sample["persons"][index]
            team = sample["person_teams"].pop(str(original))
            sample["persons"][index] = [identity, *row[1:]]
            sample["person_teams"][str(identity)] = team
    # A full source check catches accidental duplicate IDs or altered evidence.
    _observations(output, source, timeline)
    return output, audit
