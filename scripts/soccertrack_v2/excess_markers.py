"""Ürünün GT'de eşi olmayan işaretlerini (kesinlik kaybı) konuma göre sınıflandırır.

GSR etiketleri yalnız oyuncu ve kaleci içerir; hakem ve kenardaki kişiler etiketli değildir.
Bu yüzden sınıflandırma kimliğe değil konuma dayanır ve bir tanıdır, ölçüt değildir:

  clamped      : tam çizgi üstünde. Ürün koordinatı 0..100'e kırpar; saha dışındaki kişi (yedek,
                 görevli, top toplayıcı) çizgiye yapışır. Bu yüzden saha dışı ayrı görünmez.
  duplicate    : eşleşmiş bir GT oyuncusuna `DUPLICATE_RADIUS_M` içinde (aynı kişinin ikinci işareti)
  near_miss    : eşleşmemiş bir GT oyuncusuna 3-`NEAR_MISS_M` metre (konum hatası 3 m'yi aşmış)
  alone_line   : hiçbir GT oyuncusuna `NEAR_MISS_M` içinde değil, çizgiye `LINE_BAND_M` yakın (yan hakem, kenar)
  alone_inside : hiçbir GT oyuncusuna `NEAR_MISS_M` içinde değil, saha içinde (orta hakem adayı)
  other        : kalan

Hizalama (saha yönü, kare kayması) `product_vs_gt` ile aynıdır ve yalnız geliştirme karelerinden öğrenilir.
Bu pencere ön kayıtlı ölçümde tüketildi; buradaki sonuç ayar için değil, tanı içindir.

    venv/Scripts/python.exe -X utf8 -m scripts.soccertrack_v2.excess_markers \\
        --frames job_x_frames.json --gt-rows gt.npy --clip-start 1800 --out sonuc.json
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

from scripts.soccertrack_v2.product_vs_gt import (
    DRIFT_WINDOW,
    Frame,
    Truth,
    _gt_frame,
    best_delta,
    flip,
    gt_by_frame,
    learn_alignment,
    match,
    product_frames,
)

CLAMP_TOL_M = 0.01
LINE_BAND_M = 3.0
DUPLICATE_RADIUS_M = 1.5
NEAR_MISS_M = 6.0
CLASSES = ("clamped", "duplicate", "near_miss", "alone_line", "alone_inside", "other")


def classify(point: np.ndarray, truth: np.ndarray, matched_truth: set[int]) -> str:
    """Eşi olmayan tek bir ürün işaretinin sınıfı."""
    x, y = float(point[0]), float(point[1])
    edge = min(x, 105.0 - x, y, 68.0 - y)
    if edge <= CLAMP_TOL_M:
        return "clamped"
    alone = "alone_line" if edge <= LINE_BAND_M else "alone_inside"
    if not len(truth):
        return alone
    dist = np.sqrt(((truth - point) ** 2).sum(-1))
    if any(dist[j] <= DUPLICATE_RADIUS_M for j in matched_truth):
        return "duplicate"
    free = [j for j in range(len(truth)) if j not in matched_truth]
    if any(dist[j] <= NEAR_MISS_M for j in free):
        return "near_miss"
    if float(dist.min()) > NEAR_MISS_M:
        return alone
    return "other"


def attribute(frames: list[Frame], gt: Truth, alignment: dict[str, Any]) -> dict[str, Any]:
    """Eşleşmeyen işaretleri sınıflandırır; sınıf başına sayı, kare başı ortalama ve takım dağılımı."""
    which = (bool(alignment["flip_x"]), bool(alignment["flip_y"]))
    delta = int(alignment["delta_frames"])
    counts: Counter[str] = Counter()
    team_by_class: dict[str, Counter[int]] = {c: Counter() for c in CLASSES}
    used = ours_n = matched_n = clamped_all = 0
    for seconds, pts, team in frames:
        local = best_delta(gt, seconds, pts, which, range(delta - DRIFT_WINDOW, delta + DRIFT_WINDOW + 1))
        if local is None:
            continue
        used += 1
        delta = local
        truth_pts, _ = gt[_gt_frame(seconds, local)]
        ours = flip(pts, which)
        pairs = match(ours, truth_pts)
        ours_n += len(ours)
        matched_n += len(pairs)
        clamped_all += int((np.minimum.reduce([ours[:, 0], 105.0 - ours[:, 0], ours[:, 1], 68.0 - ours[:, 1]])
                            <= CLAMP_TOL_M).sum()) if len(ours) else 0
        matched_ours = {i for i, _, _ in pairs}
        matched_truth = {j for _, j, _ in pairs}
        for i in range(len(ours)):
            if i in matched_ours:
                continue
            c = classify(ours[i], truth_pts, matched_truth)
            counts[c] += 1
            team_by_class[c][int(team[i])] += 1
    unmatched = sum(counts.values())
    return {
        "frames_evaluated": used, "product_markers": ours_n, "unmatched": unmatched,
        "unmatched_per_frame": round(unmatched / used, 2) if used else None,
        "precision": round(matched_n / ours_n, 4) if ours_n else None,
        "clamped_markers_all": clamped_all,
        "precision_without_clamped": round(matched_n / (ours_n - clamped_all), 4) if ours_n > clamped_all else None,
        "by_class": {c: {"count": counts[c], "per_frame": round(counts[c] / used, 2) if used else None,
                         "share_of_unmatched": round(counts[c] / unmatched, 3) if unmatched else None,
                         "team": {"home": team_by_class[c][0], "away": team_by_class[c][1],
                                  "none": team_by_class[c][-1]}}
                     for c in CLASSES},
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--frames", required=True)
    p.add_argument("--gt-rows", required=True)
    p.add_argument("--clip-start", type=float, required=True)
    p.add_argument("--dev-seconds", type=float, default=60.0)
    p.add_argument("--out", required=True)
    args = p.parse_args()
    payload = json.loads(Path(args.frames).read_text(encoding="utf-8"))
    frames = product_frames(payload, args.clip_start)
    gt = gt_by_frame(np.load(args.gt_rows))
    cut = args.clip_start + args.dev_seconds
    alignment = learn_alignment([f for f in frames if f[0] < cut], gt)
    result = {"alignment_from_dev": alignment,
              "held_out": attribute([f for f in frames if f[0] >= cut], gt, alignment)}
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["held_out"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
