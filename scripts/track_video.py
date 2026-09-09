"""Video → tracking frame JSON (venv-cv işçisi; torch + rfdetr + supervision + opencv).

Kullanım:
    venv-cv\\Scripts\\python.exe -m scripts.track_video \\
        --video clip.mp4 --calibration calib.json --out frames.json \\
        --match-id 990001 --home-team 217 --away-team 213 \\
        --fps 5 --model medium --tiles 2 --preview preview.mp4

Sonra ana ortamda:
    venv\\Scripts\\python.exe -m scripts.ingest_tracking_json --json frames.json --tenant t-default

Kalibrasyon JSON şeması: app/tracking/calibration.py docstring.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from app.tracking.calibration import PitchCalibration
from app.tracking.detect import DetectorConfig
from app.tracking.frames import frames_to_json
from app.tracking.pipeline import PipelineConfig, process_video, video_info


def main() -> int:
    p = argparse.ArgumentParser(description="Video → TrackingFrame JSON (RF-DETR + ByteTrack)")
    p.add_argument("--video", required=True)
    p.add_argument("--calibration", required=True, help="Saha kalibrasyon JSON'u")
    p.add_argument("--out", required=True, help="Çıktı frames JSON")
    p.add_argument("--match-id", type=int, required=True)
    p.add_argument("--home-team", type=int, required=True)
    p.add_argument("--away-team", type=int, required=True)
    p.add_argument("--fps", type=float, default=5.0, help="Çıktı kare hızı (TrackingFrame/sn)")
    p.add_argument("--track-fps", type=float, default=15.0, help="Tespit+takip kare hızı (küçük/hızlı oyuncular için yüksek)")
    p.add_argument("--max-seconds", type=float, default=None)
    p.add_argument("--model", default="medium", choices=["nano", "small", "medium", "base", "large"])
    p.add_argument("--threshold", type=float, default=0.35)
    p.add_argument("--ball-threshold", type=float, default=0.4, help="Top için ayrı güven eşiği")
    p.add_argument("--tiles", type=int, default=1, help="1=tam kare, 2=2×2 dilim (küçük oyuncular için)")
    p.add_argument("--resolution", type=int, default=None)
    p.add_argument("--weights", default=None, help="İnce ayarlı ağırlık klasörü (meta.json + checkpoint_best_total.pth)")
    p.add_argument("--clip-offset-minutes", type=float, default=0.0, help="Klibin maç dakikası başlangıcı")
    p.add_argument("--period", type=int, default=1)
    p.add_argument("--preview", default=None, help="Etiketli önizleme mp4 yolu")
    args = p.parse_args()

    calib = PitchCalibration.load(args.calibration)
    info = video_info(args.video)
    print(f"video: {Path(args.video).name} {info['width']}x{info['height']} @{info['fps']:.2f}fps {info['frames']} kare")
    print(f"kalibrasyon: {len(calib.points)} nokta · geri-izdüşüm hatası ~{calib.reprojection_error_m:.2f} m")

    cfg = PipelineConfig(
        fps_out=args.fps, track_fps=args.track_fps, max_seconds=args.max_seconds,
        detector=DetectorConfig(model=args.model, threshold=args.threshold, tiles=args.tiles, resolution=args.resolution, weights=args.weights),
        clip_offset_minutes=args.clip_offset_minutes, period=args.period,
        preview_path=args.preview, ball_threshold=args.ball_threshold,
    )
    started = time.time()
    frames, summary = process_video(
        args.video, calib, match_id=args.match_id,
        home_team_id=args.home_team, away_team_id=args.away_team, cfg=cfg,
    )
    payload = frames_to_json(frames, match_id=args.match_id, extra={
        "video": Path(args.video).name, "video_info": info,
        "home_team_external_id": args.home_team, "away_team_external_id": args.away_team,
        "config": {"fps": args.fps, "track_fps": args.track_fps, "model": args.model, "tiles": args.tiles, "threshold": args.threshold, "weights": args.weights},
        "summary": summary,
    })
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    summary["elapsed_seconds"] = round(time.time() - started, 1)
    print("\n=== Track Report ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    print(f"  out: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
