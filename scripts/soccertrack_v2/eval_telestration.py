"""Telestrasyonu SoccerTrack v2 saha gerçeğiyle (GSR) karşılaştır.

Aynı `Telestrator` üç girdiyle kare kare çalıştırılır:

- **gt**: GSR oyuncu/kaleci konumları ve takımları (referans)
- **pred**: takip çıktısı (`TrackingFrame` JSON'ları) — üretimde çizilen
- **pred_gt_team**: takip konumları, takımı eşleşen GT oyuncusundan; tahmin ile
  bunun farkı takım atamasından, bununla gt'nin farkı tespit/konumdan gelir

Ortak tutulanlar (ölçülmeyenler): sahiplik her üç koşuda da takip karesinin
`possession_team_external_id` alanıdır (GSR'de top yok); hücum yönü GT
kalecilerinden çıkarılır ve hepsine verilir. Yani bu ölçüm sahiplik ve yön
doğruluğunu DEĞİL, konum + takım + hat/etiket hesabını sınar.

Hizalama `data/tracking/bench/signal_quality_alignment.json` (geliştirme
segmentlerinde sabitlendi): GT karesi = round(t·25) + 1 + delta, t = mutlak sn.

    venv-cv\\Scripts\\python.exe -X utf8 -m scripts.soccertrack_v2.eval_telestration \\
        --frames "data/tracking/live/990401/frames/seg_*.json" \\
        --gt data/tracking/bench/signal_quality_gt.npy \\
        --alignment data/tracking/bench/signal_quality_alignment.json \\
        --calibration data/tracking/calibrations/soccertrack_v2_117092.json \\
        --out docs/measurements/telestration-eval-117092.json
"""
from __future__ import annotations

import argparse
import glob
import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment

from app.domain import TrackingFrame
from app.tracking.calibration import PitchCalibration
from app.tracking.telestration import PlayerSpot, Telestrator, spots_from_frame

GT_PLAYER, GT_KEEPER = 1, 2
MATCH_RADIUS_M = 3.0
VARIANTS = ("gt", "pred", "pred_gt_team")


def gt_frame(minute: float, delta: int) -> int:
    return round(minute * 60.0 * 25) + 1 + delta


def gt_index(rows: np.ndarray) -> dict[int, np.ndarray]:
    rows = rows[np.isin(rows[:, 3], (GT_PLAYER, GT_KEEPER)) & np.isfinite(rows[:, 6:8]).all(axis=1)]
    ids, starts = np.unique(rows[:, 0].astype(int), return_index=True)
    return {int(f): a for f, a in zip(ids, np.split(rows, starts[1:]), strict=True)}


def gt_metres(g: np.ndarray) -> np.ndarray:
    return g[:, 6:8] + [52.5, 34.0]  # GSR merkez sıfırlı metre → 0..105 × 0..68


def match(pred: np.ndarray, gt: np.ndarray, radius: float = MATCH_RADIUS_M) -> list[tuple[int, int]]:
    if not len(pred) or not len(gt):
        return []
    dist = np.linalg.norm(pred[:, None] - gt[None], axis=-1)
    ii, jj = linear_sum_assignment(np.where(dist <= radius, dist, 1000 + dist))
    return [(int(i), int(j)) for i, j in zip(ii, jj, strict=True) if dist[i, j] <= radius]


def home_gt_team(pairs: Counter[tuple[int, int]]) -> int:
    """Takip 'ev sahibi' (0) hangi GT takımına (0 sol / 1 sağ) karşılık gelir."""
    same = pairs[(0, 0)] + pairs[(1, 1)]
    crossed = pairs[(0, 1)] + pairs[(1, 0)]
    return 0 if same >= crossed else 1


def gt_attack_direction(gt: dict[int, np.ndarray], frames: list[int], team: int) -> int:
    """GT kalecilerinden: `team`'in kalecisi rakibinkinden geride ise x+ hücum eder."""
    xs: dict[int, list[float]] = {0: [], 1: []}
    for f in frames:
        g = gt.get(f)
        if g is None:
            continue
        for row in g[g[:, 3] == GT_KEEPER]:
            if int(row[2]) in xs:
                xs[int(row[2])].append(float(row[6]))
    if not xs[0] or not xs[1]:
        return 0
    own, other = float(np.median(xs[team])), float(np.median(xs[1 - team]))
    return 1 if own < other else -1


