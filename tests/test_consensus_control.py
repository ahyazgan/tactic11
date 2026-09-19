"""Control evidence cannot silently be rewritten or replayed after label edits."""
import pytest

from scripts.soccertrack_v2 import consensus_control as control


@pytest.mark.parametrize("changed", ["code", "input"])
def test_frozen_control_rejects_changed_evidence(tmp_path, monkeypatch, changed):
    code, source, freeze = [tmp_path / n for n in ("code.py", "source.bin", "freeze.json")]
    code.write_text("value = 1\n", encoding="utf-8")
    source.write_bytes(b"original")
    control.write_new(freeze, dict(code_sha256_lf={str(code): control.code_hash(code)},
        input_sha256={str(source): control.digest(source)}))
    monkeypatch.setattr(control, "FREEZE", freeze)
    control.verify()
    (code if changed == "code" else source).write_bytes(b"changed")
    with pytest.raises(ValueError, match="Frozen .* changed"):
        control.verify()


def test_new_evidence_writer_refuses_overwrite(tmp_path):
    path = tmp_path / "proof.json"
    control.write_new(path, {"first": True})
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        control.write_new(path, {"replacement": True})
    assert path.read_bytes() == before


def test_prediction_replay_rejects_edited_sealed_labels(tmp_path, monkeypatch):
    pytest.importorskip("supervision")
    freeze, label = tmp_path / "freeze.json", tmp_path / "labels.json"
    freeze.write_text("{}", encoding="utf-8")
    label.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(control, "ROOT", tmp_path)
    monkeypatch.setattr(control, "FREEZE", freeze)
    control.write_new(tmp_path / "day/label-seal.json", dict(freeze_sha256=control.digest(freeze),
        label_sha256={str(label): control.digest(label)}))
    label.write_text('{"changed":true}', encoding="utf-8")
    with pytest.raises(ValueError, match="Sealed labels changed"):
        control.replay("day", {})
    assert not (tmp_path / "day/predictions").exists()
