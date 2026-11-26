"""Ürün çıktısını SoccerTrack v2 GSR gerçek konumlarıyla karşılaştırır: konum, kapsama, takım.

Girdi: ürün işinin kare çıktısı (JSON) ve `export_gt.py` satırları (kare, iz, takım, sınıf,
görüntü u/v, saha x/y metre merkezli, kutu en/boy).

Hizalama iki katmanlıdır ve yalnız `--dev-seconds` içindeki karelerden öğrenilir:
  1. Saha yönü: GT ve ürün ekseni ters olabilir; dört çevirmeden (x, y) en iyisi seçilir.
  2. Kare kayması: GT kare sayacı videoyla hizalı değildir; tek bir küresel kayma seçilir.
Sonra bunlar DONDURULUR. Kalan karelerde kayma yalnız +-`DRIFT_WINDOW` kare içinde aranır
(sayaç kayıyor; 117092 ölçümünde 90 saniyede 30 kare). Bu arama her karede en iyi uyanı
seçtiği için konum hatasını bir miktar iyimser gösterir.

Eşleme: Macar yöntemi, en çok `MATCH_RADIUS_M` metre. Takım: eşleşen ve iki tarafta da
takımı olan çiftlerde; takım numarası eşlemesi yine yalnız geliştirme karelerinden seçilir.

    venv-cv\\Scripts\\python.exe -X utf8 -m scripts.soccertrack_v2.product_vs_gt \\
        --frames job_x_frames.json --gt-rows gt.npy --clip-start 600 --out sonuc.json
"""
from __future__ import annotations

import argparse
import itertools
import json
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import linear_sum_assignment

MATCH_RADIUS_M = 3.0
GT_FPS = 25.0
GLOBAL_RANGE = range(-150, 151, 3)
DRIFT_WINDOW = 60
PLAYER_CATEGORIES = (1, 2)  # GSR: 1 oyuncu, 2 kaleci
FLIPS = tuple(itertools.product((False, True), repeat=2))

Frame = tuple[float, np.ndarray, np.ndarray]
Truth = dict[int, tuple[np.ndarray, np.ndarray]]


def flip(points: np.ndarray, which: tuple[bool, bool]) -> np.ndarray:
    """Metre cinsinden saha noktalarını (0..105, 0..68) x ve/veya y ekseninde çevirir."""
    out = points.astype(float).copy()
    if which[0]:
        out[:, 0] = 105.0 - out[:, 0]
    if which[1]:
        out[:, 1] = 68.0 - out[:, 1]
    return out


def match(ours: np.ndarray, truth: np.ndarray, radius_m: float = MATCH_RADIUS_M) -> list[tuple[int, int, float]]:
    """Bire bir eşleşmeler: (bizim sıra, GT sıra, metre)."""
    if not len(ours) or not len(truth):
        return []
    cost = np.sqrt(((ours[:, None, :] - truth[None, :, :]) ** 2).sum(-1))
    rows, cols = linear_sum_assignment(cost)
    return [(int(r), int(c), float(cost[r, c])) for r, c in zip(rows, cols, strict=True) if cost[r, c] <= radius_m]


def gt_by_frame(rows: np.ndarray) -> Truth:
    """Kare -> (saha noktaları metre 0..105/0..68, takım); yalnız konumu olan oyuncu ve kaleci."""
    out: Truth = {}
    keep = rows[np.isin(rows[:, 3], PLAYER_CATEGORIES) & np.isfinite(rows[:, 6:8]).all(axis=1)]
    for frame in np.unique(keep[:, 0]):
        part = keep[keep[:, 0] == frame]
        out[int(frame)] = (np.column_stack([part[:, 6] + 52.5, part[:, 7] + 34.0]), part[:, 2].astype(int))
    return out


def product_frames(payload: dict[str, Any], clip_start: float) -> list[Frame]:
    """(yarı içi saniye, saha noktaları metre, takım 0/1/-1) listesi."""
    teams = {payload.get("home_team_external_id"): 0, payload.get("away_team_external_id"): 1}
    out: list[Frame] = []
    for frame in payload["frames"]:
        players = frame.get("players") or []
        pts = np.array([[p["x"] * 1.05, p["y"] * 0.68] for p in players], dtype=float).reshape(-1, 2)
        team = np.array([teams.get(p.get("team_external_id"), -1) for p in players], dtype=int)
        out.append((float(frame["minute"]) * 60.0 + clip_start, pts, team))
    return out


def _gt_frame(seconds: float, delta: int) -> int:
    return round(seconds * GT_FPS) + 1 + delta


def _score(pts: np.ndarray, truth: np.ndarray) -> float:
    pairs = match(pts, truth)
    return len(pairs) - 0.01 * sum(d for _, _, d in pairs)


