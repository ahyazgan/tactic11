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
    assess_readiness,
    change_of_direction_deficit,
    cmj_neuromuscular_drop,
    derive_vo2max_from_yoyo_ir1,
    estimate_vo2max_from_vift,
    hamstring_quad_ratio,
    limb_asymmetry,
    return_to_play_clearance,
    sprint_split_analysis,
    vift_to_aerobic_targets,
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


def test_position_preset_en_alias():
    # EN kod TR preset'e map olur (GK→kaleci, CM→orta_saha, WB_W→kanat)
    assert protocols_for_position("GK") == protocols_for_position("kaleci")
    assert protocols_for_position("CM") == protocols_for_position("orta_saha")
    assert protocols_for_position("WB_W") == protocols_for_position("kanat")


# --------------------------------------------------------------------------- #
# Sprint split faz analizi
# --------------------------------------------------------------------------- #


def test_sprint_split_phases_computed():
    r = sprint_split_analysis(0.98, 1.75, 4.10)
    assert r.reaction == 0.98
    assert r.acceleration == 0.77   # 1.75 − 0.98
    assert r.max_speed == 2.35      # 4.10 − 1.75


def test_sprint_split_limiter_max_speed():
    # max hız fazı elit referansın (2.30) çok üstünde → limitör
    r = sprint_split_analysis(0.96, 1.72, 4.60)  # max_speed 2.88 vs 2.30
    assert r.limiter == "maksimal hız"


def test_sprint_split_balanced_when_near_elite():
    r = sprint_split_analysis(0.95, 1.70, 4.00)  # tam referans
    assert r.limiter == "dengeli"


def test_sprint_split_partial_inputs():
    r = sprint_split_analysis(None, 1.75, 4.10)  # t5 yok → reaksiyon yok
    assert r.reaction is None
    assert r.acceleration is None    # t5 gerektirir
    assert r.max_speed == 2.35


def test_sprint_split_no_data():
    r = sprint_split_analysis(None, None, None)
    assert r.limiter == "yetersiz veri"


def test_sprint_split_rejects_nonpositive():
    with pytest.raises(ValueError):
        sprint_split_analysis(-0.5, 1.7, 4.0)


# --------------------------------------------------------------------------- #
# VIFT → aerobik hedef hızlar
# --------------------------------------------------------------------------- #


def test_vift_targets_values():
    r = vift_to_aerobic_targets(20.0)
    assert r.speed_95 == 19.0
    assert r.speed_100 == 20.0
    assert r.speed_105 == 21.0


def test_vift_targets_rejects_nonpositive():
    with pytest.raises(ValueError):
        vift_to_aerobic_targets(0.0)


# --------------------------------------------------------------------------- #
# Return-to-play clearance (çok protokol)
# --------------------------------------------------------------------------- #


def test_rtp_clearance_green_all_above_95():
    r = return_to_play_clearance(
        {"cmj": 39.0, "yoyo_irl1": 18.0}, {"cmj": 40.0, "yoyo_irl1": 18.5},
    )
    assert r.cleared is True
    assert r.light == "yeşil"


def test_rtp_clearance_red_when_one_below():
    r = return_to_play_clearance(
        {"cmj": 32.0, "yoyo_irl1": 18.0}, {"cmj": 40.0, "yoyo_irl1": 18.5},
    )
    assert r.cleared is False
    assert r.light == "kırmızı"
    assert r.lowest_protocol == "cmj"   # 0.80 en düşük


def test_rtp_clearance_direction_aware_lower_is_better():
    # sprint_30m düşük-iyi: dönüş yavaşladı (4.20 vs baseline 4.00) → oran<1
    r = return_to_play_clearance({"sprint_30m": 4.20}, {"sprint_30m": 4.00})
    assert r.ratios["sprint_30m"] < 1.0     # baseline/current = 0.952
    # 0.952 ≥ 0.95 → yeşil (sınırda)
    assert r.cleared is True


def test_rtp_clearance_no_common_raises():
    with pytest.raises(ValueError):
        return_to_play_clearance({"cmj": 40.0}, {"yoyo_irl1": 18.0})


