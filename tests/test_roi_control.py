"""Dense evidence guards catch errors hidden by rounded/downsampled output frames."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from scripts.soccertrack_v2.roi_control import compare_samples


def sample():
    return {"order": 1, "frame_idx": 2, "seconds": .08, "persons": [[3, 1., 2., 4., 8., .9]],
        "person_teams": {"3": 0}, "continuity_id": 0, "ball": [12., 15., .7], "ball_source": "roi"}


def test_dense_rounding_is_bounded_without_changing_players():
    old = sample()
    new = deepcopy(old)
    new["ball"] = [12.1, 15.1, .701]
    assert compare_samples([old], [new])["passed"]


@pytest.mark.parametrize("changed", ["count", "identity", "team", "presence", "source", "position", "confidence", "nan"])
def test_dense_guard_rejects_hidden_regressions(changed):
    old = sample()
    new = deepcopy(old)
    if changed == "identity":
        new["persons"][0][0] = 4
    elif changed == "team":
        new["person_teams"]["3"] = 1
    elif changed == "presence":
        new["ball"] = None
    elif changed == "source":
        new["ball_source"] = "interp"
    elif changed == "position":
        new["ball"][0] += .251
    elif changed == "confidence":
        new["ball"][2] += .006
    elif changed == "nan":
        new["ball"][0] = float("nan")
    assert not compare_samples([old], [] if changed == "count" else [new])["passed"]


def test_out_of_range_interval_is_rejected_before_control_files(tmp_path, monkeypatch):
    cv2 = pytest.importorskip("cv2")
    from scripts.soccertrack_v2 import roi_control

    monkeypatch.setattr(roi_control, "FREEZE", tmp_path / "freeze.json")
    monkeypatch.setattr(roi_control, "ROOT", tmp_path / "pixels")
    monkeypatch.setattr(roi_control, "GROUPS", {"night": (117092, 2700)})
    monkeypatch.setattr(cv2, "VideoCapture", lambda _: SimpleNamespace(release=lambda: None,
        get=lambda prop: 67375 if prop == cv2.CAP_PROP_FRAME_COUNT else 25))
    with pytest.raises(ValueError, match="fit source metadata"):
        roi_control.freeze()
    assert not roi_control.FREEZE.exists() and not roi_control.ROOT.exists()
