"""Ürünün fiziksel yük oranlarını SoccerTrack v2 GSR gerçek konumlarıyla karşılaştırır.

İki taraf da AYNI hesapla (`app.engine.tracking.physical_load`) ölçülür: GT izleri
(oyuncu + kaleci, 25 fps) ve ürünün takım atanmış izleri. Karşılaştırılan şey toplam
değil ORANdır (oyuncu-dakika başına metre, yüksek hız ve sprint payı); bu yüzden kare
hizalaması gerekmez, yalnız aynı zaman penceresi gerekir.

    venv/Scripts/python.exe -X utf8 -m scripts.soccertrack_v2.physical_load_vs_gt ...
        --database isler.db --match-id 990814 --gt-rows gt.npy --out sonuc.json
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

import numpy as np

from app.engine.tracking.physical_load import Sample, rates, total_load

GT_FPS = 25.0
PLAYER_CATEGORIES = (1, 2)
GATES = {"m_per_player_min_relative": 0.15, "hsr_share_abs": 0.015, "sprint_share_abs": 0.0075}


def gt_tracks(rows: np.ndarray) -> dict[int, list[Sample]]:
    keep = rows[np.isin(rows[:, 3], PLAYER_CATEGORIES) & np.isfinite(rows[:, 6:8]).all(axis=1)]
    out: dict[int, list[Sample]] = {}
    for frame, track, x, y in zip(keep[:, 0], keep[:, 1], keep[:, 6], keep[:, 7], strict=True):
        out.setdefault(int(track), []).append((float(frame) / GT_FPS, float(x) + 52.5, float(y) + 34.0, None))
    return out


def product_tracks(database: str, match_id: int) -> dict[int, list[Sample]]:
    """Takım atanmış izler; saha yüzdesi metreye çevrilir."""
    out: dict[int, list[Sample]] = {}
    with sqlite3.connect(f"file:{Path(database).as_posix()}?mode=ro", uri=True) as db:
        rows = db.execute(
            "select minute, players_json from tracking_frames where match_external_id = ? order by minute", (match_id,))
        for minute, players_json in rows:
            for p in json.loads(players_json):
                if p.get("team_external_id") is None:
                    continue
                out.setdefault(int(p["player_external_id"]), []).append(
                    (minute * 60.0, p["x"] * 1.05, p["y"] * 0.68, p["team_external_id"]))
    return out


def compare(product: dict[str, Any], truth: dict[str, Any], gates: dict[str, float] = GATES) -> dict[str, Any]:
    relative = product["m_per_player_min"] / truth["m_per_player_min"] - 1.0
    hsr = product["hsr_share"] - truth["hsr_share"]
    sprint = product["sprint_share"] - truth["sprint_share"]
    checks = {
        "m_per_player_min": abs(relative) <= gates["m_per_player_min_relative"],
        "hsr_share": abs(hsr) <= gates["hsr_share_abs"],
        "sprint_share": abs(sprint) <= gates["sprint_share_abs"],
    }
    return {"m_per_player_min_relative_error": round(relative, 4), "hsr_share_error": round(hsr, 4),
            "sprint_share_error": round(sprint, 4), "checks": checks, "passed": all(checks.values())}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--database", required=True)
    p.add_argument("--match-id", type=int, required=True)
    p.add_argument("--gt-rows", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()
    product = rates(total_load(product_tracks(args.database, args.match_id)))
    truth = rates(total_load(gt_tracks(np.load(args.gt_rows))))
    result = {"gates": GATES, "product": product, "ground_truth": truth, **compare(product, truth)}
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
