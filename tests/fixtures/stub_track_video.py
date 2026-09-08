"""Test işçisi — scripts.track_video yerine: argümanları okur, küçük bir frames JSON yazar."""
import argparse
import json
import sys

p = argparse.ArgumentParser()
for flag in ("--video", "--calibration", "--weights", "--preview"):
    p.add_argument(flag)
for flag in ("--fps", "--track-fps", "--threshold", "--ball-threshold", "--clip-offset-minutes", "--max-seconds"):
    p.add_argument(flag, type=float)
for flag in ("--home-team", "--away-team", "--tiles"):
    p.add_argument(flag, type=int)
p.add_argument("--out", required=True)
p.add_argument("--match-id", type=int, required=True)
a = p.parse_args()

if a.video and a.video.endswith("fail.mp4"):
    print("stub: kasıtlı hata")
    sys.exit(3)

frames = [
    {
        "sport": "football",
        "match_external_id": a.match_id,
        "timestamp": f"2000-01-01T00:00:0{i}+00:00",
        "period": 1,
        "minute": i / 60,
        "ball": {"player_external_id": 0, "x": 50.0, "y": 50.0},
        "players": [{
            "player_external_id": 30001, "x": 40.0, "y": 50.0, "team_external_id": a.home_team,
            "is_actor": True, "is_keeper": False, "identity_estimated": True, "velocity_mps": 3.0,
        }],
        "source": "video_tracking",
        "event_type": "video_sample",
        "visible_area": [[0, 0], [100, 0], [100, 100], [0, 100]],
    }
    for i in range(3)
]
payload = {
    "match_external_id": a.match_id, "source": "video_tracking", "frames": frames,
    "home_team_external_id": a.home_team, "away_team_external_id": a.away_team,
    "video": a.video, "summary": {"frames_written": 3, "tracks": 1},
}
with open(a.out, "w", encoding="utf-8") as f:
    json.dump(payload, f)
print("stub: ok")
