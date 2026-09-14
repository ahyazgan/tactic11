"""Replay cached observations through the production frame/event builders, no GPU/DB.

Writes separate sparse and dense event evidence. Existing outputs are rejected.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np

from app.tracking.calibration import PitchCalibration
from app.tracking.frames import frames_from_json, frames_to_json
from app.tracking.passes import extract_passes
from app.tracking.pipeline import (
    PipelineConfig,
    SampledObservation,
    build_frames,
    interpolate_ball,
    reject_ball_spikes,
)
from app.tracking.recoveries import extract_recoveries
from app.tracking.teams import TeamAssigner


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument("--cache", type=Path)
    source.add_argument("--frames", type=Path, help="event-only regression on existing exported frames")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--keep-cached-ball", action="store_true", help="ablation: skip new ball cleanup")
    p.add_argument("--calibration", type=Path, help="compare a calibration on identical cached detections")
    args = p.parse_args()
    if args.out.exists():
        p.error("choose a new output directory to preserve previous evidence")
    args.out.mkdir(parents=True)
    if args.frames:
        for path in sorted(args.frames.glob("seg_*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            frames = frames_from_json(payload)
            passes = extract_passes(frames)
            defense = extract_recoveries(frames)
            payload["derived_passes"] = [asdict(p) for p in passes.passes]
            payload["derived_defensive_actions"] = [asdict(d) for d in defense.actions]
            payload["summary"] = {"passes": {"count": len(passes.passes), "rejected": passes.rejected},
                                  "defense_rejected": defense.rejected}
            (args.out / path.name).write_text(json.dumps(payload), encoding="utf-8")
            print(f"{path.name}: passes={len(passes.passes)} recoveries={len(defense.actions)}")
        return 0
    anchor = None
    for path in sorted(args.cache.glob("seg_*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        cal = (PitchCalibration.load(args.calibration) if args.calibration
               else PitchCalibration.from_dict(data["calibration"]))
        samples = [SampledObservation(**s) for s in data["samples"]]
        spikes = 0
        if not args.keep_cached_ball:
            for sample in samples:
                if sample.ball_source == "interp":
                    sample.ball = sample.ball_source = None
            spikes = reject_ball_spikes(samples, cal)
            cfg = PipelineConfig()
            interpolate_ball(samples, int(cfg.track_fps * cfg.ball_gap_seconds),
                             max_gap_seconds=cfg.ball_gap_seconds, calib=cal)
        teams = TeamAssigner()
        for t, cs in data["colors"].items():
            for c in cs:
                teams.observe(int(t), np.asarray(c))
        assignment = teams.fit(anchor, eligible_tracks={r[0] for s in samples for r in s.persons})
        if anchor is None:
            anchor = assignment.centers
        for mode in ("sparse", "dense"):
            cfg = PipelineConfig(clip_offset_minutes=10 + data["segment"] * 0.5)
            if mode == "dense":
                cfg = replace(cfg, fps_out=cfg.track_fps)
            frames = build_frames(samples, assignment.team_by_track, cal, match_id=990401,
                                  home_team_id=30798, away_team_id=30799, cfg=cfg)
            events = extract_passes(frames)
            extra = {"derived_passes": [asdict(x) for x in events.passes],
                     "summary": {"passes": {"count": len(events.passes),
                                             "actor_ratio": events.actor_ratio,
                                             "rejected": events.rejected}},
                     "mode": mode, "segment": data["segment"]}
            defense = extract_recoveries(frames)
            extra["derived_defensive_actions"] = [asdict(x) for x in defense.actions]
            extra["ball_spikes_rejected"] = spikes
            folder = args.out / mode
            folder.mkdir(exist_ok=True)
            (folder / path.name).write_text(json.dumps(frames_to_json(frames, match_id=990401, extra=extra)), encoding="utf-8")
            print(f"{path.name} {mode}: frames={len(frames)}, passes={len(events.passes)}, actor={events.actor_ratio}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
