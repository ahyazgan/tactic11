"""Canlı telestrasyon işçisi: bekleyen segmentler, hata kaydı, yarım dosya ve canlı mod sayacı."""
import json

from scripts.canli_mac import _telestration_backlog
from scripts.telestrate_live import LiveState, continues, pending, process, write_json


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
    state = LiveState()
    process(tmp_path / "seg_0000.mp4", tmp_path / "frames" / "seg_0000.json", "seg_0000", out,
            calib=None, state=state, home_attack=0, width=640, h264=False)  # type: ignore[arg-type]
    assert state.tele is None
    error = json.loads((out / "seg_0000.error.json").read_text(encoding="utf-8"))
    assert error["segment"] == "seg_0000" and error["error"]
    assert not (out / "seg_0000.mp4").exists() and not (out / "latest.json").exists()
    assert pending(tmp_path, out) == []


def test_half_written_frames_are_retried_not_errored(tmp_path) -> None:
    out = tmp_path / "tele"
    out.mkdir()
    _segment(tmp_path, "seg_0000", '{"frames": [')
    process(tmp_path / "seg_0000.mp4", tmp_path / "frames" / "seg_0000.json", "seg_0000", out,
            calib=None, state=LiveState(), home_attack=0, width=640, h264=False)  # type: ignore[arg-type]
    assert not (out / "seg_0000.error.json").exists()
    assert [stem for *_, stem in pending(tmp_path, out)] == ["seg_0000"]


def test_write_json_replaces_atomically(tmp_path) -> None:
    target = tmp_path / "latest.json"
    write_json(target, {"segment": "seg_0001"})
    write_json(target, {"segment": "seg_0002"})
    assert json.loads(target.read_text(encoding="utf-8")) == {"segment": "seg_0002"}
    assert not list(tmp_path.glob("*.tmp"))


def test_attack_direction_swaps_from_given_minute() -> None:
    from scripts.telestrate_live import segment_attack

    first = {"frames": [{"minute": 44.5}, {"minute": 44.99}]}
    second = {"frames": [{"minute": 45.0}, {"minute": 45.4}]}
    assert segment_attack(first, 1, 45.0) == 1
    assert segment_attack(second, 1, 45.0) == -1
    assert segment_attack(second, 1, None) == 1
    assert segment_attack({"frames": []}, -1, 45.0) == -1


def test_telestrator_attack_change_resets_lines_only() -> None:
    import pytest

    from app.tracking.telestration import Line, Telestrator

    t = Telestrator(fps=5, home_attack_direction=1)
    t._line_state = [Line(30.0, 0.0, 10.0)]
    t.set_home_attack(1)
    assert t._line_state                       # aynı yön: durum korunur
    t.set_home_attack(-1)
    assert t._line_state == [] and t._direction(0) == -1 and t._direction(1) == 1
    with pytest.raises(ValueError):
        t.set_home_attack(2)


def test_continuity_breaks_only_across_skipped_segments() -> None:
    def seg(start: float) -> dict:
        return {"frames": [{"minute": start + i * 0.08 / 60} for i in range(375)]}

    first = seg(10.0)
    end = max(f["minute"] for f in first["frames"])
    assert continues(None, first)
    assert continues(end, seg(10.5))          # ardışık segment: ~0,1 sn boşluk
    assert not continues(end, seg(11.5))      # --keep-up iki segment atladı: ~60 sn
    assert continues(end, {"frames": []})     # boş segment kararı değiştirmez


def test_refined_frames_wait_for_tracking_ingest(tmp_path, monkeypatch) -> None:
    import json as _json
    import subprocess

    from scripts import telestrate_live as tl

    (tmp_path / "frames_ball").mkdir()
    for name in ("seg_0000", "seg_0001"):
        (tmp_path / "frames_ball" / f"{name}.json").write_text("{}", encoding="utf-8")
    (tmp_path / tl.STATE_FILE).write_text(_json.dumps({"processed": ["seg_0000.mp4"]}), encoding="utf-8")
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs["env"].get("DATABASE_URL")))
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(tl.subprocess, "run", fake_run)
    target = tl.IngestTarget("t-default", 990800, "sqlite:///x.db", "py")
    assert tl.ingest_refined(tmp_path, target) == 1          # seg_0001: takip aktarımı bitmedi
    assert calls[0][0][:3] == ["py", "-m", "scripts.ingest_tracking_json"]
    assert calls[0][0][-1] == "--append" and calls[0][1] == "sqlite:///x.db"
    assert (tmp_path / "frames_ball" / "seg_0000.ingested").exists()
    assert tl.ingest_refined(tmp_path, target) == 0          # bir kez gider


def test_failed_refined_ingest_is_retried(tmp_path, monkeypatch) -> None:
    import json as _json
    import subprocess

    from scripts import telestrate_live as tl

    (tmp_path / "frames_ball").mkdir()
    (tmp_path / "frames_ball" / "seg_0000.json").write_text("{}", encoding="utf-8")
    (tmp_path / tl.STATE_FILE).write_text(_json.dumps({"processed": ["seg_0000.mp4"]}), encoding="utf-8")
    monkeypatch.setattr(tl.subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, "", "db yok"))
    assert tl.ingest_refined(tmp_path, tl.IngestTarget("t", 1, None, "py")) == 0
    assert not (tmp_path / "frames_ball" / "seg_0000.ingested").exists()
