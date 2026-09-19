"""Optional identity partitions supported by independent appearance and motion.

ByteTrack retains ownership of source observations and team evidence. A shadow
Deep OC-SORT/OSNet stream only corroborates persistent color discontinuities.
This never joins people, deletes detections, or refits teams after a split.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from typing import TYPE_CHECKING, Any

import numpy as np

from app.tracking.identity_split import appearance_phases
from app.tracking.person_filter import filter_person_tracks
from app.tracking.teams import TeamAssigner, TeamAssignment

if TYPE_CHECKING:
    from app.tracking.calibration import PitchCalibration
    from app.tracking.pipeline import PipelineConfig, SampledObservation

PROFILE = "bytetrack-osnet-color-consensus-v1"


class ConsensusTracker:
    def __init__(self, primary: Any, secondary: Any):
        self.primary = primary
        self.secondary = secondary
        self.max_time_lost = primary.max_time_lost
        self.last_secondary: Any = None

    def reset(self) -> None:
        self.primary.reset()
        self.secondary.reset()
        self.last_secondary = None

    def update_with_detections(self, detections: Any, bgr: np.ndarray) -> Any:
        # Independent copies prevent either implementation changing the other's
        # input rows or metadata. The returned primary result is not rematched.
        indices = np.arange(len(detections))
        self.last_secondary = self.secondary.update_with_detections(detections[indices], bgr)
        return self.primary.update_with_detections(detections[indices])


class ConsensusTeamAssigner(TeamAssigner):
    def __init__(self) -> None:
        super().__init__()
        self._current_colors: dict[int, np.ndarray | None] = {}
        self._colors: dict[tuple[int, int, int], np.ndarray | None] = {}
        self._secondary_samples: list[SampledObservation] = []

    def observe(self, track_id: int, color: np.ndarray | None) -> None:
        super().observe(track_id, color)
        self._current_colors[track_id] = None if color is None else np.asarray(color).copy()

    def record_frame(self, sample: SampledObservation, secondary: Any) -> None:
        from app.tracking.pipeline import SampledObservation

        for person in sample.persons:
            self._colors[sample.continuity_id, sample.order, person[0]] = self._current_colors.get(person[0])
        people = [(int(tid), float(box[0]), float(box[1]), float(box[2]), float(box[3]), float(conf))
                  for tid, box, conf in zip(secondary.tracker_id, secondary.xyxy, secondary.confidence, strict=True)]
        self._secondary_samples.append(SampledObservation(sample.order, sample.frame_idx, sample.seconds,
            people, None, continuity_id=sample.continuity_id))
        self._current_colors.clear()

    def refine(self, samples: list[SampledObservation], assignment: TeamAssignment,
               calib: PitchCalibration, cfg: PipelineConfig, fps: float) -> tuple[TeamAssignment, dict[str, Any]]:
        from app.tracking.pipeline import person_filter_enabled

        secondary = deepcopy(self._secondary_samples)
        hits = Counter((s.continuity_id, p[0]) for s in secondary for p in s.persons)
        minimum = max(1, round(cfg.min_track_seconds * fps))
        for sample in secondary:
            sample.persons = [p for p in sample.persons if hits[sample.continuity_id, p[0]] >= minimum]
        filter_person_tracks(secondary, calib, enabled=person_filter_enabled(cfg, calib))
        support: dict[tuple[int, int, tuple[float, ...]], int | None] = {}
        primary_counts = Counter((s.continuity_id, s.order, tuple(p[1:5])) for s in samples for p in s.persons)
        for sample in secondary:
            for person in sample.persons:
                source_key = (sample.continuity_id, sample.order, tuple(person[1:5]))
                # Identical boxes cannot establish which original detection
                # belongs to which stream. Withhold ambiguous support.
                support[source_key] = person[0] if source_key not in support and primary_counts[source_key] == 1 else None
        grouped: dict[tuple[int, int], list[tuple[SampledObservation, int, np.ndarray | None, int | None]]] = defaultdict(list)
        for sample in samples:
            for index, person in enumerate(sample.persons):
                key = (sample.continuity_id, sample.order, person[0])
                grouped[sample.continuity_id, person[0]].append((sample, index, self._colors[key],
                    support.get((sample.continuity_id, sample.order, tuple(person[1:5])))))
        next_id = max((p[0] for s in samples for p in s.persons), default=0) + 1
        mapping = dict(assignment.team_by_track)
        audit = []
        for sample in samples:
            sample.person_teams = {}
        for (continuity_id, original_id), observations in grouped.items():
            _, boundaries = appearance_phases([r[2] for r in observations],
                seconds=[r[0].seconds for r in observations], max_gap_seconds=1.5 / fps)
            accepted = {}
            for boundary in boundaries:
                start, end = boundary.first_index, boundary.confirmed_index
                before = [r[3] for r in observations[max(0, start - 3):start]]
                after = [r[3] for r in observations[start:end + 1]]
                if (len(before) == 3 and len(after) >= 3 and None not in before + after
                        and len(set(before)) == len(set(after)) == 1 and before[0] != after[0]):
                    accepted[start] = next_id
                    mapping[next_id] = assignment.team_by_track.get(original_id)
                    audit.append(dict(continuity_id=continuity_id, raw_id=original_id, new_id=next_id,
                        first_order=observations[start][0].order, confirmed_order=observations[end][0].order,
                        prior_motion_id=before[0], new_motion_id=after[0]))
                    next_id += 1
            identity = original_id
            for position, (sample, index, _, _) in enumerate(observations):
                identity = accepted.get(position, identity)
                person = sample.persons[index]
                sample.persons[index] = (identity, *person[1:])
                assert sample.person_teams is not None
                sample.person_teams[str(identity)] = mapping.get(identity)
        used = {p[0] for s in samples for p in s.persons}
        mapping = {tid: mapping.get(tid) for tid in used}
        final = TeamAssignment(mapping, assignment.centers,
                               frozenset(t for t, team in mapping.items() if team is None), assignment.note)
        return final, dict(profile=PROFILE, boundaries=audit, boxes_removed=0, boxes_created=0,
            observation_teams_preserved=True, support_is_ground_truth=False,
            confirmation="Retrospective within each segment; three color observations and stable distinct support IDs")
