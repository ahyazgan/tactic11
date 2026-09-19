"""Reproduce two known identity splits without changing the production tracker.

The one-box removals are visually annotated oracle interventions, never an
automatic detector filter. Both windows are already-seen development data.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np

FIXTURES = Path("tests/fixtures/identity_failures")
CASES = {
    "white_turn": dict(segment=0, endpoints=["0-280-d20", "0-310-d18"],
                       fragment_frame=298, fragment_index=18, support_index=17,
                       roi=[1950, 100, 2220, 310], window=[260, 330]),
    "blue_referee": dict(segment=3, endpoints=["3-440-d10", "3-460-d10"],
                         fragment_frame=458, fragment_index=24, support_index=14,
                         roi=[2470, 130, 2760, 340], window=[420, 480]),
}


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def load_fixture(path: Path) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        data = json.load(stream)
    samples = data["samples"]
    if not samples or [r["order"] for r in samples] != list(range(len(samples))):
        raise ValueError("Full contiguous warmup from order zero is required")
    if any(r["frame_idx"] != r["order"] * data["stride"] for r in samples):
        raise ValueError("Source frame cadence changed")
    for sample in samples:
        indices = [r["raw_index"] for r in sample["detections"]]
        if len(set(indices)) != len(indices):
            raise ValueError("Duplicate source detection index")
    for endpoint in data["endpoints"] + [data["fragment"], data["support"]]:
        sample = next((s for s in samples if s["frame_idx"] == endpoint["frame_idx"]), None)
        if sample is None or not any(r["raw_index"] == endpoint["raw_index"] and r["box"] == endpoint["box"]
                                     for r in sample["detections"]):
            raise ValueError("Annotation no longer matches the exact source box")
    return data


def prepare_fixtures() -> None:
    from app.tracking.calibration import PitchCalibration

    labels_path = Path("docs/measurements/identity-person-development-labels.json")
    labels = json.loads(labels_path.read_text(encoding="utf-8"))
    FIXTURES.mkdir(parents=True, exist_ok=True)
    for name, case in CASES.items():
        target = FIXTURES / f"{name}.json.gz"
        if target.exists():
            raise ValueError("Never overwrite a regression fixture")
        source = Path(f"data/tracking/bench/identity_day_detections/seg_{case['segment']:04d}.json")
        video = Path(f"data/tracking/bench/daylight_117093/source/seg_{case['segment']:04d}.mp4")
        data = json.loads(source.read_text(encoding="utf-8"))
        cal = PitchCalibration.from_dict(data["calibration"])
        endpoints = [next(r for r in labels["observations"] if r["id"] == eid) for eid in case["endpoints"]]
        samples = []
        for sample in data["samples"]:
            if sample["frame_idx"] > case["window"][1]:
                break
            rows = data["detected_persons"][str(sample["order"])]
            detections = [dict(raw_index=i, box=r["box"], confidence=r["confidence"])
                          for i, r in enumerate(rows) if cal.is_on_pitch(
                              (r["box"][0] + r["box"][2]) / 2, r["box"][3],
                              margin_m=data["config"]["pitch_margin_m"])]
            samples.append(dict(order=sample["order"], frame_idx=sample["frame_idx"], detections=detections))
        event = next(s for s in samples if s["frame_idx"] == case["fragment_frame"])
        annotations = {}
        for kind, index in (("fragment", case["fragment_index"]), ("support", case["support_index"])):
            row = next(r for r in event["detections"] if r["raw_index"] == index)
            annotations[kind] = dict(frame_idx=event["frame_idx"], **row)
        payload = dict(name=name, segment=case["segment"], video=str(video), stride=2,
            scope="Known development; fragment/support visually annotated; removals are oracle only",
            source_sha256={str(p): digest(p) for p in (source, video, labels_path)},
            window=case["window"], roi=case["roi"], threshold=.25, lost_frames=7,
            endpoints=[dict(id=r["id"], frame_idx=r["frame_idx"], raw_index=r["detector_index"],
                            box=r["bbox"]) for r in endpoints], samples=samples, **annotations)
        target.write_bytes(gzip.compress(json.dumps(payload, separators=(",", ":")).encode(), mtime=0))


def replay_case(data: dict, *, iou: float = .3, remove_fragment: bool = False) -> dict:
    import supervision as sv

    from app.tracking._vendor.deepocsort import ocsort
    from app.tracking._vendor.deepocsort.association import iou_batch
    from app.tracking.deepocsort import DeepOCSortTracker

    tracker = DeepOCSortTracker(threshold=data["threshold"], lost_frames=data["lost_frames"], appearance=False)
    tracker.tracker.iou_threshold = iou  # research-only single-parameter diagnostic
    original_associate = ocsort.associate
    endpoint_ids: dict[str, int | None] = {}
    frames, traces = [], []
    target_id = None
    active_rows: list[dict] = []
    frame_idx = -1

    def associate(*args):
        outcome = original_associate(*args)
        if target_id is None:
            return outcome
        column = next((i for i, t in enumerate(tracker.tracker.trackers) if t.id + 1 == target_id), None)
        if column is None:
            return outcome
        overlaps = iou_batch(args[0], args[1])[:, column]
        assigned = {int(d): int(t) for d, t in outcome[0]}
        accepted = [r for r in active_rows if r["confidence"] > data["threshold"]]
        traces.append(dict(frame_idx=frame_idx, target_id=target_id,
            candidates=[dict(raw_index=row["raw_index"], box=row["box"], iou=float(overlap),
                             geometrically_eligible=bool(overlap >= iou),
                             assigned_track_id=(tracker.tracker.trackers[assigned[i]].id + 1
                                                if i in assigned else None))
                        for i, (row, overlap) in enumerate(zip(accepted, overlaps, strict=True)) if overlap > 0]))
        return outcome

    with patch.object(ocsort, "associate", side_effect=associate):
        for sample in data["samples"]:
            frame_idx = sample["frame_idx"]
            active_rows = [r for r in sample["detections"] if not (
                remove_fragment and frame_idx == data["fragment"]["frame_idx"]
                and r["raw_index"] == data["fragment"]["raw_index"])]
            det = sv.Detections(xyxy=np.asarray([r["box"] for r in active_rows]).reshape(-1, 4),
                confidence=np.asarray([r["confidence"] for r in active_rows]),
                data={"raw_index": np.asarray([r["raw_index"] for r in active_rows], dtype=int)})
            # Motion-only backend reads image shape for a scale of exactly one.
            result = tracker.update_with_detections(det, np.zeros((1, 1, 3), dtype=np.uint8))
            observations = [dict(raw_index=int(index), track_id=int(tid), box=box.tolist())
                            for index, tid, box in zip(result.data["raw_index"], result.tracker_id,
                                                       result.xyxy, strict=True)]
            for endpoint in data["endpoints"]:
                if endpoint["frame_idx"] != frame_idx:
                    continue
                match = next((r for r in observations if r["raw_index"] == endpoint["raw_index"]
                              and r["box"] == endpoint["box"]), None)
                endpoint_ids[endpoint["id"]] = None if match is None else match["track_id"]
                if endpoint is data["endpoints"][0] and match is not None:
                    target_id = match["track_id"]
            if frame_idx >= data["window"][0]:
                frames.append(dict(frame_idx=frame_idx, observations=observations))
    values = list(endpoint_ids.values())
    return dict(iou=iou, oracle_fragment_removed=remove_fragment, endpoint_ids=endpoint_ids,
                linked=len(values) == 2 and None not in values and len(set(values)) == 1,
                frames=frames, first_stage=traces)


def export_video(data: dict, output: Path) -> None:
    import cv2

    video = Path(data["video"])
    if digest(video) != data["source_sha256"][str(video)]:
        raise ValueError("Source video changed")
    cap = cv2.VideoCapture(str(video))
    writer = cv2.VideoWriter(str(output), cv2.VideoWriter_fourcc(*"mp4v"), 25., (900, 700))
    if not cap.isOpened() or not writer.isOpened():
        cap.release()
        writer.release()
        raise ValueError("Cannot open video evidence reader/writer")
    x1, y1, x2, y2 = data["roi"]
    start, end = data["window"]
    try:
        # Decode from the beginning; no keyframe seek ambiguity.
        for frame in range(end + 1):
            ok, bgr = cap.read()
            if not ok:
                raise ValueError("Source ended before evidence window")
            if frame < start:
                continue
            crop = bgr[y1:y2, x1:x2]
            scale = min(900 / crop.shape[1], 640 / crop.shape[0])
            crop = cv2.resize(crop, (round(crop.shape[1] * scale), round(crop.shape[0] * scale)))
            panel = np.zeros((700, 900, 3), np.uint8)
            left, top = (900 - crop.shape[1]) // 2, 60 + (640 - crop.shape[0]) // 2
            panel[top:top + crop.shape[0], left:left + crop.shape[1]] = crop
            cv2.putText(panel, f"{data['name']} | source frame {frame} | development", (12, 36),
                        cv2.FONT_HERSHEY_SIMPLEX, .65, (240, 240, 240), 2)
            writer.write(panel)
            if frame == data["fragment"]["frame_idx"]:
                for kind, color in (("fragment", (0, 220, 255)), ("support", (60, 80, 255))):
                    row = data[kind]
                    bx1, by1, bx2, by2 = row["box"]
                    a = (round((bx1 - x1) * scale) + left, round((by1 - y1) * scale) + top)
                    b = (round((bx2 - x1) * scale) + left, round((by2 - y1) * scale) + top)
                    cv2.rectangle(panel, a, b, color, 2)
                    cv2.putText(panel, f"{kind}: raw {row['raw_index']}", (a[0], a[1] - 7),
                                cv2.FONT_HERSHEY_SIMPLEX, .55, color, 2)
                cv2.imwrite(str(output.with_suffix(".jpg")), panel)
    finally:
        cap.release()
        writer.release()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-fixtures", action="store_true")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--video", action="store_true")
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Fresh output directory required")
    if args.prepare_fixtures:
        prepare_fixtures()
    args.out.mkdir(parents=True)
    result = {}
    fixture_hashes = {}
    code_paths = [Path(__file__), Path("app/tracking/deepocsort.py")]
    code_paths += list(Path("app/tracking/_vendor/deepocsort").glob("*.py"))
    code_hashes = {str(p): hashlib.sha256(p.read_text(encoding="utf-8").encode()).hexdigest() for p in code_paths}
    for name in CASES:
        path = FIXTURES / f"{name}.json.gz"
        fixture_hashes[str(path)] = digest(path)
        data = load_fixture(path)
        result[name] = {}
        for label, iou, remove in (("original", .3, False), ("iou_02", .2, False),
                                   ("oracle", .3, True), ("oracle_iou_02", .2, True)):
            result[name][label] = replay_case(data, iou=iou, remove_fragment=remove)
            print(name, label, result[name][label]["endpoint_ids"], flush=True)
        if args.video:
            export_video(data, args.out / f"{name}.mp4")
    if code_hashes != {str(p): hashlib.sha256(p.read_text(encoding="utf-8").encode()).hexdigest() for p in code_paths}:
        raise ValueError("Diagnostic implementation changed during replay")
    if fixture_hashes != {name: digest(Path(name)) for name in fixture_hashes}:
        raise ValueError("Source fixture changed during replay")
    report = dict(scope=__doc__, fixture_sha256=fixture_hashes, code_sha256_lf=code_hashes,
                  production_changed=False, new_control_opened=False, results=result)
    (args.out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    summary = {k: v for k, v in report.items() if k != "results"}
    summary["detailed_trace_sha256"] = digest(args.out / "report.json")
    summary["results"] = {
        name: {label: {**{k: v for k, v in run.items() if k not in ("frames", "first_stage")},
                       "event_first_stage": next(r for r in run["first_stage"]
                                                 if r["frame_idx"] == CASES[name]["fragment_frame"]),
                       "window_frames": len(run["frames"])}
               for label, run in arms.items()} for name, arms in result.items()
    }
    summary["visual_artifact_sha256"] = {p.name: digest(p) for p in args.out.iterdir()
                                         if p.suffix in (".mp4", ".jpg")}
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
