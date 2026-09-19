"""Freeze ROI batch-one evaluation, including dense ball evidence and exact events."""
from __future__ import annotations

import argparse
import math
import platform
import subprocess
import sys
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

from scripts.soccertrack_v2.consensus_control import code_hash, digest, load, write_new

FREEZE = Path("docs/measurements/roi-batch-frozen-decision.json")
ROOT = Path("data/tracking/bench/roi_batch_control_v1")
GROUPS = {"day": (117093, 2220), "night": (117092, 2640)}
PACKAGES = ("torch", "rfdetr", "supervision", "numpy", "opencv-python-headless", "imageio-ffmpeg")
POSITION_TOLERANCE_PX = .25
CONFIDENCE_TOLERANCE = .005


def compare_samples(legacy: list[dict], candidate: list[dict]) -> dict:
    """Permit bounded FP16 ball rounding, never identity/source/presence changes."""
    failures = []
    max_position, max_confidence = 0., 0.
    if len(legacy) != len(candidate):
        failures.append("sample_count")
    for i, (old, new) in enumerate(zip(legacy, candidate, strict=False)):
        if {k: v for k, v in old.items() if k != "ball"} != {k: v for k, v in new.items() if k != "ball"}:
            failures.append(f"sample.{i}.non_ball_evidence")
        before, after = old["ball"], new["ball"]
        if before is None or after is None:
            if before != after:
                failures.append(f"sample.{i}.ball_presence")
            continue
        if (len(before) != 3 or len(after) != 3 or not all(math.isfinite(x) for x in before + after)
                or not 0 <= before[2] <= 1 or not 0 <= after[2] <= 1):
            failures.append(f"sample.{i}.invalid_ball")
            continue
        position = math.hypot(before[0] - after[0], before[1] - after[1])
        confidence = abs(before[2] - after[2])
        max_position, max_confidence = max(max_position, position), max(max_confidence, confidence)
        if position > POSITION_TOLERANCE_PX:
            failures.append(f"sample.{i}.ball_position")
        if confidence > CONFIDENCE_TOLERANCE:
            failures.append(f"sample.{i}.ball_confidence")
    return dict(passed=not failures, failures=failures, max_ball_position_error_px=max_position,
        max_ball_confidence_error=max_confidence, samples_compared=min(len(legacy), len(candidate)))


def verify() -> dict:
    decision = load(FREEZE)
    if decision["python_version"] != platform.python_version():
        raise ValueError("Frozen Python changed")
    if decision["runtime_versions"] != {name: version(name) for name in PACKAGES}:
        raise ValueError("Frozen runtime changed")
    for name, expected in decision["code_sha256_lf"].items():
        if code_hash(Path(name)) != expected:
            raise ValueError(f"Frozen code changed: {name}")
    for name, expected in decision["input_sha256"].items():
        if digest(Path(name)) != expected:
            raise ValueError(f"Frozen input changed: {name}")
    return decision


def freeze() -> None:
    import cv2

    if FREEZE.exists() or ROOT.exists():
        raise ValueError("Control must be frozen before extraction")
    code = list(Path("app/tracking").rglob("*.py")) + [Path(__file__),
        Path("scripts/profile_tracking.py"), Path("scripts/soccertrack_v2/consensus_control.py"),
        Path("scripts/track_video.py"), Path("scripts/track_live.py"),
        Path("scripts/soccertrack_v2/benchmark_tracker_backends.py"),
        Path("tests/test_detector_roi_batch.py"), Path("tests/test_roi_control.py"),
        Path("tests/test_tracking_reid_integration.py")]
    inputs = [Path("docs/ROI-GRUPLAMA-KONTROL-PLANI.md")]
    inputs += [Path("data/tracking/models/rfdetr_mixed_small") / name
               for name in ("checkpoint_best_total.pth", "meta.json")]
    groups = {}
    for group, (match, start) in GROUPS.items():
        video = Path(f"data/tracking/datasets/soccertrack_v2/{match}/{match}_panorama_1st_half.mp4")
        calibration = Path(f"data/tracking/calibrations/soccertrack_v2_{match}_landmarks.json")
        cap = cv2.VideoCapture(str(video))
        count, fps = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)), cap.get(cv2.CAP_PROP_FPS)
        cap.release()
        if fps != 25 or start < 0 or (start + 30) * fps > count:
            raise ValueError("Control interval must fit source metadata before extraction")
        inputs += [video, calibration]
        groups[group] = dict(video=str(video), calibration=str(calibration), start=start,
            seconds=30, repeats=2, source_frames=count, source_fps=fps)
    write_new(FREEZE, dict(created_utc=datetime.now(UTC).isoformat(), control_pixels_opened=False,
        python_version=platform.python_version(), runtime_versions={name: version(name) for name in PACKAGES},
        code_sha256_lf={str(p): code_hash(p) for p in code},
        input_sha256={str(p): digest(p) for p in inputs}, groups=groups,
        acceptance=dict(exact_frames=True, exact_events=True, exact_repeats=True,
            dense_non_ball_exact=True, dense_ball_presence_and_source_exact=True,
            ball_position_tolerance_px=POSITION_TOLERANCE_PX, ball_confidence_tolerance=CONFIDENCE_TOLERANCE,
            candidate_roi_model_must_be_used=True)))


