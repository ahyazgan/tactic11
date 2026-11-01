from __future__ import annotations

import json
from pathlib import Path

from scripts.soccertrack_v2.derive_event_mapping import first_half_padding_s
from scripts.soccertrack_v2.evaluate_ball_events import (
    EventMapping,
    load_touches,
    possession_intervals,
)

NODES_HEADER = ("id,match_id,match_full_time,extra_full_time,player_id,back_number,player_name,player_last_name,"
                "team_id,team_name,event_time,event_period,is_side_changed,event_types,filtered_event_types,x,y\n")


def write_nodes(path: Path) -> Path:
    rows = ["1,9,0,0,7,1,a,b,A,ta,1000,FIRST_HALF,False,pass,passSucceeded shortPass,0.25,0.10",
            "2,9,0,0,8,2,a,b,A,ta,2000,FIRST_HALF,False,pass,passReceived,0.30,0.20",
            "3,9,0,0,9,3,a,b,B,tb,3000,FIRST_HALF,False,pass,passReceived,0.25,0.10",
            "4,9,0,0,9,3,a,b,B,tb,9000,SECOND_HALF,False,pass,passReceived,0.5,0.5"]
    path.write_text(NODES_HEADER + "\n".join(rows) + "\n", encoding="utf-8")
    return path


def test_mapping_swaps_axes_flips_per_team_and_offsets_time(tmp_path: Path) -> None:
    m = EventMapping(write_nodes(tmp_path / "n.csv"), {"A": False, "B": True}, 2007.0, {"A": 1, "B": 0})
    touches = load_touches(m)
    assert [round(t.t, 3) for t in touches] == [2008.0, 2009.0, 2010.0]      # ikinci yarı dışarıda
    assert (round(touches[0].x, 2), round(touches[0].y, 2)) == (10.5, 17.0)  # x = olay y · 105
    assert (round(touches[2].x, 2), round(touches[2].y, 2)) == (94.5, 51.0)  # B ters
    assert possession_intervals(touches, m.team_side) == [(2008.0, 2009.0, 1)]


def test_mapping_round_trips_json(tmp_path: Path) -> None:
    path = tmp_path / "m.json"
    path.write_text(json.dumps({"nodes": "x.csv", "flip": {"A": 1}, "video_offset_s": "-0.28",
                                "team_side": {"A": "0"}}), encoding="utf-8")
    m = EventMapping.load(path)
    assert m.flip == {"A": True} and m.video_offset_s == -0.28 and m.team_side == {"A": 0}


def test_first_half_padding(tmp_path: Path) -> None:
    path = tmp_path / "p.csv"
    path.write_text("Event Period,Period Order,Video,Padding,Start Match Time,End Match Time\n"
                    "FIRST_HALF,0,132877,2007000,0,2709000\nSECOND_HALF,1,132877,5663000,2700000,5475000\n",
                    encoding="utf-8")
    assert first_half_padding_s(path) == 2007.0
