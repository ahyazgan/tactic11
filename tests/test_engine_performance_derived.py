"""performance_test — Faz 2 türetilmiş metrikler (saf engine).

Bangsbo/VIFT VO2max, RSA Yorgunluk İndeksi, COD Deficit, RSI, bacak asimetri,
MD+1 adductor/CMJ düşüş, return-to-play, mevki preset'leri.
"""
from __future__ import annotations

import pytest

from app.engine.performance_test import (
    DEFAULT_POSITION_PRESET,
    PROTOCOLS,
    adductor_squeeze_drop,
    change_of_direction_deficit,
    cmj_neuromuscular_drop,
    derive_vo2max_from_yoyo_ir1,
    estimate_vo2max_from_vift,
    hamstring_quad_ratio,
    limb_asymmetry,
    protocols_for_position,
    reactive_strength_index,
    repeated_sprint_fatigue_index,
    return_to_play_readiness,
)
from app.engine.performance_test.compute import (
    ASYMMETRY_HIGH_PCT,
    RSA_FATIGUE_FLAG_PCT,
)

# --------------------------------------------------------------------------- #
# Yeni protokoller kütüphaneye girdi
# --------------------------------------------------------------------------- #


def test_new_protocols_registered():
    for key in ("sprint_5m", "t505", "arrowhead", "illinois", "ift_30_15",
                "adductor_squeeze", "drop_jump_rsi", "triple_hop"):
        assert key in PROTOCOLS, f"{key} PROTOCOLS'a eklenmemiş"


# --------------------------------------------------------------------------- #
# VO2max türetme
# --------------------------------------------------------------------------- #


def test_bangsbo_vo2max_from_yoyo():
    # VO2 = 2000 × 0.0084 + 36.4 = 53.2
    assert derive_vo2max_from_yoyo_ir1(2000.0) == 53.2


def test_bangsbo_zero_distance_is_intercept():
    assert derive_vo2max_from_yoyo_ir1(0.0) == 36.4


def test_bangsbo_negative_raises():
    with pytest.raises(ValueError):
        derive_vo2max_from_yoyo_ir1(-10.0)


def test_vift_vo2max_reasonable_range():
    # 20 km/sa, 24 yaş, 75 kg erkek → elit futbolcu ~55-60 aralığı
    v = estimate_vo2max_from_vift(20.0, 24, 75.0)
    assert 50.0 < v < 65.0


def test_vift_female_lower_than_male():
    male = estimate_vo2max_from_vift(19.0, 25, 70.0, female=False)
    female = estimate_vo2max_from_vift(19.0, 25, 70.0, female=True)
    assert female < male


def test_vift_nonpositive_raises():
    with pytest.raises(ValueError):
        estimate_vo2max_from_vift(0.0, 25, 70.0)


# --------------------------------------------------------------------------- #
# RSA Yorgunluk İndeksi
# --------------------------------------------------------------------------- #


def test_rsa_fatigue_index_no_fatigue():
    # Hepsi neredeyse eşit → FI ~%0, bayrak yok
    r = repeated_sprint_fatigue_index([4.30, 4.31, 4.30, 4.32, 4.31, 4.30])
    assert r.fatigue_index_pct < RSA_FATIGUE_FLAG_PCT
    assert r.insufficient_recovery is False
    assert r.best == 4.30


def test_rsa_fatigue_index_flags_high():
    # Belirgin yorgunluk: süreler artıyor → FI > %7
    r = repeated_sprint_fatigue_index([4.30, 4.45, 4.60, 4.80, 5.00, 5.20])
    assert r.fatigue_index_pct > RSA_FATIGUE_FLAG_PCT
    assert r.insufficient_recovery is True
    assert r.n == 6


def test_rsa_fatigue_formula_exact():
    # FI = (toplam/(en_iyi×n) − 1)×100; [4,4,4,5] → toplam17, best4, n4
    # = (17/16 − 1)×100 = 6.25
    r = repeated_sprint_fatigue_index([4.0, 4.0, 4.0, 5.0])
    assert r.fatigue_index_pct == 6.25


def test_rsa_requires_two_sprints():
    with pytest.raises(ValueError):
        repeated_sprint_fatigue_index([4.3])


def test_rsa_rejects_nonpositive():
    with pytest.raises(ValueError):
        repeated_sprint_fatigue_index([4.3, 0.0, 4.5])


# --------------------------------------------------------------------------- #
# COD Deficit
# --------------------------------------------------------------------------- #


def test_cod_deficit_value():
    r = change_of_direction_deficit(2.50, 1.75)
    assert r.deficit == 0.75
    assert r.poor_deceleration is False  # 0.75 < 1.0 eşik


def test_cod_deficit_flags_poor_deceleration():
    r = change_of_direction_deficit(3.00, 1.70)  # deficit 1.30 > 1.0
    assert r.poor_deceleration is True


def test_cod_deficit_rejects_nonpositive():
    with pytest.raises(ValueError):
        change_of_direction_deficit(0.0, 1.7)


# --------------------------------------------------------------------------- #
# RSI
# --------------------------------------------------------------------------- #


def test_rsi_ratio():
    assert reactive_strength_index(0.50, 0.25) == 2.0


