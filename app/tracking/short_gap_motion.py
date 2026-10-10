"""Explicit experimental observation-motion recovery for recent ByteTrack IDs.

The underlying assignment thresholds and source detections are unchanged.
Derived from the measured v1 candidate; frozen research code remains separate.
"""

from __future__ import annotations

from collections import defaultdict, deque

import numpy as np

from app.tracking.teams import chromaticity


def _iou(a, b):
    area = np.maximum(np.minimum(a[2:], b[2:]) - np.maximum(a[:2], b[:2]), 0).prod()
    return float(area / max(np.prod(a[2:] - a[:2]) + np.prod(b[2:] - b[:2]) - area, 1e-9))


def valid_color(value):
    """Missing or malformed color must never become affirmative evidence."""
    if value is None:
        return None
    color = np.asarray(value, dtype=float)
    if color.shape != (3,) or not np.isfinite(color).all() or np.any((color < 0) | (color > 255)):
        return None
    return color.copy()


class ShortGapMotionTracker:
    """Keep recent exact-box motion; recover only a unique, color-supported gap."""

    def __init__(self, primary):
        self.primary = primary
        self.max_time_lost = primary.max_time_lost
        self.history = defaultdict(lambda: deque(maxlen=5))
        self.events = []

    def reset(self):
        self.primary.reset()
        self.history.clear()
        self.events.clear()

    def update_with_detections(self, detections, colors):
        if len(colors) != len(detections):
            raise ValueError("One color or explicit None required per source detection")
        if (
            detections.confidence is None
            or not np.isfinite(detections.confidence).all()
            or np.any((detections.confidence < 0) | (detections.confidence > 1))
            or not np.isfinite(detections.xyxy).all()
            or np.any(detections.xyxy[:, 2:] <= detections.xyxy[:, :2])
            or len({tuple(box) for box in detections.xyxy}) != len(detections)
        ):
            raise ValueError("Finite, unique source boxes and confidence required")
        colors = [valid_color(color) for color in colors]
        order = self.primary.frame_id + 1
        edges = []
        pool = self.primary.tracked_tracks + self.primary.lost_tracks
        for track in self.primary.lost_tracks:
            past = list(self.history[track.external_track_id])
            if len(past) < 5 or not 1 < order - past[-1][0] <= min(4, self.max_time_lost):
                continue
            times = np.array([r[0] for r in past], dtype=float)
            boxes = np.array([r[1] for r in past])
            if np.any(np.diff(times) != 1):
                continue
            centers = (boxes[:, :2] + boxes[:, 2:]) / 2
            velocity = np.median(np.diff(centers, axis=0), axis=0)
            heights = boxes[:, 3] - boxes[:, 1]
            height = float(np.median(heights))
            if height < 10 or max(heights) / min(heights) > 1.3:
                continue
            residual = np.linalg.norm(
                centers - (centers[-1] + (times - times[-1])[:, None] * velocity), axis=1
            )
            if max(residual) > 0.2 * height or np.linalg.norm(velocity) > 0.5 * height:
                continue
            if any(r[2] is None for r in past):
                continue
            palette = np.median(np.array([r[2] for r in past]), axis=0)
            shift = np.tile(velocity * (order - times[-1]), 2)
            proposal = boxes[-1] + shift
            original_mean = track.mean.copy()
            original_mean[7] = 0
            predicted_mean, predicted_covariance = self.primary.shared_kalman.predict(
                original_mean, track.covariance
            )
            size = np.array([predicted_mean[2] * predicted_mean[3], predicted_mean[3]])
            original_box = np.r_[predicted_mean[:2] - size / 2, predicted_mean[:2] + size / 2]
            # Do not move a track that already has any legal first-stage edge.
            # Otherwise a second plausible box could steal its normal match.
            if any(
                confidence >= self.primary.track_activation_threshold
                and 1 - _iou(original_box, box) * confidence
                <= self.primary.minimum_matching_threshold
                for box, confidence in zip(detections.xyxy, detections.confidence, strict=True)
            ):
                continue
            for j, box in enumerate(detections.xyxy):
                color = colors[j]
                if color is None or detections.confidence[j] < self.primary.det_thresh:
                    continue
                ratio = (box[3] - box[1]) / height
                if not 0.8 <= ratio <= 1.25 or _iou(proposal, box) < 0.5:
                    continue
                if (
                    np.linalg.norm(chromaticity(palette) - chromaticity(color)) > 12
                    or np.linalg.norm(palette - color) > 60
                ):
                    continue
                # A plausible rival retains ownership. Predictions advance by
                # the same single-frame translation as the underlying filter.
                rivals = []
                for other in pool:
                    if other is track or other.mean is None:
                        continue
                    projected = other.tlbr + np.tile(other.mean[4:6], 2)
                    clearance = np.linalg.norm(
                        (projected[:2] + projected[2:] - box[:2] - box[2:]) / 2
                    )
                    if _iou(projected, box) >= 0.2 or clearance <= 0.75 * max(
                        projected[3] - projected[1], box[3] - box[1]
                    ):
                        rivals.append(other)
                if rivals:
                    continue
                # A color-rejected source box still participates in ByteTrack.
                # Require exactly one legal edge at the actual nudged geometry.
                candidate_box = original_box + np.tile(
                    (proposal[:2] + proposal[2:]) / 2 - predicted_mean[:2], 2
                )
                legal = [
                    index
                    for index, (other_box, confidence) in enumerate(
                        zip(detections.xyxy, detections.confidence, strict=True)
                    )
                    if confidence >= self.primary.track_activation_threshold
                    and 1 - _iou(candidate_box, other_box) * confidence
                    <= self.primary.minimum_matching_threshold
                ]
                if legal != [j]:
                    continue
                edges.append((track, j, velocity, proposal, predicted_mean, predicted_covariance))
        accepted = [
            edge
            for edge in edges
            if sum(e[0] is edge[0] for e in edges) == 1 and sum(e[1] == edge[1] for e in edges) == 1
        ]
        changes = []
        for track, index, velocity, proposal, predicted_mean, predicted_covariance in accepted:
            before = track.mean.copy()
            # The normal Kalman prediction adds velocity once. Leave the
            # covariance, shape and all assignment thresholds untouched.
            track.mean[:2] = (proposal[:2] + proposal[2:]) / 2 - velocity
            track.mean[4:6] = velocity
            changes.append((track, index, before, proposal, predicted_mean, predicted_covariance))
        result = self.primary.update_with_detections(detections)
        for track, index, before, proposal, predicted_mean, predicted_covariance in changes:
            matched = any(
                int(tid) == track.external_track_id and np.array_equal(box, detections.xyxy[index])
                for tid, box in zip(result.tracker_id, result.xyxy, strict=True)
            )
            if not matched and track.frame_id == order:
                raise ValueError("Motion proposal matched an unexpected source box")
            if track.frame_id != order:
                # An unsuccessful proposal must not change future motion.
                track.mean = predicted_mean
                track.covariance = predicted_covariance
            self.events.append(
                dict(
                    order=order - 1,
                    track_id=track.external_track_id,
                    source_index=int(index),
                    proposal=proposal.tolist(),
                    matched=matched,
                    previous_mean=before.tolist(),
                )
            )
        lookup = {tuple(box): color for box, color in zip(detections.xyxy, colors, strict=True)}
        for tid, box in zip(result.tracker_id, result.xyxy, strict=True):
            self.history[int(tid)].append((order, box.copy(), lookup[tuple(box)]))
        active = {
            t.external_track_id for t in self.primary.tracked_tracks + self.primary.lost_tracks
        }
        for tid in self.history.keys() - active:
            del self.history[tid]
        return result