def best_delta(gt: Truth, seconds: float, pts: np.ndarray, which: tuple[bool, bool], deltas: range) -> int | None:
    """Verilen aralıkta en çok eşleşme veren kare kayması; hiç GT karesi yoksa None."""
    best: tuple[float, int] | None = None
    for delta in deltas:
        truth = gt.get(_gt_frame(seconds, delta))
        if truth is None:
            continue
        score = _score(flip(pts, which), truth[0])
        if best is None or score > best[0]:
            best = (score, delta)
    return None if best is None else best[1]


def learn_alignment(frames: list[Frame], gt: Truth) -> dict[str, Any]:
    """Geliştirme karelerinden saha yönü, küresel kare kayması ve takım eşlemesi."""
    votes: Counter[tuple[tuple[bool, bool], int]] = Counter()
    for seconds, pts, _team in frames:
        if len(pts) < 8:
            continue
        for which in FLIPS:
            delta = best_delta(gt, seconds, pts, which, GLOBAL_RANGE)
            if delta is not None:
                votes[(which, delta)] += len(match(flip(pts, which), gt[_gt_frame(seconds, delta)][0]))
    if not votes:
        raise ValueError("geliştirme karelerinde GT ile örtüşen kare yok")
    by_flip: Counter[tuple[bool, bool]] = Counter()
    for (which, _delta), n in votes.items():
        by_flip[which] += n
    which = by_flip.most_common(1)[0][0]
    delta = max((n, d) for (w, d), n in votes.items() if w == which)[1]
    straight = crossed = 0
    for seconds, pts, team in frames:
        local = best_delta(gt, seconds, pts, which, range(delta - DRIFT_WINDOW, delta + DRIFT_WINDOW + 1))
        if local is None:
            continue
        truth_pts, truth_team = gt[_gt_frame(seconds, local)]
        for i, j, _d in match(flip(pts, which), truth_pts):
            if team[i] >= 0 and truth_team[j] >= 0:
                straight += int(team[i] == truth_team[j])
                crossed += int(team[i] != truth_team[j])
    return {"flip_x": which[0], "flip_y": which[1], "delta_frames": delta, "team_crossed": crossed > straight}


def evaluate(frames: list[Frame], gt: Truth, alignment: dict[str, Any]) -> dict[str, Any]:
    """Dondurulmuş hizalamayla kapsama, kesinlik, konum hatası ve takım uyumu."""
    which = (bool(alignment["flip_x"]), bool(alignment["flip_y"]))
    delta, crossed = int(alignment["delta_frames"]), bool(alignment["team_crossed"])
    truth_n = ours_n = matched = team_n = team_ok = no_team = used = 0
    distances: list[float] = []
    for seconds, pts, team in frames:
        local = best_delta(gt, seconds, pts, which, range(delta - DRIFT_WINDOW, delta + DRIFT_WINDOW + 1))
        if local is None:
            continue
        used += 1
        delta = local
        truth_pts, truth_team = gt[_gt_frame(seconds, local)]
        pairs = match(flip(pts, which), truth_pts)
        truth_n += len(truth_pts)
        ours_n += len(pts)
        matched += len(pairs)
        distances += [d for _, _, d in pairs]
        for i, j, _d in pairs:
            if truth_team[j] < 0:
                continue
            if team[i] < 0:
                no_team += 1
                continue
            team_n += 1
            team_ok += int((team[i] == truth_team[j]) != crossed)
    return {
        "frames_evaluated": used, "gt_players": truth_n, "product_players": ours_n, "matched": matched,
        "recall": round(matched / truth_n, 4) if truth_n else None,
        "precision": round(matched / ours_n, 4) if ours_n else None,
        "median_distance_m": round(float(np.median(distances)), 3) if distances else None,
        "p90_distance_m": round(float(np.percentile(distances, 90)), 3) if distances else None,
        "team_labelled_pairs": team_n, "team_agreement": round(team_ok / team_n, 4) if team_n else None,
        "matched_without_team_share": round(no_team / matched, 4) if matched else None,
        "final_delta_frames": delta,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--frames", required=True)
    p.add_argument("--gt-rows", required=True)
    p.add_argument("--clip-start", type=float, required=True, help="klibin yarı içindeki başlangıcı (sn)")
    p.add_argument("--dev-seconds", type=float, default=60.0, help="hizalamanın öğrenildiği ilk saniyeler")
    p.add_argument("--out", required=True)
    args = p.parse_args()
    payload = json.loads(Path(args.frames).read_text(encoding="utf-8"))
    frames = product_frames(payload, args.clip_start)
    gt = gt_by_frame(np.load(args.gt_rows))
    cut = args.clip_start + args.dev_seconds
    dev = [f for f in frames if f[0] < cut]
    held_out = [f for f in frames if f[0] >= cut]
    alignment = learn_alignment(dev, gt)
    result = {"alignment_from_dev": alignment, "dev_seconds": args.dev_seconds, "match_radius_m": MATCH_RADIUS_M,
              "dev": evaluate(dev, gt, alignment), "held_out": evaluate(held_out, gt, alignment)}
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["held_out"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
