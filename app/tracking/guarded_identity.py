"""Retrospective segment recovery with independent baseline and ReID evidence.

The detector runs once. Three separate trackers consume copies of the same
source rows. Baseline kit fitting happens before any recovery or partitions.
Without a prior fixed palette, the first segment only establishes that palette.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, replace
from typing import TYPE_CHECKING, Any

import numpy as np

from app.tracking.guarded_partition import partition
from app.tracking.person_filter import filter_person_tracks
from app.tracking.short_gap_motion import ShortGapMotionTracker
from app.tracking.teams import TeamAssigner, TeamAssignment, distinct_team_colors, kit_color

if TYPE_CHECKING:
    from app.tracking.calibration import PitchCalibration
    from app.tracking.pipeline import PipelineConfig, SampledObservation

PROFILE = "bytetrack-osnet-guarded-identity-v2"


class GuardedTracker:
    def __init__(self, baseline: Any, recovery: Any, secondary: Any):
        self.baseline = baseline
        self.recovery = ShortGapMotionTracker(recovery)
        self.secondary = secondary
        self.max_time_lost = baseline.max_time_lost
        self.recovery_offset = 0
        self.recovery_highest = 0
        self.last_recovery: Any = None
        self.last_secondary: Any = None
        self.last_source: list[dict[str, Any]] = []
        self.last_motion: list[dict[str, Any]] = []

    def reset(self) -> None:
        self.baseline.reset()
        self.recovery.reset()
        self.secondary.reset()
        self.recovery_offset = self.recovery_highest
        self.last_recovery = self.last_secondary = None
        self.last_source = []
        self.last_motion = []

    def update_with_detections(self, detections: Any, bgr: np.ndarray) -> Any:
        rgb = np.ascontiguousarray(bgr[:, :, ::-1])
        colors = [kit_color(rgb, tuple(box), normalize_light=False) for box in detections.xyxy]
        self.last_source = [dict(box=box.tolist(), confidence=float(confidence),
                                 color=None if color is None else color.tolist())
            for box, confidence, color in zip(detections.xyxy, detections.confidence, colors, strict=True)]
        indices = np.arange(len(detections))
        before = len(self.recovery.events)
        self.last_recovery = self.recovery.update_with_detections(detections[indices], colors)
        self.recovery_highest = max(self.recovery_highest,
            max((int(t) + self.recovery_offset for t in self.last_recovery.tracker_id), default=0))
        self.last_motion = self.recovery.events[before:]
        self.last_secondary = self.secondary.update_with_detections(detections[indices], bgr)
        return self.baseline.update_with_detections(detections[indices])


def _people(detections: Any, offset: int = 0) -> list:
    return [(int(identity) + offset, *map(float, box), float(confidence))
        for identity, box, confidence in zip(detections.tracker_id, detections.xyxy,
                                             detections.confidence, strict=True)]


class GuardedTeamAssigner(TeamAssigner):
    def __init__(self) -> None:
        super().__init__()
        self._raw_samples: list[dict[str, Any]] = []
        self._detected: dict[str, Any] = {}
        self._recovery_samples: list[SampledObservation] = []
        self._secondary_samples: list[SampledObservation] = []
        self._motion: list[dict[str, Any]] = []

    def record_frame(self, sample: SampledObservation, tracker: GuardedTracker) -> None:
        self._raw_samples.append(dict(order=sample.order, frame_idx=sample.frame_idx,
                                      seconds=sample.seconds, continuity_id=sample.continuity_id))
        self._detected[str(sample.order)] = tracker.last_source
        self._recovery_samples.append(replace(sample, persons=_people(
            tracker.last_recovery, tracker.recovery_offset), person_teams={}))
        self._secondary_samples.append(replace(sample, persons=_people(
            tracker.last_secondary), person_teams={}))
        self._motion.extend({**event, "tracker_order": event["order"], "order": sample.order,
            "continuity_id": sample.continuity_id,
            "track_id": event["track_id"] + tracker.recovery_offset} for event in tracker.last_motion)

    def refine(self, samples: list[SampledObservation], assignment: TeamAssignment,
               calib: PitchCalibration, cfg: PipelineConfig, fps: float,
               anchors: np.ndarray | None) -> tuple[TeamAssignment, dict[str, Any]]:
        from app.tracking.pipeline import person_filter_enabled

        stats: dict[str, Any] = dict(profile=PROFILE, boundaries=[], motion_proposals=self._motion,
            motion_proposals_applied=0, boxes_removed=0, boxes_created=0,
            observation_teams_preserved=True, support_is_ground_truth=False,
            confirmation="Retrospective within the completed segment; no cross-segment person identity")
        if anchors is None:
            stats["status"] = "baseline_warmup_missing_fixed_palette"
            return assignment, stats
        if not distinct_team_colors(anchors) or np.any((anchors < 0) | (anchors > 255)):
            raise ValueError("Guarded identity requires distinct fixed palette anchors")
        # Filter each independent stream exactly as the baseline collection path.
        # Baseline teams are never learned from either of these streams.
        for stream in (self._recovery_samples, self._secondary_samples):
            hits = Counter((s.continuity_id, p[0]) for s in stream for p in s.persons)
            minimum = max(1, round(cfg.min_track_seconds * fps))
            for sample in stream:
                sample.persons = [p for p in sample.persons if hits[sample.continuity_id, p[0]] >= minimum]
            filter_person_tracks(stream, calib, enabled=person_filter_enabled(cfg, calib))
        baseline = dict(samples=[asdict(s) for s in samples])
        for baseline_sample in baseline["samples"]:
            baseline_sample["person_teams"] = {str(p[0]): assignment.team_by_track.get(p[0]) for p in baseline_sample["persons"]}
        raw = dict(samples=self._raw_samples, detected_persons=self._detected,
                   config=dict(lost_track_seconds=cfg.lost_track_seconds),
                   stats=dict(effective_track_fps=fps))
        output, audit = partition(raw,
            dict(samples=[asdict(s) for s in self._recovery_samples]),
            dict(samples=[asdict(s) for s in self._secondary_samples]), baseline, anchors,
            baseline_centers=assignment.centers)
        teams_by_identity: dict[int, set[int | None]] = defaultdict(set)
        for sample, result in zip(samples, output["samples"], strict=True):
            sample.persons = [tuple(row) for row in result["persons"]]
            sample.person_teams = result["person_teams"]
            for person in sample.persons:
                teams_by_identity[person[0]].add(result["person_teams"][str(person[0])])
        # Per-observation teams are authoritative. A mixed track has no global
        # team label; build_frames and preview both read the observation value.
        mapping = {identity: next(iter(teams)) if len(teams) == 1 else None
                   for identity, teams in teams_by_identity.items()}
        final = TeamAssignment(mapping, assignment.centers,
                               frozenset(t for t, team in mapping.items() if team is None), assignment.note)
        fallback = output.get("recovery_fallback")
        stats.update(status="applied", boundaries=audit, recovery_fallback=fallback,
            motion_proposals_applied=0 if fallback else sum(e["matched"] for e in self._motion),
            boxes_created=sum(len(s.persons) for s in samples) - sum(len(s["persons"]) for s in baseline["samples"]))
        return final, stats
