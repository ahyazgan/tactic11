"""İki dilim ayarının çıktısını kare kare karşılaştırır: aday, referansın bulduğu oyuncuları buluyor mu?

Bu bir doğruluk ölçüsü DEĞİLDİR: referans (4 dilim) gerçek konum değil, başka bir ayarın
çıktısıdır. Gerçek konum verisi olan gündüz videosu diskte olmadığında (SoccerTrack videoları
token ister) hızlı ayarın referansa göre ne kaybettiğini söyler; referansın kendi hatasını söylemez.

Eşleme: aynı dakikalı karelerde oyuncu konumları Macar yöntemiyle, sahada en çok
`MATCH_RADIUS_M` metre uzaklıkla eşlenir.

    venv-cv\\Scripts\\python.exe -X utf8 -m scripts.soccertrack_v2.tile_agreement \\
        --reference t4_a.json t4_b.json --candidate t3_a.json t3_b.json --out sonuc.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import linear_sum_assignment

MATCH_RADIUS_M = 3.0
PITCH_M = np.array([105.0, 68.0])
BANDS = ("y_0_33", "y_33_67", "y_67_100")


def _positions(frame: dict[str, Any]) -> np.ndarray:
    players = frame.get("players") or []
    return np.array([[p["x"], p["y"]] for p in players], dtype=float).reshape(-1, 2)


def _band(y: float) -> str:
    return BANDS[0] if y < 100 / 3 else BANDS[1] if y < 200 / 3 else BANDS[2]


def match_frame(reference: np.ndarray, candidate: np.ndarray, radius_m: float = MATCH_RADIUS_M) -> list[bool]:
    """Her referans oyuncusu için: adayda `radius_m` içinde bire bir eşi var mı."""
    found = [False] * len(reference)
    if not len(reference) or not len(candidate):
        return found
    distance = np.linalg.norm((reference[:, None, :] - candidate[None, :, :]) * PITCH_M / 100.0, axis=2)
    rows, cols = linear_sum_assignment(np.where(distance <= radius_m, distance, 1e6))
    for r, c in zip(rows, cols, strict=True):
        found[r] = bool(distance[r, c] <= radius_m)
    return found


def compare(reference_frames: list[dict[str, Any]], candidate_frames: list[dict[str, Any]]) -> dict[str, Any]:
    """Aynı dakikalı kareleri eşler; referans oyuncularının adayda bulunma payını ve fazlalığı sayar."""
    by_minute = {round(float(f["minute"]), 4): f for f in candidate_frames if f.get("minute") is not None}
    reference_players = matched = candidate_players = frames = 0
    bands = {b: [0, 0] for b in BANDS}
    for frame in reference_frames:
        other = by_minute.get(round(float(frame["minute"]), 4)) if frame.get("minute") is not None else None
        if other is None:
            continue
        frames += 1
        ref, cand = _positions(frame), _positions(other)
        found = match_frame(ref, cand)
        reference_players += len(ref)
        candidate_players += len(cand)
        matched += sum(found)
        for (_, y), ok in zip(ref, found, strict=True):
            bands[_band(float(y))][0] += 1
            bands[_band(float(y))][1] += ok
    return {
        "frames_compared": frames, "reference_frames": len(reference_frames),
        "reference_players": reference_players, "candidate_players": candidate_players, "matched": matched,
        "recall_vs_reference": matched / reference_players if reference_players else 0.0,
        "extra_share": (candidate_players - matched) / candidate_players if candidate_players else 0.0,
        "band_recall": {b: (ok / n if n else None) for b, (n, ok) in bands.items()},
        "band_reference_players": {b: n for b, (n, _) in bands.items()},
    }


def _frames(path: Path) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as f:
        return list(json.load(f)["frames"])


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--reference", type=Path, nargs="+", required=True)
    p.add_argument("--candidate", type=Path, nargs="+", required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    if len(args.reference) != len(args.candidate):
        raise SystemExit("referans ve aday dosya sayısı eşit olmalı (pencere pencere)")
    windows = [compare(_frames(r), _frames(c)) | {"reference": r.name, "candidate": c.name}
               for r, c in zip(args.reference, args.candidate, strict=True)]
    total_ref = sum(w["reference_players"] for w in windows)
    total_cand = sum(w["candidate_players"] for w in windows)
    total_match = sum(w["matched"] for w in windows)
    bands = {b: [sum(w["band_reference_players"][b] for w in windows),
                 sum(round((w["band_recall"][b] or 0.0) * w["band_reference_players"][b]) for w in windows)]
             for b in BANDS}
    result = {
        "match_radius_m": MATCH_RADIUS_M, "windows": windows,
        "overall": {
            "reference_players": total_ref, "candidate_players": total_cand, "matched": total_match,
            "recall_vs_reference": total_match / total_ref if total_ref else 0.0,
            "extra_share": (total_cand - total_match) / total_cand if total_cand else 0.0,
            "band_recall": {b: (ok / n if n else None) for b, (n, ok) in bands.items()},
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps(result["overall"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
