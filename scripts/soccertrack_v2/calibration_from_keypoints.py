"""Build a fixed panorama calibration from the dataset's annotated pitch landmarks.

No player detections, temporal alignment, event labels or control frames are fit.
Operator-supplied landmarks remain the production path for other cameras.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path

import numpy as np

from app.tracking.calibration import PitchCalibration


def from_keypoints(data: dict, image_size: tuple[int, int]) -> PitchCalibration:
    points = []
    for label, pixel in data.items():
        pitch = ast.literal_eval(label)
        if (not isinstance(pitch, tuple) or len(pitch) != 2
                or not all(isinstance(v, int | float) for v in pitch)
                or not 0 <= pitch[0] <= 105 or not 0 <= pitch[1] <= 68):
            raise ValueError(f"invalid pitch landmark: {label}")
        if (not isinstance(pixel, list) or len(pixel) != 2
                or not all(isinstance(v, int | float) for v in pixel)
                or not 0 <= pixel[0] < image_size[0] or not 0 <= pixel[1] < image_size[1]):
            raise ValueError(f"invalid image landmark: {label}")
        points.append({"image": pixel, "pitch": list(pitch)})
    return PitchCalibration.from_dict({"image_size": list(image_size), "method": "tps",
                                       "points": points, "meta": {"camera": "fixed_panoramic", "experimental": True,
                                       "source": "annotated pitch landmarks; no player/event GT fitting"}})


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--keypoints", type=Path, required=True)
    p.add_argument("--width", type=int, required=True)
    p.add_argument("--height", type=int, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--compare", type=Path, help="existing calibration to check at the same landmarks")
    args = p.parse_args()
    if args.out.exists():
        p.error("output exists; choose a new path to preserve prior calibration")
    raw = args.keypoints.read_bytes()
    cal = from_keypoints(json.loads(raw), (args.width, args.height))
    cal.meta["keypoint_sha256"] = hashlib.sha256(raw).hexdigest()
    error = cal.reprojection_error_m  # solve/validate before persisting any artifact
    report = {"points": len(cal.points), "leave_one_landmark_out_mean_m": error, "out": str(args.out)}
    if args.compare:
        previous = PitchCalibration.load(args.compare)
        if previous.image_size != cal.image_size:
            p.error("comparison requires the same image dimensions")
        errors = np.array([np.linalg.norm(np.array(previous.image_to_pitch_m(*point.image))-point.pitch)
                           for point in cal.points])
        report["previous_at_landmarks"] = {"mean_m": float(errors.mean()), "median_m": float(np.median(errors)),
                                            "p90_m": float(np.percentile(errors,90)), "max_m": float(errors.max())}
    cal.save(args.out)
    print(json.dumps(report))


if __name__ == "__main__":
    main()
