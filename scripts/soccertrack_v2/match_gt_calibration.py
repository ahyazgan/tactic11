"""SoccerTrack v2: video pikseli → saha (m) kalibrasyonu, tespit ↔ GT eşleştirmesiyle (venv-cv).

Veri setine özel araştırma aracı (ürün yolu değil). Ürün yolu: operatör arayüzde
nokta tıklar (`/video-tracking/calibrate`). Bu script, veri setinin GT'sini bizim
video karesine taşımak için var; çıktısı `data/tracking/calibrations/soccertrack_v2_<id>.json`.

Neden gerekli: GSR bbox pikselleri ham balıkgözü karesine (3840x1504) ait, Drive'daki
panorama videosu undistort edilmiş (3840x1906). Ölçüldü (117092): video_y ≈ 1.51·y_gt − 270
(+ küçük doğrusal olmayan terim). Bu yüzden GT'nin saha koordinatları doğru ama pikselleri
videoya uymaz; çiftler videodaki TESPİTLERLE kurulur.

Yöntem: örnek karelerde tespit ayak noktaları ↔ GT (kaba afinle video uzayına taşınmış)
karşılıklı en yakın komşu (<30 px), kare ofseti (Δ) aranır (GT sayacı videoyla hizalı
değil ve kayıyor). Çiftlerden 2. derece polinom px→px, tüm GT video uzayına taşınır,
saha hücresi başına 1 nokta ile TPS kalibrasyon kurulur.

Sonuç (117092): 359 çift, polinom artık medyan 12 px; 500 noktalı TPS; bağımsız
video-tespit çiftlerinde medyan 1.59 m, p90 3.8 m. Elle okunan 11 nokta (halfway, orta
daire, direkler) 5 m verdi — panorama için yetersiz.

Kullanım (proje kökünden):
    set PYTHONPATH=.
    venv-cv\\Scripts\\python.exe scripts/soccertrack_v2/match_gt_calibration.py ^
        --gt-rows <klasör>/st_gt_rows_15k_25k.npy ^
        --video data/tracking/videos/soccertrack_117092_sample_600_960.mp4 ^
        --sample-start 600 --out data/tracking/calibrations/soccertrack_v2_117092.json
`--gt-rows`: [kare, x_merkez, y_alt, px, py] satırları (GSR JSON'dan çıkarılmış).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from app.tracking.calibration import PitchCalibration
from app.tracking.detect import DetectorConfig, make_detector

MATCH_PX = 30.0          # karşılıklı en yakın eşleşme eşiği (px)
POLY_RESID_PX = 25.0     # polinom fit'inde atılan artık eşiği (px)
DELTA_RANGE = range(-90, 31)
CELL_M = (3.5, 3.4)      # saha hücresi (m): hücre başına 1 nokta


def feats(u: np.ndarray, v: np.ndarray) -> np.ndarray:
    return np.stack([u, v, u * u, u * v, v * v, np.ones_like(u)], 1)


def load_gt(path: Path) -> dict[int, np.ndarray]:
    gt = np.load(path)
    by: dict[int, list[tuple[float, float, float, float]]] = {}
    for f, xc, yb, px, py in gt:
        by.setdefault(int(f), []).append((xc, yb, px + 52.5, py + 34.0))
    return {k: np.array(v) for k, v in by.items()}


def detect_feet(video: Path, times: np.ndarray, weights: str, tiles: int) -> dict[float, np.ndarray]:
    cap = cv2.VideoCapture(str(video))
    det = make_detector(DetectorConfig(tiles=tiles, weights=weights, threshold=0.3))
    feet: dict[float, np.ndarray] = {}
    for t in times:
        cap.set(cv2.CAP_PROP_POS_MSEC, float(t) * 1000)
        ok, bgr = cap.read()
        if not ok:
            continue
        r = det.detect(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
        xy = r.xyxy[r.class_id == 0]
        feet[float(t)] = np.stack([(xy[:, 0] + xy[:, 2]) / 2, xy[:, 3]], 1)
    return feet


def match_pairs(feet: dict[float, np.ndarray], gt_by: dict[int, np.ndarray],
                affine: np.ndarray, sample_start: float) -> np.ndarray:
    pairs: list[tuple[float, ...]] = []
    for t, f in feet.items():
        base = int(round((sample_start + t) * 25)) + 1
        best = None
        for delta in DELTA_RANGE:
            g = gt_by.get(base + delta)
            if g is None or len(g) < 15:
                continue
            gp = g[:, :2] @ affine[:, :2].T + affine[:, 2]
            d = np.sqrt(((gp[:, None, :] - f[None, :, :]) ** 2).sum(-1))
            score = float(np.median(d.min(1)))
            if best is None or score < best[0]:
                best = (score, g, d)
        if best is None:
            continue
        _, g, d = best
        j = d.argmin(1)
        nn = d.min(1)
        for i in range(len(g)):
            if nn[i] < MATCH_PX and d[:, j[i]].argmin() == i:
                u, v = f[j[i]]
                pairs.append((u, v, g[i, 2], g[i, 3], g[i, 0], g[i, 1]))
    return np.array(pairs)


def main() -> int:
    p = argparse.ArgumentParser(description="SoccerTrack v2 GT → video uzayı kalibrasyonu")
    p.add_argument("--gt-rows", required=True, type=Path)
    p.add_argument("--video", required=True, type=Path)
    p.add_argument("--sample-start", type=float, required=True, help="örnek videonun yarı içindeki başlangıcı (sn)")
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--weights", default="data/tracking/models/rfdetr_mixed_small")
    p.add_argument("--tiles", type=int, default=4)
    p.add_argument("--image-size", default="3840x1906")
    args = p.parse_args()
    w, h = (int(x) for x in args.image_size.split("x"))

    gt_by = load_gt(args.gt_rows)
    feet = detect_feet(args.video, np.arange(4.0, 356.0, 6.0), args.weights, args.tiles)
    affine = np.array([[1.0, 0.0, 0.0], [0.0, 1.5, -270.0]])   # kaba başlangıç; iterasyonla düzelir
    pairs = np.zeros((0, 6))
    for it in range(3):
        pairs = match_pairs(feet, gt_by, affine, args.sample_start)
        if len(pairs) >= 10:
            src = np.hstack([pairs[:, 4:6], np.ones((len(pairs), 1))])
            affine = np.linalg.lstsq(src, pairs[:, 0:2], rcond=None)[0].T
        print(f"iterasyon {it}: çift {len(pairs)} · afin {np.round(affine, 3).tolist()}")

    # px→px polinom, artık süzgeciyle
    su, sv, dst = pairs[:, 4], pairs[:, 5], pairs[:, 0:2]
    mask = np.ones(len(pairs), bool)
    coef = np.zeros((6, 2))
    for _ in range(3):
        coef = np.linalg.lstsq(feats(su[mask], sv[mask]), dst[mask], rcond=None)[0]
        res = np.hypot(*(feats(su, sv) @ coef - dst).T)
        mask = res < POLY_RESID_PX
    print(f"px→px polinom: {mask.sum()}/{len(pairs)} çift · artık medyan {np.median(res[mask]):.1f} px")

    gt = np.load(args.gt_rows)
    vid = feats(gt[:, 1], gt[:, 2]) @ coef
    x_m, y_m = gt[:, 3] + 52.5, gt[:, 4] + 34.0
    rng = np.random.default_rng(0)
    cells: dict[tuple[int, int], int] = {}
    seen: set[tuple[int, int]] = set()
    keep: list[int] = []
    for i in rng.permutation(len(gt)):
        key = (int(x_m[i] // CELL_M[0]), int(y_m[i] // CELL_M[1]))
        pk = (round(float(vid[i, 0])), round(float(vid[i, 1])))
        if pk in seen or cells.get(key, 0) >= 1:
            continue
        cells[key] = cells.get(key, 0) + 1
        seen.add(pk)
        keep.append(i)
    d = {
        "image_size": [w, h], "pitch_length_m": 105, "pitch_width_m": 68, "method": "tps",
        "points": [
            {"image": [round(float(vid[i, 0]), 1), round(float(vid[i, 1]), 1)],
             "pitch": [round(float(x_m[i]), 2), round(float(y_m[i]), 2)]}
            for i in keep
        ],
        "meta": {
            "source": "SoccerTrack v2 (CC BY 4.0) — GT oyuncu konumları video piksel uzayına "
                      "2. derece polinomla taşındı (video tespitleri ↔ GT eşleşmeleri)",
            "camera": "fixed_panoramic",
            "note": "y=68 yakın taç; bbox_pitch orijini saha merkezi (+52.5/+34).",
        },
    }
    cal = PitchCalibration.from_dict(d)
    err = np.array([
        np.hypot(*(np.array(cal.image_to_pitch_m(pairs[i, 0], pairs[i, 1])) - (pairs[i, 2], pairs[i, 3])))
        for i in range(len(pairs)) if mask[i]
    ])
    note = f" Bağımsız video-tespit çiftlerinde medyan {np.median(err):.2f} m, p90 {np.percentile(err, 90):.2f} m."
    d["meta"]["note"] += note
    print(f"nokta {len(keep)} ·{note}")
    args.out.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"yazıldı: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
