"""Research identity partitions confirmed by palette and independent source tracks.

Unlike a tint discontinuity, a confident palette crossover can distinguish
nearly achromatic night kits. Original per-observation teams remain evidence;
this step never refits them after an identity change.
"""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy

import numpy as np

from app.tracking.teams import distinct_team_colors
from scripts.soccertrack_v2.candidates.short_gap_motion_v1 import valid_color


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


def partition(raw, primary, secondary, baseline, centers):
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
