"""Takip çıktısı + video → otomatik telestrasyonlu video (venv-cv; opencv + pillow).

Takip hattından (`scripts/track_video.py`) SONRA çalışır, onu değiştirmez:

    venv-cv\\Scripts\\python.exe -m scripts.telestrate_video \\
        --video clip.mp4 --calibration calib.json --frames frames.json \\
        --out tele.mp4 --home-attack x+ --marks-json marks.json

Her takip karesi için oyuncu halkaları, savunan takımın blok çizgileri ve faz
etiketi (app/tracking/telestration.py) kaynak videonun aynı anına çizilir.
Çıktı takip kare hızındadır (konum ile görüntü aynı andan gelsin diye).
`--marks-json` aynı çizim öğelerini kare başına yazar (panel katmanı için).

Sınır: yalnız sabit kalibrasyon (sabit kamera). Kare başına kalibrasyonla
işlenmiş hareketli kamera çıktısı karelerin kendi homografisini taşımadığı
için desteklenmez.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from app.domain import TrackingFrame
from app.tracking.calibration import PitchCalibration
from app.tracking.telestration import Telestrator, render, spots_from_frame

HOME_ATTACK = {"auto": 0, "x+": 1, "x-": -1}


def output_size(width: int, height: int, max_width: int) -> tuple[int, int]:
    """Kodek uyumlu çift boyutlar."""
    scale = min(1.0, max_width / max(width, 1))
    return max(2, int(width * scale) // 2 * 2), max(2, round(height * scale / 2) * 2)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--video", required=True)
    p.add_argument("--calibration", required=True, help="Takipte kullanılan sabit kalibrasyon JSON")
    p.add_argument("--frames", required=True, help="scripts.track_video çıktısı (frames JSON)")
    p.add_argument("--out", required=True, help="Telestrasyonlu mp4")
    p.add_argument("--home-attack", default="auto", choices=sorted(HOME_ATTACK),
                   help="Ev sahibi kalibrasyonun saha x'i artan (x+) ya da azalan (x-) yöne hücum eder; "
                        "auto = kaleci/en derin oyuncudan çıkar")
    p.add_argument("--clip-offset-minutes", type=float, default=0.0,
                   help="Takipte verilen klip başlangıç dakikası (track_video ile aynı)")
    p.add_argument("--width", type=int, default=1600, help="Çıktı genişliği (en fazla)")
    p.add_argument("--marks-json", default=None, help="Kare başına çizim öğeleri JSON yolu")
    args = p.parse_args()

    import cv2

    data = json.loads(Path(args.frames).read_text(encoding="utf-8"))
    frames = sorted((TrackingFrame.model_validate(f) for f in data["frames"]), key=lambda f: f.minute)
    if len(frames) < 2:
        print("hata: en az iki takip karesi gerekli", file=sys.stderr)
        return 2
    calib = PitchCalibration.load(args.calibration)
    home, away = data["home_team_external_id"], data["away_team_external_id"]
    seconds = [(f.minute - args.clip_offset_minutes) * 60.0 for f in frames]
    steps = sorted(b - a for a, b in zip(seconds, seconds[1:], strict=False) if b > a)
    fps = 1.0 / steps[len(steps) // 2]

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        print(f"hata: video açılamadı: {args.video}", file=sys.stderr)
        return 2
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    size = output_size(int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)), args.width)
    writer = cv2.VideoWriter(args.out, cv2.VideoWriter_fourcc(*"mp4v"), fps, size)
    if not writer.isOpened():
        print(f"hata: video yazıcısı açılamadı: {args.out}", file=sys.stderr)
        return 2

    tele = Telestrator(fps, HOME_ATTACK[args.home_attack])
    log: list[dict] = []
    position = 0
    written = 0
    try:
        for frame, t in zip(frames, seconds, strict=True):
            target = round(t * src_fps)
            if target < position:
                continue  # aynı video karesine düşen ikinci takip karesi
            while position < target and cap.grab():
                position += 1
            ok, bgr = cap.read()
            if not ok:
                break
            position += 1
            players, ball, owner = spots_from_frame(frame, home, away, calib)
            marks = tele.marks(players, ball, calib, owner)
            render(bgr, marks)
            if (bgr.shape[1], bgr.shape[0]) != size:
                bgr = cv2.resize(bgr, size, interpolation=cv2.INTER_AREA)
            writer.write(bgr)
            written += 1
            if args.marks_json:
                log.append({"minute": frame.minute, "marks": [asdict(m) for m in marks]})
    finally:
        writer.release()
        cap.release()

    gates = dict(tele.gate_counts)
    summary = {"frames_written": written, "fps": round(fps, 3), "home_attack": args.home_attack,
               "gates": gates, "drawn_ratio": round(gates.get("drawn", 0) / max(written, 1), 3)}
    if args.marks_json:
        Path(args.marks_json).write_text(json.dumps({"summary": summary, "frames": log}, ensure_ascii=False),
                                         encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if written else 1


if __name__ == "__main__":
    raise SystemExit(main())
