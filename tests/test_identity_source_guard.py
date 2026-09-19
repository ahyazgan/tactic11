"""A reused fixed-camera calibration cannot authorize a moving source."""
from __future__ import annotations

import pytest

from app.tracking.calibration import PitchCalibration
from app.tracking.camera import STATIC_SOURCE
from app.tracking.pipeline import PipelineConfig, identity_refinement_enabled


@pytest.fixture
def fixed_calibration() -> PitchCalibration:
    calibration = PitchCalibration.from_dict({"image_size": [1300, 800], "points": [
        {"image": [x * 10 + 100, y * 10 + 50], "pitch": [x, y]}
        for x, y in [(0, 0), (105, 0), (105, 68), (0, 68)]
    ]})
    calibration.meta["identity_profile"] = "fixed_camera_identity_v1"
    return calibration


@pytest.mark.parametrize("source", ["broadcast_tracking", "unknown", "", "statsbomb_360"])
def test_profile_does_not_enable_nonfixed_source(source, fixed_calibration):
    cfg = PipelineConfig(source_name=source, per_frame_calibration=False)
    assert not identity_refinement_enabled(cfg, fixed_calibration)


@pytest.mark.parametrize("source", ["broadcast_tracking", "unknown", "", "statsbomb_360"])
def test_explicit_on_rejects_nonfixed_source(source, fixed_calibration):
    cfg = PipelineConfig(source_name=source, refine_player_identities=True)
    with pytest.raises(ValueError, match="sabit kamera kaynağı"):
        identity_refinement_enabled(cfg, fixed_calibration)


@pytest.mark.parametrize("source", [STATIC_SOURCE, "broadcast_tracking", "unknown"])
def test_explicit_off_remains_valid_for_every_source(source, fixed_calibration):
    cfg = PipelineConfig(source_name=source, refine_player_identities=False)
    assert not identity_refinement_enabled(cfg, fixed_calibration)


@pytest.mark.parametrize("enabled", [None, True])
def test_supported_fixed_camera_keeps_its_existing_behavior(enabled, fixed_calibration):
    cfg = PipelineConfig(source_name=STATIC_SOURCE, refine_player_identities=enabled)
    assert identity_refinement_enabled(cfg, fixed_calibration)


def test_fixed_source_without_profile_still_requires_explicit_on(fixed_calibration):
    fixed_calibration.meta.clear()
    assert not identity_refinement_enabled(PipelineConfig(), fixed_calibration)
    assert identity_refinement_enabled(PipelineConfig(refine_player_identities=True), fixed_calibration)


@pytest.mark.parametrize("unsupported", ["per_frame_calibration", "normalize_kit_light"])
def test_fixed_source_does_not_bypass_existing_guard(unsupported, fixed_calibration):
    cfg = PipelineConfig()
    setattr(cfg, unsupported, True)
    assert not identity_refinement_enabled(cfg, fixed_calibration)
    cfg.refine_player_identities = True
    with pytest.raises(ValueError, match="sabit kamera kaynağı"):
        identity_refinement_enabled(cfg, fixed_calibration)
