"""Göz etiketli forma kutularına karşı takım ataması: üretim ve yeniden atama (venv).

GSR'si olmayan maçta takım doğruluğu, montajdan göz etiketlenen tespit kutularıyla
ölçülür (`docs/TAKIM-AYRIMI-GUNES.md`). Her kutu: ayak noktası kalibrasyonla sahaya
izdüşürülür, aynı andaki kareden ≤ 1 m'deki oyuncu alınır; o oyuncunun
`team_external_id_tracking` (üretim) ve `team_external_id` (yeniden atama) etiketi
göz etiketiyle karşılaştırılır. Etiket değerleri: Y (ev formasıyla eşlenen renk),
B (deplasman), other (hakem/kaleci/başka renk), pale (göz karar veremedi).

Girdi: kutular JSON'u (`kit_probe` çıktısı: i, frame "stem:sec", box) ve etiket
JSON'u ({"Y": [...], "B": [...], "other": [...], "paleY": [...], "paleB": [...], "home_label": "Y"}).
`paleY`/`paleB`: büyük montajdan karar verilebilen soluk kutular; ayrı raporlanır (C2).

    venv\\Scripts\\python.exe -X utf8 -m scripts.soccertrack_v2.eval_team_eye_labels \\
        --boxes kit_rows.json --labels labels.json --frames data/tracking/live/990752/frames_team \\
        --calibration data/tracking/calibrations/soccertrack_v2_132831_landmarks.json --out rapor.json
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

from app.tracking.calibration import PitchCalibration

MATCH_M = 1.0


def nearest_player(frame: dict[str, Any], px: float, py: float) -> dict[str, Any] | None:
    best: tuple[float, dict[str, Any]] | None = None
    for q in frame.get("players", []):
        d = float(np.hypot((q["x"] - px) * 1.05, (q["y"] - py) * 0.68))
        if d <= MATCH_M and (best is None or d < best[0]):
            best = (d, q)
    return best[1] if best else None


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--boxes", type=Path, required=True)
    p.add_argument("--labels", type=Path, required=True)
    p.add_argument("--frames", type=Path, required=True, help="yeniden atanmış frames klasörü")
    p.add_argument("--calibration", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    cal = PitchCalibration.load(args.calibration)
    boxes = json.loads(args.boxes.read_text(encoding="utf-8"))
    lab = json.loads(args.labels.read_text(encoding="utf-8"))
    eye = {i: k for k in ("Y", "B", "other", "paleY", "paleB") for i in lab.get(k, [])}
    home_label = lab.get("home_label", "Y")
    frames: dict[str, list[dict[str, Any]]] = {}
    payloads: dict[str, dict[str, Any]] = {}
    for path in args.frames.glob("seg_*.json"):
        payloads[path.stem] = json.loads(path.read_text(encoding="utf-8"))
        frames[path.stem] = payloads[path.stem]["frames"]
    conf: Counter[tuple[str, str, str]] = Counter()
    for b in boxes:
        stem, sec = b["frame"].split(":")
        fr = frames[stem]
        home, away = payloads[stem]["home_team_external_id"], payloads[stem]["away_team_external_id"]
        name = {home: "home", away: "away", None: "none"}
        t = fr[0]["minute"] * 60.0 + float(sec)
        f = min(fr, key=lambda f: abs(f["minute"] * 60.0 - t))
        x1, y1, x2, y2 = b["box"]
        px, py = cal.image_to_normalized((x1 + x2) / 2, y2)
        q = nearest_player(f, px, py)
        label = eye.get(b["i"], "pale")
        if q is None:
            conf[(label, "unmatched", "unmatched")] += 1
            continue
        prod = name.get(q.get("team_external_id_tracking", q.get("team_external_id")), "none")
        conf[(label, prod, name.get(q.get("team_external_id"), "none"))] += 1

    def accuracy(idx: int, clear: tuple[str, ...]) -> dict[str, float | int]:
        ok = tot = other_assigned = boxes_n = 0
        for (label, prod, new), n in conf.items():
            got = (prod, new)[idx]
            if label == "other" and got in ("home", "away"):
                other_assigned += n
            if label not in clear:
                continue
            boxes_n += n
            if got not in ("home", "away"):
                continue
            want = "home" if label.endswith(home_label) else "away"
            tot += n
            ok += n * (got == want)
        return {"correct": ok, "assigned": tot, "boxes": boxes_n, "accuracy_pct": round(100.0 * ok / max(1, tot), 1),
                "assigned_share_pct": round(100.0 * tot / max(1, boxes_n), 1), "other_assigned_team": other_assigned}

    report = {"boxes": len(boxes), "labels": {k: len(v) for k, v in lab.items() if isinstance(v, list)},
              "production": accuracy(0, ("Y", "B")), "refit": accuracy(1, ("Y", "B")),
              "pale_decidable": {"production": accuracy(0, ("paleY", "paleB")), "refit": accuracy(1, ("paleY", "paleB"))},
              "confusion": [{"eye": a, "production": b_, "refit": c, "n": n} for (a, b_, c), n in sorted(conf.items())]}
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("production", "refit", "pale_decidable")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
