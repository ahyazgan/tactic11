"""Canlı telestrasyon işçisi: bekleyen segmentler, hata kaydı, yarım dosya ve canlı mod sayacı."""
import json

from scripts.canli_mac import _telestration_backlog
from scripts.telestrate_live import pending, process, write_json


def _segment(watch, stem: str, frames: str = '{"frames": []}') -> None:
    (watch / "frames").mkdir(parents=True, exist_ok=True)
    (watch / f"{stem}.mp4").write_bytes(b"")
    (watch / "frames" / f"{stem}.json").write_text(frames, encoding="utf-8")


def test_pending_skips_done_errored_and_unfinished(tmp_path) -> None:
    out = tmp_path / "tele"
    out.mkdir()
    for stem in ("seg_0000", "seg_0001", "seg_0002", "seg_0003"):
        _segment(tmp_path, stem)
    (out / "seg_0000.mp4").write_bytes(b"x")                    # bitti
    (out / "seg_0001.error.json").write_text("{}", encoding="utf-8")  # hata kaydı var
    (tmp_path / "seg_0003.mp4").unlink()                         # video henüz yok
    assert [stem for *_, stem in pending(tmp_path, out)] == ["seg_0002"]
    assert _telestration_backlog(tmp_path) == 2                  # 0002 ve 0003 (takibi bitmiş)


def test_failed_segment_is_recorded_and_stream_continues(tmp_path) -> None:
    out = tmp_path / "tele"
    out.mkdir()
    _segment(tmp_path, "seg_0000", json.dumps({"frames": [], "home_team_external_id": 1,
                                               "away_team_external_id": 2}))
    tele = process(tmp_path / "seg_0000.mp4", tmp_path / "frames" / "seg_0000.json", "seg_0000", out,
                   calib=None, tele=None, home_attack=0, width=640, h264=False)  # type: ignore[arg-type]
    assert tele is None
    error = json.loads((out / "seg_0000.error.json").read_text(encoding="utf-8"))
    assert error["segment"] == "seg_0000" and error["error"]
    assert not (out / "seg_0000.mp4").exists() and not (out / "latest.json").exists()
    assert pending(tmp_path, out) == []


def test_half_written_frames_are_retried_not_errored(tmp_path) -> None:
    out = tmp_path / "tele"
    out.mkdir()
    _segment(tmp_path, "seg_0000", '{"frames": [')
    process(tmp_path / "seg_0000.mp4", tmp_path / "frames" / "seg_0000.json", "seg_0000", out,
            calib=None, tele=None, home_attack=0, width=640, h264=False)  # type: ignore[arg-type]
    assert not (out / "seg_0000.error.json").exists()
    assert [stem for *_, stem in pending(tmp_path, out)] == ["seg_0000"]


def test_write_json_replaces_atomically(tmp_path) -> None:
    target = tmp_path / "latest.json"
    write_json(target, {"segment": "seg_0001"})
    write_json(target, {"segment": "seg_0002"})
    assert json.loads(target.read_text(encoding="utf-8")) == {"segment": "seg_0002"}
    assert not list(tmp_path.glob("*.tmp"))
