from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from app.tracking.frames import VIDEO_PLAYER_BASE_ID
from app.tracking.identity_namespace import LOCAL_ID_STRIDE
from app.tracking.team_refit import apply_refit, refit_segment, refit_teams

YELLOW, BLUE, PALE_BLUE, RED = (240, 230, 60), (40, 80, 200), (120, 125, 180), (230, 40, 40)


def kits(rows: dict[int, tuple[int, int, int]], n: int = 5) -> dict:
    return {"namespace": 7, "tracks": {str(t): {"median": list(c), "bright": [250, 250, 240], "n": n}
                                       for t, c in rows.items()}}


def test_chroma_split_puts_washed_out_blue_with_blue_and_referee_to_none() -> None:
    k = kits({1: YELLOW, 2: YELLOW, 3: (250, 245, 120), 4: BLUE, 5: BLUE, 6: (90, 120, 210), 7: PALE_BLUE, 8: RED})
    r = refit_teams(k, anchor=None)
    assert r.reason is None
    assert r.team_by_track[1] == r.team_by_track[2] == r.team_by_track[3]      # sarılar bir takım (büyük küme = 0)
    assert r.team_by_track[4] == r.team_by_track[5] == r.team_by_track[6] == r.team_by_track[7]
    assert r.team_by_track[1] != r.team_by_track[4]
    assert r.team_by_track[8] is None                                            # kırmızı kaleci dışarıda


def test_anchor_keeps_team_identity_across_segments() -> None:
    k = kits({1: YELLOW, 2: YELLOW, 3: BLUE, 4: BLUE, 5: BLUE, 6: BLUE, 7: BLUE})
    first = refit_teams(k, anchor=None)                 # çoğunluk (mavi) 0 olur
    assert first.team_by_track[3] == 0
    anchor = np.array([[255 * 240 / 530, 255 * 230 / 530, 255 * 60 / 530], [255 * 40 / 320, 255 * 80 / 320, 255 * 200 / 320]])
    anchored = refit_teams(k, anchor=anchor)             # çapa: sarı = 0
    assert anchored.team_by_track[1] == 0 and anchored.team_by_track[3] == 1
    by_prod = refit_teams(k, anchor=None, production={1: 0, 2: 0, 3: 1, 4: 1, 5: None})  # üretim: sarı = 0
    assert by_prod.team_by_track[1] == 0 and by_prod.team_by_track[7] == 1


def test_single_kit_is_left_unassigned() -> None:
    k = kits({i: (240 - i, 230, 60 + i) for i in range(1, 9)})
    r = refit_teams(k, anchor=None)
    assert r.reason is not None and r.team_by_track == {}


def test_apply_refit_rewrites_by_scoped_track_id(tmp_path: Path) -> None:
    k = kits({1: YELLOW, 2: YELLOW, 3: YELLOW, 4: BLUE, 5: BLUE, 6: (250, 245, 120)})   # sarı çoğunluk → 0
    frames = [{"players": [{"player_external_id": 7 * LOCAL_ID_STRIDE + VIDEO_PLAYER_BASE_ID + t, "team_external_id": 111} for t in (1, 4, 9)]}]
    stats = refit_segment(frames, k, tmp_path / "anchor.json", 111, 222)
    teams = {p["player_external_id"] - 7 * LOCAL_ID_STRIDE - VIDEO_PLAYER_BASE_ID: p["team_external_id"] for p in frames[0]["players"]}
    assert teams[1] == 111 and teams[4] == 222 and teams[9] == 111        # bilinmeyen takip dokunulmaz
    assert frames[0]["players"][1]["team_external_id_tracking"] == 111
    assert stats["changed"] == 1 and stats["players"] == 3
    assert json.loads((tmp_path / "anchor.json").read_text(encoding="utf-8"))[0][2] < 40   # çapa yazıldı (sarı B oranı düşük)
    assert apply_refit(frames, refit_teams(kits({1: YELLOW}), None), 7, 111, 222)["changed"] == 0
