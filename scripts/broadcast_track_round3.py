"""Yayın takibi 3. tur geliştirme kapıları (venv-cv): filtre duruş kesmez + sabit kamera bekçisi. Ürüne bağlı değil.

Ön kayıt: docs/measurements/broadcast-tracking-round3-preregistration.json. Görüntüler repoda değildir.

    venv-cv\\Scripts\\python.exe -X utf8 -m scripts.broadcast_track_round3 run --match kyoto_kobe --out <klasör>
    venv-cv\\Scripts\\python.exe -X utf8 -m scripts.broadcast_track_round3 pick --dir <klasör> --base <klasör> --grids <klasör>
    venv-cv\\Scripts\\python.exe -X utf8 -m scripts.broadcast_track_round3 gates --dir <klasör> --base <klasör>

`--base` mevcut kodun koşuları (<maç>__base.json); yeni üretilen örnek buna göre bulunur.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

import app.tracking.broadcast_track as bt
from app.tracking.fixed_camera import guard_poses
from scripts.broadcast_track_exam import FPS, track_video
from scripts.coverage_diagnosis import marked_samples, source
from scripts.tracking_funnel import mark_errors

TUNING = ("verdy_kashima", "kashiwa_hiroshima_final", "hiroshima_kyoto")
UNSEEN = ("gamba_kashiwa", "kashima_marinos", "kyoto_kobe")
TRUTH_POINTS = Path("docs/measurements/broadcast-track-round3-truth-points.json")
NEW_MARKS_MAX = 30
NEW_MARKS_MIN = 10
WRONG_M = 5.0
MAX_MEDIAN_M = 2.0
MAX_WRONG = 0.05
MIN_MAIN = 0.70
MIN_MATCH = 0.50
MAX_OTHER = 0.05


def run(match: str, out: Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    original = bt.BackfillingTracker
    bt.BackfillingTracker = lambda fps=FPS: original(fps, filters=False)  # type: ignore[misc, assignment]
    video, others = source(match)
    record = track_video(match, video, others, set())
    (out / f"{match}.json").write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    return 0


def guarded(record: dict) -> list[dict]:
    """Bekçiden sonra örnekler: reddedilen duruş üretilmemiş sayılır, `guard_rejected` işaretlenir."""
    posed = [s for s in record["samples"] if s["posed"]]
    keep = guard_poses([np.array(s["pose"]) for s in posed], tuple(record["size"]))
    verdict = {s["sample"]: k for s, k in zip(posed, keep, strict=True)}
    return [{**s, "posed": verdict.get(s["sample"], False), "guard_rejected": s["posed"] and not verdict[s["sample"]]}
            for s in record["samples"]]


def load(folder: Path, base: Path) -> dict[str, dict]:
    result = {}
    for path in sorted(folder.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        match = record["match"]
        before = json.loads((base / f"{match}__base.json").read_text(encoding="utf-8"))
        result[match] = {"samples": guarded(record), "base": {s["sample"]: s["posed"] for s in before["samples"]}}
    return result


def is_new(sample: dict, base: dict[int, bool]) -> bool:
    return sample["label"] == "main" and sample["posed"] and not base[sample["sample"]]


def pick_even(items: list, count: int) -> list:
    """Eşit aralıklı en çok `count` öğe; seçim yalnız sıraya bakar."""
    if len(items) <= count:
        return list(items)
    return [items[int(i * len(items) / count)] for i in range(count)]


def new_unmarked(data: dict[str, dict]) -> list[tuple[str, int]]:
    items = []
    for match, item in sorted(data.items()):
        marks = marked_samples(match)
        items += [(match, s["sample"]) for s in item["samples"] if is_new(s, item["base"]) and s["sample"] not in marks]
    return items


def pick(folder: Path, base: Path, grids: Path) -> int:
    """D2_new kareleri: duruş çizilmeden, ızgaralı. Seçim sayıdan bağımsız, duruşun değerine bakmaz."""
    import cv2

    from scripts.calibration_funnel import draw_grid
    from scripts.shot_exam import sampled_frames

    grids.mkdir(parents=True, exist_ok=True)
    chosen = pick_even(new_unmarked(load(folder, base)), NEW_MARKS_MAX)
    for match in sorted({m for m, _ in chosen}):
        wanted = {i for m, i in chosen if m == match}
        for i, frame in sampled_frames(source(match)[0]):
            if i in wanted:
                cv2.imwrite(str(grids / f"{match}_{i}.jpg"), draw_grid(frame), [cv2.IMWRITE_JPEG_QUALITY, 85])
    print(json.dumps(chosen, ensure_ascii=False))
    return 0


def truth_points(match: str) -> dict[int, list[dict]]:
    if not TRUTH_POINTS.exists():
        return {}
    frames = json.loads(TRUTH_POINTS.read_text(encoding="utf-8"))["frames"].get(match, {})
    return {int(k): v["points"] for k, v in frames.items() if len(v.get("points", [])) >= 4}


def accuracy(medians: list[float], minimum: int = 1) -> dict:
    if len(medians) < minimum:
        return {"n": len(medians), "passed": False}
    wrong = sum(m > WRONG_M for m in medians)
    median = float(np.median(medians))
    return {"n": len(medians), "median_m": round(median, 2), "wrong": wrong,
            "passed": median <= MAX_MEDIAN_M and wrong / len(medians) <= MAX_WRONG}


def group(samples: list[dict]) -> dict:
    main = [s for s in samples if s["label"] == "main"]
    other = [s for s in samples if s["label"] == "other"]
    return {"main": f"{sum(s['posed'] for s in main)}/{len(main)}",
            "main_rate": round(sum(s["posed"] for s in main) / len(main), 3),
            "other": f"{sum(s['posed'] for s in other)}/{len(other)}",
            "other_rate": round(sum(s["posed"] for s in other) / len(other), 3),
            "guard_rejected_main": sum(s["guard_rejected"] for s in main),
            "guard_rejected_other": sum(s["guard_rejected"] for s in other)}


def evaluate(data: dict[str, dict]) -> dict:
    per_match = {m: group(item["samples"]) for m, item in data.items()}
    samples = [s for item in data.values() for s in item["samples"]]
    pooled = group(samples)
    old, new = [], []
    for match, item in data.items():
        old_marks = marked_samples(match)
        new_marks = truth_points(match)
        for s in item["samples"]:
            if s["label"] != "main" or not s["posed"]:
                continue
            pose = np.array(s["pose"])
            if s["sample"] in new_marks:
                new.append(round(float(np.median(mark_errors(pose, new_marks[s["sample"]]))), 2))
            elif s["sample"] in old_marks:
                old.append(round(float(np.median(mark_errors(pose, old_marks[s["sample"]]))), 2))
    d1 = pooled["main_rate"] >= MIN_MAIN and all(r["main_rate"] >= MIN_MATCH for r in per_match.values())
    d2 = accuracy(old)
    d2_new = accuracy(new, NEW_MARKS_MIN)
    d3 = pooled["other_rate"] <= MAX_OTHER
    return {"per_match": per_match, "pooled": pooled,
            **{name: group([s for m in matches for s in data[m]["samples"]])
               for name, matches in (("tuning_3", TUNING), ("unseen_3", UNSEEN)) if all(m in data for m in matches)},
            "D1": d1, "D2": d2, "D2_new": d2_new, "D3": d3,
            "passed": bool(d1 and d2["passed"] and d2_new["passed"] and d3)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--match", required=True)
    r.add_argument("--out", type=Path, required=True)
    for name in ("pick", "gates"):
        c = sub.add_parser(name)
        c.add_argument("--dir", type=Path, required=True)
        c.add_argument("--base", type=Path, required=True)
        if name == "pick":
            c.add_argument("--grids", type=Path, required=True)
    args = parser.parse_args()
    if args.cmd == "run":
        return run(args.match, args.out)
    if args.cmd == "pick":
        return pick(args.dir, args.base, args.grids)
    json.dump(evaluate(load(args.dir, args.base)), sys.stdout, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
