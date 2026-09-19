"""Development: richer appearance confirmation only around full-body overlap."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from copy import deepcopy
from pathlib import Path

import numpy as np

from app.tracking.identity_split import appearance_phases
from app.tracking.teams import TeamAssigner, chromaticity, distinct_team_colors
from scripts.soccertrack_v2.benchmark_track_buffer import box_key, score_rows
from scripts.soccertrack_v2.identity_eval_pairs import evaluate as evaluate_pairs


def cue_split(data, features):
    data = deepcopy(data)
    feature_map = {(s['frame_idx'], tuple(p['box'])): p['features']
                   for s in features['samples'] for p in s['persons']}
    obs = defaultdict(list)
    for sample in data['samples']:
        rows = sample['persons']
        boxes = np.asarray([p[1:5] for p in rows], dtype=float).reshape(-1, 4)
        sizes = boxes[:, 2:] - boxes[:, :2]
        areas = sizes.prod(axis=1)
        for i, person in enumerate(rows):
            overlap = False
            for j in range(len(rows)):
                if i == j or min(sizes[i, 1], sizes[j, 1]) < max(sizes[i, 1], sizes[j, 1]) * .55:
                    continue
                intersection = np.maximum(np.minimum(boxes[i, 2:], boxes[j, 2:])
                                          - np.maximum(boxes[i, :2], boxes[j, :2]), 0).prod()
                if intersection / max(min(areas[i], areas[j]), 1) >= .25:
                    overlap = True
                    break
            color = feature_map[sample['frame_idx'], tuple(person[1:5])]
            obs[person[0]].append((sample, i, color, overlap))
    next_id = max(obs, default=0) + 1
    audit = []
    for tid, records in obs.items():
        raw_colors = [np.asarray(r[2]['torso_0.4']) for r in records]
        alternate = [np.asarray(r[2]['torso_bright_saturated']) for r in records]
        _, confirmed_boundaries = appearance_phases(
            raw_colors, auxiliary_colors=alternate,
            collision_mask=[r[3] for r in records],
            seconds=[r[0]['seconds'] for r in records],
            max_gap_seconds=.12,
        )
        boundaries = {b.first_index: b.source for b in confirmed_boundaries}
        for boundary in confirmed_boundaries:
            if boundary.source != 'collision_appearance':
                continue
            first, confirmed = boundary.first_index, boundary.confirmed_index
            seconds = records[first][0]['seconds']
            prior = np.median(raw_colors[max(0, first - 32):first], axis=0)
            current = np.median(raw_colors[first:confirmed + 1], axis=0)
            rgb_distance = np.linalg.norm(current - prior)
            tint_distance = np.linalg.norm(chromaticity(current) - chromaticity(prior))
            audit.append({'raw_track': tid, 'first_frame': records[first][0]['frame_idx'],
                          'seconds': seconds, 'confirmed_frame': records[confirmed][0]['frame_idx'],
                          'rgb_distance': float(rgb_distance), 'tint_distance': float(tint_distance)})
        current_id = tid
        for index, (sample, row, _color, _overlap) in enumerate(records):
            if index in boundaries:
                current_id = next_id
                next_id += 1
            sample['persons'][row][0] = current_id
    teams = TeamAssigner()
    for sample in data['samples']:
        for person in sample['persons']:
            color = feature_map[sample['frame_idx'], tuple(person[1:5])]['torso_0.4']
            teams.observe(person[0], np.asarray(color))
    data['colors'] = {str(t): [c.tolist() for c in cs] for t, cs in teams._obs.items()}
    data['collision_cue_boundaries'] = audit
    return data, teams


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cache', type=Path, required=True, help='deduplicated retrack baseline')
    p.add_argument('--site', choices=['day', 'night'], required=True)
    p.add_argument('--labels', type=Path, nargs='+', required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--export-cache', type=Path, required=True)
    p.add_argument('--pair-labels', type=Path)
    args = p.parse_args()
    if args.out.exists() or args.export_cache.exists():
        p.error('Fresh output paths required')
    rows = [r for path in args.labels for r in json.loads(path.read_text(encoding='utf-8'))['records']]
    predictions, payloads, anchor = {}, {}, None
    for seg in sorted({r['segment'] for r in rows}):
        data = json.loads((args.cache / f'seg_{seg:04d}.json').read_text())
        features = json.loads(Path(f'.cache/kit_joint_agent/raw_features_{args.site}_{seg:04d}.json').read_text())
        data, teams = cue_split(data, features)
        tracks = {p[0] for s in data['samples'] for p in s['persons']}
        assignment = teams.fit(anchor, eligible_tracks=tracks)
        if anchor is None and distinct_team_colors(assignment.centers):
            anchor = np.round(assignment.centers, 1)
        for sample in data['samples']:
            for person in sample['persons']:
                predictions[seg, box_key(sample['frame_idx'], person[1:5])] = (person[0], assignment.team_by_track.get(person[0]))
        payloads[seg] = data
        args.export_cache.mkdir(parents=True, exist_ok=True)
        (args.export_cache / f'seg_{seg:04d}.json').write_text(json.dumps(data) + '\n', encoding='utf-8')
    mapping = [r for r in rows if r['segment'] == 0]
    correct = [score_rows(mapping, predictions, blue)['correct'] for blue in (0, 1)]
    blue = int(correct[1] > correct[0])
    report = {'score': score_rows(rows, predictions, blue), 'blue_slot': blue,
              'collision_cue_boundaries': {str(seg): d['collision_cue_boundaries'] for seg, d in payloads.items()},
              'experiment_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    if args.pair_labels:
        report['identity'] = evaluate_pairs(json.loads(args.pair_labels.read_text()), payloads)
    args.out.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k not in ('identity', 'collision_cue_boundaries')}, indent=2))
    if 'identity' in report:
        print(report['identity']['counts'])
    print('collision cue boundaries', {seg: len(d['collision_cue_boundaries']) for seg, d in payloads.items()})


if __name__ == '__main__':
    main()