# --------------------------------------------------------------------------- #
# Hazırlık Kararı (assess_readiness) — çok-metrik sentez
# --------------------------------------------------------------------------- #


def test_readiness_no_metrics_is_yellow_no_data():
    d = assess_readiness()
    assert d.light == "sarı"
    assert d.checked == 0
    assert d.flags == ()
    assert "verisi yok" in d.summary.lower()


def test_readiness_all_green_ready():
    d = assess_readiness(
        rtp=(40.0, 40.0, True),          # %100 → yeşil
        hq=(2.0, 3.0),                   # 0.667 ideal → yeşil
        asymmetry=(50.0, 49.0, "Triple Hop"),  # %2 → yeşil
        rsa=[7.0, 7.1, 7.2, 7.3],        # FI düşük → yeşil
        acwr=1.1,                        # tatlı bölge → yeşil
    )
    assert d.light == "yeşil"
    assert d.verdict == "tam maça hazır"
    assert d.red_count == 0 and d.yellow_count == 0
    assert d.checked == 5


def test_readiness_rtp_red_forces_dont_play():
    d = assess_readiness(rtp=(30.0, 40.0, True))   # %75 < %95 → kırmızı
    assert d.light == "kırmızı"
    assert d.verdict == "sahaya çıkmasın"
    assert d.red_count == 1
    assert d.flags[0].metric == "RTP"
    assert d.flags[0].severity == "kırmızı"


def test_readiness_hq_high_risk_is_red():
    d = assess_readiness(hq=(1.0, 3.0))   # 0.33 < 0.47 → yüksek_risk
    assert d.light == "kırmızı"
    assert any(f.metric == "H:Q" and f.severity == "kırmızı" for f in d.flags)


def test_readiness_only_yellow_is_monitor():
    # RSA yetersiz toparlanma (sarı) + ACWR sınırda (sarı), kırmızı yok
    d = assess_readiness(rsa=[7.0, 7.6, 8.0, 8.4], acwr=1.4)
    assert d.light == "sarı"
    assert d.verdict == "izle / yük yönet"
    assert d.red_count == 0 and d.yellow_count >= 1


def test_readiness_flags_sorted_red_first():
    d = assess_readiness(
        rsa=[7.0, 7.6, 8.0, 8.4],        # sarı
        rtp=(30.0, 40.0, True),          # kırmızı
        hq=(2.0, 3.0),                   # yeşil
    )
    sev = [f.severity for f in d.flags]
    # kırmızı önce, yeşil sonda
    assert sev[0] == "kırmızı"
    assert sev[-1] == "yeşil"
    assert d.light == "kırmızı"


def test_readiness_acwr_above_high_is_red():
    d = assess_readiness(acwr=1.7)   # > 1.50 → kırmızı
    assert d.light == "kırmızı"
    assert d.flags[0].metric == "ACWR"


def test_readiness_invalid_input_raises():
    with pytest.raises(ValueError):
        assess_readiness(hq=(1.0, 0.0))   # quadriceps 0 → ValueError


def test_readiness_wellness_good_is_green():
    d = assess_readiness(wellness=(7, 7, 7, 6, 7))  # readiness 34/35≈0.97 → hazır
    assert d.light == "yeşil"
    assert any(f.metric == "Wellness" and f.severity == "yeşil" for f in d.flags)


def test_readiness_wellness_poor_is_red():
    d = assess_readiness(wellness=(2, 2, 2, 3, 2))  # readiness 11/35≈0.31 → dikkat
    assert d.light == "kırmızı"
    assert any(f.metric == "Wellness" and f.severity == "kırmızı" for f in d.flags)


def test_readiness_regression_sudden_drop_flags():
    # CMJ (yüksek iyi) son 3 ölçümde belirgin düşüş → regresyon (sarı)
    d = assess_readiness(regression=[("cmj", [52, 51, 53, 52, 50, 42, 41, 40])])
    assert any(f.metric == "Regresyon" and f.severity == "sarı" for f in d.flags)
    assert d.light in ("sarı", "kırmızı")


def test_readiness_regression_stable_no_flag():
    d = assess_readiness(regression=[("cmj", [50, 51, 50, 52, 51, 50, 51, 50])])
    assert not any(f.metric == "Regresyon" for f in d.flags)
