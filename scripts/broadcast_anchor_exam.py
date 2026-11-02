"""Yayın çapası geliştirme kapıları (venv-cv). Ön kayıt: docs/measurements/broadcast-anchor-preregistration.json.

    venv-cv\\Scripts\\python.exe -X utf8 -m scripts.broadcast_anchor_exam g1
    venv-cv\\Scripts\\python.exe -X utf8 -m scripts.broadcast_anchor_exam g2
    venv-cv\\Scripts\\python.exe -X utf8 -m scripts.broadcast_anchor_exam frames --match gamba_kashiwa --out <klasör>
    venv-cv\\Scripts\\python.exe -X utf8 -m scripts.broadcast_anchor_exam tally --dir <klasör>

G1: elle gerçek duruştan çizilmiş kusursuz çizgi maskesinde yöntem doğruyu buluyor mu?
G2: aynı karelerde gerçek çizgi maskesiyle. `frames` + `tally`: 5 geliştirme maçında main kabul
oranı ve G3 (other karelerde kabul). Kontrol maçı bu araçla koşulmaz.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from statistics import median

from app.tracking.broadcast_anchor import (
    GRASS_HSV_HIGH,
    GRASS_HSV_LOW,
    daylight_line_mask,
    find_broadcast_anchor,
)
from scripts.calibration_funnel import (
    MATCH_GROUP,
    homography_from_points,
    ideal_dist_map,
    other_frames,
    probe_distance_m,
    refined_pose,
    video_of,
)
from scripts.shot_exam import sampled_frames, wilson

POINTS = Path("docs/measurements/daylight-calibration-truth-points.json")
G1_MIN_ACCEPTED, G1_MAX_MEDIAN_M, G1_MAX_ANY_M = 13, 1.0, 5.0
G2_MIN_ACCEPTED, G2_MAX_MEDIAN_M, G2_MAX_ANY_M = 5, 2.0, 5.0
G3_MAX_OTHER_RATE = 0.05
MIN_GRASS_RATIO = 0.50


def truth_frames():
    """(maç, kare no, BGR, gerçek duruş); işaretlenemeyen kareler atlanır."""
    spec = json.loads(POINTS.read_text(encoding="utf-8"))
    for match, frames_spec in spec["frames"].items():
        wanted = {int(k): v["points"] for k, v in frames_spec.items() if v.get("points")}
        for i, frame in sampled_frames(video_of(match)):
            if i in wanted:
                yield match, i, frame, refined_pose(frame, homography_from_points(wanted[i]))


def gate(name: str, rows: list[dict], min_accepted: int, max_median: float, max_any: float) -> None:
    accepted = [r for r in rows if r["accepted"]]
    errors = [r["error_m"] for r in accepted]
    med = median(errors) if errors else None
    worst = max(errors) if errors else None
    passed = len(accepted) >= min_accepted and med is not None and med <= max_median and worst <= max_any
    print(f"{name}: kabul {len(accepted)}/{len(rows)}, medyan hata {med}, en kötü {worst} → "
          f"{'GEÇTİ' if passed else 'KALDI'}")


def truth_row(match: str, i: int, res, pose, size: tuple[int, int], seconds: float) -> dict:
    found = res.best_homography
    row = {"match": match, "frame": i, "accepted": res.accepted,
           "error_m": round(probe_distance_m(found, pose, size), 2) if found is not None else None,
           "note": res.note, "inlier": res.inlier, "explained": res.explained,
           "hypotheses": res.hypotheses, "seconds": round(seconds, 2)}
    print(json.dumps(row, ensure_ascii=False), flush=True)
    return row


def g1() -> int:
    rows = []
    for match, i, frame, pose in truth_frames():
        size = (frame.shape[1], frame.shape[0])
        dist, _px = ideal_dist_map(pose, size)
        start = time.perf_counter()
        res = find_broadcast_anchor(dist <= 0.5)
        rows.append(truth_row(match, i, res, pose, size, time.perf_counter() - start))
    gate("G1", rows, G1_MIN_ACCEPTED, G1_MAX_MEDIAN_M, G1_MAX_ANY_M)
    return 0


def g2() -> int:
    rows = []
    for match, i, frame, pose in truth_frames():
        size = (frame.shape[1], frame.shape[0])
        start = time.perf_counter()
        res = find_broadcast_anchor(daylight_line_mask(frame))
        rows.append(truth_row(match, i, res, pose, size, time.perf_counter() - start))
    gate("G2", rows, G2_MIN_ACCEPTED, G2_MAX_MEDIAN_M, G2_MAX_ANY_M)
    return 0


def frames(match: str, out: Path) -> int:
    """Maçın tüm örnek kareleri: etiket + kabul. Çim oranı düşük kare yönteme hiç girmez."""
    import cv2
    import numpy as np

    out.mkdir(parents=True, exist_ok=True)
    others = other_frames(match)
    rows = []
    for i, frame in sampled_frames(video_of(match)):
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        grass = float((cv2.inRange(hsv, np.array(GRASS_HSV_LOW), np.array(GRASS_HSV_HIGH)) > 0).mean())
        res = None if grass < MIN_GRASS_RATIO else find_broadcast_anchor(daylight_line_mask(frame))
        rows.append({"match": match, "frame": i, "label": "other" if i in others else "main",
                     "grass": round(grass, 3), "accepted": bool(res and res.accepted),
                     "note": res.note if res else "çim oranı düşük",
                     "inlier": res.inlier if res else 0.0, "explained": res.explained if res else 0.0})
    (out / f"{match}.json").write_text(json.dumps(rows, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"{match}: {len(rows)} kare")
    return 0


def tally(folder: Path) -> int:
    rows: list[dict] = []
    for match in MATCH_GROUP:
        part = json.loads((folder / f"{match}.json").read_text(encoding="utf-8"))
        rows += part
        for label in ("main", "other"):
            sel = [r for r in part if r["label"] == label]
            print(f"{match} {label}: kabul {sum(r['accepted'] for r in sel)}/{len(sel)}")
    for label in ("main", "other"):
        sel = [r for r in rows if r["label"] == label]
        hits = sum(r["accepted"] for r in sel)
        low, high = wilson(hits, len(sel))
        print(f"TOPLAM {label}: {hits}/{len(sel)} = %{100 * hits / len(sel):.1f} "
              f"(Wilson %{100 * low:.1f}-%{100 * high:.1f})")
    other = [r for r in rows if r["label"] == "other"]
    rate = sum(r["accepted"] for r in other) / len(other)
    print(f"G3: other kabul %{100 * rate:.1f} → {'GEÇTİ' if rate <= G3_MAX_OTHER_RATE else 'KALDI'}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("g1")
    sub.add_parser("g2")
    f = sub.add_parser("frames")
    f.add_argument("--match", required=True, choices=sorted(MATCH_GROUP))
    f.add_argument("--out", required=True)
    t = sub.add_parser("tally")
    t.add_argument("--dir", required=True)
    a = p.parse_args()
    if a.cmd == "g1":
        return g1()
    if a.cmd == "g2":
        return g2()
    if a.cmd == "frames":
        return frames(a.match, Path(a.out))
    return tally(Path(a.dir))


if __name__ == "__main__":
    raise SystemExit(main())
