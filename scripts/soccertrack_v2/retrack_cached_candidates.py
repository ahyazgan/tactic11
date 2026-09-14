"""Re-run pitch filtering, tracking and team colour collection without another GPU run.

Full-frame detections are identical across calibrations. Cached ROI observations
retain their original anchor; this limitation is written into the output.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path

import numpy as np
import supervision as sv

from app.tracking.calibration import PitchCalibration
from app.tracking.pipeline import SampledObservation
from app.tracking.teams import TeamAssigner


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cache", type=Path, required=True)
    p.add_argument("--calibration", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    if args.out.exists():
        p.error("choose a fresh output directory")
    args.out.mkdir(parents=True)
    cal = PitchCalibration.load(args.calibration)
    for path in sorted(args.cache.glob("seg_*.json")):
        payload = json.loads(path.read_text())
        cfg = payload["config"]
        fps = payload["stats"]["effective_track_fps"]
        tracker = sv.ByteTrack(track_activation_threshold=cfg["track_activation_threshold"],
                               lost_track_buffer=max(1,int(cfg["lost_track_seconds"]*fps)),
                               minimum_matching_threshold=.8, frame_rate=max(1,round(fps)),
                               minimum_consecutive_frames=1)
        teams = TeamAssigner()
        hits: Counter = Counter()
        samples = []
        for sample in payload["samples"]:
            raw = payload["detected_persons"][str(sample["order"])]
            eligible = [(i,r) for i,r in enumerate(raw)
                        if cal.is_on_pitch((r["box"][0]+r["box"][2])/2,r["box"][3],margin_m=cfg["pitch_margin_m"])]
            detections = sv.Detections(
                xyxy=np.array([r["box"] for _,r in eligible]).reshape(-1,4),
                confidence=np.array([r["confidence"] for _,r in eligible]),
                class_id=np.zeros(len(eligible),dtype=int),
                data={"raw_index":np.array([i for i,_ in eligible],dtype=int)},
            )
            tracked = tracker.update_with_detections(detections)
            rows = []
            for box,score,tid,idx in zip(tracked.xyxy,tracked.confidence,tracked.tracker_id,
                                       tracked.data["raw_index"],strict=True):
                tid = int(tid)
                rows.append((tid,*map(float,box),float(score)))
                hits[tid] += 1
                colour = raw[int(idx)]["color"]
                teams.observe(tid,np.array(colour) if colour is not None else None)
            balls = [b for b in payload["candidates"][str(sample["order"])]
                     if b["confidence"] >= cfg["ball_threshold"]
                     and cal.is_on_pitch((b["box"][0]+b["box"][2])/2,b["box"][3],margin_m=1)]
            ball,source = None,None
            if balls:
                b = max(balls,key=lambda b:b["confidence"])
                x1,y1,x2,y2 = b["box"]
                ball,source = ((x1+x2)/2,(y1+y2)/2,b["confidence"]),"det"
            elif sample["ball_source"] == "roi" and sample["ball"]:
                b = sample["ball"]
                if cal.is_on_pitch(b[0],b[1],margin_m=1):
                    ball,source = b,"roi"
            samples.append(SampledObservation(sample["order"],sample["frame_idx"],sample["seconds"],rows,ball,source))
        min_hits = max(1,round(cfg["min_track_seconds"]*fps))
        for sample in samples:
            sample.persons = [r for r in sample.persons if hits[r[0]] >= min_hits]
        payload["samples"] = [asdict(s) for s in samples]
        payload["calibration"] = cal.to_dict()
        payload["colors"] = {str(t):[c.tolist() for c in cs] for t,cs in teams._obs.items()}
        payload["retracking"] = {"same_full_frame_detections":True,"roi_anchor_replayed":False}
        (args.out/path.name).write_text(json.dumps(payload),encoding="utf-8")
        print(path.name,len(samples),flush=True)


if __name__ == "__main__":
    main()
