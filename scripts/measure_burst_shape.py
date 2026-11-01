"""Patlama (burst) takibi şekil ölçümünü ne kadar bozar? — tam takip çıktısından benzetim.

Soru: her 30 sn'lik canlı segmentin yalnız ilk B saniyesini takip edersek
(`track_live --burst-seconds B`) işlem süresi ~B/30'a iner ve hiçbir segment
atlanmaz. Ama şekil bekçisinin (`engine.shape_watch`) dakikalık medyanları ne
kadar değişir?

Yöntem: tam takip edilmiş bir canlı klasörün kare JSON'larından her segmentin
ilk B saniyesindeki kareler seçilir (segment içi zaman = kare dakikası − segmentin
ilk karesinin dakikası). Her segment takipte zaten sıfırdan başladığı için bu,
B saniyelik gerçek koşunun iyi bir yaklaşığıdır; fark yalnız ileriye bakan
son işlemlerin B sınırında (ör. kısa iz süzgeci) olabilir.

Karşılaştırılan: 1 dakikalık pencerelerde, savunan takımın her metriğinin
medyanı (tam ↔ patlama), mutlak fark; ve bir dakikalık pencerede yeterli
(≥ `MIN_SAMPLES`) savunma karesi olup olmadığı.

    python -m scripts.measure_burst_shape --watch data/tracking/live/990741 \\
        --bursts 5,8,10,15 --out burst.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import median

from app.domain import TrackingFrame
from app.engine.shape_watch.compute import METRICS, MIN_SAMPLES, _directions, sample_frame


def load_segments(folder: Path) -> list[list[TrackingFrame]]:
    segs = []
    for path in sorted(folder.glob("seg_*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        frames = sorted((TrackingFrame.model_validate(f) for f in payload["frames"]), key=lambda f: f.minute)
        if frames:
            segs.append(frames)
    return segs


def burst(segs: list[list[TrackingFrame]], seconds: float) -> list[TrackingFrame]:
    out = []
    for frames in segs:
        t0 = frames[0].minute
        out += [f for f in frames if (f.minute - t0) * 60.0 < seconds]
    return out


def window_medians(frames: list[TrackingFrame], home: int, away: int,
                   home_attack: int = 0, window_min: int = 1) -> dict[tuple[int, int], dict]:
    """(dakika, takım) → {metrik: medyan, n: örnek sayısı}; yön tam veriden verilmez, her
    kümede ayrı çıkarılır (canlıda da patlama kareleri yönü kendisi bulur)."""
    dirs = _directions(frames, home, away, home_attack)
    buckets: dict[tuple[int, int], list] = {}
    start = int(min((f.minute for f in frames), default=0))
    for f in frames:
        owner = f.possession_team_external_id
        if owner not in (home, away):
            continue
        team = away if owner == home else home
        s = sample_frame(f, team, dirs.get((f.period, team), 0))
        if s is None:
            continue
        # kayan pencere: kare, başladığı dakika [w, w + window_min) içinde kalan her pencereye girer
        m = int(f.minute)
        for w in range(max(start, m - window_min + 1), m + 1):
            buckets.setdefault((w, team), []).append(s)
    end = max((f.minute for f in frames), default=0.0)
    out = {}
    for key, samples in buckets.items():
        if key[0] + window_min > end + 1e-6 and window_min > 1:
            continue   # verinin sonunda yarım kalan kayan pencere karşılaştırılmaz
        row: dict = {"n": len(samples)}
        for m in METRICS:
            vals = [v for s in samples if (v := getattr(s, m)) is not None]
            row[m] = median(vals) if vals else None
        out[key] = row
    return out


def compare(full: dict, part: dict) -> dict:
    keys = [k for k in full if full[k]["n"] >= MIN_SAMPLES]
    res: dict = {"windows_full": len(keys),
                 "windows_enough_after_burst": sum(1 for k in keys if part.get(k, {}).get("n", 0) >= MIN_SAMPLES)}
    for m in METRICS:
        diffs = [abs(full[k][m] - part[k][m]) for k in keys
                 if k in part and part[k]["n"] >= MIN_SAMPLES and full[k][m] is not None and part[k][m] is not None]
        res[m] = {"median_abs_diff_m": round(median(diffs), 2) if diffs else None,
                  "max_abs_diff_m": round(max(diffs), 2) if diffs else None, "windows": len(diffs)}
    return res


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--watch", required=True, help="canlı klasör (frames_ball/ varsa o, yoksa frames/)")
    p.add_argument("--bursts", default="5,8,10,15")
    p.add_argument("--home-attack", default="auto", choices=["auto", "x+", "x-"])
    p.add_argument("--window-min", type=int, default=1, help="pencere (dk); şekil bekçisinin 'şimdi'si 5 dk")
    p.add_argument("--out", default=None)
    args = p.parse_args()
    watch = Path(args.watch)
    folder = watch / "frames_ball" if (watch / "frames_ball").exists() else watch / "frames"
    segs = load_segments(folder)
    meta = json.loads(next(folder.glob("seg_*.json")).read_text(encoding="utf-8"))
    home, away = meta["home_team_external_id"], meta["away_team_external_id"]
    every = [f for s in segs for f in s]
    ha = {"x+": 1, "x-": -1}.get(args.home_attack, 0)
    full = window_medians(every, home, away, ha, args.window_min)
    report: dict = {"watch": str(watch), "folder": folder.name, "segments": len(segs), "frames": len(every),
                    "home_attack": args.home_attack, "window_min": args.window_min,
                    "min_samples": MIN_SAMPLES, "bursts": {}}
    for b in (float(v) for v in args.bursts.split(",")):
        part_frames = burst(segs, b)
        report["bursts"][f"{b:g}"] = {"frames": len(part_frames),
                                      **compare(full, window_medians(part_frames, home, away, ha, args.window_min))}
    text = json.dumps(report, ensure_ascii=False, indent=1)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
