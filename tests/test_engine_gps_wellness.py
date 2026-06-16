"""GPS yük + wellness (spor bilimi) — saf engine testleri."""
from __future__ import annotations

import pytest

from app.engine.gps_load import GpsSession, compute_gps_load, srpe_session_load
from app.engine.wellness import WellnessInput, compute_wellness


def test_srpe_session_load_foster():
    # RPE 7 × 60 dk = 420 AU (Foster sRPE)
    assert srpe_session_load(7.0, 60.0) == 420.0


def test_srpe_rejects_out_of_range_rpe():
    with pytest.raises(ValueError):
        srpe_session_load(11.0, 60.0)
    with pytest.raises(ValueError):
        srpe_session_load(0.0, 60.0)


def test_srpe_rejects_nonpositive_duration():
    with pytest.raises(ValueError):
        srpe_session_load(7.0, 0.0)


def test_gps_uses_device_player_load_when_present():
    r = compute_gps_load(GpsSession(duration_min=90, total_distance_m=10000,
                                    player_load=650.0))
    assert r.session_load == 650.0


def test_gps_estimates_load_without_device():
    r = compute_gps_load(GpsSession(
        duration_min=90, total_distance_m=10000, hsr_distance_m=800,
        sprint_distance_m=200, accelerations=30, decelerations=25,
    ))
    # 10000*0.01 + 800*0.05 + 200*0.08 + 55*0.5 = 100+40+16+27.5 = 183.5
    assert r.session_load == 183.5


def test_gps_high_intensity_flag():
    r = compute_gps_load(GpsSession(duration_min=20, total_distance_m=3000))
    assert r.high_intensity_session is True
    assert any("yüksek yoğunluk" in f for f in r.flags)


def test_gps_rpe_load():
    r = compute_gps_load(GpsSession(duration_min=60, total_distance_m=5000, rpe=7))
    assert r.rpe_load == 420.0


def test_gps_feeds_acwr():
    """gps_load.session_load doğrudan ACWR'ye beslenebilir."""
    from app.engine.workload import compute_workload
    daily = [compute_gps_load(GpsSession(duration_min=90, total_distance_m=9000,
             player_load=500)).session_load for _ in range(28)]
    acwr = compute_workload(daily)
    assert acwr.acwr is not None and acwr.risk_zone == "ideal"


def test_wellness_ready_when_high():
    r = compute_wellness(WellnessInput(7, 7, 7, 6, 7))
    assert r.zone == "hazır"
    assert r.readiness >= 0.7


def test_wellness_caution_when_low():
    r = compute_wellness(WellnessInput(2, 2, 2, 3, 3))
    assert r.zone == "dikkat"
    assert any("kas ağrısı" in f for f in r.flags)


def test_wellness_below_personal_baseline():
    # baseline ortalama ~32; bugün 24 → %15+ düşüş
    r = compute_wellness(WellnessInput(5, 5, 5, 5, 4),
                         baseline_totals=[33, 32, 31, 32])
    assert r.below_baseline is True


def test_wellness_soreness_injury_flag():
    r = compute_wellness(WellnessInput(6, 6, 2, 6, 6))
    assert any("sakatlık" in f for f in r.flags)
