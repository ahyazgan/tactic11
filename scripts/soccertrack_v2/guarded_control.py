"""Freeze, acquire and replay the predeclared guarded identity temporal control.

No new pixels before a committed freeze; no predictions before both groups'
complete blind labels are committed. Existing candidates and controls are read-only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from contextlib import contextmanager, nullcontext
from dataclasses import asdict
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from unittest.mock import patch

import numpy as np

from app.tracking import identity_consensus, pipeline
from app.tracking.calibration import PitchCalibration
from app.tracking.deepocsort import DEFAULT_MODEL
from app.tracking.detect import DetectorConfig, make_detector
from app.tracking.guarded_identity import PROFILE
from app.tracking.teams import kit_color
from scripts.soccertrack_v2.benchmark_tracker_backends import digest, load
from scripts.soccertrack_v2.candidates.identity_consensus_palette_v2 import (
    ConsensusTeamAssigner as PaletteAssigner,
)
from scripts.soccertrack_v2.consensus_palette_control import validate_control_timing, write_new
from scripts.soccertrack_v2.prepare_identity_control import (
    PAIR_DELTA_FRAMES,
    START_FRAMES,
    select_raw_frames,
)
from scripts.soccertrack_v2.validate_palette_acquisition import validate_group, validate_payload

DOC = Path("docs/measurements")
FREEZE = DOC / "identity-guarded-frozen-decision.json"
ROOT = Path("data/tracking/bench/guarded_control_v1")
PLAN = Path("docs/BIRLESIK-KIMLIK-KONTROL-PLANI.md")
METHODS = ("supervision", "palette", "guarded")
PACKAGES = ("torch", "rfdetr", "supervision", "trackers", "numpy", "scipy",
            "opencv-python-headless", "imageio-ffmpeg", "filterpy")
SOURCES = {
    "day": dict(match=117093, segments={68: 2040, 72: 2160},
                template="data/tracking/bench/identity_day_detections/seg_0000.json"),
    "night": dict(match=117092, segments={74: 2220, 76: 2280},
                  template="data/tracking/bench/landmark_candidates_v1/seg_0000.json"),
}


def code_hash(path):
    return hashlib.sha256(Path(path).read_text(encoding="utf-8").encode()).hexdigest()


def committed(path):
    """A local file is not a seal until its exact bytes are in HEAD."""
    relative = Path(path).resolve().relative_to(Path.cwd().resolve()).as_posix()
    saved = subprocess.check_output(["git", "show", f"HEAD:{relative}"])
    if saved != Path(path).read_bytes():
        raise ValueError(f"Evidence must be committed unchanged: {relative}")


def verify(*, require_commit=True):
    decision = load(FREEZE)
    if decision.get("profile") != PROFILE or decision.get("methods") != list(METHODS):
        raise ValueError("Unexpected frozen candidate")
    if decision["python"] != platform.python_version() or any(
            version(name) != expected for name, expected in decision["runtime_versions"].items()):
        raise ValueError("Frozen runtime changed")
    for name, expected in decision["code_sha256_lf"].items():
        if code_hash(name) != expected:
            raise ValueError(f"Frozen code changed: {name}")
    for name, expected in decision["input_sha256"].items():
        if digest(Path(name)) != expected:
            raise ValueError(f"Frozen input changed: {name}")
    if require_commit:
        committed(FREEZE)
        paths = list(decision["code_sha256_lf"])
        subprocess.run(["git", "ls-files", "--error-unmatch", "--", *paths],
                       stdout=subprocess.DEVNULL, check=True)
        subprocess.run(["git", "diff", "--quiet", "HEAD", "--", *paths], check=True)
    return decision


def prerequisites():
    """Recheck accepted integration evidence, not just a success field."""
    paths = [DOC / f"{name}.json" for name in (
        "identity-guarded-production-19", "identity-guarded-production-db",
        "identity-guarded-real-live", "identity-guarded-real-live-db",
        "identity-guarded-integration-audit", "joint-identity-guarded-integration-parity",
        "joint-identity-guarded-integration-amendment")]
    production, database, live, live_db, audit, parity, _ = map(load, paths)
    if (not production.get("completed_at_utc") or len(production["comparisons"]) != 19
            or not all(c["equal"] and c["baseline_equal"] for c in production["comparisons"])
            or not database["all_evidence_preserved"] or database["clips"] != 19
            or not live.get("completed_at_utc") or len(live["cases"]) != 2
            or not all(c["same_frames"] and c["same_identity_audit"] for c in live["cases"])
            or not live_db["all_evidence_preserved"] or not live_db["same_recorded_warm_events"]
            or len(parity["comparisons"]) != 22 or not all(c["equal"] for c in parity["comparisons"])):
        raise ValueError("Completed development and integration evidence required")
    for key, path in (("production_report_sha256", paths[0]), ("live_report_sha256", paths[2]),
                      ("live_db_report_sha256", paths[3])):
        if audit[key] != digest(path):
            raise ValueError("Integration audit refers to changed evidence")
    for report, keys in ((production, ("input_code_sha256", "output_sha256")),
                         (live, ("code_model_input_sha256", "output_sha256"))):
        for key in keys:
            for name, expected in report[key].items():
                if digest(Path(name)) != expected:
                    raise ValueError(f"Integration input/output changed: {name}")
    return paths


def freeze():
    if FREEZE.exists() or ROOT.exists():
        raise ValueError("Control must be frozen before extraction")
    evidence = prerequisites()
    prior_source_record = DOC / "identity-palette-frozen-decision.json"
    committed(prior_source_record)
    known_inputs = {Path(p).resolve(): sha for p, sha in load(prior_source_record)["input_sha256"].items()}
    code = set(Path("app/tracking").rglob("*.py"))
    code.update(Path("scripts/soccertrack_v2").glob("*.py"))
    code.update(Path("scripts/soccertrack_v2/candidates").glob("*.py"))
    code.update(Path(p) for p in ("scripts/track_live.py", "scripts/track_video.py",
        "tests/test_guarded_control.py", "tests/test_guarded_control_scoring.py"))
    inputs = [PLAN, Path("docs/SABIT-KAMERA-KONTROL-ETIKETLEME.md"), Path(DEFAULT_MODEL),
        Path("data/tracking/models/rfdetr_mixed_small/checkpoint_best_total.pth"),
        Path("data/tracking/models/rfdetr_mixed_small/meta.json"), prior_source_record, *evidence]
    groups = {}
    import cv2
    for group, spec in SOURCES.items():
        source = Path(f"data/tracking/datasets/soccertrack_v2/{spec['match']}/{spec['match']}_panorama_1st_half.mp4")
        template = Path(str(spec["template"]))
        anchor = DOC / f"joint-identity-development-{group}-results.json"
        raw = load(template)
        cfg = pipeline.PipelineConfig(**{k: v for k, v in raw["config"].items() if k != "detector"})
        cfg.detector = DetectorConfig(**raw["config"]["detector"])
        cfg.detector.backend, cfg.detector.roi_single_batch = "torch", False
        cfg.tracker_backend, cfg.refine_player_identities, cfg.preview_path = "supervision", False, None
        cap = cv2.VideoCapture(str(source), cv2.CAP_FFMPEG, [cv2.CAP_PROP_N_THREADS, 1])
        fps, count = cap.get(cv2.CAP_PROP_FPS), cap.get(cv2.CAP_PROP_FRAME_COUNT)
        size = [int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))]
        cap.release()
        validate_control_timing(fps, count, list(spec["segments"].values()))
        inputs.extend((source, template, anchor))
        groups[group] = dict(source=source.as_posix(), segments=spec["segments"],
            config=asdict(cfg), calibration=raw["calibration"], anchor=load(anchor)["anchors"]["before"],
            source_frames=count, source_fps=fps, image_size=size)
    input_hashes = {p.as_posix(): digest(p) for p in inputs}
    if any(input_hashes[spec["source"]] != known_inputs.get(Path(spec["source"]).resolve())
           for spec in groups.values()):
        raise ValueError("Original full-match source differs from the previous frozen source")
    write_new(FREEZE, dict(created_at_utc=datetime.now(UTC).isoformat(), profile=PROFILE,
        code_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        control_pixels_opened=False, methods=list(METHODS), python=platform.python_version(),
        runtime_versions={n: version(n) for n in PACKAGES}, decoder_threads=1, gradients=False,
        code_sha256_lf={p.as_posix(): code_hash(p) for p in sorted(code)},
        input_sha256=input_hashes, groups=groups,
        acceptance="Per-source non-regression against both comparisons, exact baseline evidence, real-source unknown-team extras, all changes reviewed, positive independent correction; no automatic promotion."))
    verify(require_commit=False)


@contextmanager
def decoding():
    import cv2
    import torch
    original, threads = cv2.VideoCapture, cv2.getNumThreads()

    def capture(path):
        cap = original(str(path), cv2.CAP_FFMPEG, [cv2.CAP_PROP_N_THREADS, 1])
        if not cap.isOpened() or cap.get(cv2.CAP_PROP_N_THREADS) != 1:
            cap.release()
            raise ValueError("Verified single-thread video decoder required")
        return cap

    cv2.setNumThreads(1)
    try:
        with torch.no_grad(), patch.object(cv2, "VideoCapture", side_effect=capture):
            yield
    finally:
        cv2.setNumThreads(threads)


def extract(group, decision):
    import cv2
    import imageio_ffmpeg
    spec, out = decision["groups"][group], ROOT / group / "source"
    if out.exists():
        raise ValueError("Fresh source directory required")
    executable = imageio_ffmpeg.get_ffmpeg_exe()
    out.mkdir(parents=True)
    clips = []
    for segment, start in spec["segments"].items():
        target = out / f"seg_{int(segment):04d}.mp4"
        command = [executable, "-nostdin", "-hide_banner", "-loglevel", "error", "-n",
            "-threads", "1", "-ss", str(start), "-i", spec["source"], "-frames:v", "750",
            "-an", "-c:v", "libx264", "-qp", "0", "-preset", "fast", "-threads", "1", str(target)]
        subprocess.run(command, check=True)
        cap = cv2.VideoCapture(str(target), cv2.CAP_FFMPEG, [cv2.CAP_PROP_N_THREADS, 1])
        observed = [int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))]
        count, fps = cap.get(cv2.CAP_PROP_FRAME_COUNT), cap.get(cv2.CAP_PROP_FPS)
        cap.release()
        if observed != spec["image_size"] or count != 750 or fps != 25:
            raise ValueError("Extracted source geometry or duration differs")
        clips.append(dict(segment=int(segment), start_seconds=start, frames=750,
                          sha256=digest(target), command=command))
    verify()
    write_new(out / "manifest.json", dict(freeze_sha256=digest(FREEZE), clips=clips,
        codec="Lossless H.264 qp=0, original 25fps dimensions", ffmpeg_sha256=digest(Path(executable))))


def validate_sources(group, decision):
    spec = decision["groups"][group]
    manifest = load(ROOT / group / "source/manifest.json")
    clips = manifest["clips"]
    if (manifest["freeze_sha256"] != digest(FREEZE) or len(clips) != len(spec["segments"])
            or {str(c["segment"]) for c in clips} != set(spec["segments"])):
        raise ValueError("Incomplete frozen source manifest")
    for clip in clips:
        if (clip["frames"] != 750 or clip["start_seconds"] != spec["segments"][str(clip["segment"])]
                or digest(ROOT / group / "source" / f"seg_{clip['segment']:04d}.mp4") != clip["sha256"]):
            raise ValueError("Source interval or hash changed")


def capture(group, decision):
    spec, out = decision["groups"][group], ROOT / group / "raw"
    if out.exists():
        raise ValueError("Fresh raw directory required")
    validate_sources(group, decision)
    cfg = pipeline.PipelineConfig(**{k: v for k, v in spec["config"].items() if k != "detector"})
    cfg.detector = DetectorConfig(**spec["config"]["detector"])
    cal = PitchCalibration.from_dict(spec["calibration"])
    videos = {s: ROOT / group / "source" / f"seg_{int(s):04d}.mp4" for s in spec["segments"]}
    hashes = {str(p): digest(p) for p in videos.values()}
    with decoding():
        detector = make_detector(cfg.detector)
        for segment, video in videos.items():
            people = {}

            def hook(rgb, detections, sample, people=people):
                persons, _ = detector.split(detections)
                people[str(sample.order)] = []
                for box, confidence in zip(persons.xyxy, persons.confidence, strict=True):
                    color = kit_color(rgb, tuple(map(float, box)))
                    people[str(sample.order)].append(dict(box=box.tolist(), confidence=float(confidence),
                        color=None if color is None else color.tolist()))

            samples, teams, stats = pipeline.collect_observations(video, cfg, detector=detector,
                calib=cal, observation_hook=hook)
            payload = dict(segment=int(segment), video=str(video), config=asdict(cfg),
                calibration=cal.to_dict(), stats=stats, samples=[asdict(s) for s in samples],
                detected_persons=people, colors={str(t): [c.tolist() for c in cs] for t, cs in teams._obs.items()})
            write_new(out / f"seg_{int(segment):04d}.json", payload)
            validate_payload(payload, spec, int(segment))
            print(f"Captured {group}/{segment}: {len(samples)} samples", flush=True)
    if hashes != {p: digest(Path(p)) for p in hashes}:
        raise ValueError("Source changed during capture")
    verify()
    write_new(out / "manifest.json", dict(freeze_sha256=digest(FREEZE), video_sha256=hashes,
        output_sha256={str(p): digest(p) for p in out.glob("seg_*.json")}))
    validate_group(group, root=ROOT, freeze=FREEZE)


def prepare(group, decision):
    from scripts.soccertrack_v2.prepare_identity_control import main as prepare_main
    validate_group(group, root=ROOT, freeze=FREEZE)
    root = ROOT / group
    args = ["prepare_identity_control", "--cache", str(root / "raw"), "--source", str(root / "source"),
            "--segments", *decision["groups"][group]["segments"], "--out", str(root / "blind")]
    with decoding(), patch.object(sys, "argv", args):
        if prepare_main() != 0:
            raise ValueError("Blind source preparation failed")
    verify()
    validate_group(group, root=ROOT, freeze=FREEZE)


def expected_labels(raws):
    observations, starts = {}, set()
    for segment, raw in raws.items():
        selected = select_raw_frames(raw, segment)
        for frame in (*START_FRAMES, *(f + PAIR_DELTA_FRAMES for f in START_FRAMES)):
            for row in selected[frame]:
                observations[row["id"]] = row
                if frame in START_FRAMES:
                    starts.add(row["id"])
    return observations, starts


def validate_labels(labels, pairs, raws):
    expected, starts = expected_labels(raws)
    for document in (labels, pairs):
        if (document.get("predictions_visible_during_labeling") is not False
                or not document.get("reviewer") or not document.get("limitations")):
            raise ValueError("Blind reviewer and limitations required")
    for rows in (labels["records"], pairs["observations"]):
        if len(rows) != len(expected) or {r["id"] for r in rows} != set(expected):
            raise ValueError("Every source endpoint must be labeled exactly once")
        for row in rows:
            if any(row.get(k) != expected[row["id"]][k] for k in
                   ("segment", "frame_idx", "detector_index", "bbox")):
                raise ValueError("Label source geometry changed")
    for row in labels["records"]:
        if (row.get("kit") not in {"blue", "white", "other", "uncertain", "not_person"}
                or not row.get("box_scope") or not row.get("visual_basis")):
            raise ValueError("Complete visual kit and box-scope labels required")
    reviews = labels["source_review"]
    if len(reviews) != len(starts) or {r["id"] for r in reviews} != starts:
        raise ValueError("Every starting source box must be reviewed")
    status = {r["id"]: r["status"] for r in reviews}
    if any(r["status"] not in {"same_labeled", "uncertain", "visible_person_without_source_box", "not_person"}
           or not r.get("reason") for r in reviews):
        raise ValueError("Explicit source visibility reasons required")
    links = {}
    kits = {r["id"]: r["kit"] for r in labels["records"]}
    for pair in pairs["pairs"]:
        left, right = expected.get(pair["left"]), expected.get(pair["right"])
        if (left is None or right is None or pair["left"] not in starts
                or left["segment"] != right["segment"]
                or right["frame_idx"] - left["frame_idx"] != PAIR_DELTA_FRAMES
                or pair["relation"] not in {"same", "different"} or not pair.get("visual_basis")
                or status[pair["left"]] != "same_labeled"
                or kits[pair["left"]] == "not_person" or kits[pair["right"]] == "not_person"):
            raise ValueError("Invalid or uncertain source association")
        key = pair["left"], pair["relation"]
        if key in links:
            raise ValueError("Duplicate source association")
        links[key] = pair["right"]
    for identity, state in status.items():
        if state == "same_labeled" and (
                (identity, "same") not in links or (identity, "different") not in links
                or links[identity, "same"] == links[identity, "different"]):
            raise ValueError("Same-person review requires a distinct negative source pair")
    return dict(start_boxes=len(starts), endpoint_boxes=len(expected), pairs=len(links))


def seal_path(group):
    return DOC / f"identity-guarded-control-{group}-seal.json"


def validate_blind_packet(group, decision):
    root = ROOT / group
    blind = load(root / "blind/manifest.json")
    segments = decision["groups"][group]["segments"]
    expected = {root / kind / f"seg_{int(s):04d}.{suffix}"
                for s in segments for kind, suffix in (("raw", "json"), ("source", "mp4"))}
    observed = {Path(p).resolve(): sha for p, sha in blind["input_sha256"].items()}
    if (len(observed) != len(expected) or set(observed) != {p.resolve() for p in expected}
            or any(digest(p) != sha for p, sha in observed.items())
            or len(blind["segments"]) != len(segments)
            or {str(s["segment"]) for s in blind["segments"]} != set(segments)
            or blind.get("predictions_visible_during_labeling") is not False):
        raise ValueError("Blind packet source changed or incomplete")
    for segment in blind["segments"]:
        if not segment["assets_sha256"]:
            raise ValueError("Blind source images missing")
        for name, sha in segment["assets_sha256"].items():
            if digest(root / "blind" / name) != sha:
                raise ValueError("Blind source image changed")


def seal(group, decision, labels_path, pairs_path):
    if any((ROOT / g / "predictions").exists() for g in SOURCES):
        raise ValueError("Cannot seal labels after predictions were opened")
    validate_group(group, root=ROOT, freeze=FREEZE)
    root = ROOT / group
    raws = {int(s): load(root / "raw" / f"seg_{int(s):04d}.json") for s in decision["groups"][group]["segments"]}
    counts = validate_labels(load(labels_path), load(pairs_path), raws)
    for path in (labels_path, pairs_path):
        committed(path)
    validate_blind_packet(group, decision)
    verify()
    write_new(seal_path(group), dict(sealed_at_utc=datetime.now(UTC).isoformat(),
        freeze_sha256=digest(FREEZE), label_sha256={str(p): digest(p) for p in (labels_path, pairs_path)},
        blind_manifest_sha256=digest(root / "blind/manifest.json"), counts=counts,
        predictions_opened=False, independently_adjudicated=False))


def verify_seals(decision):
    for group in SOURCES:
        validate_group(group, root=ROOT, freeze=FREEZE)
        path = seal_path(group)
        seal_record = load(path)
        if (seal_record["freeze_sha256"] != digest(FREEZE)
                or seal_record["predictions_opened"] is not False
                or seal_record["blind_manifest_sha256"] != digest(ROOT / group / "blind/manifest.json")):
            raise ValueError("Labels refer to different control evidence")
        committed(path)
        if len(seal_record["label_sha256"]) != 2:
            raise ValueError("Exactly one complete labels and pairs document required")
        documents = []
        for name, sha in seal_record["label_sha256"].items():
            if digest(Path(name)) != sha:
                raise ValueError("Sealed labels changed")
            committed(Path(name))
            documents.append(load(Path(name)))
        labels = next(d for d in documents if "records" in d)
        pairs = next(d for d in documents if "observations" in d)
        raws = {int(s): load(ROOT / group / "raw" / f"seg_{int(s):04d}.json")
                for s in decision["groups"][group]["segments"]}
        if validate_labels(labels, pairs, raws) != seal_record["counts"]:
            raise ValueError("Sealed label completeness changed")
        validate_blind_packet(group, decision)


def source_coverage(raw, baseline, candidate):
    """Allow only identity changes and unknown-team additions from real source rows."""
    def index(payload):
        rows = {}
        if len(payload["samples"]) != len(raw["samples"]):
            raise ValueError("Prediction sample coverage changed")
        for reference, sample in zip(raw["samples"], payload["samples"], strict=True):
            if any(sample[k] != reference[k] for k in ("order", "frame_idx", "seconds", "continuity_id")):
                raise ValueError("Prediction source timeline changed")
            source = {tuple((*r["box"], r["confidence"])) for r in raw["detected_persons"][str(sample["order"]) ]}
            seen = set()
            for row in sample["persons"]:
                key = (sample["continuity_id"], sample["frame_idx"], tuple(row[1:]))
                if tuple(row[1:]) not in source or key in rows or row[0] in seen:
                    raise ValueError("Prediction altered or duplicated source evidence")
                seen.add(row[0])
                rows[key] = sample["person_teams"][str(row[0])]
        return rows
    before, after = index(baseline), index(candidate)
    if (before.keys() - after.keys() or any(after[k] != v for k, v in before.items())
            or any(after[k] is not None for k in after.keys() - before.keys())):
        raise ValueError("Candidate lost baseline evidence or changed observation teams")
    return dict(baseline=len(before), candidate=len(after), removed=0,
                added=len(after.keys() - before.keys()), changed_teams=0)


def replay(group, decision):
    verify_seals(decision)
    import supervision as sv
    root, spec = ROOT / group, decision["groups"][group]
    out = root / "predictions"
    if out.exists():
        raise ValueError("Fresh prediction directory required")
    comparisons = []
    with decoding():
        for segment in spec["segments"]:
            raw = load(root / "raw" / f"seg_{int(segment):04d}.json")
            baseline = None
            for backend in METHODS:
                cfg = pipeline.PipelineConfig(**{k: v for k, v in spec["config"].items() if k != "detector"})
                cfg.detector = DetectorConfig(**spec["config"]["detector"])
                cfg.tracker_backend = "consensus" if backend == "palette" else backend

                class CachedDetector:
                    def __init__(self, data):
                        self.data, self.index = data, 0

                    def detect(self, rgb):
                        sample = self.data["samples"][self.index]
                        self.index += 1
                        rows = self.data["detected_persons"][str(sample["order"])]
                        return sv.Detections(xyxy=np.asarray([r["box"] for r in rows]).reshape(-1, 4),
                            confidence=np.asarray([r["confidence"] for r in rows]), class_id=np.zeros(len(rows), dtype=int))

                    def split(self, detections):
                        return detections, sv.Detections.empty()

                detector = CachedDetector(raw)
                collected, assigned = [], {}
                original, original_build = pipeline.collect_observations, pipeline.build_frames

                def collect(*a, original=original, collected=collected, **kw):
                    result = original(*a, **kw)
                    collected.extend(result[0])
                    return result

                def build(samples, teams, *a, assigned=assigned, original_build=original_build, **kw):
                    assigned.update(teams)
                    return original_build(samples, teams, *a, **kw)

                with (patch.object(pipeline, "collect_observations", side_effect=collect),
                      patch.object(pipeline, "build_frames", side_effect=build),
                      patch.object(identity_consensus, "ConsensusTeamAssigner", PaletteAssigner) if backend == "palette" else nullcontext()):
                    _, summary = pipeline.process_video(Path(raw["video"]), PitchCalibration.from_dict(spec["calibration"]),
                        cfg=cfg, detector=detector, team_anchor=np.asarray(spec["anchor"]),
                        match_id=991014, home_team_id=217, away_team_id=213)
                if detector.index != len(raw["samples"]):
                    raise ValueError("Incomplete replay")
                samples = [asdict(s) for s in collected]
                if backend == "supervision":
                    for sample in samples:
                        sample["person_teams"] = {str(p[0]): assigned.get(p[0]) for p in sample["persons"]}
                    baseline = dict(samples=samples)
                payload = dict(samples=samples, summary=summary)
                check = source_coverage(raw, baseline, payload)
                if backend == "palette" and check["added"]:
                    raise ValueError("Previous palette comparison changed source coverage")
                write_new(out / backend / f"seg_{int(segment):04d}.json", payload)
                comparisons.append(dict(segment=int(segment), backend=backend, coverage=check))
    verify()
    verify_seals(decision)
    write_new(out / "manifest.json", dict(freeze_sha256=digest(FREEZE),
        label_seal_sha256={g: digest(seal_path(g)) for g in SOURCES}, comparisons=comparisons,
        output_sha256={str(p): digest(p) for p in out.glob("*/seg_*.json")}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["freeze", "verify", "extract", "capture", "validate", "prepare", "seal", "replay"])
    parser.add_argument("--group", choices=list(SOURCES))
    parser.add_argument("--labels", type=Path)
    parser.add_argument("--pairs", type=Path)
    args = parser.parse_args()
    if args.action == "freeze":
        freeze()
        return
    decision = verify()
    if args.action == "verify":
        print("Frozen guarded control verified")
        return
    if not args.group:
        parser.error("--group required")
    if args.action == "validate":
        print(json.dumps(validate_group(args.group, root=ROOT, freeze=FREEZE)))
    elif args.action == "seal":
        if not args.labels or not args.pairs:
            parser.error("--labels and --pairs required")
        seal(args.group, decision, args.labels, args.pairs)
    else:
        {"extract": extract, "capture": capture, "prepare": prepare, "replay": replay}[args.action](args.group, decision)


if __name__ == "__main__":
    main()
