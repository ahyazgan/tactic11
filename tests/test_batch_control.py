"""Frozen batching evidence rejects drift before opening control pixels."""
import platform

import pytest

from scripts.soccertrack_v2 import batch_control as control


@pytest.mark.parametrize("changed", ["code", "input", "runtime", "python"])
def test_control_rejects_frozen_evidence_drift(tmp_path, monkeypatch, changed):
    code, source, freeze = [tmp_path / n for n in ("code.py", "source.bin", "freeze.json")]
    code.write_text("value = 1\n", encoding="utf-8")
    source.write_bytes(b"original")
    monkeypatch.setattr(control, "FREEZE", freeze)
    monkeypatch.setattr(control, "version", lambda name: "fixed")
    control.write_new(freeze, dict(python_version=platform.python_version(),
        runtime_versions=dict.fromkeys(control.PACKAGES, "fixed"),
        code_sha256_lf={str(code): control.code_hash(code)},
        input_sha256={str(source): control.digest(source)}))
    control.verify()
    if changed == "runtime":
        monkeypatch.setattr(control, "version", lambda name: "changed")
    elif changed == "python":
        monkeypatch.setattr(control.platform, "python_version", lambda: "changed")
    else:
        (code if changed == "code" else source).write_bytes(b"changed")
    with pytest.raises(ValueError, match="Frozen .* changed"):
        control.verify()


@pytest.mark.parametrize("existing", ["freeze", "pixels"])
def test_freeze_refuses_existing_control(tmp_path, monkeypatch, existing):
    freeze, root = tmp_path / "freeze.json", tmp_path / "pixels"
    monkeypatch.setattr(control, "FREEZE", freeze)
    monkeypatch.setattr(control, "ROOT", root)
    if existing == "freeze":
        freeze.write_text("{}", encoding="utf-8")
    else:
        root.mkdir()
    with pytest.raises(ValueError, match="before extraction"):
        control.freeze()


def test_run_refuses_existing_group_before_extraction(tmp_path, monkeypatch):
    pytest.importorskip("cv2")
    pytest.importorskip("imageio_ffmpeg")
    monkeypatch.setattr(control, "ROOT", tmp_path)
    (tmp_path / "day").mkdir()
    with pytest.raises(ValueError, match="Fresh group"):
        control.run("day", {"groups": {"day": {}}})
