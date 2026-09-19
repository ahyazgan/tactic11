"""Frozen palette-consensus control acquisition and three-arm production replay.

Capture writes no team predictions to the blind review. Replay is permitted only
after independently authored label files have been sealed. No thresholds are fit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
from contextlib import nullcontext
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
from app.tracking.teams import kit_color
from scripts.soccertrack_v2.benchmark_tracker_backends import digest, load
from scripts.soccertrack_v2.candidates.identity_consensus_palette_v2 import (
    ConsensusTeamAssigner as PaletteAssigner,
)

FREEZE = Path("docs/measurements/identity-palette-frozen-decision.json")
ROOT = Path("data/tracking/bench/consensus_palette_control_v1")
SOURCES = {
    "day": dict(match=117093, segments={64: 1920, 66: 1980},
                template="data/tracking/bench/identity_day_detections/seg_0000.json"),
    "night": dict(match=117092, segments={78: 2340, 84: 2520},
                  template="data/tracking/bench/landmark_candidates_v1/seg_0000.json"),
}


def write_new(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def code_hash(path: Path) -> str:
    return hashlib.sha256(path.read_text(encoding="utf-8").encode()).hexdigest()


def verify() -> dict:
    decision = load(FREEZE)
    if decision["python"] != platform.python_version() or any(version(n) != v for n, v in decision["runtime_versions"].items()):
        raise ValueError("Frozen runtime changed")
    for name, expected in decision["code_sha256_lf"].items():
        if code_hash(Path(name)) != expected:
            raise ValueError(f"Frozen code changed: {name}")
    for name, expected in decision["input_sha256"].items():
        if digest(Path(name)) != expected:
            raise ValueError(f"Frozen input changed: {name}")
    return decision


def validate_control_timing(fps: float, count: float, starts: list[int]) -> None:
    if (fps != 25 or not np.isfinite(count) or count <= 0 or not starts
            or any(not np.isfinite(start) or start < 0 or (start + 30) * fps > count for start in starts)):
        raise ValueError("Control interval must fit source metadata before extraction")


def freeze() -> None:
    if FREEZE.exists() or ROOT.exists():
        raise ValueError("Control must be frozen before extraction")
    code = list(Path("app/tracking").rglob("*.py")) + [Path(__file__), Path("tests/test_consensus_palette_candidate.py"),
        Path("tests/test_consensus_palette_control.py"), Path("scripts/soccertrack_v2/score_palette_control.py")]
    code += list(Path("scripts/soccertrack_v2/candidates").glob("*.py"))
    code += [Path("scripts/soccertrack_v2") / n for n in (
        "prepare_identity_control.py", "benchmark_tracker_backends.py",
        "benchmark_joint_identity.py", "benchmark_track_buffer.py")]
    inputs = [Path(DEFAULT_MODEL), Path("data/tracking/models/rfdetr_mixed_small/checkpoint_best_total.pth"),
              Path("data/tracking/models/rfdetr_mixed_small/meta.json"),
              Path("docs/PALET-UZLASISI-KONTROL-PLANI.md"),
              Path("docs/SABIT-KAMERA-KONTROL-ETIKETLEME.md")]
    inputs += [Path("docs/measurements") / n for n in (
        "identity-palette-development-results.json", "identity-palette-production-parity.json",
        "joint-identity-consensus-integration-parity.json")]
    groups = {}
    for group, spec in SOURCES.items():
        template = Path(str(spec["template"]))
        source = Path(f"data/tracking/datasets/soccertrack_v2/{spec['match']}/{spec['match']}_panorama_1st_half.mp4")
        anchor = Path(f"docs/measurements/joint-identity-development-{group}-results.json")
        raw = load(template)
        cfg = pipeline.PipelineConfig(**{k: v for k, v in raw["config"].items() if k != "detector"})
        cfg.detector = DetectorConfig(**raw["config"]["detector"])
        # Pin the working CUDA implementation; auto selection must not change
        # silently if a local ONNX file is added during control acquisition.
        cfg.detector.backend = "torch"
        cfg.refine_player_identities = False
        inputs += [template, source, anchor]
        import cv2
        cap = cv2.VideoCapture(str(source))
        fps, count = cap.get(cv2.CAP_PROP_FPS), cap.get(cv2.CAP_PROP_FRAME_COUNT)
        cap.release()
        validate_control_timing(fps, count, list(spec["segments"].values()))
        groups[group] = dict(source=source.as_posix(), segments=spec["segments"],
            config=asdict(cfg), calibration=raw["calibration"],
            anchor=load(anchor)["anchors"]["before"])
    write_new(FREEZE, dict(created_utc=datetime.now(UTC).isoformat(),
        code_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        control_pixels_opened=False, profile="bytetrack-osnet-color-palette-consensus-v2",
        python=platform.python_version(), runtime_versions={n: version(n) for n in
            ("torch", "rfdetr", "supervision", "numpy", "opencv-python-headless", "imageio-ffmpeg")},
        code_sha256_lf={p.as_posix(): code_hash(p) for p in code},
        input_sha256={p.as_posix(): digest(p) for p in inputs}, groups=groups,
        detector_note="Explicit torch backend; all other parameters copied from development caches",
        acceptance="No source-group regressions and independently verified positive boundary; never auto-promote on unchanged output"))


def capture(group: str, decision: dict) -> None:
    spec = decision["groups"][group]
    out = ROOT / group / "raw"
    if out.exists():
        raise ValueError("Fresh raw directory required")
    cfg = pipeline.PipelineConfig(**{k: v for k, v in spec["config"].items() if k != "detector"})
    cfg.detector = DetectorConfig(**spec["config"]["detector"])
    detector = make_detector(cfg.detector)
    cal = PitchCalibration.from_dict(spec["calibration"])
    videos = {s: ROOT / group / "source" / f"seg_{int(s):04d}.mp4" for s in spec["segments"]}
    hashes = {str(p): digest(p) for p in videos.values()}
    for segment, video in videos.items():
        people = {}

        def hook(rgb, detections, sample, people=people):
            persons, _ = detector.split(detections)
            rows = []
            for box, confidence in zip(persons.xyxy, persons.confidence, strict=True):
                color = kit_color(rgb, tuple(map(float, box)))
                rows.append(dict(box=box.tolist(), confidence=float(confidence),
                                 color=None if color is None else color.tolist()))
            people[str(sample.order)] = rows

        samples, teams, stats = pipeline.collect_observations(video, cfg, detector=detector,
            calib=cal, observation_hook=hook)
        write_new(out / f"seg_{int(segment):04d}.json", dict(segment=int(segment), video=str(video),
            config=asdict(cfg), calibration=cal.to_dict(), stats=stats,
            samples=[asdict(s) for s in samples], detected_persons=people,
            colors={str(t): [c.tolist() for c in cs] for t, cs in teams._obs.items()}))
        print(f"Captured {group}/{segment}: {len(samples)} frames", flush=True)
    if hashes != {name: digest(Path(name)) for name in hashes}:
        raise ValueError("Source changed during capture")
    verify()
    write_new(out / "manifest.json", dict(freeze_sha256=digest(FREEZE), video_sha256=hashes,
        output_sha256={str(p): digest(p) for p in out.glob("seg_*.json")}))


def extract(group: str, decision: dict) -> None:
    import cv2
    import imageio_ffmpeg

    spec = decision["groups"][group]
    out = ROOT / group / "source"
    if out.exists():
        raise ValueError("Fresh source directory required")
    source = Path(spec["source"])
    cap = cv2.VideoCapture(str(source))
    fps, count = cap.get(cv2.CAP_PROP_FPS), cap.get(cv2.CAP_PROP_FRAME_COUNT)
    width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    if abs(fps - 25.) > .01 or count / fps < max(spec["segments"].values()) + 30:
        raise ValueError("Source does not cover the frozen 25fps intervals")
    executable = imageio_ffmpeg.get_ffmpeg_exe()
    out.mkdir(parents=True)
    clips = []
    for segment, start in spec["segments"].items():
        target = out / f"seg_{int(segment):04d}.mp4"
        command = [executable, "-nostdin", "-hide_banner", "-loglevel", "error", "-n",
            "-ss", str(start), "-i", str(source), "-frames:v", "750", "-an", "-c:v", "libx264",
            "-qp", "0", "-preset", "fast", str(target)]
        subprocess.run(command, check=True)
        cap = cv2.VideoCapture(str(target))
        observed = [int(cap.get(cv2.CAP_PROP_FRAME_COUNT)), int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                    int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))]
        clip_fps = cap.get(cv2.CAP_PROP_FPS)
        cap.release()
        if observed != [750, width, height] or abs(clip_fps - 25.) > .01:
            raise ValueError("Extracted clip geometry or duration differs")
        clips.append(dict(segment=int(segment), start_seconds=start, frames=750,
                          sha256=digest(target), command=command))
        print(f"Extracted frozen interval {group}/{segment}", flush=True)
    verify()
    write_new(out / "manifest.json", dict(freeze_sha256=digest(FREEZE), clips=clips,
        codec="Lossless H.264 qp=0; accurate input seeking, original dimensions and 25fps",
        ffmpeg_sha256=digest(Path(executable))))


def source_evidence(samples: list[dict]) -> list[tuple]:
    """Identity may change, but every source observation and team must survive."""
    return [(s["order"], s["frame_idx"], s["seconds"], s["continuity_id"], s["ball"], s["ball_source"],
             [(p[1:], s["person_teams"][str(p[0])]) for p in s["persons"]]) for s in samples]


def replay(group: str, decision: dict) -> None:
    import supervision as sv

    root = ROOT / group
    seal = load(root / "label-seal.json")
    if seal["freeze_sha256"] != digest(FREEZE):
        raise ValueError("Labels refer to another candidate")
    for name, expected in seal["label_sha256"].items():
        if digest(Path(name)) != expected:
            raise ValueError("Sealed labels changed")
    manifest = load(root / "raw/manifest.json")
    for name, expected in {**manifest["video_sha256"], **manifest["output_sha256"]}.items():
        if digest(Path(name)) != expected:
            raise ValueError("Raw evidence changed")
    out = root / "predictions"
    if out.exists():
        raise ValueError("Fresh prediction directory required")
    spec = decision["groups"][group]
    for segment in spec["segments"]:
        raw = load(root / "raw" / f"seg_{int(segment):04d}.json")
        original_evidence = None
        for backend in ("supervision", "consensus", "palette"):
            cfg = pipeline.PipelineConfig(**{k: v for k, v in spec["config"].items() if k != "detector"})
            cfg.detector = DetectorConfig(**spec["config"]["detector"])
            cfg.tracker_backend = "consensus" if backend == "palette" else backend

            class CachedDetector:
                def __init__(self, source):
                    self.index = 0
                    self.source = source

                def detect(self, rgb):
                    sample = self.source["samples"][self.index]
                    self.index += 1
                    rows = self.source["detected_persons"][str(sample["order"])]
                    return sv.Detections(xyxy=np.asarray([r["box"] for r in rows]).reshape(-1, 4),
                        confidence=np.asarray([r["confidence"] for r in rows]), class_id=np.zeros(len(rows), dtype=int))

                def split(self, detections):
                    return detections, sv.Detections.empty()

            detector = CachedDetector(raw)
            collected = []
            assigned = {}
            original = pipeline.collect_observations
            original_build = pipeline.build_frames

            def collect(*a, original=original, collected=collected, **kw):
                result = original(*a, **kw)
                collected.append(result[0])
                return result

            def build(samples, teams, *a, assigned=assigned, original_build=original_build, **kw):
                assigned.update(teams)
                return original_build(samples, teams, *a, **kw)

            with (patch.object(pipeline, "collect_observations", side_effect=collect),
                  patch.object(pipeline, "build_frames", side_effect=build),
                  patch.object(identity_consensus, "ConsensusTeamAssigner", PaletteAssigner) if backend == "palette" else nullcontext()):
                _, summary = pipeline.process_video(Path(raw["video"]), PitchCalibration.from_dict(spec["calibration"]),
                    cfg=cfg, detector=detector, team_anchor=np.asarray(spec["anchor"]),
                    match_id=990909, home_team_id=217, away_team_id=213)
            if detector.index != len(raw["samples"]):
                raise ValueError("Incomplete replay")
            samples = [asdict(s) for s in collected[0]]
            if backend == "supervision":
                for sample in samples:
                    sample["person_teams"] = {str(p[0]): assigned.get(p[0]) for p in sample["persons"]}
            evidence = source_evidence(samples)
            if backend == "supervision":
                original_evidence = evidence
            elif evidence != original_evidence:
                raise ValueError("Candidate changed source observations or per-observation teams")
            write_new(out / backend / f"seg_{int(segment):04d}.json", dict(samples=samples, summary=summary))
    verify()
    write_new(out / "manifest.json", dict(freeze_sha256=digest(FREEZE), label_seal_sha256=digest(root / "label-seal.json"), source_evidence_exact=True))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["freeze", "verify", "extract", "capture", "replay"])
    parser.add_argument("--group", choices=list(SOURCES))
    args = parser.parse_args()
    if args.action == "freeze":
        freeze()
    else:
        decision = verify()
        if args.action != "verify":
            if not args.group:
                parser.error("--group required")
            {"extract": extract, "capture": capture, "replay": replay}[args.action](args.group, decision)


if __name__ == "__main__":
    main()
