"""Kalibrasyonun telestrasyon doğruluğuna etkisi: aynı tespit + aynı takım, farklı kalibrasyon.

Ham gözlem önbelleğindeki (`cache_observations`) piksel kutuları ve üretim takım
ataması (`TeamAssigner.fit`, ilk segmentin renkleri çapa) sabit tutulur; yalnız
ayak pikselini sahaya çeviren kalibrasyon değişir. Her kalibrasyonla aynı
`Telestrator` çalıştırılır ve GSR saha gerçeğiyle (GT konum + GT takım, aynı
ayar) karşılaştırılır (`eval_telestration.summarise`). Sahiplik her iki tarafta
topa en yakın tahmin oyuncusundan (≤4 m) değil, önbellekteki top pikselinin o
kalibrasyondaki konumundan çıkarılır; GT tarafında top yoktur, bu yüzden GT
koşusu da aynı (kalibrasyona bağlı) sahiplik dizisini kullanır. Hücum yönü GT
kalecilerinden.

Kalibrasyonlar bu veriye bakılarak seçilmedi: `soccertrack_v2_117092.json` GT
oyuncu eşleşmelerinden, `..._landmarks.json` veri setinin saha çizgisi
noktalarından kurulmuştur (çizgi doğrulaması 10,71 m'ye karşı 1,76 m;
docs/TOP-SECIMI-SONUCLARI.md).

    venv-cv\\Scripts\\python.exe -X utf8 -m scripts.soccertrack_v2.telestration_calibration_compare \\
        --cache data/tracking/bench/team_tele_v1 --gt data/tracking/bench/signal_quality_gt.npy \\
        --start-seconds 600 --out compare.json \\
        --calibrations data/tracking/calibrations/soccertrack_v2_117092.json \\
                       data/tracking/calibrations/soccertrack_v2_117092_landmarks.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

import app.tracking.telestration as telestration
from app.tracking.calibration import PitchCalibration
from app.tracking.telestration import PlayerSpot, Telestrator, _Projector
from scripts.soccertrack_v2.anchored_team_experiment import production
from scripts.soccertrack_v2.eval_telestration import (
    Record,
    gt_attack_direction,
    gt_index,
    summarise,
)

DELTA = 9
POSSESSION_MAX_M = 4.0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cache", type=Path, required=True)
    p.add_argument("--anchor-cache", type=Path, default=Path("data/tracking/bench/team_tele_v1"))
    p.add_argument("--gt", type=Path, required=True)
    p.add_argument("--start-seconds", type=float, required=True)
    p.add_argument("--calibrations", type=Path, nargs="+", required=True)
    p.add_argument("--home-gt-team", type=int, default=0)
    p.add_argument("--stride", type=int, default=3, help="Önbellek örnek adımı (12,5 fps / 3 ≈ 4,2 fps)")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--ignore-calibration-gate", action="store_true",
                   help="Telestrasyonun kalibrasyon hatası kapısını (LOO ≤ 1,5 m) kapat: LOO, oyuncudan "
                        "türetilmiş kalibrasyonda kendi noktalarına göre ölçülür ve çizgi hatasını yansıtmaz")
    args = p.parse_args()
    if args.ignore_calibration_gate:
        telestration.MAX_REPROJECTION_M = float("inf")

    gt = gt_index(np.load(args.gt))
    anchor_payload = json.loads((args.anchor_cache / "seg_0000.json").read_text(encoding="utf-8"))
    _, anchor = production(anchor_payload, None)
    payloads = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(args.cache.glob("seg_*.json"))]
    team_maps = [production(pl, None if args.cache == args.anchor_cache and pl["segment"] == 0 else anchor)[0]
                 for pl in payloads]
    samples = [(pl, tm, s) for pl, tm in zip(payloads, team_maps, strict=True) for s in pl["samples"][::args.stride]]
    frames = [round((args.start_seconds + pl["segment"] * 30 + s["seconds"]) * 25) + 1 + DELTA for pl, _, s in samples]
    direction = gt_attack_direction(gt, frames, args.home_gt_team)
    if direction == 0:
        p.error("GT kalecilerinden hücum yönü çıkarılamadı")
    fps = 12.5 / args.stride
    team_of_gt = {args.home_gt_team: 0, 1 - args.home_gt_team: 1}

    report: dict = {"cache": str(args.cache), "start_seconds": args.start_seconds, "stride": args.stride,
                    "calibration_gate": not args.ignore_calibration_gate,
                    "frames": len(samples), "gt_home_attack_direction": direction, "calibrations": {}}
    for cal_path in args.calibrations:
        cal = PitchCalibration.load(cal_path)
        proj = _Projector(cal)
        tele_pred, tele_gt = Telestrator(fps, direction), Telestrator(fps, direction)
        pred_rec: list[Record] = []
        gt_rec: list[Record] = []
        for (_pl, teams, s), f in zip(samples, frames, strict=True):
            g = gt.get(f)
            if g is None:
                continue
            people = s["persons"]
            feet = np.array([((r[1] + r[3]) / 2, r[4]) for r in people]).reshape(-1, 2)
            xy = proj.forward(feet) if len(feet) else np.empty((0, 2))
            spots = [PlayerSpot(int(r[0]), teams.get(int(r[0])), float(x), float(y))
                     for r, (x, y) in zip(people, xy, strict=True)]
            ball = None
            if s.get("ball"):
                bx, by = proj.forward(np.array([s["ball"][:2]]))[0]
                ball = (float(bx), float(by))
            owner = None
            if ball is not None:
                cand = [(float(np.hypot(sp.x_m - ball[0], sp.y_m - ball[1])), sp.team) for sp in spots
                        if sp.team in (0, 1)]
                if cand and min(cand)[0] <= POSSESSION_MAX_M:
                    owner = min(cand)[1]
            gm = g[:, 6:8] + [52.5, 34.0]
            gt_spots = [PlayerSpot(int(r[1]) + 100000, team_of_gt.get(int(r[2])), float(x), float(y))
                        for r, (x, y) in zip(g, gm, strict=True)]
            for t, sp_list, rec in ((tele_pred, spots, pred_rec), (tele_gt, gt_spots, gt_rec)):
                t.marks(sp_list, ball, cal, owner)
                rec.append(Record(t.last_gate or "", t.label if t.last_gate == "drawn" else None,
                                  [(ln.depth, ln.y_min, ln.y_max) for ln in t.last_lines], t.last_pressers))
        report["calibrations"][cal_path.name] = {**summarise(gt_rec, pred_rec),
                                                 "loo_error_m": round(cal.reprojection_error_m, 2)}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    for name, r in report["calibrations"].items():
        print(name, "drawn", r["drawn_test"], "/", r["frames"], "block", r["block_match_pct"],
              "base", r["majority_baseline_pct"], "bal", r["block_balanced_pct"], "line", r["def_line_error"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
