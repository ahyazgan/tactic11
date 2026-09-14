"""Probe player-foot ROI reacquisition at labelled contacts, without DB or rollout.

GT supplies evaluation timestamps/positions only. ROI locations come exclusively
from detector player boxes. Report candidate availability separately from chosen
ball consistency; neither is full-video precision or independent ball-box GT.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import cv2
import numpy as np

from app.tracking.calibration import PitchCalibration
from app.tracking.detect import DetectorConfig, RFDetrDetector
from scripts.soccertrack_v2.audit_event_evidence import distance, reference_events


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--split", choices=("development", "control"), required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--calibration", type=Path, default=Path("data/tracking/calibrations/soccertrack_v2_117092_landmarks.json"))
    args = p.parse_args()
    if args.out.exists():
        p.error("choose a fresh output file")
    refs = reference_events(Path("data/tracking/datasets/soccertrack_v2/117092/117092_player_nodes.csv"))[0]
    lo, hi = (600, 780) if args.split == "development" else (780, 960)
    refs = [r for r in refs if lo <= r["seconds"] < hi]
    refs = [refs[i] for i in np.linspace(0, len(refs)-1, 8, dtype=int)]
    cal = PitchCalibration.load(args.calibration)
    det = RFDetrDetector(DetectorConfig(model="small", weights="data/tracking/models/rfdetr_mixed_small", tiles=4))
    cap = cv2.VideoCapture("data/tracking/videos/soccertrack_117092_sample_600_960.mp4")
    report = {"split": args.split, "roi_size": [320, 180], "threshold": .4, "events": []}
    for ref in refs:
        frames = []
        for offset in (-.24, 0, .24):
            cap.set(cv2.CAP_PROP_POS_MSEC, (ref["seconds"]-600+offset)*1000)
            ok, bgr = cap.read()
            if not ok:
                continue
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            start = time.perf_counter()
            persons, balls = det.split(det.detect(rgb))
            def eligible(detections, origin=(0,0), contact=ref["start"]):
                rows = []
                for box, score in zip(detections.xyxy, detections.confidence, strict=True):
                    u, v = (box[0]+box[2])/2+origin[0], (box[1]+box[3])/2+origin[1]
                    if score >= .4 and cal.is_on_pitch(u, v, margin_m=1):
                        point = cal.image_to_normalized(u, v)
                        rows.append({"pixel": [float(u),float(v)], "confidence": float(score),
                                     "distance_m": distance(point, contact)})
                return sorted(rows, key=lambda row: -row["confidence"])
            global_balls = eligible(balls)
            full_s = time.perf_counter()-start
            crops, origins = [], []
            for box in persons.xyxy:
                u, v = (box[0]+box[2])/2, box[3]
                if not cal.is_on_pitch(u,v,margin_m=2):
                    continue
                x = int(np.clip(u-160, 0, rgb.shape[1]-320))
                y = int(np.clip(v-90, 0, rgb.shape[0]-180))
                crops.append(rgb[y:y+180,x:x+320])
                origins.append((x,y))
            roi_balls = []
            start = time.perf_counter()
            # Respect the detector's compiled batch; no per-crop padded runs.
            batch_size = det._fixed_batch or det.cfg.effective_batch_size(rgb.shape[1],rgb.shape[0])
            for base in range(0,len(crops),batch_size):
                results = det._predict_batch(crops[base:base+batch_size])
                for k,result in enumerate(results):
                    roi_balls.extend(eligible(det.split(result)[1],origins[base+k]))
            roi_balls.sort(key=lambda r:-r["confidence"])
            chosen = global_balls[:1] or roi_balls[:1]
            frames.append({"offset": offset, "global":global_balls, "roi":roi_balls,
                           "selected":chosen, "crops":len(crops), "full_seconds":full_s,
                           "roi_seconds":time.perf_counter()-start})
        record = {"id":ref["id"],"seconds":ref["seconds"],"frames":frames}
        for name in ("global","roi","selected"):
            record[name+"_near_contact"] = any(r["distance_m"]<=5 for f in frames for r in f[name])
        record["global_selected_near_contact"] = any(f["global"] and f["global"][0]["distance_m"]<=5 for f in frames)
        report["events"].append(record)
        print(ref["seconds"], {k:v for k,v in record.items() if "contact" in k},flush=True)
    cap.release()
    report["summary"] = {k:sum(e[k] for e in report["events"])
                          for k in ("global_near_contact","roi_near_contact","selected_near_contact","global_selected_near_contact")}
    args.out.write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(report["summary"],flush=True)


if __name__ == "__main__":
    main()
