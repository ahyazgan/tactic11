"""Tespit kalitesi denetimi: hayalet, izdüşüm hatası, kopya ve kaçırılan oyuncu.

Telestrasyon ölçümü savunan takımdaki tespitlerin yaklaşık yarısının GT'de 3 m
içinde karşılık bulmadığını gösterdi. Bu betik o tespitleri ayırır. GSR'nin görüntü
kutuları videonun koordinatında değildir (sabit ~30×32 px, dolgulu panorama); bu
yüzden GT saha konumları KENDİ kalibrasyonumuzla (TPS sayısal tersi, destek bölgesi
içinde) görüntüye izdüşürülür ve tespit kutularıyla görüntüde karşılaştırılır.

Her tespit için:
- **good**: sahada ≤3 m GT eşleşmesi (Macar eşleme)
- **projection**: sahada eşleşmedi ama görüntüde bir GT oyuncusunun ayağı tespitin
  ayağına ≤ `IMAGE_NEAR` × kutu yüksekliği uzaklıkta ve o GT başka tespitle eşleşmemiş
- **duplicate**: görüntüde yakın GT'si zaten başka bir tespitle eşleşmiş
- **ghost**: görüntüde yakınında hiç GT oyuncusu yok (yanlış tespit, saha dışı kişi)

Her GT oyuncusu (destek bölgesine izdüşenler) için: tespit edildi (good/projection)
ya da kaçırıldı. Sonuçlar saha bölgelerine göre de verilir.

    venv-cv\\Scripts\\python.exe -X utf8 -m scripts.soccertrack_v2.detection_audit \\
        --cache data/tracking/bench/team_tele_v1 --gt data/tracking/bench/signal_quality_gt.npy \\
        --start-seconds 600 --out audit.json
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment

from app.tracking.calibration import PitchCalibration
from app.tracking.telestration import _Projector

MATCH_RADIUS_M = 3.0
IMAGE_NEAR = 0.6   # kutu yüksekliğinin oranı
DELTA = 9


def gt_index(path: Path) -> dict[int, np.ndarray]:
    rows = np.load(path)
    rows = rows[np.isfinite(rows[:, 6:8]).all(axis=1)]
    ids, starts = np.unique(rows[:, 0].astype(int), return_index=True)
    return {int(f): a for f, a in zip(ids, np.split(rows, starts[1:]), strict=True)}


def zone(x: float, y: float) -> str:
    """Saha bölgesi: uzunlamasına üçte bir × enine (kameraya yakın/orta/uzak)."""
    third = ("sol", "orta", "sag")[min(2, int(x // 35))]
    band = ("bant0", "bant1", "bant2", "bant3")[min(3, max(0, int(y // 17)))]
    return f"{third}/{band}"


def classify(feet: np.ndarray, heights: np.ndarray, det_m: np.ndarray, gt_m: np.ndarray,
             gt_uv: np.ndarray, gt_ok: np.ndarray) -> tuple[list[str], np.ndarray]:
    """Tespit sınıfları ve GT başına 'tespit edildi' maskesi."""
    labels = ["ghost"] * len(feet)
    found = np.zeros(len(gt_m), dtype=bool)
    if len(feet) and len(gt_m):
        dist = np.linalg.norm(det_m[:, None] - gt_m[None], axis=-1)
        ii, jj = linear_sum_assignment(np.where(dist <= MATCH_RADIUS_M, dist, 1000 + dist))
        for i, j in zip(ii, jj, strict=True):
            if dist[i, j] <= MATCH_RADIUS_M:
                labels[i], found[j] = "good", True
        # sahada eşleşmeyenler: görüntüde izdüşmüş GT ayağına yakınlık
        img = np.linalg.norm(feet[:, None] - gt_uv[None], axis=-1) / np.maximum(heights[:, None], 1.0)
        img[:, ~gt_ok] = np.inf
        rest = [i for i in range(len(feet)) if labels[i] != "good"]
        for i in sorted(rest, key=lambda i: float(img[i].min())):
            near = np.where(img[i] <= IMAGE_NEAR)[0]
            if not len(near):
                continue
            free = [j for j in near if not found[j]]
            if free:
                j = min(free, key=lambda j: img[i, j])
                labels[i], found[j] = "projection", True
            else:
                labels[i] = "duplicate"
    return labels, found


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cache", type=Path, required=True)
    p.add_argument("--gt", type=Path, required=True)
    p.add_argument("--start-seconds", type=float, required=True)
    p.add_argument("--segments", type=int, nargs="+", default=list(range(12)))
    p.add_argument("--stride", type=int, default=4)
    p.add_argument("--calibration", type=Path, default=None,
                   help="Önbellekteki yerine bu kalibrasyon (aynı piksel tespitleri, farklı saha konumu)")
    p.add_argument("--delta", type=int, default=DELTA, help="GT kare kaydırması")
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()

    gt = gt_index(args.gt)
    det_counts: Counter[str] = Counter()
    det_zone: dict[str, Counter[str]] = {}
    gt_zone: dict[str, Counter[str]] = {}
    proj_err: list[float] = []
    heights_by: dict[str, list[float]] = {"good": [], "projection": [], "duplicate": [], "ghost": []}
    for seg in args.segments:
        payload = json.loads((args.cache / f"seg_{seg:04d}.json").read_text(encoding="utf-8"))
        cal = (PitchCalibration.load(args.calibration) if args.calibration
               else PitchCalibration.from_dict(payload["calibration"]))
        proj = _Projector(cal)
        for s in payload["samples"][::args.stride]:
            g = gt.get(round((args.start_seconds + seg * 30 + s["seconds"]) * 25) + 1 + args.delta)
            if g is None:
                continue
            g = g[g[:, 3] == 1]  # saha oyuncuları (kaleciler ayrı forma; sayılmaz)
            people = s["persons"]
            feet = np.array([((r[1] + r[3]) / 2, r[4]) for r in people]).reshape(-1, 2)
            heights = np.array([r[4] - r[2] for r in people], dtype=float)
            det_m = proj.forward(feet)
            gt_m = g[:, 6:8] + [52.5, 34.0]
            gt_uv, gt_ok = proj.project(gt_m)
            labels, found = classify(feet, heights, det_m, gt_m, gt_uv, gt_ok)
            for i, lab in enumerate(labels):
                det_counts[lab] += 1
                heights_by[lab].append(float(heights[i]))
                det_zone.setdefault(zone(*det_m[i]), Counter())[lab] += 1
                if lab == "projection":
                    proj_err.append(float(np.min(np.linalg.norm(gt_m - det_m[i], axis=1))))
            for j in np.where(gt_ok)[0]:
                gt_zone.setdefault(zone(*gt_m[j]), Counter())["found" if found[j] else "missed"] += 1
    total = sum(det_counts.values())
    gt_total = Counter()
    for c in gt_zone.values():
        gt_total.update(c)
    report = {
        "cache": str(args.cache), "start_seconds": args.start_seconds, "stride": args.stride,
        "calibration": str(args.calibration or "cache"), "delta": args.delta,
        "detections": total,
        "detection_share": {k: round(v / total, 3) for k, v in det_counts.most_common()},
        "box_height_median_px": {k: round(float(np.median(v)), 1) for k, v in heights_by.items() if v},
        "projection_error_m": ({"median": round(float(np.median(proj_err)), 2),
                                "p90": round(float(np.percentile(proj_err, 90)), 2)} if proj_err else None),
        "gt_players": sum(gt_total.values()),
        "recall": round(gt_total["found"] / max(1, sum(gt_total.values())), 3),
        "by_zone": {z: {"detections": sum(det_zone.get(z, Counter()).values()),
                        "ghost_share": round(det_zone.get(z, Counter())["ghost"]
                                             / max(1, sum(det_zone.get(z, Counter()).values())), 3),
                        "projection_share": round(det_zone.get(z, Counter())["projection"]
                                                  / max(1, sum(det_zone.get(z, Counter()).values())), 3),
                        "gt": sum(gt_zone.get(z, Counter()).values()),
                        "recall": round(gt_zone.get(z, Counter())["found"]
                                        / max(1, sum(gt_zone.get(z, Counter()).values())), 3)}
                    for z in sorted(set(det_zone) | set(gt_zone))},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "by_zone"}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
