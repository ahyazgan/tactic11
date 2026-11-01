"""Dedektörü SoccerTrack Challenge MOT kutularıyla ölç (venv-cv, GPU).

Klipten `--every` karede bir, üretimdeki dilimli çıkarımla (`DetectorConfig`)
oyuncu kutuları üretilir ve GT kutularıyla birebir eşlenir (Macar). Varsayılan
eşleşme AYAK NOKTASI: alt-orta noktalar arası uzaklık ≤ 0,5 × GT kutu yüksekliği.
IoU (`--match iou`) kutu çizim biçimine duyarlıdır: TeamTrack ile eğitilmiş
model MOT kutularından daha geniş çizer (aynı oyuncuda IoU ≥0,3 %41–77, ≥0,5
%9–45); MOT ile ince ayarlanan model yalnız biçimi öğrenerek IoU'da "iyileşmiş"
görünür. Takip hattı da ayak noktasını kullanır. Raporlanan: tespit oranı (recall), kesinlik (precision), görüntünün
yatay üçte birlerinde (sol/orta/sağ = panoramanın uçları) ve dikey yarılarında
(uzak/yakın) tespit oranı, karede top tespiti olan kare oranı (MOT'ta top
etiketi yok; yalnız kıyas için).

    venv-cv\\Scripts\\python.exe -X utf8 -m scripts.soccertrack_v2.evaluate_detector_mot \\
        --clip data/tracking/datasets/soccertrack_mot/117092 \\
        --weights data/tracking/models/rfdetr_mixed_small --tiles 3 --out eval.json
"""
from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment

from scripts.soccertrack_v2.build_mot_dataset import read_mot

FOOT_RADIUS = 0.5   # GT kutu yüksekliği oranı


def iou_matrix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """a: N×4, b: M×4 (x1,y1,x2,y2)."""
    x1 = np.maximum(a[:, None, 0], b[None, :, 0])
    y1 = np.maximum(a[:, None, 1], b[None, :, 1])
    x2 = np.minimum(a[:, None, 2], b[None, :, 2])
    y2 = np.minimum(a[:, None, 3], b[None, :, 3])
    inter = np.clip(x2 - x1, 0, None) * np.clip(y2 - y1, 0, None)
    area_a = (a[:, 2] - a[:, 0]) * (a[:, 3] - a[:, 1])
    area_b = (b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1])
    return inter / np.maximum(area_a[:, None] + area_b[None] - inter, 1e-9)


def match(pred: np.ndarray, gt: np.ndarray, threshold: float, mode: str = "foot") -> list[tuple[int, int]]:
    if not len(pred) or not len(gt):
        return []
    if mode == "iou":
        iou = iou_matrix(pred, gt)
        ii, jj = linear_sum_assignment(-iou)
        return [(int(i), int(j)) for i, j in zip(ii, jj, strict=True) if iou[i, j] >= threshold]
    foot_p = np.c_[(pred[:, 0] + pred[:, 2]) / 2, pred[:, 3]]
    foot_g = np.c_[(gt[:, 0] + gt[:, 2]) / 2, gt[:, 3]]
    dist = np.linalg.norm(foot_p[:, None] - foot_g[None], axis=-1) / np.maximum(gt[None, :, 3] - gt[None, :, 1], 1.0)
    ii, jj = linear_sum_assignment(np.where(dist <= FOOT_RADIUS, dist, 1000 + dist))
    return [(int(i), int(j)) for i, j in zip(ii, jj, strict=True) if dist[i, j] <= FOOT_RADIUS]


def region(box: np.ndarray, width: int, height: int, foot_split: float) -> tuple[str, str]:
    cx, foot = (box[0] + box[2]) / 2, box[3]
    third = ("sol", "orta", "sag")[min(2, int(3 * cx / width))]
    return third, "uzak" if foot < foot_split else "yakin"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--clip", type=Path, required=True, help="<dizin>/<maç> (yanında .mp4 ve .txt)")
    p.add_argument("--weights", required=True)
    p.add_argument("--tiles", type=int, default=3)
    p.add_argument("--threshold", type=float, default=0.35)
    p.add_argument("--every", type=int, default=25)
    p.add_argument("--iou", type=float, default=0.5)
    p.add_argument("--match", choices=["foot", "iou"], default="foot")
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()

    import cv2

    from app.tracking.detect import DetectorConfig, make_detector

    gt = read_mot(args.clip.with_suffix(".txt"))
    foot_ys = [b[1] + b[3] for f in gt.values() for b in f]
    foot_split = float(np.median(foot_ys))
    det = make_detector(DetectorConfig(model="small", weights=args.weights, tiles=args.tiles,
                                       threshold=args.threshold))
    cap = cv2.VideoCapture(str(args.clip.with_suffix(".mp4")))
    counts: Counter[str] = Counter()
    by_region: dict[str, Counter[str]] = {}
    fi, frames, ball_frames, elapsed = 0, 0, 0, 0.0
    while True:
        ok, bgr = cap.read()
        if not ok:
            break
        if fi % args.every == 0 and fi in gt:
            h, w = bgr.shape[:2]
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            started = time.perf_counter()
            persons, balls = det.split(det.detect(rgb))
            elapsed += time.perf_counter() - started
            pred = np.asarray(persons.xyxy, dtype=float).reshape(-1, 4)
            g = np.array([(x, y, x + bw, y + bh) for x, y, bw, bh in gt[fi]], dtype=float).reshape(-1, 4)
            pairs = match(pred, g, args.iou, args.match)
            found = {j for _i, j in pairs}
            counts["gt"] += len(g)
            counts["pred"] += len(pred)
            counts["tp"] += len(pairs)
            for j, box in enumerate(g):
                key = "/".join(region(box, w, h, foot_split))
                by_region.setdefault(key, Counter())["gt"] += 1
                by_region[key]["tp"] += j in found
            ball_frames += len(balls) > 0
            frames += 1
        fi += 1
    cap.release()
    report = {
        "clip": str(args.clip), "weights": args.weights, "tiles": args.tiles, "threshold": args.threshold,
        "every": args.every, "match": args.match, "iou": args.iou if args.match == "iou" else None,
        "foot_radius": FOOT_RADIUS if args.match == "foot" else None, "frames": frames,
        "recall": round(counts["tp"] / max(1, counts["gt"]), 4),
        "precision": round(counts["tp"] / max(1, counts["pred"]), 4),
        "ball_frame_share": round(ball_frames / max(1, frames), 4),
        "seconds_per_frame": round(elapsed / max(1, frames), 3),
        "by_region_recall": {k: round(v["tp"] / max(1, v["gt"]), 4) for k, v in sorted(by_region.items())},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