def run(group: str, decision: dict) -> None:
    import cv2
    import imageio_ffmpeg

    spec = decision["groups"][group]
    out = ROOT / group
    if out.exists():
        raise ValueError("Fresh group output required")
    out.mkdir(parents=True)
    video = out / "source.mp4"
    extraction = [imageio_ffmpeg.get_ffmpeg_exe(), "-nostdin", "-v", "error", "-ss", str(spec["start"]),
        "-i", spec["video"], "-t", str(spec["seconds"]), "-an", "-c:v", "libx264", "-qp", "0",
        "-preset", "fast", "-n", str(video)]
    subprocess.run(extraction, check=True)
    cap = cv2.VideoCapture(str(video))
    count, fps = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)), cap.get(cv2.CAP_PROP_FPS)
    cap.release()
    if count != spec["seconds"] * spec["source_fps"] or fps != spec["source_fps"]:
        raise ValueError("Unexpected source clip timing")
    video_hash = digest(video)
    reports, samples, events, hashes = {}, {}, [], {}
    for name in ("legacy", "candidate"):
        command = [sys.executable, "-X", "utf8", "-m", "scripts.profile_tracking", "--video", str(video),
            "--calibration", spec["calibration"], "--out", str(out / name), "--tracker", "supervision",
            "--seconds", str(spec["seconds"]), "--runs", str(spec["repeats"]), "--capture-samples",
            "--no-roi-single-batch" if name == "legacy" else "--roi-single-batch"]
        with (out / f"{name}.log").open("w", encoding="utf-8") as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
        reports[name] = load(out / name / "report.json")
        samples[name] = []
        if reports[name]["config"]["detector"]["roi_single_batch"] != (name == "candidate"):
            raise ValueError("Wrong ROI configuration")
        for row in reports[name]["runs"]:
            for suffix, expected in (("frames", row["output_sha256"]), ("samples", row["sample_output_sha256"])):
                path = out / name / f"run_{row['run']}.{suffix}.json"
                hashes[str(path)] = digest(path)
                if hashes[str(path)] != expected:
                    raise ValueError("Profile output hash mismatch")
            path = out / name / f"run_{row['run']}.summary.json"
            hashes[str(path)] = digest(path)
            events.append(load(path)["derived_events"])
            samples[name].append(load(out / name / f"run_{row['run']}.samples.json"))
    exact_frames = len({r["output_sha256"] for report in reports.values() for r in report["runs"]}) == 1
    exact_events = all(e == events[0] for e in events)
    exact_repeats = all(len({r["sample_output_sha256"] for r in report["runs"]}) == 1 for report in reports.values())
    dense = compare_samples(samples["legacy"][0], samples["candidate"][0])
    roi_used = all(r["roi_model_prepared"] and sum(v["calls"] for k, v in r["components"].items()
        if k.startswith("roi_")) > 0 for r in reports["candidate"]["runs"])
    if video_hash != digest(video):
        raise ValueError("Extracted source changed")
    verify()
    passed = exact_frames and exact_events and exact_repeats and dense["passed"] and roi_used
    write_new(out / "result.json", dict(freeze_sha256=digest(FREEZE), source_sha256=video_hash,
        extraction_command=extraction, source_frames=count, source_fps=fps, evidence_sha256=hashes,
        exact_frames_equal=exact_frames, exact_events_equal=exact_events, dense_repeats_equal=exact_repeats,
        dense_comparison=dense, candidate_roi_used=roi_used, passed=passed, reports=reports))
    print(group, "control passed", passed, dense, flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["freeze", "verify", "run"])
    parser.add_argument("--group", choices=list(GROUPS))
    args = parser.parse_args()
    if args.action == "freeze":
        freeze()
    else:
        decision = verify()
        if args.action == "run":
            if not args.group:
                parser.error("Group required")
            run(args.group, decision)


if __name__ == "__main__":
    main()
