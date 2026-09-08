"""Videodan tek kare (JPEG) çıkar — kalibrasyon arayüzü için (venv-cv, cv2).

    python -m scripts.extract_frame --video clip.mp4 --t 2.0 --out frame.jpg [--width 1920]

Çıktı JSON (stdout): {"width": W, "height": H, "src_width": .., "src_height": .., "t": ..}
"""
from __future__ import annotations

import argparse
import json
import sys


def main() -> int:
    import cv2

    p = argparse.ArgumentParser()
    p.add_argument("--video", required=True)
    p.add_argument("--t", type=float, default=1.0)
    p.add_argument("--out", required=True)
    p.add_argument("--width", type=int, default=0, help="0 = kaynak çözünürlük")
    args = p.parse_args()

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        print(json.dumps({"error": "video açılamadı"}))
        return 1
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(args.t * fps))
    ok, bgr = cap.read()
    cap.release()
    if not ok:
        print(json.dumps({"error": "kare okunamadı"}))
        return 1
    sh, sw = bgr.shape[:2]
    if args.width and args.width < sw:
        scale = args.width / sw
        bgr = cv2.resize(bgr, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    cv2.imwrite(args.out, bgr, [cv2.IMWRITE_JPEG_QUALITY, 90])
    h, w = bgr.shape[:2]
    print(json.dumps({"width": w, "height": h, "src_width": sw, "src_height": sh, "t": args.t}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
