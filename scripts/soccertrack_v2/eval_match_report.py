"""Maç raporunun (`engine.tracking.match_report`) sayılarını ve bulgularını gerçek konuma karşı ölç (venv).

Aynı `build_match_report` iki girdiyle çalışır: takip kareleri ve aynı anların GSR referansından
kurulmuş kareleri (`eval_shape_watch.gsr_frame_like`; takım eşlemesi konum eşleşmesinden, top
takip karesinden). Ölçülenler:

- dilim başına mutlak hata: genişlik, derinlik, kompaktlık, pres, savunma hattı (iki tarafta da
  güvenilir dilim); savunma hattı için hücum yönü referans kalecilerinden (`gt_attack_direction`)
  alınıp iki rapora da operatör girdisi olarak verilir, blok etiketi uyumu ayrıca sayılır;
- bulgu uyumu: takipteki bulguların (taraf, dilim, ölçü, yön) kaçı referansta da var (kesinlik),
  referanstakilerin kaçı takipte de var (duyarlılık).

Referans kalecileri içerir; ürün kaleciyi ayıramaz (raporun gördüğü tanım budur). Betimleyicidir;
eşik ayarı yapmaz.

    venv\\Scripts\\python.exe -X utf8 -m scripts.soccertrack_v2.eval_match_report \\
        --frames "data/tracking/live/990741/frames_ball/seg_*.json" \\
        --gt data/tracking/bench/gsr_132877_600_1200_corrected.npy \\
        --alignment data/tracking/bench/gsr_132877_alignment.json \\
        --calibration data/tracking/calibrations/soccertrack_v2_132877_landmarks.json \\
        --slice-minutes 1 5 --out rapor.json
"""
from __future__ import annotations

import argparse
import glob
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median
from typing import Any

import numpy as np

from app.domain import TrackingFrame
from app.engine.tracking.match_report import build_match_report
from app.tracking.calibration import PitchCalibration
from app.tracking.telestration import spots_from_frame
from scripts.soccertrack_v2.eval_shape_watch import gsr_frame_like
from scripts.soccertrack_v2.eval_telestration import (
    GT_KEEPER,
    gt_attack_direction,
    gt_frame,
    gt_index,
    gt_metres,
    home_gt_team,
    match,
)

METRICS = ("width_m", "depth_m", "compactness_m", "press_index", "def_line_m")


def paired_frames(raw: list[dict[str, Any]], gt: dict[int, np.ndarray], delta: int, calib: PitchCalibration,
                  home: int, away: int) -> tuple[list[TrackingFrame], list[TrackingFrame], int, int]:
    """(takip kareleri, aynı anların referans kareleri, eşleşen oyuncu çifti sayısı, ev sahibinin
    referans kalecilerinden hücum yönü)."""
    frames = [TrackingFrame.model_validate(f) for f in raw]
    pairs: Counter[tuple[int, int]] = Counter()
    for f in frames:
        g = gt.get(gt_frame(f.minute, delta))
        if g is None:
            continue
        players, _ball, _owner = spots_from_frame(f, home, away, calib)
        pts = np.array([(s.x_m, s.y_m) for s in players]).reshape(-1, 2)
        for i, j in match(pts, gt_metres(g)):
            if players[i].team is not None and g[j, 3] != GT_KEEPER:
                pairs[(players[i].team, int(g[j, 2]))] += 1
    hg = home_gt_team(pairs)
    team_of_gt = {hg: 0, 1 - hg: 1}
    tracked, ref = [], []
    for f, d in zip(frames, raw, strict=True):
        g = gt.get(gt_frame(f.minute, delta))
        if g is not None:
            tracked.append(f)
            ref.append(gsr_frame_like(d, g, team_of_gt, home, away))
    home_attack = gt_attack_direction(gt, [gt_frame(f.minute, delta) for f in tracked], hg)
    return tracked, ref, sum(pairs.values()), home_attack


