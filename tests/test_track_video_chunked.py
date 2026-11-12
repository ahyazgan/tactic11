"""Parçalı video işleme: bölme planı, parça komutları, birleştirme ve çöken parçanın kaydı."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import track_video_chunked as chunked


def test_short_video_is_not_chunked():
    assert chunked.needs_chunking(400, 300) is False
    assert chunked.needs_chunking(451, 300) is True
    assert chunked.needs_chunking(5000, 0) is False


def test_parse_segment_list_reads_real_boundaries(tmp_path):
    (tmp_path / "s.csv").write_text("seg_0000.mp4,0.000000,301.250000\nseg_0001.mp4,301.250000,598.000000\n",
                                    encoding="utf-8")
    assert chunked.parse_segment_list(tmp_path / "s.csv") == [
        ("seg_0000.mp4", 0.0, 301.25), ("seg_0001.mp4", 301.25, 598.0)]


def test_team_anchor_is_refused_when_colors_were_not_learned():
    assert chunked.usable_team_anchor({"team_colors": [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0]]}) is None
    assert chunked.usable_team_anchor(None) is None
    assert chunked.usable_team_anchor({"team_colors": [[10, 20, 30], [200, 200, 200]]}) == [
        [10, 20, 30], [200, 200, 200]]


def _payload(minute: float, colors=None, calibrated: int = 5) -> dict:
    return {"match_external_id": 1, "source": "video_tracking", "frames": [{"minute": minute}],
            "summary": {"tracks": 2, "team_colors": colors,
                        "calibration_stats": {"frames_calibrated": calibrated, "frames_rejected": 5}}}


class _Runner:
    """track_video yerine: komutu kaydeder, istenen parçada çöker, diğerlerinde çıktı yazar."""

    def __init__(self, fail_index: int | None = None, colors=None):
        self.calls: list[list[str]] = []
        self.fail_index, self.colors = fail_index, colors

    def __call__(self, cmd: list[str]) -> int:
        self.calls.append(cmd)
        index = len(self.calls) - 1
        if index == self.fail_index:
            return 1
        out = Path(cmd[cmd.index("--out") + 1])
        offset = float(cmd[cmd.index("--clip-offset-minutes") + 1])
        out.write_text(json.dumps(_payload(offset, self.colors)), encoding="utf-8")
        return 0


def _segments(tmp_path: Path, n: int = 3) -> list[tuple[str, float, float]]:
    segs = []
    for i in range(n):
        (tmp_path / f"seg_{i:04d}.mp4").write_bytes(b"x")
        segs.append((f"seg_{i:04d}.mp4", i * 300.0, (i + 1) * 300.0))
    return segs


def test_chunks_are_merged_in_order_and_segment_files_removed(tmp_path):
    run = _Runner(colors=[[10, 20, 30], [200, 200, 200]])
    out = tmp_path / "out.json"
    summary = chunked.process_chunks(_segments(tmp_path), tmp_path, ["w"], out=str(out), preview="p.mp4",
                                     max_seconds=None, video="mac.mp4", run=run)
    merged = json.loads(out.read_text(encoding="utf-8"))
    assert [f["minute"] for f in merged["frames"]] == [0.0, 5.0, 10.0]
    assert summary["frames_written"] == 3 and summary["chunks_failed"] == 0 and summary["tracks"] == 6
    assert summary["calibration_stats"] == {"frames_calibrated": 15, "frames_rejected": 15, "calibrated_ratio": 0.5}
    assert not list(tmp_path.glob("seg_*.mp4")) and not list(tmp_path.glob("part_*.json"))
    # Önizleme yalnız ilk parçada; takım çapası ikinci parçadan itibaren taşınır.
    assert "--preview" in run.calls[0] and "--preview" not in run.calls[1]
    assert "--team-anchor-json" not in run.calls[0] and "--team-anchor-json" in run.calls[1]


@pytest.mark.parametrize("start", [304.320667, 603.553, 608.607633, 5399.994933, 0.0004])
def test_frame_time_boundaries_get_an_offset_the_identity_namespace_accepts(start):
    """Gerçek koşuda (iş 0bd6447d5c) 59,94 fps sınırları ikinci parçadan itibaren işçiyi düşürdü."""
    from app.tracking.identity_namespace import segment_namespace

    with pytest.raises(ValueError, match="whole millisecond"):
        segment_namespace(1, 304.320667 / 60.0)
    minutes = chunked.snapped_offset_minutes(start)
    assert segment_namespace(1, float(repr(minutes))) == round(start * 1000)
    assert abs(minutes * 60.0 - start) <= 0.0005


def test_real_boundaries_reach_the_worker_snapped(tmp_path):
    from app.tracking.identity_namespace import segment_namespace

    for i in range(2):
        (tmp_path / f"seg_{i:04d}.mp4").write_bytes(b"x")
    run = _Runner()
    chunked.process_chunks([("seg_0000.mp4", 0.0, 304.320667), ("seg_0001.mp4", 304.320667, 603.553)],
                           tmp_path, ["w"], out=str(tmp_path / "o.json"), preview=None, max_seconds=None,
                           video="mac.mp4", run=run)
    sent = float(run.calls[1][run.calls[1].index("--clip-offset-minutes") + 1])
    assert segment_namespace(1, sent) == 304321


def test_failed_chunk_is_recorded_and_the_rest_survive(tmp_path):
    out = tmp_path / "out.json"
    summary = chunked.process_chunks(_segments(tmp_path), tmp_path, ["w"], out=str(out), preview=None,
                                     max_seconds=None, video="mac.mp4", run=_Runner(fail_index=1))
    assert summary["chunks_failed"] == 1 and summary["frames_written"] == 2
    assert [c["state"] for c in summary["chunks"]] == ["done", "failed", "done"]
    assert summary["chunks"][1]["exit_code"] == 1


def test_all_chunks_failing_is_an_error_not_an_empty_success(tmp_path):
    with pytest.raises(ValueError, match="hiçbir parça"):
        chunked.process_chunks(_segments(tmp_path, 2), tmp_path, ["w"], out=str(tmp_path / "o.json"),
                               preview=None, max_seconds=None, video="mac.mp4", run=lambda cmd: 1)


def test_max_seconds_stops_at_the_right_chunk_and_trims_it(tmp_path):
    run = _Runner()
    chunked.process_chunks(_segments(tmp_path), tmp_path, ["w"], out=str(tmp_path / "o.json"), preview=None,
                           max_seconds=450.0, video="mac.mp4", run=run)
    assert len(run.calls) == 2
    assert "--max-seconds" not in run.calls[0]
    assert run.calls[1][run.calls[1].index("--max-seconds") + 1] == "150.0"
