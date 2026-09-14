"""Per-event SoccerTrack evidence audit, using event time AND annotated positions.

Player-nodes coordinates use transverse x and reversed longitudinal y. Convert
to the GSR/tracking frame as (100*(1-y), 100*(1-x)); this was checked on the
development interval against GSR player positions. Team permutation is selected
on development and frozen in --alignment for subsequent runs.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment

PASS_TYPES = {"passSucceeded", "passFailed", "crossSucceeded", "crossFailed"}
RECOVERY_TYPES = {"intercept", "tackleSucceeded", "possession", "cutoff", "duelSucceeded"}
TIME_TOLERANCE_S = 2.0
START_TOLERANCE_M = 5.0
END_TOLERANCE_M = 8.0


def point(row, prefix=""):
    x, y = row.get(prefix + "x"), row.get(prefix + "y")
    if not x or not y:
        return None
    return [100 * (1 - float(y)), 100 * (1 - float(x))]


def distance(a, b):
    return float(np.linalg.norm((np.asarray(a) - b) * [1.05, 0.68]))


def reference_events(path: Path):
    passes, recoveries = [], []
    with path.open(encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            if row["event_period"] != "FIRST_HALF":
                continue
            t = int(row["event_time"]) / 1000
            if not 600 <= t < 960:
                continue
            kinds = set(row["filtered_event_types"].split())
            if not kinds & (PASS_TYPES | RECOVERY_TYPES):
                continue
            item = {"id": row["id"], "seconds": t, "player": int(row["player_id"]) if row["player_id"] else None,
                    "team": int(row["team_id"]), "start": point(row), "end": point(row, "relative_"),
                    "complete": bool(kinds & {"passSucceeded", "crossSucceeded"}),
                    "types": sorted(kinds)}
            if kinds & PASS_TYPES:
                passes.append(item)
            if kinds & RECOVERY_TYPES:
                recoveries.append(item)
    return passes, recoveries


def pair_events(predictions, references, mapping, *, spatial=True, full=False, recovery=False):
    if not predictions or not references:
        return []
    costs = np.full((len(predictions), len(references)), 1e6)
    for i, pred in enumerate(predictions):
        start = [pred["x"], pred["y"]] if recovery else [pred["start_x"], pred["start_y"]]
        for j, ref in enumerate(references):
            dt = abs(pred["minute"] * 60 - ref["seconds"])
            if dt > TIME_TOLERANCE_S:
                continue
            if spatial and (ref["start"] is None or distance(start, ref["start"]) > START_TOLERANCE_M):
                continue
            if full:
                if mapping.get(str(pred["team_external_id"])) != ref["team"]:
                    continue
                if not recovery:
                    if pred["complete"] != ref["complete"]:
                        continue
                    if ref["complete"] and (ref["end"] is None or distance([pred["end_x"], pred["end_y"]], ref["end"]) > END_TOLERANCE_M):
                        continue
            costs[i, j] = dt
    ii, jj = linear_sum_assignment(costs)
    return [(int(i), int(j)) for i, j in zip(ii, jj, strict=True) if costs[i, j] < 1e6]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--frames", type=Path, required=True)
    p.add_argument("--nodes", type=Path, required=True)
    p.add_argument("--alignment", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    references, recovery_refs = reference_events(args.nodes)
    frames, predictions, recoveries, intervals = [], [], [], []
    for path in sorted(args.frames.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        fs = payload["frames"]
        if not fs:
            continue
        frames.extend(fs)
        predictions.extend(payload.get("derived_passes", []))
        recoveries.extend(payload.get("derived_defensive_actions", []))
        # A 30-second segment can have lost leading/trailing tracking samples.
        lo = 600 + int(path.stem.split("_")[-1]) * 30
        intervals.append((lo, lo + 30))
    if not frames:
        p.error("no frame evidence")
    references = [r for r in references if any(lo <= r["seconds"] < hi for lo, hi in intervals)]
    recovery_refs = [r for r in recovery_refs if any(lo <= r["seconds"] < hi for lo, hi in intervals)]
    if args.alignment.exists():
        alignment = json.loads(args.alignment.read_text())
    else:
        dev_p = [r for r in predictions if r["minute"] * 60 < 780]
        dev_r = [r for r in references if r["seconds"] < 780]
        votes: Counter = Counter()
        for i, j in pair_events(dev_p, dev_r, {}):
            votes[(dev_p[i]["team_external_id"], dev_r[j]["team"])] += 1
        options = [{"30798": 30798, "30799": 30799}, {"30798": 30799, "30799": 30798}]
        scores = [sum(votes[(int(k), v)] for k, v in m.items()) for m in options]
        alignment = {"team_mapping": options[int(scores[1] > scores[0])], "development_votes": scores,
                     "time_offset_seconds": 0, "note": "team permutation only; no control-time alignment search"}
        args.alignment.write_text(json.dumps(alignment, indent=2), encoding="utf-8")
    mapping = alignment["team_mapping"]
    report = {"alignment": alignment, "source": str(args.frames), "splits": {},
              "tolerances": {"time_seconds": TIME_TOLERANCE_S, "start_m": START_TOLERANCE_M, "end_m": END_TOLERANCE_M},
              "limitations": "Event-consistency matches, not verified passer/recipient identities. Recovery reference vocabulary is incomplete. Existing TPS shares this match; full-match generalisation is unproven."}
    for name, lo, hi in (("development", 600, 780), ("control", 780, 960)):
        ps = [r for r in predictions if lo <= r["minute"] * 60 < hi]
        rs = [r for r in references if lo <= r["seconds"] < hi]
        fs = [r for r in frames if lo <= r["minute"] * 60 < hi]
        ds = [r for r in recoveries if lo <= r["minute"] * 60 < hi]
        dr = [r for r in recovery_refs if lo <= r["seconds"] < hi]
        spatial = pair_events(ps, rs, mapping)
        full = pair_events(ps, rs, mapping, full=True)
        matched_ids = {j for _, j in spatial}
        events = []
        for j, ref in enumerate(rs):
            window = [f for f in fs if abs(f["minute"] * 60 - ref["seconds"]) <= 0.6]
            observed = [f for f in window if f.get("ball") is not None and not f.get("ball_estimated")]
            ball_distances = [distance([f["ball"]["x"], f["ball"]["y"]], ref["start"])
                              for f in observed if ref["start"] is not None]
            contact_near = bool(ball_distances and min(ball_distances) <= START_TOLERANCE_M)
            actors = [p for f in observed for p in f["players"] if p.get("is_actor")]
            if j in matched_ids:
                reason = "time_and_start_matched"
            elif not observed:
                reason = "no_observed_ball_near_event"
            elif not contact_near:
                reason = "observed_ball_far_from_annotated_contact"
            elif not actors:
                reason = "ball_observed_no_actor"
            else:
                reason = "actor_present_transition_or_position_failed"
            events.append({**ref, "diagnosis": reason, "nearby_frames": len(window),
                           "ball_near_annotated_contact": contact_near,
                           "min_ball_contact_distance_m": round(min(ball_distances), 3) if ball_distances else None,
                           "observed_ball_frames": len(observed), "actor_observations": len(actors)})
        report["splits"][name] = {
            "frames": len(fs), "reference_passes": len(rs), "predicted_passes": len(ps),
            "time_only_matches": len(pair_events(ps, rs, mapping, spatial=False)),
            "time_start_matches": len(spatial), "time_start_team_outcome_end_matches": len(full),
            "unmatched_predictions_by_time_and_start": len(ps) - len(spatial),
            "observed_ball_fraction": sum(f.get("ball") is not None and not f.get("ball_estimated") for f in fs) / max(1, len(fs)),
            "actor_fraction": sum(any(p.get("is_actor") for p in f["players"]) for f in fs) / max(1, len(fs)),
            "reference_recovery_candidates": len(dr), "predicted_recoveries": len(ds),
            "pass_windows_with_ball_near_annotated_contact": sum(e["ball_near_annotated_contact"] for e in events),
            "passes_with_observed_flight": (None if any("observed_flight" not in p for p in ps)
                                            else sum(p["observed_flight"] for p in ps)),
            "recovery_time_start_team_matches": len(pair_events(ds, dr, mapping, full=True, recovery=True)),
            "diagnoses": dict(Counter(e["diagnosis"] for e in events)), "events": events,
        }
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: {a: b for a, b in v.items() if a != "events"} for k, v in report["splits"].items()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
