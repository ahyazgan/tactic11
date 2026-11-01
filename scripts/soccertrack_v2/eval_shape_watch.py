"""Şekil bekçisinin ölçümlerini (blok derinliği, genişlik, hat aralığı, boy) referansa karşı ölç (venv-cv).

`engine.shape_watch` eşikleri (6/6/4/6 m) sezgiseldir. Bu araç aynı kare için aynı
`sample_frame` hesabını iki girdiyle yapar — takip kareleri ve GSR referansı
(tercihen saha işaretlerine göre düzeltilmiş, `correct_gsr_positions`) — ve
farkı raporlar: kare başına mutlak hata (medyan/p90), bekçinin kullandığı
dakikalık medyanların mutlak hatası, ve her eşik için "ölçüm gürültüsü eşiğin
altında mı" payı. Genişlik için uç değere dayanıklı iki aday tanım da ölçülür
(`width_trim1`: her uçtan bir oyuncu atılmış yayılım, `width_p10_90`: %10–90
yüzdelik aralığı) — hayalet/ kenar tespitleri en-boy yayılımını şişirir. Hücum yönü iki tarafta da GSR kalecilerinden; takım eşlemesi
konum eşleşmesinden (eval_telestration ile aynı). Sahiplik kullanılmaz: her iki
takım için her karede şekil hesaplanır (geometri hatası sahiplik hatasından ayrı).

    venv-cv\\Scripts\\python.exe -X utf8 -m scripts.soccertrack_v2.eval_shape_watch \\
        --frames "data/tracking/live/990741/frames_ball/seg_*.json" \\
        --gt data/tracking/bench/gsr_132877_600_1200_corrected.npy \\
        --alignment data/tracking/bench/gsr_132877_alignment.json \\
        --calibration data/tracking/calibrations/soccertrack_v2_132877_landmarks.json --out rapor.json
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
from app.engine.shape_watch.compute import METRICS, THRESHOLDS_M, sample_frame

ALT_WIDTHS = ("width_trim1", "width_p10_90", "length_p90")


def alt_widths(frame: TrackingFrame, team: int, direction: int) -> dict[str, float] | None:
    """Uç değere dayanıklı adaylar: kırpılmış genişlik ve boy (p90 derinlik − en geri hat)."""
    pts = [(p.x / 100.0 * 105.0, p.y / 100.0 * 68.0) for p in frame.players if p.team_external_id == team and not p.is_keeper]
    if len(pts) < 6 or direction == 0:
        return None
    ys = np.sort(np.asarray([y for _x, y in pts]))
    depth = np.sort(np.asarray([x if direction > 0 else 105.0 - x for x, _y in pts]))
    back = depth[1:4].mean() if len(depth) >= 4 else depth[0]   # en geri 2.–4. oyuncu: izole kaleci/hayalet düşer
    return {"width_trim1": float(ys[-2] - ys[1]), "width_p10_90": float(np.percentile(ys, 90) - np.percentile(ys, 10)),
            "length_p90": float(np.percentile(depth, 90) - back)}
from app.tracking.calibration import PitchCalibration
from app.tracking.telestration import spots_from_frame
from scripts.soccertrack_v2.eval_telestration import (
    GT_KEEPER,
    gt_attack_direction,
    gt_frame,
    gt_index,
    gt_metres,
    home_gt_team,
    match,
)


def gsr_frame_like(frame: dict[str, Any], g: np.ndarray, team_of_gt: dict[int, int], home: int, away: int) -> TrackingFrame:
    """Takip karesinin kopyası, oyuncuları GSR'den (takım ve kaleci bilgisiyle)."""
    ids = {0: home, 1: away}
    players = []
    for row, (x, y) in zip(g, gt_metres(g), strict=True):
        t = team_of_gt.get(int(row[2]))
        players.append({"player_external_id": 200000 + int(row[1]), "x": float(np.clip(x / 105.0 * 100.0, 0, 100)),
                        "y": float(np.clip(y / 68.0 * 100.0, 0, 100)), "velocity_mps": None,
                        "team_external_id": ids.get(t) if t is not None else None, "is_actor": False,
                        "is_keeper": bool(row[3] == GT_KEEPER), "identity_estimated": False})
    return TrackingFrame.model_validate({**frame, "players": players})


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--frames", required=True)
    p.add_argument("--gt", type=Path, required=True)
    p.add_argument("--alignment", type=Path, required=True)
    p.add_argument("--calibration", type=Path, required=True)
    p.add_argument("--window-s", type=float, default=60.0, help="bekçinin medyan penceresi (sn)")
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    payloads = [json.loads(Path(f).read_text(encoding="utf-8")) for f in sorted(glob.glob(args.frames))]
    home, away = payloads[0]["home_team_external_id"], payloads[0]["away_team_external_id"]
    raw = sorted((f for d in payloads for f in d["frames"]), key=lambda f: f["minute"])
    frames = [TrackingFrame.model_validate(f) for f in raw]
    calib = PitchCalibration.load(args.calibration)
    delta = int(json.loads(args.alignment.read_text(encoding="utf-8"))["delta_frames"])
    gt = gt_index(np.load(args.gt))

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
    direction_home = gt_attack_direction(gt, [gt_frame(f.minute, delta) for f in frames], hg)
    direction = {home: direction_home, away: -direction_home}

    per_frame: dict[tuple[int, str], list[float]] = defaultdict(list)
    series: dict[tuple[int, str], list[tuple[float, float, float]]] = defaultdict(list)  # (minute, tracked, gsr)
    coverage = Counter()
    for f, d in zip(frames, raw, strict=True):
        g = gt.get(gt_frame(f.minute, delta))
        if g is None:
            continue
        ref = gsr_frame_like(d, g, team_of_gt, home, away)
        for team in (home, away):
            a, b = sample_frame(f, team, direction[team]), sample_frame(ref, team, direction[team])
            coverage["gsr"] += b is not None
            coverage["tracked"] += a is not None
            coverage["frames"] += 1
            if a is None or b is None:
                continue
            for m in METRICS:
                va, vb = getattr(a, m), getattr(b, m)
                if va is None or vb is None:
                    continue
                per_frame[(team, m)].append(abs(va - vb))
                series[(team, m)].append((f.minute, va, vb))
            wa, wb = alt_widths(f, team, direction[team]), alt_widths(ref, team, direction[team])
            if wa is not None and wb is not None:
                for m in ALT_WIDTHS:
                    per_frame[(team, m)].append(abs(wa[m] - wb[m]))
                    series[(team, m)].append((f.minute, wa[m], wb[m]))

    def window_medians(rows: list[tuple[float, float, float]]) -> list[float]:
        buckets: dict[int, list[tuple[float, float]]] = defaultdict(list)
        for minute, va, vb in rows:
            buckets[int(minute * 60.0 // args.window_s)].append((va, vb))
        return [abs(median(x for x, _ in v) - median(y for _, y in v)) for v in buckets.values() if len(v) >= 5]

    report: dict[str, Any] = {"frames_files": len(payloads), "home_is_gt_team": hg, "home_attack_direction": direction_home,
                              "coverage": dict(coverage), "window_s": args.window_s, "thresholds_m": THRESHOLDS_M, "metrics": {}}
    for m in METRICS + ALT_WIDTHS:
        errs = per_frame[(home, m)] + per_frame[(away, m)]
        wins = window_medians(series[(home, m)]) + window_medians(series[(away, m)])
        if not errs:
            continue
        report["metrics"][m] = {
            "frames": len(errs), "frame_abs_error_median_m": round(float(np.median(errs)), 2),
            "frame_abs_error_p90_m": round(float(np.percentile(errs, 90)), 2),
            "windows": len(wins), "window_median_abs_error_median_m": round(float(np.median(wins)), 2) if wins else None,
            "window_median_abs_error_p90_m": round(float(np.percentile(wins, 90)), 2) if wins else None,
            "share_of_windows_below_threshold": round(float(np.mean([w < THRESHOLDS_M.get(m, THRESHOLDS_M["length" if m.startswith("length") else "width"]) for w in wins])), 3) if wins else None,
            "gsr_value_median_m": round(float(np.median([vb for _t, _a, vb in series[(home, m)] + series[(away, m)]])), 1),
        }
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