def slices_of(frames: list[TrackingFrame], minutes: float) -> list[tuple[float, float, list[TrackingFrame]]]:
    buckets: dict[float, list[TrackingFrame]] = defaultdict(list)
    for f in frames:
        buckets[f.minute // minutes * minutes].append(f)
    return [(start, start + minutes, buckets[start]) for start in sorted(buckets)]


def finding_keys(report: dict[str, Any]) -> set[tuple[str, float, str, int]]:
    return {(f["side"], f["from_minute"], f["metric"], 1 if f["delta"] > 0 else -1) for f in report["findings"]}


def compare(tracked: list[TrackingFrame], ref: list[TrackingFrame], home: int, away: int, minutes: float,
            home_attack: int = 0) -> dict[str, Any]:
    a = build_match_report(home, away, slices_of(tracked, minutes), home_attack=home_attack)
    b = build_match_report(home, away, slices_of(ref, minutes), home_attack=home_attack)
    errors: dict[str, list[float]] = defaultdict(list)
    blocks = Counter()
    for sa, sb in zip(a["slices"], b["slices"], strict=True):
        for side in ("home", "away"):
            ta, tb = sa[side], sb[side]
            if not (ta["reliable"] and tb["reliable"]):
                continue
            for m in METRICS:
                if ta[m] is not None and tb[m] is not None:
                    errors[m].append(abs(ta[m] - tb[m]))
            if ta["block"] is not None and tb["block"] is not None:
                blocks["same" if ta["block"] == tb["block"] else "different"] += 1
    fa, fb = finding_keys(a), finding_keys(b)
    both = fa & fb
    return {
        "slices": len(a["slices"]),
        "reliable_slices": {side: [s[side]["reliable"] for s in a["slices"]].count(True) for side in ("home", "away")},
        "slice_abs_error": {m: {"n": len(v), "median": round(median(v), 2), "p90": round(float(np.percentile(v, 90)), 2),
                                "max": round(max(v), 2)} for m, v in errors.items() if v},
        "thresholds": a["thresholds"],
        "block_label_agreement": {**blocks, "rate": round(blocks["same"] / sum(blocks.values()), 3) if blocks else None},
        "findings": {
            "tracked": len(fa), "reference": len(fb), "both": len(both),
            "precision": round(len(both) / len(fa), 3) if fa else None,
            "recall": round(len(both) / len(fb), 3) if fb else None,
            "by_metric": {m: {"tracked": sum(k[2] == m for k in fa), "reference": sum(k[2] == m for k in fb),
                              "both": sum(k[2] == m for k in both)} for m in METRICS},
        },
        "summary": {"tracked": {s: a["teams"][s]["summary"] for s in ("home", "away")},
                    "reference": {s: b["teams"][s]["summary"] for s in ("home", "away")}},
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--frames", required=True)
    p.add_argument("--gt", type=Path, required=True)
    p.add_argument("--alignment", type=Path, required=True)
    p.add_argument("--calibration", type=Path, required=True)
    p.add_argument("--slice-minutes", type=float, nargs="+", default=[1.0, 5.0])
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    payloads = [json.loads(Path(path).read_text(encoding="utf-8")) for path in sorted(glob.glob(args.frames))]
    home, away = payloads[0]["home_team_external_id"], payloads[0]["away_team_external_id"]
    raw = sorted((f for d in payloads for f in d["frames"]), key=lambda f: f["minute"])
    delta = int(json.loads(args.alignment.read_text(encoding="utf-8"))["delta_frames"])
    tracked, ref, pairs, home_attack = paired_frames(raw, gt_index(np.load(args.gt)), delta,
                                        PitchCalibration.load(args.calibration), home, away)
    out = {"frames": args.frames, "gt": str(args.gt), "paired_frames": len(tracked), "matched_player_pairs": pairs,
           "home_attack_from_gt_keepers": home_attack,
           "by_slice_minutes": {f"{m:g}": compare(tracked, ref, home, away, m, home_attack) for m in args.slice_minutes}}
    args.out.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k != "by_slice_minutes"}, ensure_ascii=False))
    for m, r in out["by_slice_minutes"].items():
        print(m, "dk:", json.dumps({"err": r["slice_abs_error"], "blocks": r["block_label_agreement"],
                                     "findings": r["findings"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
