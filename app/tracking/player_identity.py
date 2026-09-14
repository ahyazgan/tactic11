"""Fixed-camera identity refinement, shared by recorded and live video workers."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
from typing import TYPE_CHECKING, Any

import numpy as np

from app.tracking.calibration import PitchCalibration
from app.tracking.identity_links import LinkObservation, link_identities
from app.tracking.identity_split import IdentityObservation, split_identities
from app.tracking.kit_evidence import fit_kit_evidence
from app.tracking.person_parts import full_body_contacts
from app.tracking.teams import TeamAssignment

if TYPE_CHECKING:
    from app.tracking.pipeline import SampledObservation


def refine_player_tracks(
    samples: list[SampledObservation], calib: PitchCalibration, *,
    fps_eff: float, anchor: np.ndarray | None = None,
) -> tuple[TeamAssignment, dict[str, Any]]:
    """Split contradictions, fit coherent shirt histories, then link fragments.

    Each source box survives this step. Colours and local unknown assignments
    stay aligned with the box, including after an identity link. Team centres
    are never fitted again on linked fragments. IDs remain anonymous estimates.
    """
    if not np.isfinite(fps_eff) or fps_eff <= 0:
        raise ValueError("positive effective tracking frequency required")
    if any(sample.calibration is not None for sample in samples):
        raise ValueError("identity refinement requires a fixed camera")
    rows = []
    identity_observations = []
    for sample in samples:
        contacts = full_body_contacts(np.array([p[1:5] for p in sample.persons]).reshape(-1, 4))
        for index, (person, contact) in enumerate(zip(sample.persons, contacts, strict=True)):
            values = np.asarray((sample.person_kit or {}).get(str(person[0]), ()), dtype=float)
            valid = values.shape == (9,) and np.isfinite(values).all() and np.all(values >= 0)
            bright, broad, appearance = (tuple(np.split(values, 3)) if valid
                                         else (None, None, None))
            rows.append((sample, index, person, bright, broad, appearance, contact))
            identity_observations.append(IdentityObservation(
                sample.continuity_id, person[0], sample.order, sample.seconds,
                broad, appearance, contact,
            ))
    split = split_identities(identity_observations, max_gap_seconds=1.5 / fps_eff)
    bright_histories: dict[int, list[np.ndarray | None]] = defaultdict(list)
    broad_histories: dict[int, list[np.ndarray | None]] = defaultdict(list)
    for identity, row in zip(split.observation_ids, rows, strict=True):
        bright_histories[identity].append(row[3])
        broad_histories[identity].append(row[4])
    assignment = fit_kit_evidence(bright_histories, broad_histories, anchor,
                                  eligible_tracks=set(split.observation_ids))
    link_observations = []
    for identity, row in zip(split.observation_ids, rows, strict=True):
        sample, _index, person, _bright, broad, _appearance, contact = row
        box = (person[1], person[2], person[3], person[4])
        link_observations.append(LinkObservation(
            track_id=identity, continuity_id=sample.continuity_id,
            order=sample.order, seconds=sample.seconds, bbox=box,
            color=broad, pitch_position=calib.image_to_pitch_m((box[0] + box[2]) / 2, box[3]),
            team=assignment.team_by_track.get(identity), collision=contact,
        ))
    linked = link_identities(link_observations, cannot_link={
        (boundary.previous_identity, boundary.identity) for boundary in split.boundaries})
    team_sets: dict[int, set[int]] = defaultdict(set)
    for sample in samples:
        sample.person_teams = {}
        sample.person_kit = {}
    for previous_id, identity, row in zip(split.observation_ids, linked.observation_ids, rows, strict=True):
        sample, index, person, bright, broad, appearance, _contact = row
        sample.persons[index] = (identity, *person[1:])
        team = assignment.team_by_track.get(previous_id)
        assert sample.person_teams is not None and sample.person_kit is not None
        sample.person_teams[str(identity)] = team
        if bright is not None and broad is not None and appearance is not None:
            sample.person_kit[str(identity)] = tuple(float(v) for v in np.concatenate(
                [bright, broad, appearance]))
        if team is not None:
            team_sets[identity].add(team)
    mapping = {identity: next(iter(team_sets[identity])) if len(team_sets[identity]) == 1 else None
               for identity in linked.observation_ids}
    final = TeamAssignment(mapping, assignment.centers,
                           frozenset(t for t, team in mapping.items() if team is None), assignment.note)
    return final, {
        "method": "fixed_camera_identity_v1", "anonymous_identities": True,
        "raw_tracks": len({(o.continuity_id, o.track_id) for o in identity_observations}),
        "tracklets": len(set(split.observation_ids)), "linked_tracks": len(mapping),
        "splits": [asdict(boundary) for boundary in split.boundaries],
        "links": [asdict(link) for link in linked.links],
        "local_unassigned_observations": sum(team is None for s in samples
                                              for team in (s.person_teams or {}).values()),
    }
