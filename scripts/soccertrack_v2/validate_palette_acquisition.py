"""Read-only completeness gate for the frozen palette control's raw captures.

Keep the original frozen acquisition code unchanged. A decoder failure can
return an empty/truncated sequence; file existence or matching SHA alone does
not make that sequence eligible for blind labeling or scoring.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

FREEZE = Path("docs/measurements/identity-palette-frozen-decision.json")
ROOT = Path("data/tracking/bench/consensus_palette_control_v1")


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_payload(payload: dict[str, Any], spec: dict[str, Any], segment: int) -> int:
    """The predeclared 30-second, 25fps source must yield every sampled frame."""
    if payload.get("segment") != segment:
        raise ValueError("Unexpected segment")
    if payload.get("config") != spec["config"] or payload.get("calibration") != spec["calibration"]:
        raise ValueError("Frozen capture configuration changed")
    requested_fps = float(spec["config"]["track_fps"])
    if not math.isfinite(requested_fps) or requested_fps <= 0:
        raise ValueError("Invalid frozen sampling rate")
    stride = max(1, round(25.0 / requested_fps))
    indices = list(range(0, 750, stride))
    samples = payload.get("samples", [])
    if len(samples) != len(indices):
        raise ValueError(f"Incomplete capture: expected {len(indices)} samples, got {len(samples)}")
    detections = payload.get("detected_persons", {})
    if set(detections) != {str(i) for i in range(len(indices))}:
        raise ValueError("Missing or extra raw detection frames")
    for order, (frame, sample) in enumerate(zip(indices, samples, strict=True)):
        if type(sample.get("order")) is not int or sample["order"] != order:
            raise ValueError("Non-contiguous sample order")
        if type(sample.get("frame_idx")) is not int or sample["frame_idx"] != frame:
            raise ValueError("Wrong or repeated source frame")
        seconds = sample.get("seconds")
        if not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or abs(seconds - frame / 25.0) > 1e-9:
            raise ValueError("Source timestamp mismatch")
        if not isinstance(detections[str(order)], list):
            raise ValueError("Invalid raw detection frame")
    return len(samples)


def _verify_manifest_paths(values: dict[str, str], expected: set[Path]) -> None:
    paths = {Path(name).resolve(): sha for name, sha in values.items()}
    if len(paths) != len(values) or set(paths) != {p.resolve() for p in expected}:
        raise ValueError("Manifest paths do not cover exactly the frozen clips")
    for path, sha in paths.items():
        if digest(path) != sha:
            raise ValueError(f"Manifest hash mismatch: {path.name}")


def validate_group(group: str, *, root: Path = ROOT, freeze: Path = FREEZE) -> dict[str, Any]:
    spec = load(freeze)["groups"][group]
    raw = root / group / "raw"
    manifest_path = raw / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError(f"{group}: capture manifest missing; acquisition did not complete")
    manifest = load(manifest_path)
    freeze_sha = digest(freeze)
    if manifest.get("freeze_sha256") != freeze_sha:
        raise ValueError("Capture belongs to another frozen decision")
    segments = [int(s) for s in spec["segments"]]
    caches = {raw / f"seg_{s:04d}.json" for s in segments}
    videos = {root / group / "source" / f"seg_{s:04d}.mp4" for s in segments}
    source_manifest = load(root / group / "source" / "manifest.json")
    if source_manifest.get("freeze_sha256") != freeze_sha:
        raise ValueError("Source clips belong to another frozen decision")
    clips = source_manifest.get("clips", [])
    if len(clips) != len(segments) or {c.get("segment") for c in clips} != set(segments):
        raise ValueError("Source manifest does not cover exactly the frozen clips")
    for clip in clips:
        segment = clip["segment"]
        if clip.get("frames") != 750 or clip.get("start_seconds") != spec["segments"][str(segment)]:
            raise ValueError("Source clip interval changed")
        if digest(root / group / "source" / f"seg_{segment:04d}.mp4") != clip.get("sha256"):
            raise ValueError("Source clip changed since extraction")
    _verify_manifest_paths(manifest.get("output_sha256", {}), caches)
    _verify_manifest_paths(manifest.get("video_sha256", {}), videos)
    counts = {}
    for segment in segments:
        payload = load(raw / f"seg_{segment:04d}.json")
        video = root / group / "source" / f"seg_{segment:04d}.mp4"
        if Path(payload.get("video", "")).resolve() != video.resolve():
            raise ValueError("Capture source path changed")
        counts[str(segment)] = validate_payload(payload, spec, segment)
    return {"group": group, "complete": True, "samples": counts, "freeze_sha256": freeze_sha}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group", choices=["day", "night"], required=True)
    args = parser.parse_args()
    print(json.dumps(validate_group(args.group)))


if __name__ == "__main__":
    main()
