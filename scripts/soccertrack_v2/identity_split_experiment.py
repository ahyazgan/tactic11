"""Development-only persistent incompatible-kit identity segmentation.

No box is removed; no identity is joined. Confirmed contradiction splits at its
first observation so a late track handoff cannot recolor the earlier player.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict, deque
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path

import numpy as np

from app.tracking.teams import TeamAssigner, chromaticity, distinct_team_colors
from scripts.soccertrack_v2.benchmark_track_buffer import box_key, retrack, score_rows
from scripts.soccertrack_v2.nested_person_experiment import nested_keep

EXPERIMENT_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def split_samples(samples, data, *, rgb_floor=60, tint_floor=15, history=32,
                  consecutive=3, spread_factor=3):
    samples = deepcopy(samples)
    grouped = defaultdict(list)
    next_id = max((p[0] for s in samples for p in s.persons), default=0) + 1
    for sample in samples:
        colors = {tuple(r['box']): r['color'] for r in data['detected_persons'][str(sample.order)]}
        for index, person in enumerate(sample.persons):
            grouped[person[0]].append((sample, index, colors[tuple(person[1:5])]))
    changes = []
    for tid, observations in grouped.items():
        current_id = tid
        past = deque(maxlen=history)
        pending = []
        for sample, index, raw_color in observations:
            person = sample.persons[index]
            sample.persons[index] = (current_id, *person[1:])
            if raw_color is None:
                continue
            color = np.asarray(raw_color, dtype=float)
            incompatible = False
            if len(past) >= 5:
                reference = np.median(past, axis=0)
                rgb_distance = np.linalg.norm(color - reference)
                tint_distance = np.linalg.norm(chromaticity(color) - chromaticity(reference))
                rgb_tolerance = max(rgb_floor, spread_factor * np.median(np.linalg.norm(np.asarray(past) - reference, axis=1)))
                tint_tolerance = max(tint_floor, spread_factor * np.median(np.linalg.norm(chromaticity(past) - chromaticity(reference), axis=1)))
                incompatible = rgb_distance > rgb_tolerance and tint_distance > tint_tolerance
            if incompatible:
                pending.append((sample, index, color))
                if len(pending) >= consecutive:
                    previous_id = current_id
                    current_id = next_id
                    next_id += 1
                    changes.append({'raw_track': tid, 'previous_identity': previous_id,
                                    'identity': current_id, 'frame_idx': pending[0][0].frame_idx,
                                    'seconds': pending[0][0].seconds,
                                    'confirmed_at': sample.seconds,
                                    'prior_color': reference.tolist(),
                                    'new_color': np.median([item[2] for item in pending], axis=0).tolist()})
                    past.clear()
                    for earlier, idx, evidence in pending:
                        earlier.persons[idx] = (current_id, *earlier.persons[idx][1:])
                        past.append(evidence)
                    pending.clear()
            else:
                for _, _, evidence in pending:
                    past.append(evidence)
                pending.clear()
                past.append(color)
    teams = TeamAssigner()
    for sample in samples:
        colors = {tuple(r['box']): r['color'] for r in data['detected_persons'][str(sample.order)]}
        for person in sample.persons:
            color = colors[tuple(person[1:5])]
            teams.observe(person[0], np.asarray(color) if color is not None else None)
    return samples, teams, changes


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cache', type=Path, required=True)
    p.add_argument('--labels', type=Path, nargs='+', required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--export-cache', type=Path)
    p.add_argument('--nested-filter', action='store_true')
    args = p.parse_args()
    if args.out.exists():
        p.error('Fresh output path required')
    rows = [r for path in args.labels for r in json.loads(path.read_text(encoding='utf-8'))['records']]
    paths = [args.cache / f'seg_{s:04d}.json' for s in sorted({r['segment'] for r in rows})]
    payloads = {int(path.stem.split('_')[-1]): json.loads(path.read_text()) for path in paths}
    replayed = {}
    for seg, data in payloads.items():
        if args.nested_filter:
            for order, records in data['detected_persons'].items():
                mask, _ = nested_keep(np.asarray([r['box'] for r in records]).reshape(-1, 4))
                data['detected_persons'][order] = [r for r, keep in zip(records, mask, strict=True) if keep]
        replayed[seg] = retrack(data, correct_buffer=False)
    variants = {'baseline': None, 'split60_15': dict(rgb_floor=60, tint_floor=15),
                'split50_12': dict(rgb_floor=50, tint_floor=12),
                'split70_15': dict(rgb_floor=70, tint_floor=15),
                'split60_15_f2': dict(rgb_floor=60, tint_floor=15, spread_factor=2),
                'split60_12_f2': dict(rgb_floor=60, tint_floor=12, spread_factor=2)}
    results = {}
    for name, params in variants.items():
        predictions, anchor, segments = {}, None, {}
        for seg, data in sorted(payloads.items()):
            baseline_samples, baseline_teams, baseline_stats = replayed[seg]
            samples, teams, changes = ((baseline_samples, baseline_teams, []) if params is None
                                      else split_samples(baseline_samples, data, **params))
            ids = {person[0] for s in samples for person in s.persons}
            assignment = teams.fit(anchor, eligible_tracks=ids)
            if anchor is None and distinct_team_colors(assignment.centers):
                anchor = np.round(assignment.centers, 1)
            for sample in samples:
                for person in sample.persons:
                    predictions[seg, box_key(sample.frame_idx, person[1:5])] = (person[0], assignment.team_by_track.get(person[0]))
            segments[str(seg)] = {'changes': changes, 'tracks': len(ids),
                                  'observations': sum(len(s.persons) for s in samples),
                                  'palette': assignment.centers.tolist()}
            if args.export_cache:
                target = args.export_cache / name / f'seg_{seg:04d}.json'
                if target.exists():
                    raise ValueError('Fresh export required')
                target.parent.mkdir(parents=True, exist_ok=True)
                export = {k: data[k] for k in ('config', 'calibration')}
                export.update(samples=[asdict(s) for s in samples],
                              colors={str(t): [c.tolist() for c in cs] for t, cs in teams._obs.items()},
                              stats=baseline_stats, splits=changes)
                target.write_text(json.dumps(export) + '\n', encoding='utf-8')
        mapping = [r for r in rows if r['segment'] == 0]
        scores = [score_rows(mapping, predictions, blue)['correct'] for blue in (0, 1)]
        blue = int(scores[1] > scores[0])
        results[name] = {'params': params, 'score': score_rows(rows, predictions, blue),
                         'segments': segments, 'blue_slot': blue,
                         'label_predictions': {r['id']: predictions.get((r['segment'], box_key(r['frame_idx'], r['bbox']))) for r in rows}}
        print(name, results[name]['score'], flush=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({'results': results, 'nested_filter': args.nested_filter,
        'experiment_sha256': EXPERIMENT_SHA256,
        'inputs_sha256': {path.as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths + args.labels},
        'scope': 'Development only; accepted boxes unchanged, identity split rather than true identity recovery.'}, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
