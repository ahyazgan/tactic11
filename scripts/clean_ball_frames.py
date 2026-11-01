"""frames JSON klasörüne top düzeltmesi uygula (app.tracking.ball_track), yeni klasöre yaz.

Aday dosyaları (`scripts.track_live_candidates` çıktısı) verilirse top, düşük güvenli
adaylardan kurulan izle değiştirilir; verilmezse yalnız sabit sahte top atılır.

    venv\\Scripts\\python.exe -m scripts.clean_ball_frames --frames data/tracking/live/990701/frames \\
        --out data/tracking/live/990701/frames_ball \\
        [--candidates data/tracking/live/990701/ball_candidates --calibration saha.json]
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from app.tracking.ball_track import BallTrackConfig, clean_ball, refine_segment


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--frames", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--candidates", type=Path, default=None, help="ball_candidates klasörü")
    p.add_argument("--calibration", type=Path, default=None, help="adaylar için saha kalibrasyonu")
    args = p.parse_args()
    if args.out.resolve() == args.frames.resolve():
        p.error("--out kaynak klasörden farklı olmalı")
    if (args.candidates is None) != (args.calibration is None):
        p.error("--candidates ve --calibration birlikte verilir")
    calib = None
    if args.calibration is not None:
        from app.tracking.calibration import PitchCalibration

        calib = PitchCalibration.load(args.calibration)
    args.out.mkdir(parents=True, exist_ok=True)
    cfg = BallTrackConfig()
    total: Counter[str] = Counter()
    for path in sorted(args.frames.glob("seg_*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        cand = args.candidates / path.name if args.candidates is not None else None
        if cand is not None and cand.exists():
            total.update(refine_segment(payload["frames"], json.loads(cand.read_text(encoding="utf-8")),
                                        calib, cfg=cfg))
        else:
            total["no_candidates"] += cand is not None
            total.update(clean_ball(payload["frames"], cfg))
        (args.out / path.name).write_text(json.dumps(payload), encoding="utf-8")
    print(json.dumps(dict(total)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
