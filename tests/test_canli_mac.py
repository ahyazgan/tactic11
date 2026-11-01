"""scripts.canli_mac — canlı maç modu: kaynak sınıflama, ffmpeg komutu, gecikme hesabı.

ffmpeg çalıştırılmaz; komut satırı ve saf hesaplar kilitlenir. Kilit noktalar:
dosya kaynağı gerçek hızda okunur (`-re`), akışta okunmaz; RTSP TCP ile
açılır; H.264 kopya / diğerleri yeniden kodlama; gecikme = akış saati − işlenen.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from scripts.canli_mac import (
    classify_source,
    ffmpeg_segment_command,
    latency,
    resolve_weights,
)


def test_classify_file_and_streams() -> None:
    f = classify_source("C:/mac/kayit.mp4", realtime_file=True)
    assert not f.is_stream and f.realtime and "prova" in f.label
    fast = classify_source("kayit.mp4", realtime_file=False)
    assert not fast.is_stream and not fast.realtime
    for src in ("rtsp://kamera/1", "https://x/y.m3u8", "srt://host:9000", "UDP://1.2.3.4:5000"):
        k = classify_source(src, realtime_file=True)
        assert k.is_stream and not k.realtime, src   # akışta -re olmaz


def test_segment_command_file_realtime_copy(tmp_path: Path) -> None:
    kind = classify_source("mac.mp4", realtime_file=True)
    cmd = ffmpeg_segment_command("ffmpeg", "mac.mp4", kind, tmp_path,
                                 segment_seconds=30.0, start_seconds=90.0)
    assert cmd[0] == "ffmpeg" and "-re" in cmd
    assert cmd[cmd.index("-ss") + 1] == "90.000"
    assert cmd[cmd.index("-c:v") + 1] == "copy" and "-an" in cmd
    assert cmd[cmd.index("-segment_time") + 1] == "30"
    assert cmd[-1].endswith("seg_%04d.mp4") and "-rtsp_transport" not in cmd


def test_segment_command_rtsp_stream(tmp_path: Path) -> None:
    kind = classify_source("rtsp://kamera/stream", realtime_file=True)
    cmd = ffmpeg_segment_command("ffmpeg", "rtsp://kamera/stream", kind, tmp_path,
                                 segment_seconds=10.0)
    assert "-re" not in cmd and "-ss" not in cmd
    assert cmd[cmd.index("-rtsp_transport") + 1] == "tcp"
    assert cmd[cmd.index("-segment_time") + 1] == "10"


def test_segment_command_transcode_and_height(tmp_path: Path) -> None:
    kind = classify_source("mac.webm", realtime_file=False)
    cmd = ffmpeg_segment_command("ffmpeg", "mac.webm", kind, tmp_path,
                                 segment_seconds=30.0, transcode=True, height=1080)
    assert cmd[cmd.index("-c:v") + 1] == "libx264"
    assert cmd[cmd.index("-vf") + 1] == "scale=-2:1080"
    assert any("n_forced*30" in c for c in cmd)      # anahtar kare segment sınırında


def test_latency_realtime_file_uses_wall_clock() -> None:
    # 4 segment işlendi (2 dk), duvar saati 5.5 dk geçti → 3.5 dk = 210 sn geride
    lat = latency(4, 11, segment_seconds=30.0, start_minute=0.0, elapsed_seconds=330.0)
    assert lat.processed_minute == 2.0 and lat.stream_minute == 5.5 and lat.lag_seconds == 210.0


def test_latency_stream_uses_written_segments_and_start_minute() -> None:
    lat = latency(3, 5, segment_seconds=30.0, start_minute=45.0, elapsed_seconds=None)
    assert lat.processed_minute == 46.5 and lat.stream_minute == 47.5 and lat.lag_seconds == 60.0
    # işlenen akışı geçemez (tam yetişme) → 0
    assert latency(5, 5, segment_seconds=30.0, start_minute=0.0, elapsed_seconds=None).lag_seconds == 0.0


def test_latency_freezes_stream_clock_when_source_ended() -> None:
    # kaynak bitti: 12 segment yazıldı (6 dk), 10 işlendi; duvar saati 20 dk geçmiş olsa da
    # akış saati yazılan son segmentte durur → gecikme 60 sn, 9 dk değil
    lat = latency(10, 12, segment_seconds=30.0, start_minute=0.0, elapsed_seconds=1200.0,
                  source_ended=True)
    assert lat.stream_minute == 6.0 and lat.lag_seconds == 60.0


def test_scale_calibration_keeps_pitch_and_validation(tmp_path: Path) -> None:
    import json

    from app.tracking.calibration import PitchCalibration
    from app.tracking.telestration import calibration_validation
    from scripts.canli_mac import scale_calibration

    src = Path("data/tracking/calibrations/teamtrack_soccer_top_D_20220220.json")
    original = PitchCalibration.load(src)
    out = scale_calibration(src, (1920, 1080), tmp_path)
    scaled = PitchCalibration.load(out)
    assert scaled.image_size == (1920, 1080)
    assert [p.pitch for p in scaled.points] == [p.pitch for p in original.points]
    u, v = original.points[2].image
    assert scaled.points[2].image == (u * 1920 / original.image_size[0], v * 1080 / original.image_size[1])
    assert json.loads(out.read_text(encoding="utf-8"))["meta"]["scaled_from"] == list(original.image_size)
    assert calibration_validation(scaled)[0] == calibration_validation(original)[0] == "landmark_loo"
    # aynı nokta iki çözünürlükte aynı saha konumuna düşer
    assert np.allclose(scaled.image_to_pitch_m(u * 0.5, v * 0.5),
                       original.image_to_pitch_m(u * 0.5 * original.image_size[0] / 1920,
                                                 v * 0.5 * original.image_size[1] / 1080), atol=1e-6)
    assert scale_calibration(src, original.image_size, tmp_path) == src


def test_check_database_reports_reachable_and_unreachable(tmp_path: Path) -> None:
    import sys

    from scripts.canli_mac import check_database

    # gerçek ingest ön kontrolü: sqlite dosyası açılır, açılamayan yol tek satırla raporlanır
    # (ağ yok: kapalı porta bağlanma bazı güvenlik duvarlarında yanıtsız kalır)
    assert check_database(sys.executable, f"sqlite:///{(tmp_path / 'ok.db').as_posix()}") is None
    error = check_database(sys.executable, f"sqlite:///{(tmp_path / 'yok' / 'x.db').as_posix()}")
    assert error is not None and error.startswith("OperationalError")
    assert "Background on this error" not in error


def test_check_database_missing_interpreter() -> None:
    from scripts.canli_mac import check_database

    error = check_database("yok/python.exe", None)
    assert error is not None and error.startswith("yorumlayıcı başlatılamadı")


def test_keep_up_choice_waits_then_takes_newest() -> None:
    from scripts.canli_mac import keep_up_choice

    closed = ["seg_0000.mp4", "seg_0001.mp4", "seg_0002.mp4", "seg_0003.mp4"]
    assert keep_up_choice([], [], set()) is None
    assert keep_up_choice(closed[:1], [], set()) == "seg_0000.mp4"
    # takip meşgul: yeni segment alınmaz
    assert keep_up_choice(closed, ["seg_0000.mp4"], set()) is None
    # takip bitti: aradakiler atlanır, en yenisi alınır
    assert keep_up_choice(closed, ["seg_0000.mp4"], {"seg_0000.mp4"}) == "seg_0003.mp4"
    # yeni kapanan yok
    assert keep_up_choice(closed, ["seg_0000.mp4", "seg_0003.mp4"], {"seg_0000.mp4", "seg_0003.mp4"}) is None


def test_keep_up_name_round_trips_through_track_live(tmp_path: Path) -> None:
    from scripts.canli_mac import (
        KEEP_UP_MINUTE_PATTERN,
        closed_segments,
        keep_up_name,
        segment_index,
    )
    from scripts.track_live import _minute_from_name

    name = keep_up_name(7, start_minute=10.0, segment_seconds=30.0)
    assert name == "seg_0007_m13.500.mp4" and segment_index(name) == 7
    assert _minute_from_name(name, KEEP_UP_MINUTE_PATTERN) == 13.5
    for i in range(3):
        (tmp_path / f"seg_{i:04d}.mp4").write_bytes(b"")
    # son dosya ffmpeg tarafından hâlâ yazılıyor; kaynak bitince o da kapanmıştır
    assert closed_segments(tmp_path, source_ended=False) == ["seg_0000.mp4", "seg_0001.mp4"]
    assert len(closed_segments(tmp_path, source_ended=True)) == 3


def test_write_status_is_complete_json(tmp_path: Path) -> None:
    import json

    from scripts.canli_mac import write_status

    lat = latency(3, 5, segment_seconds=30, start_minute=10, elapsed_seconds=None)
    write_status(tmp_path, lat, skipped=2, keep_up=True, source_ended=False)
    data = json.loads((tmp_path / "status.json").read_text(encoding="utf-8"))
    assert data["lag_seconds"] == 60.0 and data["processed_minute"] == 11.5 and data["skipped_segments"] == 2
    assert data["keep_up"] is True and data["updated"].endswith("+00:00")
    assert not (tmp_path / "status.json.tmp").exists()


def test_resolve_weights_v2_only_for_static_camera(tmp_path: Path) -> None:
    model = tmp_path / "v2"
    model.mkdir()
    assert resolve_weights(None, "static", model) is None  # meta.json yok → COCO
    (model / "meta.json").write_text("{}", encoding="utf-8")
    assert resolve_weights(None, "static", model) == str(model)
    for camera in ("auto", "broadcast", "operated"):
        assert resolve_weights(None, camera, model) is None
    assert resolve_weights("x/mixed", "static", model) == "x/mixed"


def test_check_calibration_applies_the_telestration_gate(tmp_path: Path) -> None:
    import json

    from scripts.canli_mac import check_calibration

    corners = [{"image": [100, 50], "pitch": [0, 0]}, {"image": [1150, 50], "pitch": [105, 0]},
               {"image": [1150, 730], "pitch": [105, 68]}, {"image": [100, 730], "pitch": [0, 68]}]
    base = {"image_size": [1300, 800], "pitch_length_m": 105.0, "pitch_width_m": 68.0, "method": "homography",
            "points": corners, "meta": {}}
    four = tmp_path / "four.json"
    four.write_text(json.dumps(base), encoding="utf-8")
    assert "doğrulanmamış" in (check_calibration(four) or "")           # 4 nokta: hata ölçülemez
    verified = tmp_path / "ok.json"
    verified.write_text(json.dumps({**base, "meta": {"line_validation_error_m": 1.4}}), encoding="utf-8")
    assert check_calibration(verified) is None
    loose = tmp_path / "loose.json"
    loose.write_text(json.dumps({**base, "meta": {"line_validation_error_m": 2.7}}), encoding="utf-8")
    assert "2.7 m > 2.0 m" in (check_calibration(loose) or "")
    assert "okunamadı" in (check_calibration(tmp_path / "yok.json") or "")
    assert check_calibration(Path("data/tracking/calibrations/soccertrack_v2_117092_landmarks.json")) is None


def test_service_clock_written_and_refreshed_when_second_half_starts(tmp_path: Path) -> None:
    from datetime import UTC, datetime, timedelta

    from app.data.sources.live_service import ServiceSnapshot
    from app.tracking.match_clock import MatchClock, load_watch_clock
    from scripts.canli_mac import refresh_service_clock, service_clock

    k1 = datetime(2026, 11, 1, 17, 0, tzinfo=UTC)

    def snap(*starts: datetime) -> ServiceSnapshot:
        return ServiceSnapshot("sportmonks", 1, "live", 10, "A", "B", (0, 0), (), None, starts, k1)

    started = k1 + timedelta(minutes=5)
    service_clock(snap(k1), started_at=started, segment_seconds=30, delay_s=40).save(tmp_path / "clock.json")
    clock = load_watch_clock(tmp_path)
    assert isinstance(clock, MatchClock) and clock.delay_s == 40 and clock.stream_started_at == started
    assert not refresh_service_clock(tmp_path, snap(k1))
    k2 = k1 + timedelta(minutes=62)
    assert refresh_service_clock(tmp_path, snap(k1, k2))
    after = load_watch_clock(tmp_path)
    assert after is not None and after.period_starts == (k1, k2) and after.delay_s == 40
