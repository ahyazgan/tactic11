"""Çapa+takip sınavı (venv-cv). Ön kayıt: docs/measurements/broadcast-tracking-preregistration.json.

    venv-cv\\Scripts\\python.exe -X utf8 -m scripts.broadcast_track_exam run --match kyoto_kobe --out <klasör>
    venv-cv\\Scripts\\python.exe -X utf8 -m scripts.broadcast_track_exam sample-grids --dir <klasör> --out <klasör>
    venv-cv\\Scripts\\python.exe -X utf8 -m scripts.broadcast_track_exam gates --dir <klasör>
    venv-cv\\Scripts\\python.exe -X utf8 -m scripts.broadcast_track_exam control-inspect
    venv-cv\\Scripts\\python.exe -X utf8 -m scripts.broadcast_track_exam control-sheets --out <klasör>
    venv-cv\\Scripts\\python.exe -X utf8 -m scripts.broadcast_track_exam control-pick --labels <json>
    venv-cv\\Scripts\\python.exe -X utf8 -m scripts.broadcast_track_exam control-grids --labels <json> --out <klasör>
    venv-cv\\Scripts\\python.exe -X utf8 -m scripts.broadcast_track_exam control-run --labels <json> --points <json> --out <json>

Elle çapa verilmez, sistem çapayı kendisi bulur. Görüntüler repoda değildir.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import Counter
from collections.abc import Iterator
from pathlib import Path

import numpy as np

from scripts.calibration_funnel import MATCH_GROUP, other_frames, video_of
from scripts.tracking_funnel import mark_errors

FPS = 15.0
SAMPLE_EVERY = 45           # 3 sn: shot_exam örnek aralığı
END_OFFSET = 44             # tracking_funnel uç karesi
MAX_SAMPLES = 120
START_POINTS = Path("docs/measurements/daylight-calibration-truth-points.json")
END_POINTS = Path("docs/measurements/tracking-funnel-end-truth-points.json")
DERIVED_POINTS = Path("docs/measurements/broadcast-track-derived-truth-points.json")
D1_MIN_MAIN = 0.60
D2_MAX_MEDIAN_M = 2.0
WRONG_M = 5.0
D2_MAX_WRONG = 0.05
D3_MAX_OTHER = 0.05
DERIVED_STATES = {"backfilled", "bridged"}
SHADOW_DEVELOPMENT_MATCH = "verdy_kashima"   # görülmüş kontrol, gölgeli; geliştirmede serbest
PLAN = Path("docs/measurements/broadcast-tracking-preregistration.json")
CONTROL_TRUTH_PER_MATCH = 30
SHEET_COLS, SHEET_ROWS, TILE_W, TILE_H = 5, 4, 320, 180   # shot_exam.write_sheet yerleşimi
C1_MIN_MAIN = 0.50
C1_MIN_MATCH = 0.35
C2_MAX_MEDIAN_M = 2.0
C3_MAX_WRONG = 0.05
C4_MAX_OTHER = 0.05
C5_MIN_MARKED = 15


def is_derived(item: dict) -> bool:
    """Tek kare çapası ya da ondan ileri takip dışında üretilmiş duruş mu?"""
    return item["state"] in DERIVED_STATES or item.get("origin") == "reloc"


def timed_frames(video: Path) -> Iterator[tuple[int, np.ndarray]]:
    """(15 fps ızgara no, kare): sıralı okur, her kareyi aramaz."""
    import cv2

    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise SystemExit(f"video açılamadı: {video}")
    fps = cap.get(cv2.CAP_PROP_FPS)
    index = 0
    try:
        for k in range(MAX_SAMPLES * SAMPLE_EVERY):
            target = int(round(k / FPS * fps))
            frame = None
            while index <= target:
                ok, frame = cap.read()
                index += 1
                if not ok:
                    return
            yield k, frame
    finally:
        cap.release()


def marked_frames(match: str) -> dict[int, list[dict]]:
    """15 fps ızgara no → el noktaları: klip başı ve klip sonu işaretleri."""
    marks: dict[int, list[dict]] = {}
    for path, offset in ((START_POINTS, 0), (END_POINTS, END_OFFSET), (DERIVED_POINTS, 0)):
        if not path.exists():
            continue
        frames = json.loads(path.read_text(encoding="utf-8"))["frames"].get(match, {})
        for sample, spec in frames.items():
            if spec.get("points"):
                marks[int(sample) * SAMPLE_EVERY + offset] = spec["points"]
    return marks


def run(match: str, out: Path) -> int:
    if MATCH_GROUP.get(match) != "development" and match != SHADOW_DEVELOPMENT_MATCH:
        print(f"{match}: geliştirme maçı değil", file=sys.stderr)
        return 2
    out.mkdir(parents=True, exist_ok=True)
    record = track_video(match, video_of(match), other_frames(match), set(marked_frames(match)))
    (out / f"{match}.json").write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    return 0


def track_video(match: str, video: Path, others: set[int], marks: set[int]) -> dict:
    from app.tracking.broadcast_track import BackfillingTracker, TrackFrame

    tracker = BackfillingTracker(FPS)
    states: Counter = Counter()
    kept: dict[int, TrackFrame] = {}
    produced: set[int] = set()
    total = 0
    size = (0, 0)
    start = time.perf_counter()
    for k, frame in timed_frames(video):
        size = (frame.shape[1], frame.shape[0])
        total += 1
        for done_k, result in tracker.feed(k, frame):
            states[result.state] += 1
            if result.homography is not None:
                produced.add(done_k)
            if done_k % SAMPLE_EVERY == 0 or done_k in marks:
                kept[done_k] = result
        if k % 450 == 0:
            print(match, k, dict(states), flush=True)
    seconds = time.perf_counter() - start
    samples = [{"sample": k // SAMPLE_EVERY, "label": "other" if k // SAMPLE_EVERY in others else "main",
                "posed": result.homography is not None, "state": result.state, "origin": result.origin,
                "pose": result.homography.tolist() if result.homography is not None else None}
               for k, result in sorted(kept.items()) if k % SAMPLE_EVERY == 0]
    poses = {str(k): {"state": result.state, "origin": result.origin, "pose": result.homography.tolist()}
             for k, result in kept.items() if result.homography is not None}
    return {"match": match, "frames": total, "produced": len(produced), "states": dict(states), "size": size,
            "seconds": round(seconds, 1), "samples": samples, "poses": poses}


def attach_evidence(record: dict) -> None:
    """İşaretli karelerde kayıtlı duruşun hatası; işaret dosyası koşudan sonra da eklenebilir."""
    marks = marked_frames(record["match"])
    record["marked_frames"] = len(marks)
    record["evidence"] = []
    for k, points in sorted(marks.items()):
        kept = record["poses"].get(str(k))
        if kept is not None:
            errors = mark_errors(np.array(kept["pose"]), points)
            record["evidence"].append({"k": k, "median_m": round(float(np.median(errors)), 2),
                                       "worst_m": round(float(errors.max()), 2), "state": kept["state"],
                                       "origin": kept.get("origin", "anchor")})


def sample_grids(folder: Path, out: Path) -> int:
    """Türetilmiş duruşlu (geriye dolan, köprülenen) tüm main örneklerin ızgaralı karesi. Duruş çizilmez."""
    import cv2

    from scripts.calibration_funnel import draw_grid
    from scripts.shot_exam import sampled_frames

    out.mkdir(parents=True, exist_ok=True)
    for path in sorted(folder.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        marks = marked_frames(record["match"])
        wanted = {s["sample"] for s in record["samples"]
                  if s["label"] == "main" and s["posed"] and is_derived(s)
                  and s["sample"] * SAMPLE_EVERY not in marks}
        for i, frame in sampled_frames(video_of(record["match"])):
            if i in wanted:
                cv2.imwrite(str(out / f"{record['match']}_{i}.jpg"), draw_grid(frame), [cv2.IMWRITE_JPEG_QUALITY, 85])
    return 0


def _median(values: list[float]) -> float | None:
    return float(np.median(values)) if values else None


def _accurate(medians: list[float]) -> bool:
    """Kanıt yoksa geçmiş sayılmaz."""
    if not medians:
        return False
    wrong = sum(m > WRONG_M for m in medians) / len(medians)
    return float(np.median(medians)) <= D2_MAX_MEDIAN_M and wrong <= D2_MAX_WRONG


def evaluate(records: list[dict]) -> dict:
    samples = [s for r in records for s in r["samples"]]
    main = [s for s in samples if s["label"] == "main"]
    other = [s for s in samples if s["label"] == "other"]
    evidence = [e for r in records for e in r["evidence"]]
    medians = [e["median_m"] for e in evidence]
    wrong = sum(m > WRONG_M for m in medians)
    main_rate = sum(s["posed"] for s in main) / len(main) if main else 0.0
    other_rate = sum(s["posed"] for s in other) / len(other) if other else 0.0
    median = _median(medians)
    return {
        "per_match": {r["match"]: {
            "main_posed": sum(s["posed"] for s in r["samples"] if s["label"] == "main"),
            "main": sum(s["label"] == "main" for s in r["samples"]),
            "other_posed": sum(s["posed"] for s in r["samples"] if s["label"] == "other"),
            "other": sum(s["label"] == "other" for s in r["samples"]),
            "frames": r["frames"], "produced": r["produced"], "states": r["states"],
            "fps": round(r["frames"] / r["seconds"], 2) if r["seconds"] else None,
        } for r in records},
        "main_posed": sum(s["posed"] for s in main), "main": len(main), "main_rate": round(main_rate, 3),
        "other_posed": sum(s["posed"] for s in other), "other": len(other), "other_rate": round(other_rate, 3),
        "marked_produced": len(medians), "marked_total": sum(r["marked_frames"] for r in records),
        "median_m": median, "wrong_over_5m": wrong,
        "worst_median_m": max(medians) if medians else None,
        "derived_marked_produced": sum(is_derived(e) for e in evidence),
        "derived_median_m": _median([e["median_m"] for e in evidence if is_derived(e)]),
        "derived_wrong_over_5m": sum(is_derived(e) and e["median_m"] > WRONG_M for e in evidence),
        "reloc_marked_produced": sum(e.get("origin") == "reloc" for e in evidence),
        "reloc_median_m": _median([e["median_m"] for e in evidence if e.get("origin") == "reloc"]),
        "reloc_wrong_over_5m": sum(e.get("origin") == "reloc" and e["median_m"] > WRONG_M for e in evidence),
        "main_posed_by_reloc": sum(s["posed"] and s.get("origin") == "reloc" for s in main),
        "D1": main_rate >= D1_MIN_MAIN,
        "D2": _accurate(medians),
        "D2_derived": _accurate([e["median_m"] for e in evidence if is_derived(e)]),
        "D3": other_rate <= D3_MAX_OTHER,
    }


def gates(folder: Path) -> int:
    records = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(folder.glob("*.json"))]
    for record in records:
        attach_evidence(record)
    result = evaluate(records)
    print(json.dumps(result, ensure_ascii=False, indent=1))
    print("evidence", [(r["match"][:5], e["k"], e["median_m"], e["worst_m"], e["state"]) for r in records for e in r["evidence"]])
    return 0


def control_videos() -> dict[str, Path]:
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    return {name: Path(item["file"]) for name, item in plan["control_matches"].items()}


def sha256_lf(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def verify_freeze() -> None:
    frozen = json.loads(PLAN.read_text(encoding="utf-8"))["freeze_before_control"]["code_sha256_lf"]
    for name, expected in frozen.items():
        if sha256_lf(Path(name)) != expected:
            raise SystemExit(f"dondurulmuş kod değişmiş: {name}; kontrol koşulmaz")


def control_inspect() -> int:
    """Yalnız sayı: görüntü yazmaz, gündüz kontrolü içindir."""
    import cv2

    from scripts.shot_exam import sampled_frames

    for name, video in control_videos().items():
        values = [float(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).mean()) for _, f in sampled_frames(video)]
        print(f"{name}: {len(values)} örnek, parlaklık medyan {np.median(values):.0f}, "
              f"en düşük {min(values):.0f}, en yüksek {max(values):.0f}")
    return 0


def control_sheets(out: Path) -> int:
    """Etiket sayfaları: numaralı küçük kareler, yöntem çıktısı içermez."""
    import cv2

    from scripts.shot_exam import sampled_frames, write_sheet

    out.mkdir(parents=True, exist_ok=True)
    per_sheet = SHEET_COLS * SHEET_ROWS
    for name, video in control_videos().items():
        tiles: list[np.ndarray] = []
        page = 0
        for i, frame in sampled_frames(video):
            tile = cv2.resize(frame, (TILE_W, TILE_H), interpolation=cv2.INTER_AREA)
            cv2.rectangle(tile, (0, 0), (70, 34), (0, 0, 0), -1)
            cv2.putText(tile, str(i), (6, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.85, (0, 255, 255), 2)
            tiles.append(tile)
            if len(tiles) == per_sheet:
                write_sheet(out / f"{name}_{page:02d}.jpg", tiles)
                page, tiles = page + 1, []
        if tiles:
            write_sheet(out / f"{name}_{page:02d}.jpg", tiles)
    return 0


def picked_frames(labels: dict, video: Path, name: str) -> list[int]:
    """Gerçek duruş işaretlenecek kareler: yalnız etiket dizisinden, görüntüye bakmadan."""
    from scripts.calibration_funnel import pick_frames
    from scripts.shot_exam import sampled_frames

    count = sum(1 for _ in sampled_frames(video))
    return pick_frames(count, set(labels[name]["other"]), CONTROL_TRUTH_PER_MATCH)


def control_pick(labels_path: Path) -> int:
    labels = json.loads(labels_path.read_text(encoding="utf-8"))
    for name, video in control_videos().items():
        print(name, picked_frames(labels, video, name))
    return 0


def control_grids(labels_path: Path, out: Path) -> int:
    """Seçilen karelerin ızgaralı hali. Yöntem koşulmaz, duruş çizilmez."""
    import cv2

    from scripts.calibration_funnel import draw_grid
    from scripts.shot_exam import sampled_frames

    out.mkdir(parents=True, exist_ok=True)
    labels = json.loads(labels_path.read_text(encoding="utf-8"))
    for name, video in control_videos().items():
        wanted = set(picked_frames(labels, video, name))
        for i, frame in sampled_frames(video):
            if i in wanted:
                cv2.imwrite(str(out / f"{name}_{i}.jpg"), draw_grid(frame), [cv2.IMWRITE_JPEG_QUALITY, 85])
    return 0


def evaluate_control(records: list[dict]) -> dict:
    """Ön kayıttaki C1-C5. Türetilmiş duruşlar ayrıca raporlanır, ölçüt değildir."""
    base = evaluate(records)
    rates = [m["main_posed"] / m["main"] if m["main"] else 0.0 for m in base["per_match"].values()]
    medians = [e["median_m"] for r in records for e in r["evidence"]]
    wrong = base["wrong_over_5m"] / len(medians) if medians else 1.0
    gates = {
        "C1_coverage": base["main_rate"] >= C1_MIN_MAIN and min(rates) >= C1_MIN_MATCH,
        "C2_accuracy": base["median_m"] is not None and base["median_m"] <= C2_MAX_MEDIAN_M,
        "C3_wrong_main": wrong <= C3_MAX_WRONG,
        "C4_wrong_other": base["other_rate"] <= C4_MAX_OTHER,
        "C5_minimum_sample": len(medians) >= C5_MIN_MARKED,
    }
    for key in ("D1", "D2", "D2_derived", "D3"):
        base.pop(key)
    return {"verdict": "GEÇTİ" if all(gates.values()) else "KALDI", "gates": gates, **base,
            "worst_point_m": max((e["worst_m"] for r in records for e in r["evidence"]), default=None)}


def control_run(labels_path: Path, points_path: Path, out: Path) -> int:
    """TEK koşu. Kare dökümü üretmez, yalnız toplamları yazar; aynı kontrolle ikinci deneme yoktur."""
    verify_freeze()
    if out.exists():
        raise SystemExit(f"sonuç zaten var: {out}; kontrol ikinci kez koşulmaz")
    labels = json.loads(labels_path.read_text(encoding="utf-8"))
    points = json.loads(points_path.read_text(encoding="utf-8"))["frames"]
    records = []
    for name, video in control_videos().items():
        marks = {int(k) * SAMPLE_EVERY: v["points"] for k, v in points[name].items() if v.get("points")}
        record = track_video(name, video, set(labels[name]["other"]), set(marks))
        record["marked_frames"] = len(marks)
        record["evidence"] = []
        for k, frame_points in sorted(marks.items()):
            kept = record["poses"].get(str(k))
            if kept is not None:
                errors = mark_errors(np.array(kept["pose"]), frame_points)
                record["evidence"].append({"median_m": round(float(np.median(errors)), 2),
                                           "worst_m": round(float(errors.max()), 2),
                                           "state": kept["state"], "origin": kept["origin"]})
        records.append(record)
    result = evaluate_control(records)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=1))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--match", required=True)
    r.add_argument("--out", type=Path, required=True)
    g = sub.add_parser("gates")
    g.add_argument("--dir", type=Path, required=True)
    a = sub.add_parser("sample-grids")
    a.add_argument("--dir", type=Path, required=True)
    a.add_argument("--out", type=Path, required=True)
    sub.add_parser("control-inspect")
    c = sub.add_parser("control-sheets")
    c.add_argument("--out", type=Path, required=True)
    c = sub.add_parser("control-pick")
    c.add_argument("--labels", type=Path, required=True)
    c = sub.add_parser("control-grids")
    c.add_argument("--labels", type=Path, required=True)
    c.add_argument("--out", type=Path, required=True)
    c = sub.add_parser("control-run")
    c.add_argument("--labels", type=Path, required=True)
    c.add_argument("--points", type=Path, required=True)
    c.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.cmd == "run":
        return run(args.match, args.out)
    if args.cmd == "control-inspect":
        return control_inspect()
    if args.cmd == "control-sheets":
        return control_sheets(args.out)
    if args.cmd == "control-pick":
        return control_pick(args.labels)
    if args.cmd == "control-grids":
        return control_grids(args.labels, args.out)
    if args.cmd == "control-run":
        return control_run(args.labels, args.points, args.out)
    if args.cmd == "sample-grids":
        return sample_grids(args.dir, args.out)
    return gates(args.dir)


if __name__ == "__main__":
    sys.exit(main())
