"""Freeze and verify a real-detector batching control without fitting its settings."""
from __future__ import annotations

import argparse
import platform
import subprocess
import sys
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

from scripts.soccertrack_v2.consensus_control import code_hash, digest, load, write_new

FREEZE = Path("docs/measurements/torch-batch-frozen-decision.json")
ROOT = Path("data/tracking/bench/torch_batch_control_v1")
GROUPS = {"day": (117093, 2100, 26), "night": (117092, 2700, 16)}
PACKAGES = ("torch", "rfdetr", "supervision", "numpy", "opencv-python-headless", "imageio-ffmpeg")


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
    if FREEZE.exists() or ROOT.exists():
        raise ValueError("Control must be frozen before extraction")
    code = list(Path("app/tracking").rglob("*.py")) + [Path(__file__),
        Path("scripts/profile_tracking.py"), Path("scripts/soccertrack_v2/consensus_control.py"),
        Path("scripts/soccertrack_v2/benchmark_tracker_backends.py"),
        Path("tests/test_detector_slicer_batches.py"), Path("tests/test_batch_control.py")]
    inputs = [Path("docs/TORCH-GRUPLAMA-KONTROL-PLANI.md")]
    inputs += [Path("data/tracking/models/rfdetr_mixed_small") / name
               for name in ("checkpoint_best_total.pth", "meta.json")]
    groups = {}
    for group, (match, start, legacy) in GROUPS.items():
        video = Path(f"data/tracking/datasets/soccertrack_v2/{match}/{match}_panorama_1st_half.mp4")
        calibration = Path(f"data/tracking/calibrations/soccertrack_v2_{match}_landmarks.json")
        inputs += [video, calibration]
        groups[group] = dict(video=str(video), calibration=str(calibration), start=start,
            seconds=10, legacy_batch=legacy, repeats=2)
    write_new(FREEZE, dict(created_utc=datetime.now(UTC).isoformat(), control_pixels_opened=False,
        python_version=platform.python_version(),
        runtime_versions={name: version(name) for name in PACKAGES},
        code_sha256_lf={str(p): code_hash(p) for p in code},
        input_sha256={str(p): digest(p) for p in inputs}, groups=groups,
        acceptance="Exact repeated frames and derived events; no tuning after opening controls"))


def run(group: str, decision: dict) -> None:
    import cv2
    import imageio_ffmpeg

    spec = decision["groups"][group]
    out = ROOT / group
    if out.exists():
        raise ValueError("Fresh group output required")
    out.mkdir(parents=True)
    video = out / "source.mp4"
    extraction_command = [imageio_ffmpeg.get_ffmpeg_exe(), "-nostdin", "-v", "error", "-ss", str(spec["start"]),
        "-i", spec["video"], "-t", str(spec["seconds"]), "-an", "-c:v", "libx264", "-qp", "0",
        "-preset", "fast", "-n", str(video)]
    subprocess.run(extraction_command, check=True)
    cap = cv2.VideoCapture(str(video))
    count, fps = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)), cap.get(cv2.CAP_PROP_FPS)
    cap.release()
    if count != 250 or fps != 25:
        raise ValueError("Unexpected source clip timing")
    video_hash = digest(video)
    results = {}
    for name in ("legacy", "automatic"):
        command = [sys.executable, "-X", "utf8", "-m", "scripts.profile_tracking", "--video", str(video),
            "--calibration", spec["calibration"], "--out", str(out / name), "--tracker", "supervision",
            "--seconds", str(spec["seconds"]), "--runs", str(spec["repeats"])]
        if name == "legacy":
            command += ["--batch-size", str(spec["legacy_batch"])]
        with (out / f"{name}.log").open("w", encoding="utf-8") as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
        results[name] = load(out / name / "report.json")
        for row in results[name]["runs"]:
            if digest(out / name / f"run_{row['run']}.frames.json") != row["output_sha256"]:
                raise ValueError("Profile output hash mismatch")
    frame_hashes = {r["output_sha256"] for report in results.values() for r in report["runs"]}
    events = [load(out / name / f"run_{i}.summary.json")["derived_events"]
              for name in results for i in range(spec["repeats"])]
    passed = len(frame_hashes) == 1 and all(e == events[0] for e in events)
    if video_hash != digest(video):
        raise ValueError("Extracted source changed")
    verify()
    write_new(out / "result.json", dict(freeze_sha256=digest(FREEZE), source_sha256=video_hash,
        extraction_command=extraction_command, source_frames=count, source_fps=fps,
        exact_frames_equal=len(frame_hashes) == 1, exact_events_equal=all(e == events[0] for e in events),
        passed=passed, reports=results))
    print(group, "exact parity", passed, flush=True)


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