@dataclass
class Record:
    gate: str
    label: str | None
    lines: list[tuple[float, float, float]] = field(default_factory=list)
    pressers: int = 0


def summarise(ref: list[Record], test: list[Record]) -> dict:
    drawn_ref = [r.gate == "drawn" for r in ref]
    drawn_test = [t.gate == "drawn" for t in test]
    both = [i for i, (a, b) in enumerate(zip(drawn_ref, drawn_test, strict=True)) if a and b]
    labelled = [i for i in both if ref[i].label and test[i].label]

    def block(label: str | None) -> str | None:
        return label.split(" · ")[0] if label else None

    depth = [abs(ref[i].lines[0][0] - test[i].lines[0][0]) for i in both if ref[i].lines and test[i].lines]
    gap = [abs((ref[i].lines[1][0] - ref[i].lines[0][0]) - (test[i].lines[1][0] - test[i].lines[0][0]))
           for i in both if len(ref[i].lines) > 1 and len(test[i].lines) > 1]

    def pct(values: list[bool]) -> float | None:
        return round(100.0 * sum(values) / len(values), 1) if values else None

    def stats(values: list[float]) -> dict | None:
        if not values:
            return None
        return {"n": len(values), "median_m": round(float(np.median(values)), 2),
                "p90_m": round(float(np.percentile(values, 90)), 2)}

    ref_labels = Counter(ref[i].label for i in labelled)
    majority = ref_labels.most_common(1)[0][1] if ref_labels else 0
    confusion = Counter(f"{block(ref[i].label)} -> {block(test[i].label)}" for i in labelled)
    recalls = [sum(1 for i in labelled if block(ref[i].label) == c and block(test[i].label) == c)
               / sum(1 for i in labelled if block(ref[i].label) == c)
               for c in {block(ref[i].label) for i in labelled}]
    return {
        "frames": len(ref),
        # taban: hep referansın en sık etiketini söyleyen sabit tahmin
        "ref_label_counts": dict(ref_labels),
        "majority_baseline_pct": round(100.0 * majority / len(labelled), 1) if labelled else None,
        # sınıf başına duyarlılığın ortalaması: baskın sınıf tek başına yükseltemez (sabit tahmin = 1/k)
        "block_balanced_pct": round(100.0 * float(np.mean(recalls)), 1) if recalls else None,
        "block_confusion": dict(sorted(confusion.items())),
        "drawn_ref": sum(drawn_ref), "drawn_test": sum(drawn_test), "drawn_both": len(both),
        "test_only": sum(1 for a, b in zip(drawn_ref, drawn_test, strict=True) if b and not a),
        "ref_only": sum(1 for a, b in zip(drawn_ref, drawn_test, strict=True) if a and not b),
        "label_n": len(labelled),
        "label_exact_pct": pct([ref[i].label == test[i].label for i in labelled]),
        "block_match_pct": pct([block(ref[i].label) == block(test[i].label) for i in labelled]),
        "press_agree_pct": pct([(ref[i].pressers > 0) == (test[i].pressers > 0) for i in both]),
        "def_line_error": stats(depth),
        "line_gap_error": stats(gap),
        "test_gates": dict(Counter(t.gate for t in test)),
    }


