"""The next control must fit its source before any pixels are opened."""
import pytest

from scripts.soccertrack_v2.consensus_palette_control import SOURCES, validate_control_timing


def test_declared_intervals_fit_the_existing_full_sources():
    for group, count in [("day", 67625), ("night", 67375)]:
        validate_control_timing(25., count, list(SOURCES[group]["segments"].values()))


@pytest.mark.parametrize("fps,count,starts", [
    (25., 67375, [2700]), (25., 67375, [-1]), (25., float("nan"), [2520]),
    (25., 0, [0]), (0., 67375, [2520]), (25., 67375, []), (25., 67375, [float("nan")]),
])
def test_invalid_timing_rejected(fps, count, starts):
    with pytest.raises(ValueError, match="fit source metadata"):
        validate_control_timing(fps, count, starts)


def test_source_guard_ignores_only_identity_and_detects_team_or_box_changes():
    from copy import deepcopy

    from scripts.soccertrack_v2.consensus_palette_control import source_evidence

    sample = {"order": 0, "frame_idx": 0, "seconds": 0., "continuity_id": 0, "ball": None,
              "ball_source": None, "persons": [[1, 2., 3., 4., 5., .8]], "person_teams": {"1": 0}}
    renamed = deepcopy(sample)
    renamed["persons"][0][0] = 2
    renamed["person_teams"] = {"2": 0}
    assert source_evidence([sample]) == source_evidence([renamed])
    renamed["person_teams"]["2"] = 1
    assert source_evidence([sample]) != source_evidence([renamed])
    renamed["person_teams"]["2"] = 0
    renamed["persons"][0][1] += 1.
    assert source_evidence([sample]) != source_evidence([renamed])


@pytest.mark.parametrize("existing", ["freeze", "pixels"])
def test_freeze_refuses_existing_decision_or_pixels(tmp_path, monkeypatch, existing):
    from scripts.soccertrack_v2 import consensus_palette_control as control

    monkeypatch.setattr(control, "FREEZE", tmp_path / "freeze.json")
    monkeypatch.setattr(control, "ROOT", tmp_path / "pixels")
    if existing == "freeze":
        control.FREEZE.write_text("{}")
    else:
        control.ROOT.mkdir()
    with pytest.raises(ValueError, match="before extraction"):
        control.freeze()
