"""Export frozen observation caches through production frames and preview APIs.

This performs no detection, model fitting, evaluation or database writes. The
default source is the brighter development clip, not a new control sample.
Run with the repository venv-cv: python -m scripts.soccertrack_v2.export_joint_identity
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.tracking.calibration import PitchCalibration
from app.tracking.detect import DetectorConfig
from app.tracking.frames import VIDEO_PLAYER_BASE_ID, frames_from_json, frames_to_json
from app.tracking.identity_namespace import SegmentIdentityNamespace
from app.tracking.pipeline import (
    PipelineConfig,
    SampledObservation,
    build_frames,
    preview_fps,
    validate_video_calibration,
    video_info,
    write_preview,
)

DEFAULT_AMENDMENT = Path("docs/measurements/joint-identity-consensus-integration-amendment.json")
INTEGRATION_ALLOWLIST = frozenset({
    "app/tracking/pipeline.py", "scripts/track_video.py", "scripts/track_live.py",
})
ADDED_INTEGRATION_ALLOWLIST = frozenset({
    "app/tracking/anchor_state.py", "tests/test_tracking_cli_identity.py",
    "tests/test_identity_source_guard.py",
})
REID_INTEGRATION_ALLOWLIST = ADDED_INTEGRATION_ALLOWLIST | frozenset({
    "app/tracking/deepocsort.py", "app/tracking/tracker_config.py",
    "app/tracking/_vendor/__init__.py", "app/tracking/_vendor/deepocsort/__init__.py",
    "app/tracking/_vendor/deepocsort/ocsort.py", "app/tracking/_vendor/deepocsort/association.py",
    "app/tracking/_vendor/deepocsort/kalmanfilter.py", "app/tracking/_vendor/deepocsort/osnet_ain.py",
    "tests/test_deepocsort.py", "tests/test_tracking_reid_integration.py",
    "tests/test_tracking_reid_freeze.py", "scripts/soccertrack_v2/replay_reid_integration.py",
    "scripts/soccertrack_v2/benchmark_deepocsort.py", "scripts/setup_tracking_reid.py",
})
PREVIOUS_AMENDMENT_SHA256 = "9fa78242f1e8a7ee31f105d3be6d0c41ca4332f617eabd49cdd51e0b23fd8e01"
PREVIOUS_REID_AMENDMENT_SHA256 = "6b0ff374fffd9a43ff5215544cdd3a1fc26974ebe40a599a20c0085cd8189a32"
CONSENSUS_INTEGRATION_ALLOWLIST = REID_INTEGRATION_ALLOWLIST | frozenset({
    "app/tracking/identity_consensus.py", "tests/test_identity_consensus.py",
    "scripts/soccertrack_v2/replay_consensus_defaults.py",
    "scripts/soccertrack_v2/replay_consensus_integration.py",
})


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def save_json(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")


def _sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError(f"Invalid SHA-256 for {label}")
    return value


def _reference(value: Any, label: str) -> dict[str, str]:
    if not isinstance(value, dict) or not isinstance(value.get("path"), str) or not value["path"]:
        raise ValueError(f"Invalid {label} reference")
    return {"path": value["path"], "sha256": _sha256(value.get("sha256"), label)}


def verify_frozen_code(path: Path, amendment_path: Path | None = DEFAULT_AMENDMENT) -> dict[str, Any]:
    """Verify the original candidate or its explicitly bounded integration patch.

    Paths inside the documents are repository-relative, as in the original
    freeze. Code hashes normalize CRLF to LF; document/evidence hashes use raw
    bytes. The full original code map remains authoritative outside three CLI
    integration files. An existing amendment is always checked, never silently
    accepted or ignored. A pristine original tree needs no amendment file.
    """
    freeze_bytes = path.read_bytes()
    freeze_digest = hashlib.sha256(freeze_bytes).hexdigest()
    freeze = json.loads(freeze_bytes)
    if not isinstance(freeze, dict):
        raise ValueError("Invalid original frozen decision document")
    expected = freeze.get("code_sha256_lf")
    if not isinstance(expected, dict) or not expected or any(not isinstance(name, str) for name in expected):
        raise ValueError("Invalid original frozen code hash map")
    expected = {name: _sha256(value, name) for name, value in expected.items()}
    actual = {name: hashlib.sha256(Path(name).read_text(encoding="utf-8").encode()).hexdigest()
              for name in expected}
    verification: dict[str, Any] = {
        "mode": "original_freeze", "matches_original_freeze": actual == expected,
        "original_freeze": {"path": path.as_posix(), "sha256": freeze_digest},
        "original_code_sha256_lf": expected, "production_code_sha256_lf": actual,
        "integration_amendment": None, "parity_evidence": None, "code_changes": {},
        "added_integration_code_sha256_lf": {},
    }
    if amendment_path is None or not amendment_path.is_file():
        if actual != expected:
            raise ValueError("Production files differ from the original freeze; an integration amendment is required")
        return verification

    amendment_bytes = amendment_path.read_bytes()
    amendment = json.loads(amendment_bytes)
    if not isinstance(amendment, dict):
        raise ValueError("Invalid integration amendment")
    amendment_version = amendment.get("version", 1)
    if amendment_version not in (1, 2, 3):
        raise ValueError("Unsupported integration amendment version")
    if amendment_version in (2, 3):
        previous = _reference(amendment.get("previous_amendment"), "previous amendment")
        previous_expected = PREVIOUS_REID_AMENDMENT_SHA256 if amendment_version == 3 else PREVIOUS_AMENDMENT_SHA256
        if (previous["sha256"] != previous_expected
                or not Path(previous["path"]).is_file()
                or digest(Path(previous["path"])) != previous_expected):
            raise ValueError("Previous integration amendment must remain immutable")
        if amendment_version == 3:
            previous_document = json.loads(Path(previous["path"]).read_bytes())
            ancestor = _reference(previous_document.get("previous_amendment"), "original integration amendment")
            if (ancestor["sha256"] != PREVIOUS_AMENDMENT_SHA256 or not Path(ancestor["path"]).is_file()
                    or digest(Path(ancestor["path"])) != PREVIOUS_AMENDMENT_SHA256):
                raise ValueError("Original integration amendment must remain immutable")
    original = _reference(amendment.get("original_freeze"), "original freeze")
    if Path(original["path"]).resolve() != path.resolve() or original["sha256"] != freeze_digest:
        raise ValueError("Amendment original freeze path or raw digest does not match")
    changes = amendment.get("code_changes")
    if not isinstance(changes, dict) or set(changes) != INTEGRATION_ALLOWLIST:
        raise ValueError("Amendment code changes must name exactly the three allowed integration files")
    amended = dict(expected)
    for name, change in changes.items():
        if not isinstance(change, dict) or not isinstance(change.get("reason"), str) or not change["reason"].strip():
            raise ValueError(f"Missing integration change reason for {name}")
        before = _sha256(change.get("before_sha256_lf"), f"{name} before")
        after = _sha256(change.get("after_sha256_lf"), f"{name} after")
        if before != expected.get(name):
            raise ValueError(f"Amendment before hash disagrees with original freeze: {name}")
        amended[name] = after
    if actual != amended:
        changed = sorted(name for name in actual if actual[name] != amended.get(name))
        raise ValueError(f"Production files do not match amended hashes: {', '.join(changed)}")
    added = amendment.get("added_integration_code_sha256_lf")
    allowed_added = {1: ADDED_INTEGRATION_ALLOWLIST, 2: REID_INTEGRATION_ALLOWLIST,
                     3: CONSENSUS_INTEGRATION_ALLOWLIST}[amendment_version]
    if not isinstance(added, dict) or set(added) != allowed_added:
        raise ValueError("Amendment must identify exactly the allowed integration helper and evidence tests")
    added = {name: _sha256(value, name) for name, value in added.items()}
    actual_added = {
        name: hashlib.sha256(Path(name).read_text(encoding="utf-8").encode()).hexdigest()
        for name in added
    }
    if added != actual_added:
        raise ValueError("Added integration code does not match amendment hashes")
    parity = _reference(amendment.get("parity_evidence"), "parity evidence")
    parity_path = Path(parity["path"])
    if not parity_path.is_file():
        raise ValueError("Amendment parity evidence raw digest does not match")
    parity_bytes = parity_path.read_bytes()
    if hashlib.sha256(parity_bytes).hexdigest() != parity["sha256"]:
        raise ValueError("Amendment parity evidence raw digest does not match")
    parity_result = json.loads(parity_bytes)
    if not isinstance(parity_result, dict) or parity_result.get("all_equal") is not True:
        raise ValueError("Parity evidence must report a successful all_equal result")
    if (parity_result.get("frozen_decision_sha256") != freeze_digest
            or parity_result.get("frozen_code_sha256_lf") != expected
            or parity_result.get("amended_code_sha256_lf") != actual
            or parity_result.get("added_integration_code_sha256_lf") != actual_added):
        raise ValueError("Parity evidence code maps or original freeze digest do not match the verified code")
    verification.update(
        mode="integration_amendment",
        integration_amendment={"path": amendment_path.as_posix(),
                               "sha256": hashlib.sha256(amendment_bytes).hexdigest()},
        parity_evidence=parity, code_changes=changes,
        added_integration_code_sha256_lf=actual_added,
    )
    return verification


def frozen_hashes(path: Path, amendment_path: Path | None = DEFAULT_AMENDMENT) -> dict[str, str]:
    """Compatibility view: return actual hashes only after provenance validation."""
    return verify_frozen_code(path, amendment_path)["production_code_sha256_lf"]


def samples_from_cache(payload: dict) -> list[SampledObservation]:
    samples = []
    for row in payload["samples"]:
        values = dict(row)
        values["persons"] = [tuple(p) for p in row["persons"]]
        values["ball"] = tuple(row["ball"]) if row.get("ball") is not None else None
        if row.get("calibration"):
            values["calibration"] = PitchCalibration.from_dict(row["calibration"])
        if row.get("person_kit") is not None:
            values["person_kit"] = {key: tuple(value) for key, value in row["person_kit"].items()}
        samples.append(SampledObservation(**values))
    return samples


def ffmpeg_binary() -> str:
    executable = shutil.which("ffmpeg")
    if executable:
        return executable
    import imageio_ffmpeg

    return str(imageio_ffmpeg.get_ffmpeg_exe())


def run_ffmpeg(executable: str, arguments: list[str]) -> str:
    result = subprocess.run([executable, "-hide_banner", "-nostdin", *arguments],
                            capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError(result.stderr[-6000:])
    return result.stderr


def encode_preview(executable: str, source: Path, destination: Path, title: str) -> None:
    # Padding keeps all production image pixels visible. FFmpeg chooses its
    # default font; text deliberately uses ASCII for portable rendering.
    graph = (
        "pad=iw:ih+106:0:48:color=0x111827,"
        f"drawtext=text='{title} | 117093 daylight development clip | source 11m30s-12m00s':"
        "fontsize=25:fontcolor=white:x=20:y=12,"
        "drawtext=text='Green = anonymous team A   Red = anonymous team B   Yellow = unassigned':"
        "fontsize=21:fontcolor=white:x=20:y=h-50,"
        "drawtext=text='Numbers are local anonymous IDs (not squad identities). Ball fields are inherited; not revalidated.':"
        "fontsize=19:fontcolor=0xcbd5e1:x=20:y=h-25"
    )
    run_ffmpeg(executable, ["-n", "-i", str(source), "-an", "-vf", graph,
                           "-c:v", "libx264", "-preset", "medium", "-crf", "19",
                           "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(destination)])


def validate_preview(executable: str, path: Path, *, count: int, fps: float,
                     source_stride: int, qa_dir: Path) -> dict:
    import cv2

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise ValueError(f"Cannot decode {path}")
    actual_fps = float(cap.get(cv2.CAP_PROP_FPS))
    width, height = (int(cap.get(key)) for key in
                     (cv2.CAP_PROP_FRAME_WIDTH, cv2.CAP_PROP_FRAME_HEIGHT))
    decoded = 0
    qa_paths = []
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            source_frame = decoded * source_stride
            # These two DEVELOPMENT frames are the only exported QA images.
            # Do not view predictions on control frames 374 or 686 here.
            if source_frame in (124, 500):
                image = qa_dir / f"{path.stem}-source-{source_frame}.jpg"
                if not cv2.imwrite(str(image), frame):
                    raise RuntimeError(f"Cannot write QA image {image}")
                qa_paths.append(image.as_posix())
            decoded += 1
    finally:
        cap.release()
    if decoded != count or abs(actual_fps - fps) > 1e-6 or width != 2048:
        raise ValueError(f"Preview grid mismatch: {decoded}/{count}, {actual_fps}/{fps}, {width}")
    # An independent decoder must finish without corruption. Stream metadata
    # also verifies H.264 rather than trusting the filename extension.
    log = run_ffmpeg(executable, ["-xerror", "-i", str(path), "-f", "null", "-"])
    if "Video: h264" not in log:
        raise ValueError("Final preview is not H.264")
    return {"decoded_frames": decoded, "fps": actual_fps, "duration_seconds": decoded / actual_fps,
            "width": width, "height": height, "codec": "h264", "pixel_format": "yuv420p",
            "opencv_full_decode": True, "ffmpeg_full_decode": True, "qa_images": qa_paths}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=Path(".cache/kit_joint_agent/production_joint_day_v1"))
    parser.add_argument("--out", type=Path, default=Path("data/tracking/bench/joint_identity_export_v1"))
    parser.add_argument("--freeze", type=Path, default=Path("docs/measurements/joint-identity-frozen-decision.json"))
    parser.add_argument("--amendment", type=Path, default=DEFAULT_AMENDMENT,
                        help="Explicit integration amendment; required when frozen code hashes differ")
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Output exists; choose a fresh directory to preserve earlier exports")
    verification = verify_frozen_code(args.freeze, args.amendment)
    hashes = verification["production_code_sha256_lf"]
    paths = {tag: args.cache / tag / "seg_0003.json" for tag in ("before", "after")}
    payloads = {tag: json.loads(path.read_text(encoding="utf-8")) for tag, path in paths.items()}
    source = Path(payloads["before"]["video"])
    if any(Path(value["video"]) != source for value in payloads.values()):
        raise ValueError("Before/after videos differ")
    source_info = video_info(source)
    grids = [[(s["order"], s["frame_idx"], s["seconds"], s["ball"], s.get("ball_source"))
              for s in value["samples"]] for value in payloads.values()]
    if grids[0] != grids[1]:
        raise ValueError("Observation grids or immutable ball fields differ")
    if source_info != payloads["before"]["source_video_info"]:
        raise ValueError("Actual source metadata differs from the cached metadata")
    if source_info["frames"] != 750 or source_info["fps"] != 25 or len(grids[0]) != 375:
        raise ValueError("Expected the 30-second, 25fps daylight development source")
    executable = ffmpeg_binary()
    args.out.mkdir(parents=True)
    qa_dir = args.out / "qa"
    qa_dir.mkdir()
    outputs = {}
    for tag, payload in payloads.items():
        print(f"Exporting {tag} through production APIs", flush=True)
        cfg_data = {key: value for key, value in payload["config"].items() if key != "detector"}
        cfg_data.update(fps_out=12.5, preview_width=2048, clip_offset_minutes=11.5, max_seconds=30.0)
        cfg = PipelineConfig(**cfg_data, detector=DetectorConfig(**payload["config"]["detector"]))
        calib = PitchCalibration.from_dict(payload["calibration"])
        validate_video_calibration(source_info, calib)
        samples = samples_from_cache(payload)
        fallback = {int(key): value for key, value in payload["assignment"]["team_by_track"].items()}
        frames = build_frames(samples, fallback, calib, match_id=117093,
                              home_team_id=900000001, away_team_id=900000002, cfg=cfg)
        if len(frames) != 375:
            raise ValueError(f"Production export yielded {len(frames)} frames, expected 375")
        fps = preview_fps(float(source_info["fps"]), cfg)
        scope = SegmentIdentityNamespace(cfg.period, cfg.clip_offset_minutes)
        ids = sorted({person[0] for sample in samples for person in sample.persons})
        metadata = {
            "development_preview": True, "variant": tag, "source_video": source.as_posix(),
            "source_offset_seconds": 690, "effective_output_fps": fps,
            "anonymous_teams": {"900000001": "anonymous team A, palette slot 0",
                                "900000002": "anonymous team B, palette slot 1"},
            "local_to_player_external_id": {str(t): VIDEO_PLAYER_BASE_ID + scope.scope_track_id(t) for t in ids},
            "per_observation_teams_preserved": True,
            "ball_scope": "Inherited immutable ball pixels/source; ball accuracy and possession were not revalidated.",
            "config": asdict(cfg), "calibration": payload["calibration"],
            "cache_sha256": digest(paths[tag]),
        }
        exported = frames_to_json(frames, match_id=117093, extra={"export_metadata": metadata})
        if frames_from_json(exported) != frames:
            raise ValueError("TrackingFrame JSON round trip changed exported data")
        json_path = args.out / f"{tag}.json"
        save_json(json_path, exported)
        intermediate = args.out / f"{tag}-production-mp4v.mp4"
        write_preview(source, samples, fallback, calib, cfg, intermediate)
        final = args.out / f"{tag}.mp4"
        encode_preview(executable, intermediate, final, tag.upper())
        outputs[tag] = {"frames_json": json_path.as_posix(), "production_preview": intermediate.as_posix(),
                        "h264_preview": final.as_posix(), "config": asdict(cfg),
                        "validation": validate_preview(executable, final, count=375, fps=fps,
                                                       source_stride=2, qa_dir=qa_dir)}
    print("Creating stacked before/after comparison", flush=True)
    comparison = args.out / "comparison.mp4"
    run_ffmpeg(executable, ["-n", "-i", str(args.out / "before.mp4"), "-i", str(args.out / "after.mp4"),
                           "-filter_complex", "[0:v][1:v]vstack=inputs=2[v]", "-map", "[v]", "-an",
                           "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
                           "-movflags", "+faststart", str(comparison)])
    outputs["comparison"] = {"h264_preview": comparison.as_posix(),
                             "validation": validate_preview(executable, comparison, count=375, fps=12.5,
                                                            source_stride=2, qa_dir=qa_dir)}
    if verify_frozen_code(args.freeze, args.amendment) != verification:
        raise ValueError("Verified code, freeze, amendment or parity evidence changed during export")
    manifest = {
        "created_at_utc": datetime.now(UTC).isoformat(), "database_writes": False,
        "match_external_id": 117093, "source_offset_seconds": 690,
        "source_video_info": source_info, "source_video_sha256": digest(source),
        "source_cache_sha256": {tag: digest(path) for tag, path in paths.items()},
        "freeze_decision_sha256": digest(args.freeze), "production_code_sha256_lf": hashes,
        "production_code_verification": verification,
        "export_script_sha256": digest(Path(__file__)), "encoder": executable,
        "encoder_version": subprocess.run([executable, "-version"], capture_output=True,
                                          text=True, check=True).stdout.splitlines()[0],
        "outputs": outputs, "ball_fields_equal_between_input_variants": True,
        "local_ids_are_anonymous": True, "control_predictions_visually_reviewed": False,
        "output_sha256": {path.relative_to(args.out).as_posix(): digest(path)
                          for path in sorted(args.out.rglob("*")) if path.is_file()},
    }
    save_json(args.out / "manifest.json", manifest)
    print(json.dumps({"out": str(args.out), "manifest_sha256": digest(args.out / "manifest.json")}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
