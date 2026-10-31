"""İz içi takım oylaması (Viterbi) keşfi — geliştirme verisi, karar değil.

Takım hatalarının çoğu tek bir takip izinin içinde, iz başka takımdan bir
oyuncuya kaydığında oluşur. Her izin gözlem renkleri iki durumlu (ev/deplasman)
bir modelle yumuşatılır: maliyet = renk ile segment takım merkezi arası uzaklık /
iz içi medyan; takım değiştirmenin cezası `SWITCH`. Üretim ataması ve
çapa ayarları `anchored_team_experiment` ile aynıdır.

İki geliştirme dilimini (600–960 ve 1200–1560 sn) okur; sonuçları ekrana basar.

    venv-cv\\Scripts\\python.exe -X utf8 -m scripts.soccertrack_v2.track_vote_probe
"""
from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from app.tracking.calibration import PitchCalibration
from scripts.soccertrack_v2.anchored_team_experiment import load, production
from scripts.soccertrack_v2.evaluate_teams import matched

SLICES = [(Path("data/tracking/bench/team_tele_v1"), Path("data/tracking/bench/signal_quality_gt.npy"), 600),
          (Path("data/tracking/bench/team_tele_ctrl_v1"), Path("data/tracking/bench/team_ctrl_gt.npy"), 1200)]
SWITCH = [1.0, 2.0, 4.0, 8.0, 16.0]
DELTA = 9


def gt_index(path: Path) -> dict[int, np.ndarray]:
    rows = np.load(path)
    ids, starts = np.unique(rows[:, 0].astype(int), return_index=True)
    return {int(f): a for f, a in zip(ids, np.split(rows, starts[1:]), strict=True)}


def viterbi(cost: np.ndarray, switch: float) -> np.ndarray:
    """N×2 gözlem maliyetinden en ucuz 0/1 dizisi; her durum değişimi `switch` ekler."""
    acc = cost[0].copy()
    back = np.zeros((len(cost), 2), dtype=int)
    for t in range(1, len(cost)):
        stay, move = acc, acc[::-1] + switch
        back[t] = np.where(stay <= move, [0, 1], [1, 0])
        acc = np.minimum(stay, move) + cost[t]
    path = np.zeros(len(cost), dtype=int)
    path[-1] = int(acc.argmin())
    for t in range(len(cost) - 1, 0, -1):
        path[t - 1] = back[t, path[t]]
    return path


def main() -> int:
    _, anchor = production(load(SLICES[0][0], 0), None)
    res: Counter[tuple[object, bool | None]] = Counter()
    for cache, gt_path, start in SLICES:
        gt = gt_index(gt_path)
        for seg in range(12):
            pl = load(cache, seg)
            teams, centers = production(pl, None if (start == 600 and seg == 0) else anchor)
            cal = PitchCalibration.from_dict(pl["calibration"])
            k_of: Counter[int] = Counter()
            track: dict[int, list[tuple[int, int | None]]] = defaultdict(list)
            for s in pl["samples"]:
                people = s["persons"]
                g = gt.get(round((start + seg * 30 + s["seconds"]) * 25) + 1 + DELTA)
                pts = np.array([cal.image_to_pitch_m((r[1] + r[3]) / 2, r[4]) for r in people]).reshape(-1, 2)
                pairs = dict(matched(pts, g, 3.0)) if g is not None else {}
                for i, r in enumerate(people):
                    tid = int(r[0])
                    j = pairs.get(i)
                    track[tid].append((k_of[tid], None if j is None or g is None or g[j, 3] != 1 else int(g[j, 2])))
                    k_of[tid] += 1
            for tid, obs in track.items():
                lab = teams.get(tid)
                truth = [(k, gtt) for k, gtt in obs if gtt is not None]
                for _k, gtt in truth:
                    res[("production", None if lab is None else lab == gtt)] += 1
                cols = np.asarray(pl["colors"].get(str(tid), []), dtype=float).reshape(-1, 3)
                if lab is None or not centers.any() or len(cols) != len(obs):
                    for sw in SWITCH:
                        for _k, gtt in truth:
                            res[(sw, None if lab is None else lab == gtt)] += 1
                    continue
                d = np.linalg.norm(cols[:, None] - centers[None], axis=-1)
                cost = d / max(float(np.median(d.min(axis=1))), 1.0)
                for sw in SWITCH:
                    path = viterbi(cost, sw)
                    for k, gtt in truth:
                        res[(sw, int(path[k]) == gtt)] += 1
    for key in ["production", *SWITCH]:
        n = sum(v for (a, _), v in res.items() if a == key)
        print(key, "correct_of_matched", round(res[(key, True)] / n, 4), "unassigned", round(res[(key, None)] / n, 4))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
