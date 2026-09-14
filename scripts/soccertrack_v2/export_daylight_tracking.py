"""Export verified daylight observations through production frame builders, without DB writes.

Requires a daylight benchmark report. Anonymous team slots are not club IDs.
Run in venv-cv with --preview to also render the first available control clip.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from app.tracking.calibration import PitchCalibration
from app.tracking.detect import DetectorConfig
from app.tracking.frames import frames_to_json
from app.tracking.passes import extract_passes
from app.tracking.pipeline import PipelineConfig, SampledObservation, build_frames, write_preview
from app.tracking.recoveries import extract_recoveries


def export(report: dict, out: Path, *, preview: bool = False) -> dict:
    if out.exists():
        raise ValueError("choose a new output directory")
    inputs = []
    # Validate all inputs before creating artifacts; preserve the measured run.
    for cache_path, digest in report["cache_sha256"].items():
        path = Path(cache_path)
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError(f"measured cache changed: {path}")
        inputs.append(json.loads(path.read_text(encoding="utf-8")))
    source_clips = {r["segment"]: r for r in report["source"]["clips"]}
    out.mkdir(parents=True)
    summary = {"match": "117093", "team_slot_ids_are_anonymous": True, "color_method": "raw_rgb_v1", "clips": []}
    first_control = min(report["available_control_segments"])
    for data in sorted(inputs, key=lambda d:d["segment"]):
        segment = data["segment"]
        source = source_clips[segment]
        values = {**data["config"], "detector": DetectorConfig(**data["config"]["detector"]),
                  "normalize_kit_light": False, "clip_offset_minutes": source["source_start_seconds"] / 60}
        cfg = PipelineConfig(**values)
        samples = [SampledObservation(**row) for row in data["samples"]]
        cal = PitchCalibration.from_dict(data["calibration"])
        teams = {int(t): v for t,v in report["results"]["raw_rgb_v1"]["team_by_track"][str(segment)].items()}
        frames = build_frames(samples, teams, cal, match_id=117093, home_team_id=0, away_team_id=1, cfg=cfg)
        passes, defense = extract_passes(frames), extract_recoveries(frames)
        evidence = {"derived_passes": [asdict(p) for p in passes.passes],
                    "derived_defensive_actions": [asdict(d) for d in defense.actions],
                    "team_slot_ids_are_anonymous": True, "color_method": "raw_rgb_v1",
                    "source_clip": source, "event_accuracy_not_validated": True}
        payload = frames_to_json(frames, match_id=117093, extra=evidence)
        path = out / f"seg_{segment:04d}.json"
        path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
        summary["clips"].append({"segment": segment, "sampled_frames": len(samples), "exported_frames": len(frames),
                                 "source_start_seconds": source["source_start_seconds"],
                                 "observed_export_fps": len(frames) / source["duration_seconds"],
                                 "estimated_passes": len(passes.passes), "estimated_recoveries": len(defense.actions),
                                 "ball_frames": sum(f.ball is not None for f in frames)})
        if preview and segment == first_control:
            # Match source sampling (25/2 = 12.5 fps) so every rendered frame has
            # its own observation. Show boxes only; the separate landmark image
            # verifies this curved camera, without a homography-only line overlay.
            cfg.fps_out = data["stats"]["effective_track_fps"]
            cfg.preview_width = 2048
            write_preview(data["video"], samples, teams, None, cfg, out / "tracking_preview.mp4")
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--preview", action="store_true")
    args = parser.parse_args()
    print(json.dumps(export(json.loads(args.report.read_text(encoding="utf-8")), args.out, preview=args.preview), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
