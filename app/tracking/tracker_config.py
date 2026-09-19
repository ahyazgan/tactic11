"""Explicit tracker selection shared by recorded and live workers."""
from __future__ import annotations

from typing import Any

from app.tracking.camera import STATIC_SOURCE


def add_tracker_arguments(parser: Any) -> None:
    from app.tracking.deepocsort import DEFAULT_MODEL

    parser.add_argument("--tracker", choices=["supervision", "deepocsort"], default="supervision",
                        help="Takip motoru; deepocsort deneysel sabit kamera + OSNet profili")
    parser.add_argument("--reid-model", default=DEFAULT_MODEL,
                        help="Sabit SHA-256 ile doğrulanan resmî OSNet ağırlığı")


def validate_tracker_config(cfg: Any, calibration: Any) -> None:
    if cfg.tracker_backend not in {"supervision", "deepocsort"}:
        raise ValueError("Unknown tracker backend")
    if cfg.tracker_backend == "deepocsort" and (
            calibration is None or cfg.source_name != STATIC_SOURCE or cfg.per_frame_calibration):
        raise ValueError("Deep OC-SORT currently requires a calibrated fixed-camera source")


def tracker_context(backend: str, model: str) -> dict[str, Any]:
    if backend == "supervision":
        # Existing default live states remain compatible byte-for-byte.
        return {}
    if backend != "deepocsort":
        raise ValueError("Unknown tracker backend")
    from app.tracking.deepocsort import MODEL_SHA256, PROFILE, verified_model_path

    verified_model_path(model)
    return {"tracker": {"backend": backend, "profile": PROFILE, "model_sha256": MODEL_SHA256}}
