"""A source-range repair cannot overwrite evidence or follow a model run."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from scripts.soccertrack_v2 import batch_control_replacement as replacement


@pytest.mark.parametrize("invalid", [None, "opened", "frames", "model_run", "in_range"])
def test_replacement_preserves_candidate_and_requires_unopened_night(tmp_path, monkeypatch, invalid):
    cv2 = pytest.importorskip("cv2")
    original = replacement.original
    root = tmp_path / "old"
    empty = root / "night/source.mp4"
    empty.parent.mkdir(parents=True)
    empty.write_bytes(b"empty-container")
    parent, plan, target = [tmp_path / n for n in ("parent.json", "plan.md", "new.json")]
    parent.write_text("{}", encoding="utf-8")
    plan.write_text("Declared replacement", encoding="utf-8")
    frozen = dict(code_sha256_lf={"candidate.py": "unchanged"}, input_sha256={},
        groups={"night": dict(video="full.mp4", start=2600 if invalid == "in_range" else 2700)})
    monkeypatch.setattr(original, "verify", lambda: deepcopy(frozen))
    monkeypatch.setattr(original, "ROOT", root)
    monkeypatch.setattr(original, "FREEZE", parent)
    monkeypatch.setattr(replacement, "FREEZE", target)
    monkeypatch.setattr(replacement, "ROOT", tmp_path / "new")
    monkeypatch.setattr(replacement, "PLAN", plan)
    if invalid == "model_run":
        (empty.parent / "legacy.log").write_text("model started", encoding="utf-8")

    def capture(path):
        full = str(path) == "full.mp4"
        return SimpleNamespace(isOpened=lambda: full or invalid == "opened", release=lambda: None,
            get=lambda prop: (67375 if prop == cv2.CAP_PROP_FRAME_COUNT else 25) if full
                else (1 if invalid == "frames" else -1))

    monkeypatch.setattr(cv2, "VideoCapture", capture)
    if invalid:
        with pytest.raises(ValueError):
            replacement.freeze()
        assert not target.exists()
    else:
        replacement.freeze()
        decision = original.load(target)
        assert decision["code_sha256_lf"]["candidate.py"] == "unchanged"
        assert decision["groups"]["night"]["start"] == 2580
        assert decision["input_sha256"][str(parent)] == original.digest(parent)
        assert decision["input_sha256"][str(empty)] == original.digest(empty)
