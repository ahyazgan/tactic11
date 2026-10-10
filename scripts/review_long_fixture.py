"""Create repeated development footage for a 90-minute report transport test.

This is a duration/transport fixture, not a full-match tracking benchmark.
The source is read-only. Outputs must be new files inside the repository cache.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from app.reports.review_media import ffmpeg, probe_video


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source, output = args.source.resolve(strict=True), args.output.resolve()
    cache = Path(__file__).resolve().parents[1] / ".cache"
    if not output.is_relative_to(cache) or not output.name.startswith("review-e2e-"):
        raise SystemExit("Output must be a new .cache/review-e2e-*.mp4 file.")
    segment = output.with_suffix(".segment.mp4")
    receipt = output.with_suffix(".json")
    if output.suffix != ".mp4" or any(p.exists() for p in (output, segment, receipt)):
        raise SystemExit("Refusing to overwrite an existing fixture or source.")
    if probe_video(source) < 30:
        raise SystemExit("Use at least 30 seconds of previously approved development footage.")
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        ffmpeg(), "-nostdin", "-loglevel", "error", "-i", str(source), "-t", "30",
        "-an", "-vf", "scale=640:-2,fps=25", "-c:v", "libx264", "-preset", "fast",
        "-b:v", "600k", "-minrate", "600k", "-maxrate", "600k", "-bufsize", "1200k",
        "-x264-params", "nal-hrd=cbr:force-cfr=1", "-g", "50",
        "-pix_fmt", "yuv420p", "-threads", "2", str(segment),
    ], check=True, capture_output=True, timeout=120)
    estimated_bytes = segment.stat().st_size * 180
    if shutil.disk_usage(output.parent).free < estimated_bytes * 3 + 128 * 1024**2:
        raise SystemExit("Insufficient disk for the fixture, upload copy and delivery test.")
    subprocess.run([
        ffmpeg(), "-nostdin", "-loglevel", "error", "-stream_loop", "-1",
        "-i", str(segment), "-t", "5400", "-c", "copy", "-movflags", "+faststart", str(output),
    ], check=True, capture_output=True, timeout=120)
    duration = probe_video(output)
    if abs(duration - 5400) > .1:
        raise SystemExit(f"Unexpected duration: {duration}")
    with source.open("rb") as handle:
        source_hash = hashlib.file_digest(handle, "sha256").hexdigest()
    with output.open("rb") as handle:
        output_hash = hashlib.file_digest(handle, "sha256").hexdigest()
    result = {
        "fixture": str(output), "source": str(source), "source_sha256": source_hash,
        "sha256": output_hash, "duration_seconds": duration, "size_bytes": output.stat().st_size,
        "repeated_development_footage": True, "tracking_accuracy_measured": False,
    }
    receipt.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
