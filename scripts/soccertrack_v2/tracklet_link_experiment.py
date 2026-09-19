"""Development adapter for the production conservative fragment linker."""
from __future__ import annotations

from collections import Counter
from copy import deepcopy

import numpy as np

from app.tracking.calibration import PitchCalibration
from app.tracking.identity_links import LinkObservation, link_identities


def link_fragments(payload: dict, *, max_gap: float = 1.6, margin: float = .25,
                   team_by_track: dict | None = None, require_known_team: bool = False) -> tuple[dict, list]:
    data = deepcopy(payload)
    teams = team_by_track or {}
    cal = PitchCalibration.from_dict(data['calibration'])
    counts = Counter(p[0] for sample in data['samples'] for p in sample['persons'])
    indices: Counter = Counter()
    observations = []
    for sample in data['samples']:
        people = sample['persons']
        boxes = np.asarray([p[1:5] for p in people], dtype=float).reshape(-1, 4)
        sizes = boxes[:, 2:] - boxes[:, :2]
        areas = sizes.prod(axis=1)
        for i, person in enumerate(people):
            overlap = False
            for j in range(len(people)):
                if i == j or min(sizes[i, 1], sizes[j, 1]) < max(sizes[i, 1], sizes[j, 1]) * .55:
                    continue
                intersection = np.maximum(np.minimum(boxes[i, 2:], boxes[j, 2:])
                                          - np.maximum(boxes[i, :2], boxes[j, :2]), 0).prod()
                if intersection / max(min(areas[i], areas[j]), 1) >= .25:
                    overlap = True
                    break
            tid = person[0]
            colors = data['colors'].get(str(tid), [])
            # Current development exports explicitly contain a color per row.
            # Never guess alignment for caches that omitted missing colors.
            color = colors[indices[tid]] if len(colors) == counts[tid] else None
            indices[tid] += 1
            if require_known_team and teams.get(tid) is None:
                color = None
            point = ((person[1] + person[3]) / 2, person[4])
            observations.append(LinkObservation(
                tid, sample.get('continuity_id', 0), sample['order'], sample['seconds'],
                tuple(person[1:5]), np.asarray(color) if color is not None else None,
                cal.image_to_pitch_m(*point), teams.get(tid), overlap,
            ))
    cannot_link = {(s['previous_identity'], s['identity']) for s in data.get('splits', [])
                   if 'previous_identity' in s and 'identity' in s}
    result = link_identities(observations, cannot_link=cannot_link,
                             max_gap_seconds=max_gap, ambiguity_margin=margin)
    offset = 0
    merged_teams = {}
    for sample in data['samples']:
        local_teams = {}
        for i, person in enumerate(sample['persons']):
            identity = result.observation_ids[offset]
            offset += 1
            team = teams.get(person[0])
            sample['persons'][i] = [identity, *person[1:]]
            local_teams[str(identity)] = team
            if team is not None or str(identity) not in merged_teams:
                merged_teams[str(identity)] = team
        if len({p[0] for p in sample['persons']}) != len(sample['persons']):
            raise ValueError('link produced overlapping identities')
        sample['person_teams'] = local_teams
    # Retain the pre-link segment observations for provenance, not palette refit.
    data['colors_scope'] = 'prelink_identity_segments'
    data['team_by_track'] = merged_teams
    return data, [{'from': link.from_track, 'to': link.to_track, 'cost': link.cost,
                   'gap_seconds': link.gap_seconds, 'forward_residual': link.forward_residual,
                   'backward_residual': link.backward_residual} for link in result.links]