def common_frames(records: dict[str, list[Record]]) -> dict:
    keep = [i for i in range(len(records["gt"])) if all(records[v][i].gate == "drawn" for v in VARIANTS)]
    pick = {v: [records[v][i] for i in keep] for v in VARIANTS}
    return {"frames": len(keep), "pred": summarise(pick["gt"], pick["pred"]),
            "pred_gt_team": summarise(pick["gt"], pick["pred_gt_team"])}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--frames", required=True, help="Takip frames JSON (glob olabilir)")
    p.add_argument("--gt", type=Path, required=True)
    p.add_argument("--alignment", type=Path, required=True)
    p.add_argument("--calibration", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()

    paths = sorted(glob.glob(args.frames))
    payloads = [json.loads(Path(path).read_text(encoding="utf-8")) for path in paths]
    teams = {(d["home_team_external_id"], d["away_team_external_id"]) for d in payloads}
    if len(teams) != 1:
        p.error(f"bütün dosyalar aynı ev/deplasman kimliğini taşımalı: {teams}")
    home, away = teams.pop()
    frames = sorted((TrackingFrame.model_validate(f) for d in payloads for f in d["frames"]),
                    key=lambda f: f.minute)
    calib = PitchCalibration.load(args.calibration)
    delta = int(json.loads(args.alignment.read_text(encoding="utf-8"))["delta_frames"])
    gt = gt_index(np.load(args.gt))

    # 1) takip ev sahibi ↔ GT takımı ve her karenin eşleşmeleri
    pairs: Counter[tuple[int, int]] = Counter()
    matched_frames = []
    for f in frames:
        g = gt.get(gt_frame(f.minute, delta))
        players, ball, owner = spots_from_frame(f, home, away, calib)
        pts = np.array([(s.x_m, s.y_m) for s in players]).reshape(-1, 2)
        m = match(pts, gt_metres(g)) if g is not None else []
        for i, j in m:
            if players[i].team is not None and g is not None and g[j, 3] == GT_PLAYER:
                pairs[(players[i].team, int(g[j, 2]))] += 1
        matched_frames.append((f, g, players, ball, owner, m))
    home_gt = home_gt_team(pairs)
    team_of_gt = {home_gt: 0, 1 - home_gt: 1}
    gt_frames = [gt_frame(f.minute, delta) for f in frames]
    direction = gt_attack_direction(gt, gt_frames, home_gt)
    seconds = [f.minute * 60.0 for f in frames]
    steps = sorted(b - a for a, b in zip(seconds, seconds[1:], strict=False) if b > a)
    fps = 1.0 / steps[len(steps) // 2]

    tele = {v: Telestrator(fps, direction) for v in VARIANTS}
    records: dict[str, list[Record]] = {v: [] for v in VARIANTS}
    for _f, g, players, ball, owner, m in matched_frames:
        if g is None:
            continue
        gt_spots = [PlayerSpot(int(r[1]) + 100000, team_of_gt.get(int(r[2])), x, y)
                    for r, (x, y) in zip(g, gt_metres(g), strict=True)]
        relabelled = {i: team_of_gt.get(int(g[j, 2])) for i, j in m}
        inputs = {
            "gt": gt_spots,
            "pred": players,
            "pred_gt_team": [PlayerSpot(s.tid, relabelled.get(i), s.x_m, s.y_m) for i, s in enumerate(players)],
        }
        for v in VARIANTS:
            t = tele[v]
            t.marks(inputs[v], ball, calib, owner)
            records[v].append(Record(t.last_gate or "", t.label if t.last_gate == "drawn" else None,
                                     [(ln.depth, ln.y_min, ln.y_max) for ln in t.last_lines], t.last_pressers))

    matched_counts = [len(m) for *_, m in matched_frames]
    report = {
        "frames_files": [Path(path).as_posix() for path in paths],
        "frames_evaluated": len(records["gt"]),
        "fps": round(fps, 3),
        "home_is_gt_team": home_gt, "team_pairs": {f"{a}->{b}": n for (a, b), n in sorted(pairs.items())},
        "gt_home_attack_direction": direction,
        "matched_players_per_frame": round(float(np.mean(matched_counts)), 2) if matched_counts else 0.0,
        "held_constant": "possession = tracking frame possession; direction = GT keepers",
        "pred_vs_gt": summarise(records["gt"], records["pred"]),
        "pred_gt_team_vs_gt": summarise(records["gt"], records["pred_gt_team"]),
        "pred_vs_pred_gt_team": summarise(records["pred_gt_team"], records["pred"]),
        # adil ayrıştırma: üç koşunun da çizdiği aynı kareler
        "common_frames": common_frames(records),
        "gt_gates": dict(Counter(r.gate for r in records["gt"])),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
