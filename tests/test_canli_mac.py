"""scripts.canli_mac — canlı maç modu: kaynak sınıflama, ffmpeg komutu, gecikme hesabı.

ffmpeg çalıştırılmaz; komut satırı ve saf hesaplar kilitlenir. Kilit noktalar:
dosya kaynağı gerçek hızda okunur (`-re`), akışta okunmaz; RTSP TCP ile
açılır; H.264 kopya / diğerleri yeniden kodlama; gecikme = akış saati − işlenen.
"""
from __future__ import annotations

from pathlib import Path

from scripts.canli_mac import (
    classify_source,
    ffmpeg_segment_command,
    latency,
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
