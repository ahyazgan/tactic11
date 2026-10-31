"""SoccerTrack panoramasından canlı moddaki gibi 30 sn'lik segmentler kes (venv-cv; PyAV + OpenCV).

`data/tracking/live/990401` segmentleri panoramanın 15000. karesinden (600 sn)
başlar; piksel farkı 0 ile doğrulandı. Aynı kare ızgarasıyla başka bir aralık
keserek GT hizalaması (+9 kare) korunur. Kodlama libx264 CRF 14'tür; kaynak
dosyadan bit-bit kopya değildir.

    venv-cv\\Scripts\\python.exe -X utf8 -m scripts.soccertrack_v2.cut_segments \\
        --start-seconds 1200 --count 12 --out data/tracking/live/990402
"""
from __future__ import annotations

import argparse
from pathlib import Path

DEFAULT_SOURCE = Path("data/tracking/datasets/soccertrack_v2/117092/117092_panorama_1st_half.mp4")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    p.add_argument("--start-seconds", type=int, required=True)
    p.add_argument("--count", type=int, default=12)
    p.add_argument("--segment-seconds", type=int, default=30)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()

    import av
    import cv2

    args.out.mkdir(parents=True, exist_ok=False)
    cap = cv2.VideoCapture(str(args.source))
    fps = round(cap.get(cv2.CAP_PROP_FPS) or 25)
    cap.set(cv2.CAP_PROP_POS_FRAMES, args.start_seconds * fps)
    per = args.segment_seconds * fps
    for seg in range(args.count):
        container = av.open(str(args.out / f"seg_{seg:04d}.mp4"), "w")
        stream = container.add_stream("libx264", rate=fps)
        stream.width, stream.height = int(cap.get(3)), int(cap.get(4))
        stream.pix_fmt, stream.options = "yuv420p", {"crf": "14", "preset": "fast"}
        for _ in range(per):
            ok, frame = cap.read()
            if not ok:
                break
            for packet in stream.encode(av.VideoFrame.from_ndarray(frame, format="bgr24")):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
        container.close()
        print(f"seg_{seg:04d}.mp4", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
