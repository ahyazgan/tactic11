"""FM ekran yakalama: kare kurma, sahiplik tutma, saat, ayrıştırma uçtan uca (sentetik kare)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from app.tracking.screen2d import TeamPalette, detect
from scripts.fm_capture import CaptureClock, FrameBuilder, parse_hex, parse_region
from tests.test_screen2d import RED, scene


def test_frame_builder_maps_teams_and_holds_possession() -> None:
    img, truth = scene(ball=(51.5, 31.5))
    det = detect(img, TeamPalette(home_hint=RED))
    assert det is not None
    b = FrameBuilder(match_id=7, home_team=101, away_team=202)
    f = b.build(det, minute=12.5, now=100.0)
    assert f.source == "screen_capture" and f.period == 1 and f.minute == 12.5
    assert f.possession_team_external_id == 101
    assert {p.team_external_id for p in f.players} == {101, 202}
    assert len(f.players) == len(truth)
    no_ball, _ = scene(ball=None)
    det2 = detect(no_ball, TeamPalette(home_hint=RED))
    assert det2 is not None
    assert b.build(det2, 12.6, now=101.5).possession_team_external_id == 101   # tutuluyor
    assert b.build(det2, 12.7, now=103.0).possession_team_external_id is None  # süre doldu
    assert b.build(det2, 50.0, now=200.0).period == 2


def test_clock_and_parsers() -> None:
    c = CaptureClock(start_minute=45, speed=6, started=0.0)
    assert c.minute(30.0) == 48.0
    assert parse_hex("#d22828") == (210.0, 40.0, 40.0)
    assert parse_hex(None) is None
    with pytest.raises(ValueError):
        parse_hex("#fff")
    assert parse_region("0,0,1920,1080") == (0, 0, 1920, 1080)
    assert parse_region(None) is None


def test_image_mode_cli_writes_debug(tmp_path: Path) -> None:
    from PIL import Image

    img, _ = scene()
    src = tmp_path / "fm.png"
    Image.fromarray(img).save(src)
    out = tmp_path / "dbg.png"
    r = subprocess.run([sys.executable, "-m", "scripts.fm_capture", "--image", str(src), "--debug", str(out),
                        "--home-color", "#d22828"], capture_output=True, text=True, check=False,
                       cwd=Path(__file__).resolve().parents[1], encoding="utf-8")
    assert r.returncode == 0, r.stderr
    assert "ev 11 · dep 10" in r.stdout and out.exists()
