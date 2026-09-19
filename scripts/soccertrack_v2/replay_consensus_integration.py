"""Replay all known clips through the real consensus production video pipeline.

RF-DETR person detections are immutable inputs; source RGB decoding, kit color,
both trackers, OSNet CUDA, identity confirmation, frames and events are real.
No ball input, new control decoding or database writes occur in this replay.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

import numpy as np

from app.tracking import pipeline
from app.tracking.calibration import PitchCalibration
from app.tracking.deepocsort import DEFAULT_MODEL
from app.tracking.detect import DetectorConfig
from app.tracking.frames import frames_to_json
from scripts.soccertrack_v2.benchmark_deepocsort import VIDEO_DIRS
from scripts.soccertrack_v2.benchmark_tracker_backends import MEASUREMENTS, digest, groups, load


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Fresh output directory required")
    import supervision as sv

    expected_report = load(args.expected / "report.json")
    if not expected_report["decisions"]["deepocsort"]["development_pass"]:
        raise ValueError("Expected research candidate did not pass development")
    paths = [Path(__file__), Path(DEFAULT_MODEL), args.expected / "report.json"] + list(Path("app/tracking").rglob("*.py"))
    for group, cfg in groups().items():
        paths += [Path(VIDEO_DIRS[group]) / f"seg_{s:04d}.mp4" for s in cfg["segments"]]
        paths += [Path(cfg["cache"]) / f"seg_{s:04d}.json" for s in cfg["segments"]]
        paths += [args.expected / group / "deepocsort" / f"seg_{s:04d}.json" for s in cfg["segments"]]
        paths += [MEASUREMENTS / f"{cfg['anchor']}.json"]
    hashes = {str(p): digest(p) for p in paths}
    args.out.mkdir(parents=True)
    comparisons = []
    for group, cfg in groups().items():
        anchor = np.asarray(load(MEASUREMENTS / f"{cfg['anchor']}.json")["anchors"]["before"])
        for segment in cfg["segments"]:
            raw = load(Path(cfg["cache"]) / f"seg_{segment:04d}.json")
            config = pipeline.PipelineConfig(**{k: v for k, v in raw["config"].items() if k != "detector"})
            config.detector = DetectorConfig(**raw["config"]["detector"])
            config.tracker_backend = "consensus"
            config.refine_player_identities = False
            config.preview_path = None
            calibration = PitchCalibration.from_dict(raw["calibration"])

            class CachedDetector:
                def __init__(self, source):
                    self.position = 0
                    self.source = source

                def detect(self, rgb):
                    if self.position >= len(self.source["samples"]):
                        raise ValueError("Source decoded more samples than expected")
                    sample = self.source["samples"][self.position]
                    self.position += 1
                    people = self.source["detected_persons"][str(sample["order"])]
                    return sv.Detections(xyxy=np.asarray([p["box"] for p in people]).reshape(-1, 4),
                        confidence=np.asarray([p["confidence"] for p in people]), class_id=np.zeros(len(people), dtype=int))

                def split(self, detections):
                    return detections, sv.Detections.empty()

            detector = CachedDetector(raw)
            collected = []
            original = pipeline.collect_observations

            def capture(*a, original=original, collected=collected, **kw):
                result = original(*a, **kw)
                collected.append(result[0])
                return result

            with patch.object(pipeline, "collect_observations", side_effect=capture):
                frames, summary = pipeline.process_video(Path(VIDEO_DIRS[group]) / f"seg_{segment:04d}.mp4",
                    calibration, cfg=config, detector=detector, team_anchor=anchor,
                    match_id=990902, home_team_id=217, away_team_id=213)
            if detector.position != len(raw["samples"]):
                raise ValueError("Incomplete source replay")
            samples = [asdict(s) for s in collected[0]]
            expected = load(args.expected / group / "deepocsort" / f"seg_{segment:04d}.json")["samples"]
            # JSON canonicalization only converts tuple/list representation;
            # compare every person, timestamp and per-observation team exactly.
            def comparison_rows(rows):
                return json.loads(json.dumps([{k: s[k] for k in ("order", "frame_idx", "seconds", "persons", "person_teams")}
                                              for s in rows]))
            equal = comparison_rows(samples) == comparison_rows(expected)
            target = args.out / group / f"seg_{segment:04d}.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(dict(samples=samples, summary=summary)) + "\n", encoding="utf-8")
            target.with_suffix(".frames.json").write_text(json.dumps(frames_to_json(frames, match_id=990902)) + "\n", encoding="utf-8")
            comparisons.append(dict(group=group, segment=segment, equal=equal,
                observations=sum(len(s["persons"]) for s in samples), frames=len(frames),
                boundaries=summary["calibration_stats"]["identity_consensus"]["boundaries"],
                output_sha256=digest(target)))
            print(group, segment, "production equals research:", equal, flush=True)
            if not equal:
                (args.out / "mismatch.json").write_text(json.dumps(comparisons, indent=2), encoding="utf-8")
                raise ValueError("Production consensus differs from development candidate")
    if hashes != {name: digest(Path(name)) for name in hashes}:
        raise ValueError("Inputs or code changed during production replay")
    (args.out / "report.json").write_text(json.dumps(dict(scope=__doc__, hashes=hashes,
        comparisons=comparisons, all_equal=True, new_control_opened=False), indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
