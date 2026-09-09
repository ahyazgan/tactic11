"""Kare başına kalibrasyonun doğruluğunu ve hızını ÖLÇ (venv-cv).

README'deki kalibrasyon sayıları bu scriptle üretilir; iddiaların hepsi burada
yeniden koşturulabilir olsun diye repoda tutulur.

## Yöntem — saha gerçeği nereden geliyor

Elde etiketli yayın görüntüsü yok. Bunun yerine **sabit kameralı** bir klipten
(kalibrasyonu bilinen) kırpma penceresi gezdirilerek pan+zoom taklidi üretilir.
Kırpma parametreleri bilindiği için her karenin GERÇEK homografisi analitik
olarak hesaplanabilir:

    H_yayın = H_orijinal · A,   A = kırpma + ölçek afini

Böylece kalibrasyonun hatası metre cinsinden ölçülebilir. Sentetik olduğu için
hareket düzgündür (gerçek kameramanın ani düzeltmeleri yoktur) ve sıkıştırma
bozulmaları azdır — sayılar bu yüzden **iyimser taraftadır**; gerçek yayında
doğrulanması gerekir.

## Kullanım

    # 1) Ölçüm videosunu üret (bir kez)
    venv-cv\\Scripts\\python.exe -m scripts.bench_calibration make \\
        --source data/tracking/live/seg_0000.mp4 \\
        --calibration data/tracking/calibrations/saha.json \\
        --out-dir data/tracking/bench

    # 2) Ölç
    venv-cv\\Scripts\\python.exe -m scripts.bench_calibration run \\
        --bench-dir data/tracking/bench --scale 0.75

    # 3) Tüm tabloyu üret (README'deki)
    venv-cv\\Scripts\\python.exe -m scripts.bench_calibration table \\
        --bench-dir data/tracking/bench

    # 4) TV SENARYOSU: kesmeli yayın üret + yeniden yakalamayı ölç
    venv-cv\\Scripts\\python.exe -m scripts.bench_calibration make-cuts \\
        --bench-dir data/tracking/bench
    venv-cv\\Scripts\\python.exe -m scripts.bench_calibration cuts \\
        --bench-dir data/tracking/bench

## TV yayını ölçümü — neden ayrı

`pan_zoom.mp4` hareketli ana kamerayı taklit eder ama KESME içermez. Yayının
asıl zorluğu kesmedir: her kesmede homografi süreklilik referansını kaybeder ve
`allow_reacquire` kapalıysa kalibratör bir daha ASLA toparlanmaz — segmentin
kalanındaki her kare atılır. `make-cuts` + `cuts` bunu ölçer.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

from app.tracking.calibration import PitchCalibration
from app.tracking.homography_fit import corners_from_homography
from app.tracking.pitch_lines import PerFrameCalibrator, calibration_from_homography
from app.tracking.pitch_model import pitch_corners

BENCH_W, BENCH_H = 1280, 720
GT_NAME = "ground_truth.json"
MP4_NAME = "pan_zoom.mp4"


def make(args: argparse.Namespace) -> int:
    """Sabit kameralı klipten pan+zoom taklidi üret + gerçek homografileri kaydet."""
    import cv2

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(args.source)
    if not cap.isOpened():
        print(f"kaynak açılamadı: {args.source}")
        return 2
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    fw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    fh = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    writer = cv2.VideoWriter(str(out_dir / MP4_NAME),
                             cv2.VideoWriter_fourcc(*"mp4v"), fps, (BENCH_W, BENCH_H))
    params = []
    i = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        t = i / fps
        zoom = args.zoom_base + args.zoom_swing * math.sin(t * args.zoom_speed)
        cw, ch = int(BENCH_W * zoom), int(BENCH_H * zoom)
        cx = (fw - cw) * (0.5 + args.pan_range * math.sin(t * args.pan_speed))
        x0 = int(max(0, min(fw - cw, cx)))
        y0 = int(max(0, min(fh - ch, (fh - ch) * 0.5)))
        writer.write(cv2.resize(frame[y0:y0 + ch, x0:x0 + cw], (BENCH_W, BENCH_H)))
        params.append({"frame": i, "x0": x0, "y0": y0, "cw": cw, "ch": ch})
        i += 1
    cap.release()
    writer.release()
    (out_dir / GT_NAME).write_text(json.dumps({
        "width": BENCH_W, "height": BENCH_H, "fps": fps,
        "source": args.source, "calibration": args.calibration, "params": params,
    }), encoding="utf-8")
    xs = [p["x0"] for p in params]
    cws = [p["cw"] for p in params]
    print(f"{i} kare üretildi → {out_dir / MP4_NAME}")
    print(f"  yatay gezinme: {min(xs)} → {max(xs)} px · zoom: {min(cws)} → {max(cws)} px")
    return 0


def _load(bench_dir: Path):
    gt = json.loads((bench_dir / GT_NAME).read_text(encoding="utf-8"))
    orig = PitchCalibration.load(gt["calibration"])
    w, h = gt["width"], gt["height"]

    def true_h(p: dict) -> np.ndarray:
        a = np.array([[p["cw"] / w, 0.0, p["x0"]],
                      [0.0, p["ch"] / h, p["y0"]],
                      [0.0, 0.0, 1.0]])
        return orig.homography @ a

    return gt, true_h


def _pitch(h: np.ndarray, u: float, v: float) -> np.ndarray:
    q = h @ np.array([u, v, 1.0])
    return q[:2] / q[2]


def measure(bench_dir: Path, *, scale: float, every: int, frames: int,
            fixed_only: bool = False) -> dict:
    """Bir ayar için: kalibre oranı, metre cinsinden hata, kare başına süre."""
    import cv2

    gt, true_h = _load(bench_dir)
    w, h = gt["width"], gt["height"]
    sw, sh = int(w * scale), int(h * scale)
    to_small = np.diag([1.0 / scale, 1.0 / scale, 1.0])
    anchor = calibration_from_homography(true_h(gt["params"][0]) @ to_small, (sw, sh))
    pfc = PerFrameCalibrator(anchor, image_size=(sw, sh))
    fixed_h = true_h(gt["params"][0])

    cap = cv2.VideoCapture(str(bench_dir / MP4_NAME))
    probes = [(w / 2, h / 2), (w * 0.25, h * 0.6), (w * 0.75, h * 0.4)]
    errs: list[float] = []
    elapsed = 0.0
    idx = seen = 0
    while seen < frames:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % every:
            idx += 1
            continue
        truth = true_h(gt["params"][idx])
        if fixed_only:
            for u, v in probes:
                errs.append(float(np.hypot(*(_pitch(fixed_h, u, v) - _pitch(truth, u, v)))))
        else:
            img = frame if scale == 1.0 else cv2.resize(
                frame, (sw, sh), interpolation=cv2.INTER_AREA)
            t0 = time.time()
            res = pfc.process(img)
            elapsed += time.time() - t0
            if res.ok:
                back = res.calibration.homography @ np.diag([scale, scale, 1.0])
                for u, v in probes:
                    errs.append(float(np.hypot(*(_pitch(back, u, v) - _pitch(truth, u, v)))))
        seen += 1
        idx += 1
    cap.release()
    e = np.array(errs) if errs else np.array([np.nan])
    return {
        "frames": seen,
        "calibrated": seen if fixed_only else pfc.frames_calibrated,
        "ratio": 1.0 if fixed_only else pfc.calibrated_ratio,
        "mean_m": float(np.nanmean(e)), "p90_m": float(np.nanpercentile(e, 90)),
        "worst_m": float(np.nanmax(e)),
        "ms_per_frame": 0.0 if fixed_only else elapsed / max(seen, 1) * 1000.0,
    }


def _print_row(label: str, r: dict) -> None:
    print(f"{label:<34} kalibre {r['calibrated']:>3}/{r['frames']:<3} (%{r['ratio'] * 100:3.0f}) "
          f"· hata ort {r['mean_m']:6.2f} m, %90 {r['p90_m']:6.2f} m, en kötü {r['worst_m']:6.2f} m"
          f" · {r['ms_per_frame']:5.1f} ms/kare")


def run(args: argparse.Namespace) -> int:
    _print_row(f"ölçek {args.scale}, her {args.every}. kare",
               measure(Path(args.bench_dir), scale=args.scale, every=args.every,
                       frames=args.frames))
    return 0


def table(args: argparse.Namespace) -> int:
    bench = Path(args.bench_dir)
    n = args.frames
    print("\n=== SABİT homografi (bugünkü davranışın referansı) ===")
    _print_row("sabit homografi", measure(bench, scale=1.0, every=1, frames=n,
                                          fixed_only=True))
    print("\n=== KARE BAŞINA kalibrasyon — örnekleme sıklığı ===")
    for every in (1, 2, 3, 5):
        _print_row(f"her {every}. kare (ölçek 1.0)",
                   measure(bench, scale=1.0, every=every, frames=n))
    print("\n=== KARE BAŞINA kalibrasyon — çözünürlük ölçeği ===")
    for scale in (1.0, 0.75, 0.5):
        _print_row(f"ölçek {scale} (her kare)",
                   measure(bench, scale=scale, every=1, frames=n))
    print("\nNot: sentetik hareket düzgündür; gerçek yayında sayılar kötüleşir.")
    return 0


CUTS_NAME = "yayin_kesmeli.mp4"


def make_cuts(args: argparse.Namespace) -> int:
    """pan_zoom.mp4'ten KESMELİ yayın taklidi üret.

    pan_zoom hareketli ana kameradır ama kesme içermez; TV yayınının asıl
    zorluğu kesmedir (her kesmede homografi süreklilik referansını kaybeder).

    "İkinci kamera" yalnızca yakınlaştırma OLAMAZ: aynı içeriğin zoom'u
    histogramı değiştirmediği için `classify_pair` onu haklı olarak "hızlı
    çevirme" sayar, kesme değil. Gerçek kesme farklı bir sahneye gider — farklı
    renk dağılımı + tutarsız kayma. Onu üretmek için kırpma + yatay çevirme +
    renk tonu kaydırması birlikte uygulanır.
    """
    import cv2

    bench = Path(args.bench_dir)
    cap = cv2.VideoCapture(str(bench / MP4_NAME))
    if not cap.isOpened():
        print(f"kaynak açılamadı: {bench / MP4_NAME} — önce 'make' çalıştır")
        return 1
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    out_path = bench / CUTS_NAME
    out = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))

    i = cuts = 0
    prev_close = None
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        close = (i % (args.wide + args.close)) >= args.wide
        if close:
            ch, cw = h // 3, w // 3
            y0, x0 = (h - ch) // 2, (w - cw) // 2
            frame = cv2.resize(frame[y0:y0 + ch, x0:x0 + cw], (w, h))
            frame = cv2.flip(frame, 1)
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            hsv[:, :, 0] = (hsv[:, :, 0].astype(int) + 75) % 180
            frame = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
        if prev_close is not None and prev_close != close:
            cuts += 1
        prev_close = close
        out.write(frame)
        i += 1
    cap.release()
    out.release()
    print(f"{out_path}: {i} kare, {cuts} kesme "
          f"({args.wide} geniş / {args.close} yakın blok)")

    # Çapa kalibrasyonunu da YANINA yaz. `cuts` bunu kendisi türetiyor ama
    # `track_video`/`track_live` ile uçtan uca duman testi yapmak için diskte
    # bir JSON gerekiyor. Üretilen her şey bench klasöründe kalsın (gitignore'da);
    # ground_truth.json'dan türeyen bir dosyayı repoya koymak tutarsız olurdu.
    gt, true_h = _load(bench)
    anchor_path = bench / "anchor_frame0.json"
    with open(anchor_path, "w", encoding="utf-8") as f:
        json.dump({
            "image_size": [gt["width"], gt["height"]],
            "pitch_length_m": 105.0, "pitch_width_m": 68.0,
            "points": [{"image": [float(u), float(v)], "pitch": [float(px), float(py)]}
                       for (u, v), (px, py) in zip(
                           corners_from_homography(true_h(gt["params"][0])),
                           pitch_corners(), strict=True)],
        }, f, indent=1)
    print(f"{anchor_path}: çapa kalibrasyonu (uçtan uca duman testi için)")
    print("\nUçtan uca deneme:")
    print(f"  python -m scripts.track_video --video {out_path} \\\n"
          f"      --calibration {anchor_path} --out bench_frames.json \\\n"
          f"      --match-id 990199 --home-team 611 --away-team 612 \\\n"
          f"      --camera broadcast --track-fps 15")
    return 0


def cuts(args: argparse.Namespace) -> int:
    """Kesmeli yayında yeniden yakalamanın etkisini ölç.

    Ölçülen: kaç kare kalibre oldu. Kalibre olmayan kare ATILIR — düşük oran
    "veri yok" demektir, "yanlış veri" değil.
    """
    import cv2

    from app.tracking.camera import CutDetector
    from app.tracking.pitch_lines import extract_lines

    bench = Path(args.bench_dir)
    video = bench / CUTS_NAME
    if not video.exists():
        print(f"{video} yok — önce 'make-cuts' çalıştır")
        return 1
    gt, true_h = _load(bench)
    w, h = gt["width"], gt["height"]
    anchor = calibration_from_homography(true_h(gt["params"][0]), (w, h))

    cap = cv2.VideoCapture(str(video))
    frames = []
    while len(frames) < args.frames:
        ok, f = cap.read()
        if not ok:
            break
        frames.append(f)
    cap.release()
    print(f"video: {len(frames)} kare {w}x{h}\n")
    print(f"{'yeniden yakalama':>18} {'kesme bildirimi':>16} {'kalibre':>12} "
          f"{'oran':>6} {'kesme':>6}")
    print("-" * 64)
    for reacquire in (False, True):
        for use_cuts in (False, True):
            pfc = PerFrameCalibrator(anchor, image_size=(w, h),
                                     allow_reacquire=reacquire)
            det = CutDetector() if use_cuts else None
            for f in frames:
                if det is not None and det.update(f) == "cut":
                    pfc.mark_cut()
                ext = extract_lines(f)
                pfc.process_lines(ext.dist_map, line_pixels=ext.line_pixels,
                                  grass_ratio=ext.grass_ratio)
            print(f"{'AÇIK' if reacquire else 'kapalı':>18} "
                  f"{'VAR' if use_cuts else 'yok':>16} "
                  f"{pfc.frames_calibrated:>6}/{pfc.frames_seen:<5} "
                  f"{pfc.calibrated_ratio * 100:>5.0f}% "
                  f"{(det.cuts if det else 0):>6}")
    print("\nNot: sentetik kesmelerde 2. kamerada saha çizgisi yoktur, bu yüzden "
          "'kesme bildirimi' sayıyı değiştirmez —\nmevcut kapılar zaten düşürür. "
          "mark_cut'ın değeri İKİ kameranın da sahayı gördüğü kesmelerdedir "
          "(bkz. tests/test_per_frame_calibrator.py).")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Kare başına kalibrasyon ölçümü")
    sub = p.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("make", help="Ölçüm videosu + saha gerçeği üret")
    m.add_argument("--source", required=True, help="Sabit kameralı kaynak klip")
    m.add_argument("--calibration", required=True, help="Kaynağın kalibrasyon JSON'u")
    m.add_argument("--out-dir", required=True)
    m.add_argument("--zoom-base", type=float, default=1.30)
    m.add_argument("--zoom-swing", type=float, default=0.10)
    m.add_argument("--zoom-speed", type=float, default=0.5)
    m.add_argument("--pan-range", type=float, default=0.42)
    m.add_argument("--pan-speed", type=float, default=0.7)
    m.set_defaults(func=make)

    r = sub.add_parser("run", help="Tek ayarı ölç")
    r.add_argument("--bench-dir", required=True)
    r.add_argument("--scale", type=float, default=1.0)
    r.add_argument("--every", type=int, default=1)
    r.add_argument("--frames", type=int, default=60)
    r.set_defaults(func=run)

    t = sub.add_parser("table", help="README tablosunu üret")
    t.add_argument("--bench-dir", required=True)
    t.add_argument("--frames", type=int, default=60)
    t.set_defaults(func=table)

    mc = sub.add_parser("make-cuts", help="KESMELİ yayın taklidi üret (TV senaryosu)")
    mc.add_argument("--bench-dir", required=True)
    mc.add_argument("--wide", type=int, default=40, help="Ana kamera blok uzunluğu (kare)")
    mc.add_argument("--close", type=int, default=15, help="İkinci kamera blok uzunluğu")
    mc.set_defaults(func=make_cuts)

    c = sub.add_parser("cuts", help="Kesmeli yayında yeniden yakalamayı ölç")
    c.add_argument("--bench-dir", required=True)
    c.add_argument("--frames", type=int, default=500)
    c.set_defaults(func=cuts)

    args = p.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
