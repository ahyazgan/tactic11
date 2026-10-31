"""Çapalı takım ataması deneyi — üretim koduna (dondurulmuş `teams.py`) dokunmaz.

Üretimde canlı akış her segmenti k=2 k-means ile SIFIRDAN kümeler; ilk geçerli
segmentin renkleri (çapa) yalnız kümelerin hangisinin ev sahibi olduğunu
sıralar. Bir segmentte kümeleme takımları değil ışığı ayırırsa (aydınlık beyaz /
gölge beyaz + mavi) çapa bunu düzeltemez. Adaylar:

- **production**: üretimdeki `TeamAssigner.fit(anchor)` (karşılaştırma tabanı)
- **nearest_anchor**: her takibin medyan rengi en yakın çapa rengine atanır;
  aykırılık eşikleri üretimdekiyle aynı biçimde, çapa merkezlerine göre
- **seeded**: k-means çapadan başlar (Lloyd), merkez çapadan `max_drift` RGB'den
  fazla kayarsa o segmentte nearest_anchor'a düşer; eşikler yeni merkezlere göre
- **gated_anchor**: segmentin üretim kümesi merkezlerinden biri çapadan
  `gate_distance` RGB'den (varsayılan üretimdeki `RGB_MIN_DISTANCE` = 30, "ayrı
  renk" eşiği) fazla uzaksa segment kümelemesi çökmüş sayılır ve nearest_anchor
  kullanılır; değilse üretim ataması aynen kalır (GT'siz çökme tespiti)
- **anchor_chroma**: en yakın çapa RENK ORANINDA (parlaklıktan bağımsız) seçilir,
  yalnız renk oranı aykırılığı uygulanır — gölgedeki beyazı tutar; siyah/gri
  giysiyi beyazdan ayıramama riski taşır

Çapa, zaman sırasında ilk segmentin üretim atamasından gelir (canlı işçinin
yaptığı gibi). Ölçüm: önbellekteki takiplerin uzamsal GT eşleşmesi (≤3 m),
yalnız saha oyuncuları; kaleciler ayrı forma giydiği için sayılmaz. Bu forma
rengi doğruluğu değil, konumla eşleşmiş takım uyumudur.

    venv-cv\\Scripts\\python.exe -X utf8 -m scripts.soccertrack_v2.anchored_team_experiment \\
        --cache data/tracking/bench/team_tele_v1 --segments 0 1 2 3 4 5 \\
        --gt data/tracking/bench/signal_quality_gt.npy \\
        --alignment data/tracking/bench/signal_quality_alignment.json --out dev.json
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import numpy as np

from app.tracking.calibration import PitchCalibration
from app.tracking.teams import (
    CHROMATICITY_MIN_DISTANCE,
    RGB_MIN_DISTANCE,
    TeamAssigner,
    chromaticity,
    distinct_team_colors,
)
from scripts.soccertrack_v2.evaluate_teams import matched

METHODS = ("production", "nearest_anchor", "seeded", "anchor_chroma", "gated_anchor")
OUTLIER_FACTOR = 2.5      # üretimdeki TeamAssigner varsayılanı


def load(cache: Path, segment: int) -> dict:
    return json.loads((cache / f"seg_{segment:04d}.json").read_text(encoding="utf-8"))


def eligible_tracks(payload: dict) -> set[int]:
    return {int(r[0]) for s in payload["samples"] for r in s["persons"]}


def track_features(payload: dict) -> tuple[list[int], np.ndarray]:
    """Üretimle aynı girdi: ≥2 gözlemli ve takip hattında kalan takiplerin medyan rengi."""
    eligible = eligible_tracks(payload)
    tracks = [int(t) for t, obs in payload["colors"].items() if len(obs) >= 2 and int(t) in eligible]
    feats = np.array([np.median(np.asarray(payload["colors"][str(t)], dtype=float), axis=0) for t in tracks])
    return tracks, feats.reshape(-1, 3)


def production(payload: dict, anchor: np.ndarray | None) -> tuple[dict[int, int | None], np.ndarray]:
    assigner = TeamAssigner()
    for track, colors in payload["colors"].items():
        for color in colors:
            assigner.observe(int(track), np.asarray(color, dtype=float))
    result = assigner.fit(anchor, eligible_tracks=eligible_tracks(payload))
    return result.team_by_track, result.centers


def classify(feats: np.ndarray, centers: np.ndarray, factor: float = OUTLIER_FACTOR) -> np.ndarray:
    """En yakın merkez (0/1) ya da -1; RGB ve renk oranı aykırılığı üretimdeki kuralla."""
    if not len(feats):
        return np.zeros(0, dtype=int)
    dist = np.linalg.norm(feats[:, None] - centers[None], axis=-1)
    labels = dist.argmin(axis=1)
    own = dist[np.arange(len(feats)), labels]
    threshold = max(float(np.median(own)) * factor, RGB_MIN_DISTANCE)
    tint = np.linalg.norm(chromaticity(feats) - chromaticity(centers)[labels], axis=1)
    out = labels.copy()
    for j in (0, 1):
        members = labels == j
        if not members.any():
            continue
        tint_threshold = max(float(np.median(tint[members])) * factor, CHROMATICITY_MIN_DISTANCE)
        out[members & (tint > tint_threshold)] = -1
    out[own > threshold] = -1
    return out


def classify_chroma(feats: np.ndarray, centers: np.ndarray, factor: float = OUTLIER_FACTOR) -> np.ndarray:
    """Renk oranında en yakın merkez (0/1) ya da -1 (renk oranı aykırılığı)."""
    if not len(feats):
        return np.zeros(0, dtype=int)
    tint = np.linalg.norm(chromaticity(feats)[:, None] - chromaticity(centers)[None], axis=-1)
    labels = tint.argmin(axis=1)
    own = tint[np.arange(len(feats)), labels]
    out = labels.copy()
    for j in (0, 1):
        members = labels == j
        if members.any():
            threshold = max(float(np.median(own[members])) * factor, CHROMATICITY_MIN_DISTANCE)
            out[members & (own > threshold)] = -1
    return out


def seeded_centers(feats: np.ndarray, anchor: np.ndarray, iters: int = 10) -> np.ndarray:
    centers = anchor.astype(float).copy()
    for _ in range(iters):
        labels = np.linalg.norm(feats[:, None] - centers[None], axis=-1).argmin(axis=1)
        for j in (0, 1):
            if (labels == j).any():
                centers[j] = np.median(feats[labels == j], axis=0)
    return centers


def assign(method: str, payload: dict, anchor: np.ndarray | None, max_drift: float,
           gate_distance: float = RGB_MIN_DISTANCE) -> tuple[dict[int, int | None], str]:
    if method == "production" or anchor is None:
        return production(payload, anchor)[0], "production"
    if method == "gated_anchor":
        teams, centers = production(payload, anchor)
        collapsed = not centers.any() or float(np.linalg.norm(centers - anchor, axis=1).max()) > gate_distance
        if not collapsed:
            return teams, "production"
        method = "nearest_anchor"
    tracks, feats = track_features(payload)
    centers, used = anchor, "anchor_chroma" if method == "anchor_chroma" else "nearest_anchor"
    if method == "seeded" and len(feats):
        moved = seeded_centers(feats, anchor)
        if np.linalg.norm(moved - anchor, axis=1).max() <= max_drift and distinct_team_colors(moved):
            centers, used = moved, "seeded"
    labels = classify_chroma(feats, centers) if method == "anchor_chroma" else classify(feats, centers)
    team = {t: (int(lab) if lab >= 0 else None) for t, lab in zip(tracks, labels, strict=True)}
    return {int(t): team.get(int(t)) for t in payload["colors"]}, used


def score(payload: dict, team_by_track: dict[int, int | None], gt: dict[int, np.ndarray], delta: int,
          stride: int, start_seconds: float = 600.0) -> list[tuple[int | None, int]]:
    cal = PitchCalibration.from_dict(payload["calibration"])
    empty = np.empty((0, 10))
    pairs = []
    for s in payload["samples"][::stride]:
        people = s["persons"]
        pts = np.array([cal.image_to_pitch_m((r[1] + r[3]) / 2, r[4]) for r in people]).reshape(-1, 2)
        t = start_seconds + payload["segment"] * 30 + s["seconds"]
        g = gt.get(round(t * 25) + 1 + delta, empty)
        for i, j in matched(pts, g, 3.0):
            if g[j, 3] == 1:  # yalnız saha oyuncusu
                pairs.append((team_by_track.get(int(people[i][0])), int(g[j, 2])))
    return pairs


def summary(pairs: list[tuple[int | None, int]], home_gt: int) -> dict:
    assigned = [(a, b) for a, b in pairs if a is not None]
    correct = sum((b == home_gt) == (a == 0) for a, b in assigned)
    return {"matched": len(pairs), "assigned": len(assigned), "correct": correct,
            "accuracy_when_assigned": round(correct / len(assigned), 4) if assigned else None,
            "correct_of_matched": round(correct / len(pairs), 4) if pairs else None,
            "unassigned_ratio": round(1 - len(assigned) / len(pairs), 4) if pairs else None}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cache", type=Path, required=True)
    p.add_argument("--segments", type=int, nargs="+", required=True, help="Değerlendirilen segmentler")
    p.add_argument("--anchor-segment", type=int, default=0, help="Çapanın öğrenildiği ilk segment")
    p.add_argument("--anchor-cache", type=Path, default=None,
                   help="Çapa segmentinin önbelleği (varsayılan --cache); maçın erken bir diliminden çapa için")
    p.add_argument("--start-seconds", type=float, default=600.0, help="Önbellekteki segment 0'ın maç saniyesi")
    p.add_argument("--gate-distance", type=float, default=RGB_MIN_DISTANCE,
                   help="gated_anchor: çapadan bu RGB uzaklığının ötesindeki küme merkezi = çökme")
    p.add_argument("--home-gt-team", type=int, choices=[0, 1], default=None,
                   help="Ev sahibi ↔ GT takım eşlemesi; verilmezse çapa segmentinden çoğunlukla seçilir")
    p.add_argument("--gt", type=Path, required=True)
    p.add_argument("--alignment", type=Path, required=True)
    p.add_argument("--methods", nargs="+", default=list(METHODS), choices=METHODS)
    p.add_argument("--max-drift", type=float, default=40.0, help="seeded: çapadan izin verilen RGB kayması")
    p.add_argument("--stride", type=int, default=2)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()

    rows = np.load(args.gt)
    ids, starts = np.unique(rows[:, 0].astype(int), return_index=True)
    gt = {int(f): a for f, a in zip(ids, np.split(rows, starts[1:]), strict=True)}
    delta = int(json.loads(args.alignment.read_text(encoding="utf-8"))["delta_frames"])

    anchor_cache = args.anchor_cache or args.cache
    anchor_payload = load(anchor_cache, args.anchor_segment)
    anchor_teams, anchor = production(anchor_payload, None)
    if not distinct_team_colors(anchor):
        p.error("çapa segmenti ayrı iki takım rengi vermiyor")
    home_gt = args.home_gt_team
    if home_gt is None:
        if args.anchor_cache is not None:
            p.error("--anchor-cache ile --home-gt-team verilmeli")
        pairs = score(anchor_payload, anchor_teams, gt, delta, args.stride, args.start_seconds)
        votes = Counter((a, b) for a, b in pairs if a is not None)
        home_gt = 0 if votes[(0, 0)] + votes[(1, 1)] >= votes[(0, 1)] + votes[(1, 0)] else 1

    report: dict = {"anchor_segment": args.anchor_segment, "anchor_cache": str(anchor_cache),
                    "start_seconds": args.start_seconds, "gate_distance": args.gate_distance,
                    "anchor_colors": anchor.round(1).tolist(),
                    "home_gt_team": home_gt, "max_drift": args.max_drift, "stride": args.stride,
                    "segments": args.segments, "methods": {}}
    for method in args.methods:
        per_segment, used_counts, all_pairs = {}, Counter(), []
        for seg in args.segments:
            payload = load(args.cache, seg)
            # çapa segmenti kendi renkleriyle öğrenildi: orada her yöntem üretimle aynıdır
            same = args.anchor_cache is None and seg == args.anchor_segment
            seg_anchor = None if same else anchor
            teams, used = assign(method, payload, seg_anchor, args.max_drift, args.gate_distance)
            used_counts[used] += 1
            pairs = score(payload, teams, gt, delta, args.stride, args.start_seconds)
            per_segment[seg] = summary(pairs, home_gt)
            all_pairs += pairs
        accs = [v["accuracy_when_assigned"] for v in per_segment.values() if v["accuracy_when_assigned"] is not None]
        report["methods"][method] = {"overall": summary(all_pairs, home_gt), "min_segment_accuracy": min(accs),
                                     "used": dict(used_counts), "per_segment": per_segment}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    for method, r in report["methods"].items():
        print(method, r["overall"], "min", r["min_segment_accuracy"], r["used"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