def test_rsi_zero_contact_raises():
    with pytest.raises(ValueError):
        reactive_strength_index(0.5, 0.0)


# --------------------------------------------------------------------------- #
# Bacak asimetri
# --------------------------------------------------------------------------- #


def test_asymmetry_green_below_10():
    r = limb_asymmetry(600.0, 570.0)  # %5 → yeşil
    assert r.flag == "yeşil"
    assert r.stronger_side == "sol"


def test_asymmetry_yellow_between_10_15():
    r = limb_asymmetry(600.0, 525.0)  # %12.5 → sarı
    assert r.flag == "sarı"


def test_asymmetry_red_above_15():
    r = limb_asymmetry(600.0, 480.0)  # %20 → kırmızı
    assert r.flag == "kırmızı"
    assert r.asymmetry_pct > ASYMMETRY_HIGH_PCT


def test_asymmetry_balanced():
    r = limb_asymmetry(500.0, 500.0)
    assert r.stronger_side == "denge"
    assert r.asymmetry_pct == 0.0


def test_asymmetry_both_zero_raises():
    with pytest.raises(ValueError):
        limb_asymmetry(0.0, 0.0)


# --------------------------------------------------------------------------- #
# MD+1 adductor / CMJ düşüş
# --------------------------------------------------------------------------- #


def test_adductor_drop_flags_above_10():
    r = adductor_squeeze_drop(340.0, 400.0)  # %15 düşüş
    assert r.drop_pct == 15.0
    assert r.flagged is True


def test_adductor_no_flag_small_drop():
    r = adductor_squeeze_drop(390.0, 400.0)  # %2.5 düşüş
    assert r.flagged is False


def test_adductor_increase_negative_drop():
    r = adductor_squeeze_drop(420.0, 400.0)
    assert r.drop_pct < 0
    assert r.flagged is False


def test_cmj_neuromuscular_fatigue_flag():
    r = cmj_neuromuscular_drop(34.0, [40.0, 41.0, 39.0])  # baseline 40, %15 düşüş
    assert r.flagged is True
    assert r.drop_pct == 15.0


def test_cmj_no_fatigue():
    r = cmj_neuromuscular_drop(39.0, [40.0, 40.0, 40.0])  # %2.5
    assert r.flagged is False


def test_cmj_requires_baseline():
    with pytest.raises(ValueError):
        cmj_neuromuscular_drop(40.0, [])


# --------------------------------------------------------------------------- #
# Return-to-play
# --------------------------------------------------------------------------- #


def test_rtp_green_at_baseline():
    r = return_to_play_readiness(100.0, 100.0)
    assert r.pct_of_baseline == 100.0
    assert r.cleared is True
    assert r.light == "yeşil"


def test_rtp_red_below_95():
    r = return_to_play_readiness(90.0, 100.0)  # %90 < %95
    assert r.cleared is False
    assert r.light == "kırmızı"


def test_rtp_lower_is_better_direction():
    # Sprint süresi: baseline 1.80, dönüş 1.85 (yavaşladı) → < %100
    r = return_to_play_readiness(1.85, 1.80, higher_is_better=False)
    assert r.pct_of_baseline < 100.0
    # baseline/current = 1.80/1.85 = 0.973 → %97.3 ≥ 95 → yeşil
    assert r.cleared is True


def test_rtp_nonpositive_raises():
    with pytest.raises(ValueError):
        return_to_play_readiness(0.0, 100.0)


# --------------------------------------------------------------------------- #
# Hamstring:Quadriceps oranı
# --------------------------------------------------------------------------- #


def test_hq_ratio_ideal():
    r = hamstring_quad_ratio(1.80, 2.80)  # 0.643 ≥ 0.60
    assert r.ratio == 0.643
    assert r.band == "ideal"
    assert r.at_risk is False


def test_hq_ratio_borderline():
    r = hamstring_quad_ratio(1.50, 2.80)  # 0.536 → 0.47-0.60
    assert r.band == "sınırda"
    assert r.at_risk is False


def test_hq_ratio_high_risk():
    r = hamstring_quad_ratio(1.20, 2.90)  # 0.414 < 0.47
    assert r.band == "yüksek_risk"
    assert r.at_risk is True


def test_hq_ratio_zero_quad_raises():
    with pytest.raises(ValueError):
        hamstring_quad_ratio(1.5, 0.0)


# --------------------------------------------------------------------------- #
# Mevki preset
# --------------------------------------------------------------------------- #


def test_position_preset_known():
    kaleci = protocols_for_position("Kaleci")  # büyük/küçük harf duyarsız
    assert "cmj" in kaleci
    assert isinstance(kaleci, tuple)


def test_position_preset_unknown_returns_default():
    assert protocols_for_position("bilinmeyen") == DEFAULT_POSITION_PRESET


def test_position_preset_keys_are_valid_protocols():
    from app.engine.performance_test.compute import POSITION_TEST_PRESETS
    for pos, keys in POSITION_TEST_PRESETS.items():
        for k in keys:
            assert k in PROTOCOLS, f"{pos} preset'inde geçersiz protokol: {k}"
    for k in DEFAULT_POSITION_PRESET:
        assert k in PROTOCOLS
