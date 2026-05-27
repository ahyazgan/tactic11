"""Sentetik tracking fixture üreteci — bir maç için ~30 frame stream.

Deterministik (sabit seed). 11 ev oyuncu + 11 dep oyuncu + top, 1 dakikalık
örneklem (2 saniyede bir = 30 frame). Top sahanın orta-dış kısımlarında
gezinir; oyuncular plausible 4-3-3'e yakın yerleşimde durup hafifçe oynar.

Kullanım:
    python scripts/generate_tracking_fixture.py
    python scripts/generate_tracking_fixture.py --match 99 --frames 30

Çıktı: tests/fixtures/tracking_<match_id>.json
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

FIXTURE_DIR = _PROJECT_ROOT / "tests" / "fixtures"

# Plausible 4-3-3 base positions on a 0-100 normalized pitch (x: defense→attack).
HOME_FORMATION = [
    (5.0, 50.0),    # GK
    (20.0, 20.0), (20.0, 40.0), (20.0, 60.0), (20.0, 80.0),  # DEF
    (40.0, 30.0), (40.0, 50.0), (40.0, 70.0),                # MID
    (60.0, 25.0), (60.0, 50.0), (60.0, 75.0),                # FW
]
AWAY_FORMATION = [
    (95.0, 50.0),
    (80.0, 20.0), (80.0, 40.0), (80.0, 60.0), (80.0, 80.0),
    (60.0, 30.0), (60.0, 50.0), (60.0, 70.0),
    (40.0, 25.0), (40.0, 50.0), (40.0, 75.0),
]


def _player_ids(team_offset: int) -> list[int]:
    return [team_offset + i for i in range(1, 12)]


def _jitter(rng: random.Random, base: tuple[float, float], amplitude: float = 3.0):
    x = max(0.0, min(100.0, base[0] + rng.uniform(-amplitude, amplitude)))
    y = max(0.0, min(100.0, base[1] + rng.uniform(-amplitude, amplitude)))
    return x, y


def _ball_path(frame_idx: int, total: int) -> tuple[float, float]:
    """Top sahada gezinen bir yörünge: orta saha → hücum üçte birine doğru."""
    progress = frame_idx / max(1, total - 1)
    x = 40.0 + progress * 35.0  # 40 → 75 (orta → hücum)
    y = 50.0 + 15.0 * ((-1.0) ** frame_idx) * progress  # zigzag
    return max(0.0, min(100.0, x)), max(0.0, min(100.0, y))


def generate(match_id: int, frames: int, seed: int, home_id_base: int, away_id_base: int) -> dict:
    rng = random.Random(seed)
    start = datetime(2024, 8, 15, 18, 0, 0, tzinfo=UTC)
    home_ids = _player_ids(home_id_base)
    away_ids = _player_ids(away_id_base)
    out_frames = []
    for i in range(frames):
        ts = start + timedelta(seconds=i * 2)
        bx, by = _ball_path(i, frames)
        players = []
        for pid, base in zip(home_ids, HOME_FORMATION, strict=True):
            x, y = _jitter(rng, base)
            players.append({"player_external_id": pid, "x": round(x, 2), "y": round(y, 2)})
        for pid, base in zip(away_ids, AWAY_FORMATION, strict=True):
            x, y = _jitter(rng, base)
            players.append({"player_external_id": pid, "x": round(x, 2), "y": round(y, 2)})
        out_frames.append({
            "timestamp": ts.isoformat(),
            "period": 1,
            "minute": round(i * 2 / 60.0, 3),
            "ball": {"player_external_id": 0, "x": round(bx, 2), "y": round(by, 2)},
            "players": players,
        })
    return {
        "match_external_id": match_id,
        "sport": "football",
        "frames": out_frames,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Sentetik tracking fixture üreteci")
    parser.add_argument("--match", type=int, default=99)
    parser.add_argument("--frames", type=int, default=30)
    parser.add_argument("--seed", type=int, default=20240815)
    parser.add_argument("--home-base", type=int, default=611000, help="Home player_id offset")
    parser.add_argument("--away-base", type=int, default=607000, help="Away player_id offset")
    args = parser.parse_args()

    data = generate(args.match, args.frames, args.seed, args.home_base, args.away_base)
    out = FIXTURE_DIR / f"tracking_{args.match}.json"
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"yazıldı: {out} ({len(data['frames'])} frame)")


if __name__ == "__main__":
    main()
