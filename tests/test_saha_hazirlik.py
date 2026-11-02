"""Saha günü ön kontrolü (scripts.saha_hazirlik) — karar fonksiyonları, ffmpeg/kamera/GPU çağrısı olmadan."""
from __future__ import annotations

from scripts.saha_hazirlik import (
    DISK_RESERVE_GB,
    FAIL,
    OK,
    OUTPUT_GB_PER_HOUR,
    STREAM_GB_PER_HOUR,
    WARN,
    camera_verdict,
    disk_verdict,
    parse_device_modes,
)

X5_LIST_OPTIONS = """
[dshow @ 000001] DirectShow video device options (from video devices)
[dshow @ 000001]  Pin "Capture" (alternative pin name "0")
[dshow @ 000001]   vcodec=mjpeg  min s=1920x1080 fps=30 max s=1920x1080 fps=30
[dshow @ 000001]   vcodec=mjpeg  min s=1920x1080 fps=30 max s=1920x1080 fps=30
[dshow @ 000001]   vcodec=mjpeg  min s=2880x1440 fps=30 max s=2880x1440 fps=30
video=Insta360 X5: Immediate exit requested
"""


def test_disk_verdict_thresholds() -> None:
    need = 2 * (STREAM_GB_PER_HOUR + OUTPUT_GB_PER_HOUR) + DISK_RESERVE_GB
    assert disk_verdict(need + 0.1, 2).status == OK
    assert disk_verdict(need - 1.0, 2).status == WARN          # pay yenmiş ama akış sığar
    assert disk_verdict(need - DISK_RESERVE_GB - 0.1, 2).status == FAIL
    assert "2 saat" in disk_verdict(need, 2).detail


def test_parse_device_modes_dedups_and_types() -> None:
    modes = parse_device_modes(X5_LIST_OPTIONS)
    assert modes == [("mjpeg", 1920, 1080, 30.0), ("mjpeg", 2880, 1440, 30.0)]
    assert parse_device_modes("") == []


def test_camera_verdict() -> None:
    modes = parse_device_modes(X5_LIST_OPTIONS)
    assert camera_verdict("Insta360 X5", [], modes).status == FAIL
    assert camera_verdict("Insta360 X5", ["Insta360 X5"], []).status == WARN
    ok = camera_verdict("Insta360 X5", ["Integrated Camera", "Insta360 X5"], modes)
    assert ok.status == OK and "2880x1440" in ok.detail
    low = camera_verdict("Integrated Camera", ["Integrated Camera"], [("mjpeg", 1280, 720, 30.0)])
    assert low.status == WARN and "1440p altı" in low.detail
