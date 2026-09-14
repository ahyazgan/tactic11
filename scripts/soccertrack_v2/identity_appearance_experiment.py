"""Development-only appearance gating of otherwise unchanged ByteTrack matching.

Temporary method instrumentation is isolated to this experiment process; this is
not a proposed production monkeypatch. Labels always match immutable frame/box.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import deque
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path

import numpy as np

from app.tracking.teams import chromaticity, distinct_team_colors
from scripts.soccertrack_v2.benchmark_track_buffer import box_key, retrack, score_rows

EXPERIMENT_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


@contextmanager
def appearance_context(payload: dict, *, weight: float, rgb_floor: float = 50,
                       tint_floor: float = 12, history: int = 8, direct_output: bool = False):
    """Preserve baseline when weight=0; use only past observations, no label data."""
    from supervision.tracker.byte_tracker import matching
    from supervision.tracker.byte_tracker.core import ByteTrack
    from supervision.tracker.byte_tracker.single_object_track import STrack, TrackState

    old_init, old_update, old_reactivate, old_activate = (
        STrack.__init__, STrack.update, STrack.re_activate, STrack.activate)
    old_iou, old_frame = matching.iou_distance, ByteTrack.update_with_detections
    color_lookup = {}
    detection_lookup = {}
    order = 0
    remaps = []

    def key(box):
        # STrack stores fresh boxes as float32; use the same representation.
        return tuple(np.round(np.asarray(box, dtype=np.float32), 2))

    def frame(self, detections):
        nonlocal color_lookup, detection_lookup, order
        source = payload['detected_persons'][str(payload['samples'][order]['order'])]
        order += 1
        color_lookup = {key(r['box']): r['color'] for r in source}
        detection_lookup = {key(box): i for i, box in enumerate(detections.xyxy)}
        if direct_output:
            tracks = self.update_with_tensors(np.hstack((detections.xyxy, detections.confidence[:, None])))
            ids = np.full(len(detections), -1, dtype=int)
            for track in tracks:
                index = track.accepted_detection_index
                if index is None or index < 0 or ids[index] != -1:
                    raise ValueError('ambiguous accepted detection')
                ids[index] = track.external_track_id
            detections.tracker_id = ids
            return detections.select(ids != -1)
        result = old_frame(self, detections)
        actual = {t.external_track_id: t.accepted_detection_index for t in self.tracked_tracks if t.is_activated}
        for box, tid in zip(result.xyxy, result.tracker_id, strict=True):
            returned = detection_lookup[key(box)]
            if actual[int(tid)] != returned:
                accepted = actual[int(tid)]
                remaps.append({'order': order - 1, 'track': int(tid),
                               'kind': 'remap',
                               'accepted_index': int(accepted), 'returned_index': returned,
                               'accepted_box': detections.xyxy[accepted].tolist(),
                               'returned_box': box.tolist()})
        returned_ids = set(map(int, result.tracker_id))
        for tid, accepted in actual.items():
            if tid not in returned_ids:
                remaps.append({'order': order - 1, 'track': int(tid), 'kind': 'drop',
                               'accepted_index': int(accepted),
                               'accepted_box': detections.xyxy[accepted].tolist()})
        return result

    def init(self, *args, **kwargs):
        old_init(self, *args, **kwargs)
        color = color_lookup.get(key(self.tlbr))
        self.kit_history = deque(maxlen=history)
        self.kit_observation = np.asarray(color, dtype=float) if color is not None else None
        self.accepted_detection_index = detection_lookup.get(key(self.tlbr))

    def remember(self, other=None):
        if other is not None:
            self.accepted_detection_index = other.accepted_detection_index
        color = (other.kit_observation if other is not None else self.kit_observation)
        if color is not None and np.isfinite(color).all():
            self.kit_history.append(color)

    def update(self, other, *args, **kwargs):
        old_update(self, other, *args, **kwargs)
        remember(self, other)

    def reactivate(self, other, *args, **kwargs):
        old_reactivate(self, other, *args, **kwargs)
        remember(self, other)

    def activate(self, *args, **kwargs):
        old_activate(self, *args, **kwargs)
        remember(self)

    def iou(atracks, btracks):
        costs = old_iou(atracks, btracks)
        if weight == 0:
            return costs
        if not atracks or not btracks or not isinstance(atracks[0], STrack):
            return costs
        # Track/track duplicate pruning stays byte-for-byte geometric.
        if any(b.state != TrackState.New for b in btracks):
            return costs
        for i, a in enumerate(atracks):
            if len(a.kit_history) < 3:
                continue
            past = np.asarray(a.kit_history)
            median = np.median(past, axis=0)
            rgb_spread = np.median(np.linalg.norm(past - median, axis=1))
            tint = chromaticity(median)
            tint_spread = np.median(np.linalg.norm(chromaticity(past) - tint, axis=1))
            for j, b in enumerate(btracks):
                color = b.kit_observation
                if color is None or costs[i, j] >= 1:
                    continue
                rgb = np.linalg.norm(color - median) / max(rgb_floor, rgb_spread * 3)
                hue = np.linalg.norm(chromaticity(color) - tint) / max(tint_floor, tint_spread * 3)
                # Need both a substantial RGB change and a tint change. Pure
                # shade/illumination changes cannot produce a color penalty.
                disagreement = max(0.0, min(rgb, hue) - 1)
                costs[i, j] = min(1.0, costs[i, j] + weight * min(disagreement, 1))
        return costs

    try:
        ByteTrack.update_with_detections = frame
        STrack.__init__, STrack.update, STrack.re_activate, STrack.activate = init, update, reactivate, activate
        matching.iou_distance = iou
        yield remaps
    finally:
        ByteTrack.update_with_detections = old_frame
        STrack.__init__, STrack.update, STrack.re_activate, STrack.activate = old_init, old_update, old_reactivate, old_activate
        matching.iou_distance = old_iou


def evaluate(payloads, rows, variants, export_dir=None):
    result = {}
    for name, params in variants.items():
        predictions, anchor, segments = {}, None, {}
        for seg, payload in sorted(payloads.items()):
            with appearance_context(payload, **params) as remaps:
                samples, teams, stat = retrack(payload, correct_buffer=False)
            if (name == 'baseline' and [[list(p) for p in s.persons] for s in samples]
                    != [s['persons'] for s in payload['samples']]):
                raise ValueError(f'Baseline mismatch {seg}')
            ids = {p[0] for s in samples for p in s.persons}
            assignment = teams.fit(anchor, eligible_tracks=ids)
            if anchor is None and distinct_team_colors(assignment.centers):
                anchor = np.round(assignment.centers, 1)
            for sample in samples:
                for p in sample.persons:
                    key = (seg, box_key(sample.frame_idx, p[1:5]))
                    if key in predictions:
                        raise ValueError('duplicate box')
                    predictions[key] = (p[0], assignment.team_by_track.get(p[0]))
            stat.update(tracks=len(ids), observations=sum(len(s.persons) for s in samples),
                        palette=assignment.centers.tolist(), remaps=remaps)
            if export_dir is not None:
                target = export_dir / name / f'seg_{seg:04d}.json'
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    raise ValueError('Fresh export path required')
                exported = {k: payload[k] for k in ('config', 'calibration')}
                exported.update(samples=[asdict(s) for s in samples], stats=stat,
                                colors={str(t): [c.tolist() for c in cs] for t, cs in teams._obs.items()})
                target.write_text(json.dumps(exported) + '\n', encoding='utf-8')
            segments[str(seg)] = stat
        mapping = [r for r in rows if r['segment'] == 0]
        correct = [score_rows(mapping, predictions, b)['correct'] for b in (0, 1)]
        if correct[0] == correct[1]:
            raise ValueError('Ambiguous mapping')
        blue = int(correct[1] > correct[0])
        result[name] = {'params': params, 'score': score_rows(rows, predictions, blue),
                        'blue_slot': blue, 'segments': segments,
                        'label_predictions': {r['id']: predictions.get((r['segment'], box_key(r['frame_idx'], r['bbox']))) for r in rows}}
        print(name, result[name]['score'], flush=True)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cache', type=Path, required=True)
    p.add_argument('--labels', type=Path, nargs='+', required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--weights', type=float, nargs='+', default=[0, .2, .5, 1])
    p.add_argument('--rgb-floor', type=float, default=50)
    p.add_argument('--tint-floor', type=float, default=12)
    p.add_argument('--direct-output', action='store_true')
    p.add_argument('--nested-filter', action='store_true')
    p.add_argument('--history', type=int, default=8)
    p.add_argument('--export-cache', type=Path)
    args = p.parse_args()
    if args.out.exists():
        p.error('fresh output required')
    rows = [r for path in args.labels for r in json.loads(path.read_text(encoding='utf-8'))['records']]
    paths = [args.cache / f'seg_{s:04d}.json' for s in sorted({r['segment'] for r in rows})]
    payloads = {int(path.stem.split('_')[-1]): json.loads(path.read_text()) for path in paths}
    nested = {}
    if args.nested_filter:
        from scripts.soccertrack_v2.nested_person_experiment import nested_keep
        for seg, payload in payloads.items():
            removed = []
            for order, records in payload['detected_persons'].items():
                mask, parents = nested_keep(np.asarray([r['box'] for r in records]).reshape(-1, 4))
                removed.extend({'order': int(order), 'box': records[i]['box'],
                                'parent_box': records[parents[i]]['box']} for i in parents)
                payload['detected_persons'][order] = [r for r, keep in zip(records, mask, strict=True) if keep]
            nested[str(seg)] = removed
    variants = {('baseline' if weight == 0 and not args.direct_output and not args.nested_filter else f'appearance_{weight}'): {
        'weight': weight, 'rgb_floor': args.rgb_floor, 'tint_floor': args.tint_floor,
        'direct_output': args.direct_output, 'history': args.history} for weight in args.weights}
    results = evaluate(payloads, rows, variants, args.export_cache)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({'results': results, 'nested_removed': nested,
        'inputs_sha256': {path.as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths + args.labels},
        'experiment_sha256': EXPERIMENT_SHA256,
        'scope': 'Development only. Color consistency is not true player identity ground truth.'}, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
