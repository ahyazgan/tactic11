"""Extract label-free kit features on immutable detections for development replay.

This module does not choose a production feature or change team assignment.
Cached frame/box keys remain valid when a tracker assigns different identities.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

REGIONS = {"torso": (.1, .55), "middle": (.2, .7),
           "kit": (.1, .8), "short": (.4, .75)}
FRACTIONS = (.2, .4, .6, 1.)


def crop_features(frame_rgb: np.ndarray, box: tuple | list) -> dict[str, list[float]]:
    """Use the existing grass exclusion and several fixed body crop summaries."""
    x1, y1, x2, y2 = map(round, box)
    height, width = frame_rgb.shape[:2]
    x1, y1, x2, y2 = max(0, x1), max(0, y1), min(width, x2), min(height, y2)
    bw, bh = x2 - x1, y2 - y1
    if bw < 2 or bh < 4:
        return {}
    features = {}
    for name, (top, bottom) in REGIONS.items():
        pixels = frame_rgb[
            y1 + int(bh * top):y1 + int(bh * bottom),
            x1 + int(bw * .2):x1 + int(bw * .8),
        ].reshape(-1, 3).astype(float)
        if not len(pixels):
            continue
        r, g, b = pixels.T
        kept = pixels[~((g > 1.12 * r) & (g > 1.12 * b))]
        if len(kept) < max(4, len(pixels) * .12):
            kept = pixels
        ordered = kept[np.argsort(kept.max(axis=1))]
        for fraction in FRACTIONS:
            key = f"{name}_{fraction:g}"
            features[key] = ordered[-max(4, int(len(ordered) * fraction)):].mean(axis=0).tolist()
        features[f"{name}_median"] = np.median(kept, axis=0).tolist()
        # Coloured shirt fabric may be darker than a white number or stripe.
        # Compare saturated pixels with a variant that excludes very dark
        # pixels first; saturation alone is unstable close to black.
        for kind, candidates in (("saturated", kept),
                                 ("bright_saturated", ordered[len(ordered) // 2:])):
            value = candidates.max(axis=1)
            saturation = (value - candidates.min(axis=1)) / np.maximum(value, 1.)
            selected = candidates[np.argsort(saturation)[-max(4, len(candidates) // 2):]]
            features[f"{name}_{kind}"] = selected.mean(axis=0).tolist()
    return features


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extract(cache: Path, video: Path, output: Path) -> dict:
    """Extract every raw detection when available; do not read kit labels."""
    import cv2

    if output.exists():
        raise FileExistsError(f"Choose a fresh output file: {output}")
    data = json.loads(cache.read_text(encoding="utf-8"))
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise ValueError(f"Video cannot be opened: {video}")
    samples, previous = [], -1
    try:
        for sample in data["samples"]:
            frame_index = sample["frame_idx"]
            if frame_index <= previous:
                raise ValueError("Strictly ordered source frames required")
            for _ in range(previous + 1, frame_index):
                if not cap.grab():
                    raise ValueError(f"Cannot decode source frame {frame_index}")
            ok, frame = cap.read()
            if not ok:
                raise ValueError(f"Cannot decode source frame {frame_index}")
            previous = frame_index
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            if "detected_persons" in data:
                boxes = [p["box"] for p in data["detected_persons"][str(sample["order"])]]
            else:
                boxes = [p[1:5] for p in sample["persons"]]
            samples.append({"frame_idx": frame_index, "seconds": sample["seconds"],
                            "persons": [{"box": box, "features": crop_features(rgb, box)} for box in boxes]})
    finally:
        cap.release()
    result = {"segment": data["segment"], "video": video.as_posix(),
              "scope": "Development features; no kit labels read or production decision made.",
              "source_sha256": {cache.as_posix(): _digest(cache), video.as_posix(): _digest(video)},
              "extractor_sha256": hashlib.sha256(Path(__file__).read_text(encoding="utf-8").encode()).hexdigest(),
              "samples": samples}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = extract(args.cache, args.video, args.out)
    print(json.dumps({"frames": len(result["samples"]),
                      "boxes": sum(len(s["persons"]) for s in result["samples"])}))


if __name__ == "__main__":
    main()
