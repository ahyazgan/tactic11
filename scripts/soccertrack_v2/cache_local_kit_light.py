"""Re-extract shirt colours with nearby field illumination from identical boxes.

Experimental: no detector, GT, labels or database. Run with venv-cv. The original
cache is retained and alternative colour histories are stored in a new folder.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np

from app.tracking.teams import kit_color, normalize_kit_light, torso_color


def verify_raw_reextraction(payload: dict, colors: dict) -> None:
    """Reject changed decoding, frame/box alignment or missing observations."""
    eligible = {str(p[0]) for sample in payload["samples"] for p in sample["persons"]}
    expected = {t: cs for t, cs in payload["colors"].items() if t in eligible}
    if colors.keys() != expected.keys() or any(
        not np.array_equal(colors[t], expected[t]) for t in expected
    ):
        raise ValueError("raw observations differ from the source cache")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, nargs="+", required=True)
    parser.add_argument("--segments", type=int, nargs="+", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("choose a new output directory")
    import cv2

    args.out.mkdir(parents=True)
    for segment in args.segments:
        paths = [p / f"seg_{segment:04d}.json" for p in args.cache if (p / f"seg_{segment:04d}.json").is_file()]
        if len(paths) != 1:
            parser.error(f"exactly one source cache needed for segment {segment}")
        source = paths[0]
        payload = json.loads(source.read_text(encoding="utf-8"))
        if payload["config"].get("normalize_kit_light", False):
            parser.error("source must use raw kit colours; normalized caches cannot be normalized again")
        methods: dict[str, dict[str, list]] = {name: {} for name in ("raw_reextracted", "local_all", "local_grass")}
        cap = cv2.VideoCapture(payload["video"])
        frame_idx = -1
        started = time.perf_counter()
        try:
            for sample in payload["samples"]:
                while frame_idx < sample["frame_idx"]:
                    if not cap.grab():
                        raise ValueError(f"cannot grab frame {sample['frame_idx']} in {payload['video']}")
                    frame_idx += 1
                ok, bgr = cap.retrieve()
                if not ok:
                    raise ValueError("cannot retrieve video frame")
                rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                for person in sample["persons"]:
                    track, box = str(person[0]), person[1:5]
                    color = torso_color(rgb, box)
                    if color is None:
                        continue
                    values = {"raw_reextracted": color,
                              "local_all": normalize_kit_light(rgb, box, color, grass_only=False),
                              "local_grass": kit_color(rgb, box, normalize_light=True)}
                    for name, value in values.items():
                        methods[name].setdefault(track, []).append(value.tolist())
        finally:
            cap.release()
        verify_raw_reextraction(payload, methods["raw_reextracted"])
        payload["alternative_colors"] = methods
        payload["colour_experiment"] = {"source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                                         "seconds": time.perf_counter() - started,
                                         "source": str(source), "geometry_unchanged": True,
                                         "raw_observations_exactly_reproduced": True,
                                         "color_method": "local_grass_v1"}
        (args.out / source.name).write_text(json.dumps(payload), encoding="utf-8")
        print(json.dumps({"segment": segment, "seconds": payload["colour_experiment"]["seconds"]}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
