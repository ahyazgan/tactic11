"""Research identity partitions confirmed by palette and independent source tracks.

Unlike a tint discontinuity, a confident palette crossover can distinguish
nearly achromatic night kits. Original per-observation teams remain evidence;
this step never refits them after an identity change.
"""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy

import numpy as np

from app.tracking.identity_split import appearance_phases
from app.tracking.short_gap_motion import valid_color
from app.tracking.teams import distinct_team_colors


def palette_slot(color, centers):
    value = valid_color(color)
    if value is None:
        return None
    distance = np.linalg.norm(centers - value, axis=1)
    separation = float(np.linalg.norm(centers[0] - centers[1]))
    if min(distance) > 0.75 * separation or abs(distance[0] - distance[1]) < 0.25 * separation:
        return None
    return int(np.argmin(distance))


def _source_index(raw):
    """Namespace evidence across camera resets and reject ambiguous source rows."""
    source, timeline = {}, {}
    last = {}
    for sample in raw["samples"]:
        continuity = sample.get("continuity_id", 0)
        key = (continuity, sample["frame_idx"])
        position = (sample["order"], sample["frame_idx"], sample["seconds"])
        if (
            key in timeline
            or not np.isfinite(position).all()
            or (
                continuity in last
                and any(a <= b for a, b in zip(position, last[continuity], strict=True))
            )
        ):
            raise ValueError("Source sample positions must strictly increase within continuity")
        timeline[key] = sample
        last[continuity] = position
        for row in raw["detected_persons"][str(sample["order"])]:
            box = np.asarray(row["box"], dtype=float)
            box_key = (*key, tuple(box))
            if (
                box.shape != (4,)
                or not np.isfinite(box).all()
                or np.any(box[2:] <= box[:2])
                or not np.isfinite(row["confidence"])
                or box_key in source
            ):
                raise ValueError("Finite unique source observations required")
            source[box_key] = row
    return source, timeline


def _observations(payload, source, timeline):
    indexed, seen = {}, set()
    previous_order = -1
    for sample in payload["samples"]:
        frame = (sample.get("continuity_id", 0), sample["frame_idx"])
        reference = timeline.get(frame)
        if (
            frame in seen
            or reference is None
            or sample["order"] <= previous_order
            or any(sample[k] != reference[k] for k in ("order", "seconds"))
        ):
            raise ValueError("Prediction sample order/time must match source")
        previous_order = sample["order"]
        seen.add(frame)
        identities = set()
        for row in sample["persons"]:
            key = (*frame, tuple(row[1:5]))
            if (
                len(row) != 6
                or key not in source
                or key in indexed
                or row[0] in identities
                or row[5] != source[key]["confidence"]
            ):
                raise ValueError("Prediction must preserve unique exact source evidence")
            identities.add(row[0])
            indexed[key] = (row[0], sample.get("person_teams", {}).get(str(row[0])))
    return indexed


def palette_partition(raw, primary, secondary, baseline, centers):
    centers = np.asarray(centers, dtype=float)
    if not distinct_team_colors(centers) or np.any((centers < 0) | (centers > 255)):
        raise ValueError("Distinct fixed palette anchors required")
    fps = float(raw["stats"]["effective_track_fps"])
    if not np.isfinite(fps) or fps <= 0:
        raise ValueError("Positive effective FPS required")
    # Match the actual legacy ByteTrack lifetime, including its 30 FPS scaling.
    frames = int(max(1, round(fps)) / 30 * max(1, int(raw["config"]["lost_track_seconds"] * fps)))
    source, timeline = _source_index(raw)
    primary_rows = _observations(primary, source, timeline)
    support = _observations(secondary, source, timeline)
    base_teams = _observations(baseline, source, timeline)
    missing = base_teams.keys() - primary_rows.keys()
    fallback = None
    if missing:
        # Added detections cannot compensate for losing any existing evidence.
        # Abstain from motion recovery for this clip; retain palette refinement.
        primary = baseline
        fallback = dict(
            selected="baseline",
            reason="motion_lost_baseline_observations",
            missing_observations=[
                dict(continuity_id=k[0], frame_idx=k[1], box=[float(x) for x in k[2]])
                for k in sorted(missing)
            ],
        )
    output = deepcopy(primary)
    if fallback is not None:
        output["recovery_fallback"] = fallback
    groups = defaultdict(list)
    for sample in output["samples"]:
        for index, row in enumerate(sample["persons"]):
            key = (sample.get("continuity_id", 0), sample["frame_idx"], tuple(row[1:5]))
            groups[(key[0], row[0])].append(
                (
                    sample,
                    index,
                    support.get(key, (None, None))[0],
                    palette_slot(source[key]["color"], centers),
                    base_teams.get(key, (None, None))[1],
                )
            )
        sample["person_teams"] = {}
    next_id = (
        max((row[0] for sample in output["samples"] for row in sample["persons"]), default=0) + 1
    )
    events = []
    for (continuity, original), observations in groups.items():
        boundaries = {}
        for index in range(3, len(observations) - 2):
            before, after = observations[index - 3 : index], observations[index : index + 3]
            if any(r[2] is None or r[3] is None for r in before + after):
                continue
            if before[-1][0]["seconds"] - before[0][0]["seconds"] > 0.5 or any(
                b[0]["order"] - a[0]["order"] != 1 for a, b in zip(after, after[1:], strict=False)
            ):
                continue
            gap = after[0][0]["seconds"] - before[-1][0]["seconds"]
            if not 0 < gap <= frames / fps:
                continue
            old_motion, new_motion = {r[2] for r in before}, {r[2] for r in after}
            old_palette, new_palette = {r[3] for r in before}, {r[3] for r in after}
            if (
                len(old_motion) == len(new_motion) == len(old_palette) == len(new_palette) == 1
                and old_motion != new_motion
                and old_palette != new_palette
            ):
                boundaries[index] = next_id
                events.append(
                    dict(
                        continuity_id=continuity,
                        raw_id=original,
                        new_id=next_id,
                        first_order=after[0][0]["order"],
                        confirmed_order=after[-1][0]["order"],
                        old_support=next(iter(old_motion)),
                        new_support=next(iter(new_motion)),
                        old_palette=next(iter(old_palette)),
                        new_palette=next(iter(new_palette)),
                    )
                )
                next_id += 1
        identity = original
        for index, (sample, row_index, _, _, team) in enumerate(observations):
            identity = boundaries.get(index, identity)
            row = sample["persons"][row_index]
            sample["persons"][row_index] = [identity, *row[1:]]
            sample["person_teams"][str(identity)] = team
    return output, events


def palette_support(before, after, centers):
    if len(before) != 3 or len(after) < 3 or any(c is None for c in before + after):
        return False
    colors = np.asarray(before + after, dtype=float)
    centers = np.asarray(centers, dtype=float)
    if colors.shape != (len(before + after), 3) or not np.isfinite(colors).all() or not distinct_team_colors(centers):
        return False
    distances = np.linalg.norm(np.asarray([np.median(before, axis=0), np.median(after, axis=0)])[:, None] - centers, axis=2)
    if np.any(distances[:, 0] == distances[:, 1]):
        return False
    return bool(np.argmin(distances[0]) != np.argmin(distances[1]))


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
