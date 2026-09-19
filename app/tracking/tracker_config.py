"""Explicit tracker selection shared by recorded and live workers."""
from __future__ import annotations

from typing import Any

from app.tracking.camera import STATIC_SOURCE


def add_tracker_arguments(parser: Any) -> None:
    from app.tracking.deepocsort import DEFAULT_MODEL

    parser.add_argument("--tracker", choices=["supervision", "deepocsort", "consensus"], default="supervision",
                        help="Takip motoru; deepocsort ve consensus deneysel sabit kamera + OSNet profilleri")
    parser.add_argument("--reid-model", default=DEFAULT_MODEL,
                        help="Sabit SHA-256 ile doğrulanan resmî OSNet ağırlığı")


def validate_tracker_config(cfg: Any, calibration: Any) -> None:
    if cfg.tracker_backend not in {"supervision", "deepocsort", "consensus"}:
        raise ValueError("Unknown tracker backend")
    if cfg.tracker_backend in {"deepocsort", "consensus"} and (
            calibration is None or cfg.source_name != STATIC_SOURCE or cfg.per_frame_calibration):
        raise ValueError("Deep OC-SORT currently requires a calibrated fixed-camera source")
    if cfg.tracker_backend == "consensus" and (
            cfg.normalize_kit_light or cfg.refine_player_identities is True
            or (cfg.refine_player_identities is None and getattr(calibration, "meta", {}).get("identity_profile") == "fixed_camera_identity_v1")):
        raise ValueError("Consensus requires raw kit evidence and cannot combine identity refiners")


def tracker_context(backend: str, model: str) -> dict[str, Any]:
    if backend == "supervision":
        # Existing default live states remain compatible byte-for-byte.
        return {}
    if backend not in {"deepocsort", "consensus"}:
        raise ValueError("Unknown tracker backend")
    from app.tracking.deepocsort import MODEL_SHA256, PROFILE, verified_model_path

    verified_model_path(model)
    profile = PROFILE
    if backend == "consensus":
        from app.tracking.identity_consensus import PROFILE as CONSENSUS_PROFILE

        profile = CONSENSUS_PROFILE
    return {"tracker": {"backend": backend, "profile": profile, "model_sha256": MODEL_SHA256}}
