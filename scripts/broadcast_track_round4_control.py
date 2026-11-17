"""Yayın takibi 4. tur kör kontrolü (venv-cv). Ürüne bağlı değil; yöntem scripts.broadcast_track_round4.

Ön kayıt: docs/measurements/broadcast-tracking-round4-control-preregistration.json. Görüntüler repoda değildir.

    venv-cv\\Scripts\\python.exe -X utf8 -m scripts.broadcast_track_round4_control sheets --out <klasör>
    venv-cv\\Scripts\\python.exe -X utf8 -m scripts.broadcast_track_round4_control pick
    venv-cv\\Scripts\\python.exe -X utf8 -m scripts.broadcast_track_round4_control grids --out <klasör>
    venv-cv\\Scripts\\python.exe -X utf8 -m scripts.broadcast_track_round4_control track --match <maç> --work <klasör>
    venv-cv\\Scripts\\python.exe -X utf8 -m scripts.broadcast_track_round4_control score --work <klasör>

`track` maç başına TEK kez koşar (çıktı varsa reddeder), `score` sonuç dosyası varsa reddeder.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

import scripts.broadcast_track_exam as exam
import scripts.broadcast_track_round4 as round4
import scripts.coverage_diagnosis as diagnosis
from scripts.tracking_funnel import mark_errors

PLAN = Path("docs/measurements/broadcast-tracking-round4-control-preregistration.json")
LABELS = Path("docs/measurements/broadcast-track-round4-labels-control.json")
POINTS = Path("docs/measurements/broadcast-track-round4-truth-points-control.json")
RESULT = Path("docs/measurements/broadcast-track-round4-control-result.json")
MIN_POINTS = 4


def bind() -> None:
    """Eski sınav araçlarını bu kontrolün ön kaydına ve etiketlerine bağlar."""
    exam.PLAN = PLAN
    diagnosis.CONTROL_PLAN = PLAN
    diagnosis.CONTROL_LABELS = LABELS


def track(match: str, work: Path) -> int:
    """İki geçiş: filtreli (kamera için), sonra filtresiz + kamera önseli. Kamera bulunamazsa duruş yok sayılır."""
    exam.verify_freeze()
    if match not in exam.control_videos():
        raise SystemExit(f"kontrol maçı değil: {match}")
    final = work / "run" / f"{match}.json"
    if final.exists() or (work / "base" / f"{match}__base.json").exists():
        raise SystemExit(f"{match} zaten koşuldu; kontrol ikinci kez koşulmaz")
    round4.first(match, work / "base")
    try:
        round4.run(match, work / "base", work / "run")
    except SystemExit as error:
        print(error, flush=True)
        final.parent.mkdir(parents=True, exist_ok=True)
        final.write_text(json.dumps({"match": match, "camera": None}), encoding="utf-8")
    return 0


def samples_of(match: str, work: Path) -> tuple[list[dict], dict]:
    record = json.loads((work / "run" / f"{match}.json").read_text(encoding="utf-8"))
    if record["camera"] is None:
        base = json.loads((work / "base" / f"{match}__base.json").read_text(encoding="utf-8"))
        return [{**s, "posed": False, "guard_rejected": False} for s in base["samples"]], {"camera": None}
    return round4.guarded(record), {"camera": record["camera"], "anchor_sources": record["anchor_sources"],
                                    "states": record["states"]}


def score(work: Path) -> int:
    exam.verify_freeze()
    if RESULT.exists():
        raise SystemExit(f"sonuç zaten var: {RESULT}; kontrol ikinci kez puanlanmaz")
    points = json.loads(POINTS.read_text(encoding="utf-8"))["frames"]
    per_match, pooled, medians, worst = {}, [], [], 0.0
    for match in exam.control_videos():
        samples, extra = samples_of(match, work)
        marks = {int(k): v["points"] for k, v in points[match].items() if len(v.get("points", [])) >= MIN_POINTS}
        errors = [mark_errors(np.array(s["pose"]), marks[s["sample"]])
                  for s in samples if s["label"] == "main" and s["posed"] and s["sample"] in marks]
        frame_medians = [round(float(np.median(e)), 2) for e in errors]
        worst = max([worst, *(float(e.max()) for e in errors)])
        per_match[match] = {**round4.group(samples), **extra, "marked": len(marks),
                            "marked_produced": len(frame_medians),
                            "median_m": round(float(np.median(frame_medians)), 2) if frame_medians else None}
        pooled += samples
        medians += frame_medians
    total = round4.group(pooled)
    wrong = sum(m > exam.WRONG_M for m in medians)
    gates = {
        "C1_coverage": total["main_rate"] >= exam.C1_MIN_MAIN
        and all(m["main_rate"] >= exam.C1_MIN_MATCH for m in per_match.values()),
        "C2_accuracy": bool(medians) and float(np.median(medians)) <= exam.C2_MAX_MEDIAN_M,
        "C3_wrong_main": bool(medians) and wrong / len(medians) <= exam.C3_MAX_WRONG,
        "C4_wrong_other": total["other_rate"] <= exam.C4_MAX_OTHER,
        "C5_minimum_sample": len(medians) >= exam.C5_MIN_MARKED,
    }
    result = {"verdict": "GEÇTİ" if all(gates.values()) else "KALDI", "gates": gates, "pooled": total,
              "per_match": per_match, "marked_produced": len(medians),
              "median_m": round(float(np.median(medians)), 2) if medians else None,
              "wrong_over_5m": wrong, "worst_frame_median_m": max(medians, default=None),
              "worst_point_m": round(worst, 2)}
    RESULT.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=1))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("inspect")
    sub.add_parser("pick")
    for name in ("sheets", "grids"):
        sub.add_parser(name).add_argument("--out", type=Path, required=True)
    t = sub.add_parser("track")
    t.add_argument("--match", required=True)
    t.add_argument("--work", type=Path, required=True)
    sub.add_parser("score").add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    bind()
    if args.cmd == "inspect":
        return exam.control_inspect()
    if args.cmd == "sheets":
        return exam.control_sheets(args.out)
    if args.cmd == "pick":
        return exam.control_pick(LABELS)
    if args.cmd == "grids":
        return exam.control_grids(LABELS, args.out)
    if args.cmd == "track":
        return track(args.match, args.work)
    return score(args.work)


if __name__ == "__main__":
    sys.exit(main())
