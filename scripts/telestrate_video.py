"""Takip çıktısı + video → otomatik telestrasyonlu video (venv-cv; opencv + pillow).

Takip hattından (`scripts/track_video.py`) SONRA çalışır, onu değiştirmez:

    venv-cv\\Scripts\\python.exe -m scripts.telestrate_video \\
        --video clip.mp4 --calibration calib.json --frames frames.json \\
        --out tele.mp4 --home-attack x+ --marks-json marks.json

Oyuncu halkaları, savunan takımın blok çizgileri ve faz etiketi
(app/tracking/telestration.py) kaynak videonun aynı anına çizilir. Varsayılan
olarak çıktı kaynak kare hızındadır: takip kareleri (~5 fps) arasında oyuncular
kimliğe göre doğrusal enterpole edilir; kamera kesmesinde (continuity_id) ya da
0,6 sn'den uzun boşlukta enterpolasyon yapılmaz. `--no-interpolate` yalnız takip
karelerini yazar. `--marks-json` çizim öğelerini yazılan her kare için verir.

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
from app.tracking.telestration import (
    INTERPOLATE_MAX_GAP_S,
    MAX_REPROJECTION_M,
    PlayerSpot,
    Telestrator,
    calibration_validation,
    interpolate_point,
    interpolate_spots,
    render,
    scaled,
    spots_from_frame,
)

HOME_ATTACK = {"auto": 0, "x+": 1, "x-": -1}


def output_size(width: int, height: int, max_width: int) -> tuple[int, int]:
    """Kodek uyumlu çift boyutlar."""
    scale = min(1.0, max_width / max(width, 1))
    return max(2, int(width * scale) // 2 * 2), max(2, round(height * scale / 2) * 2)


Spots = tuple[list[PlayerSpot], tuple[float, float] | None, int | None]


def schedule(seconds: list[float], spots: list[Spots], continuity: list[int | None], src_fps: float,
             interpolate: bool) -> list[tuple[int, float, Spots]]:
    """Yazılacak video kareleri: (kare no, sn, (oyuncular, top, sahip)).

    Enterpolasyonsuz: her takip karesi en yakın video karesine (aynı kareye düşen
    ikincisi atlanır). Enterpolasyonlu: ilk ile son takip karesi arasındaki her video
    karesi; aynı süreklilikte ve kısa aralıklı iki takip karesi arasında doğrusal,
    aksi halde yalnız takip karesinin yarım adım yakınında, değilse çizimsiz (None).
    """
    if not interpolate:
        out, last = [], -1
        for t, sp in zip(seconds, spots, strict=True):
            idx = round(t * src_fps)
            if idx > last:
                out.append((idx, t, sp))
                last = idx
        return out
    out, k = [], 0
    for idx in range(round(seconds[0] * src_fps), round(seconds[-1] * src_fps) + 1):
        t = idx / src_fps
        while k + 1 < len(seconds) and seconds[k + 1] <= t:
            k += 1
        a = spots[k]
        if k + 1 < len(seconds):
            gap = seconds[k + 1] - seconds[k]
            if 0 < gap <= INTERPOLATE_MAX_GAP_S and continuity[k] == continuity[k + 1]:
                w = min(1.0, max(0.0, (t - seconds[k]) / gap))
                b = spots[k + 1]
                out.append((idx, t, (interpolate_spots(a[0], b[0], w), interpolate_point(a[1], b[1], w),
                                     a[2] if w < 0.5 else b[2])))
                continue
        if abs(t - seconds[k]) <= 0.5 / src_fps:
            out.append((idx, t, a))
    return out


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
    p.add_argument("--no-interpolate", action="store_true", help="Yalnız takip karelerini yaz (~5 fps)")
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
    interpolate = not args.no_interpolate
    out_fps = src_fps if interpolate else fps
    writer = cv2.VideoWriter(args.out, cv2.VideoWriter_fourcc(*"mp4v"), out_fps, size)
    if not writer.isOpened():
        print(f"hata: video yazıcısı açılamadı: {args.out}", file=sys.stderr)
        return 2

    spots = [spots_from_frame(f, home, away, calib) for f in frames]
    plan = schedule(seconds, spots, [f.continuity_id for f in frames], src_fps, interpolate)
    tele = Telestrator(out_fps, HOME_ATTACK[args.home_attack])
    source, error = calibration_validation(calib)
    if source == "unverified":
        print("uyarı: kalibrasyon bağımsız doğrulanmamış (noktalar saha işareti değil, çizgi doğrulaması "
              "yok); yalnız halkalar çizilecek. Saha çizgisi noktalarıyla kalibrasyon kurun.", file=sys.stderr)
    elif error is not None and error > MAX_REPROJECTION_M:
        print(f"uyarı: kalibrasyon hatası {error:.2f} m > {MAX_REPROJECTION_M} m; yalnız halkalar çizilecek.",
              file=sys.stderr)
    log: list[dict] = []
    position = 0
    written = 0
    try:
        for idx, t, (players, ball, owner) in plan:
            while position < idx and cap.grab():
                position += 1
            ok, bgr = cap.read()
            if not ok:
                break
            position += 1
            marks = tele.marks(players, ball, calib, owner)
            factor = size[0] / bgr.shape[1]
            if (bgr.shape[1], bgr.shape[0]) != size:
                # önce küçült, sonra çiz: 4K karede çizmek gerçek zamanın ~3 katı sürüyordu
                bgr = cv2.resize(bgr, size, interpolation=cv2.INTER_AREA)
            render(bgr, scaled(marks, factor))
            writer.write(bgr)
            written += 1
            if args.marks_json:
                log.append({"seconds": round(t, 3), "marks": [asdict(m) for m in marks]})
    finally:
        writer.release()
        cap.release()

    gates = dict(tele.gate_counts)
    summary = {"frames_written": written, "fps": round(out_fps, 3), "tracking_fps": round(fps, 3),
               "interpolated": interpolate, "home_attack": args.home_attack,
               "gates": gates, "drawn_ratio": round(gates.get("drawn", 0) / max(written, 1), 3)}
    if args.marks_json:
        Path(args.marks_json).write_text(json.dumps({"summary": summary, "frames": log}, ensure_ascii=False),
                                         encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if written else 1


if __name__ == "__main__":
    raise SystemExit(main())
