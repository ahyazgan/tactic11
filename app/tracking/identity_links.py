"""Conservative fixed-camera fragment links with independently checked motion.

Team assignment is an input. Linking never refits the palette, replaces a
per-observation team, or joins identities that were explicitly separated.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from app.tracking.teams import chromaticity

TrackKey = tuple[int, int]


@dataclass(frozen=True)
class LinkObservation:
    track_id: int
    continuity_id: int
    order: int
    seconds: float
    bbox: tuple[float, float, float, float]
    color: np.ndarray | None
    pitch_position: tuple[float, float] | None
    team: int | None = None
    collision: bool = False


@dataclass(frozen=True)
class FragmentLink:
    continuity_id: int
    from_track: int
    to_track: int
    cost: float
    gap_seconds: float
    forward_residual: float
    backward_residual: float


@dataclass(frozen=True)
class LinkResult:
    observation_ids: tuple[int, ...]
    links: tuple[FragmentLink, ...]


@dataclass(frozen=True)
class _Endpoint:
    point: np.ndarray
    pitch: np.ndarray
    velocity: np.ndarray
    color: np.ndarray
    height: float


@dataclass(frozen=True)
class _Node:
    start: float
    end: float
    first: _Endpoint | None
    last: _Endpoint | None


def _point(row: LinkObservation) -> np.ndarray:
    x1, _, x2, y2 = row.bbox
    return np.array([(x1 + x2) / 2, y2], dtype=float)


def _endpoint(rows: Sequence[LinkObservation], *, first: bool) -> _Endpoint | None:
    endpoint = rows[0] if first else rows[-1]
    if endpoint.collision or endpoint.pitch_position is None:
        return None
    pitch = np.asarray(endpoint.pitch_position, dtype=float)
    if pitch.shape != (2,) or not np.isfinite(pitch).all():
        return None
    nearby = ([row for row in rows[:6] if row.seconds - endpoint.seconds <= .5]
              if first else [row for row in rows[-6:] if endpoint.seconds - row.seconds <= .5])
    if len(nearby) < 3:
        return None
    colors = [np.asarray(row.color, dtype=float) for row in nearby if row.color is not None
              and np.asarray(row.color).shape == (3,) and np.isfinite(row.color).all()
              and not np.any(np.asarray(row.color) < 0)]
    if len(colors) < 3:
        return None
    # Median slopes across every pair reduce endpoint jitter without giving an
    # implausible stationary alternative a free pass through the motion gate.
    slopes = [(_point(b) - _point(a)) / (b.seconds - a.seconds)
              for i, a in enumerate(nearby) for b in nearby[i + 1:] if b.seconds > a.seconds]
    if not slopes:
        return None
    return _Endpoint(
        _point(endpoint), pitch, np.median(slopes, axis=0), np.median(colors, axis=0),
        float(np.median([row.bbox[3] - row.bbox[1] for row in nearby])),
    )


def link_identities(
    observations: Sequence[LinkObservation], *, cannot_link: set[tuple[int, int]] | None = None,
    max_gap_seconds: float = 1.6, ambiguity_margin: float = .25,
) -> LinkResult:
    """Return aligned identity IDs after unambiguous bidirectional motion links.

    Both endpoint motion predictions must agree within .75 body heights. Opposed
    endpoint motion, overlap at either endpoint, cross-camera candidates, known
    team conflicts and missing calibrated positions are rejected. Every merge
    also checks all component members for time overlap and split constraints.
    """
    if (not np.isfinite([max_gap_seconds, ambiguity_margin]).all()
            or max_gap_seconds <= 0 or ambiguity_margin < 0):
        raise ValueError("finite positive gap and nonnegative ambiguity margin required")
    grouped: dict[TrackKey, list[LinkObservation]] = defaultdict(list)
    seen = set()
    for row in observations:
        box = np.asarray(row.bbox, dtype=float)
        if (box.shape != (4,) or not np.isfinite(box).all() or np.any(box[2:] <= box[:2])
                or not np.isfinite(row.seconds)):
            raise ValueError("finite time and positive-area box required")
        key = (row.continuity_id, row.track_id)
        observation_key = (*key, row.order)
        if observation_key in seen:
            raise ValueError("duplicate link observation")
        seen.add(observation_key)
        rows = grouped[key]
        if rows and (row.order <= rows[-1].order or row.seconds <= rows[-1].seconds):
            raise ValueError("strictly ordered observations required for each identity")
        rows.append(row)
    nodes = {}
    teams = {key: {row.team for row in rows if row.team is not None} for key, rows in grouped.items()}
    blocked = {frozenset(pair) for pair in (cannot_link or set())}
    for key, rows in grouped.items():
        first, last = _endpoint(rows, first=True), _endpoint(rows, first=False)
        if (first is not None or last is not None) and len(teams[key]) <= 1:
            nodes[key] = _Node(rows[0].seconds, rows[-1].seconds, first, last)
    edges: list[tuple[float, TrackKey, TrackKey, float, float]] = []
    for ka, a in nodes.items():
        for kb, b in nodes.items():
            dt = b.start - a.end
            if ka == kb or ka[0] != kb[0] or not 0 < dt <= max_gap_seconds:
                continue
            if a.last is None or b.first is None:
                continue
            if len(teams[ka] | teams[kb]) > 1 or frozenset((ka[1], kb[1])) in blocked:
                continue
            tint = float(np.linalg.norm(chromaticity(a.last.color) - chromaticity(b.first.color)))
            rgb = float(np.linalg.norm(a.last.color - b.first.color))
            if tint > 18 or rgb > 90:
                continue
            height = (a.last.height + b.first.height) / 2
            ratio = max(a.last.height, b.first.height) / max(1., min(a.last.height, b.first.height))
            if height < 10 or ratio > 2.5:
                continue
            if np.linalg.norm(a.last.pitch - b.first.pitch) > 12 * dt + 1.5:
                continue
            va, vb = a.last.velocity, b.first.velocity
            if min(np.linalg.norm(va), np.linalg.norm(vb)) > .25 * height and np.dot(va, vb) < 0:
                continue
            forward = float(np.linalg.norm(a.last.point + va * dt - b.first.point) / height)
            backward = float(np.linalg.norm(b.first.point - vb * dt - a.last.point) / height)
            if max(forward, backward) > .75:
                continue
            cost = float(max(forward, backward) + .6 * tint / 18
                         + .1 * dt / max_gap_seconds + .1 * abs(np.log(ratio)))
            if cost <= 1.2:
                edges.append((cost, ka, kb, forward, backward))
    outgoing: dict[TrackKey, list] = defaultdict(list)
    incoming: dict[TrackKey, list] = defaultdict(list)
    for edge in sorted(edges):
        outgoing[edge[1]].append(edge)
        incoming[edge[2]].append(edge)
    accepted = []
    for edge in sorted(edges):
        score, left_key, right_key, _, _ = edge
        aa, bb = outgoing[left_key], incoming[right_key]
        if aa[0] != edge or bb[0] != edge:
            continue
        if len(aa) > 1 and aa[1][0] - score < ambiguity_margin:
            continue
        if len(bb) > 1 and bb[1][0] - score < ambiguity_margin:
            continue
        accepted.append(edge)
    parent: dict[TrackKey, TrackKey] = {}
    members = {key: {key} for key in grouped}
    component_teams = {key: set(teams[key]) for key in grouped}

    def representative(key: TrackKey) -> TrackKey:
        while key in parent:
            key = parent[key]
        return key

    kept = []
    for cost, left_key, right_key, forward, backward in sorted(accepted, key=lambda edge: nodes[edge[2]].start):
        ra, rb = representative(left_key), representative(right_key)
        if ra == rb or len(component_teams[ra] | component_teams[rb]) > 1:
            continue
        if any(frozenset((left[1], right[1])) in blocked
               for left in members[ra] for right in members[rb]):
            continue
        if any(max(grouped[left][0].seconds, grouped[right][0].seconds)
               <= min(grouped[left][-1].seconds, grouped[right][-1].seconds)
               for left in members[ra] for right in members[rb]):
            continue
        parent[rb] = ra
        members[ra] |= members[rb]
        component_teams[ra] |= component_teams[rb]
        kept.append(FragmentLink(left_key[0], left_key[1], right_key[1], cost,
                                 nodes[right_key].start - nodes[left_key].end,
                                 forward, backward))
    # Callers normally pass IDs already isolated by the splitter, but preserve
    # that guarantee even if a camera reset reused a raw numeric track ID.
    output_ids: dict[TrackKey, int] = {}
    used_ids: set[int] = set()
    next_id = max((row.track_id for row in observations), default=0) + 1
    for row in observations:
        root = representative((row.continuity_id, row.track_id))
        if root not in output_ids:
            identity = root[1]
            if identity in used_ids:
                identity = next_id
                next_id += 1
            output_ids[root] = identity
            used_ids.add(identity)
    ids = tuple(output_ids[representative((row.continuity_id, row.track_id))] for row in observations)
    return LinkResult(ids, tuple(kept))
