"""engine.coach_benchmark — koç zekâ karnesi.

Testler üç şeyi kilitler:
1. Taban çizgisi eşiği AYRIK yarıda seçilir: A'da ölçülen eşik B'den gelir.
   Aynı yarıda seçip ölçmek saat-kuralını haksız parlatırdı.
2. Bir kol boşsa F1 tanımsızdır ve hüküm "yetersiz veri"dir — sayı uydurulmaz.
3. Beceri ölçekleri sabit: AUC 0.5 → 0, TERS ilişki 0'a kırpılır; ECE tanımı.
4. Seçicilik F1'le ölçülmez: nadir hedefte hep-evet F1'i yükseltir, kaldırmayı
   yükseltmez. Kapı motorun sustuğu tikte bayrak üretemez — yalnız kısar.
"""
from __future__ import annotations

import pytest

from app.engine.coach_benchmark import (
    MIN_F1_GAIN,
    MIN_TICKS_PER_HALF,
    SHAPE_MIN_FLAG_RATE,
    SHAPE_MIN_LIFT,
    SHAPE_PRIOR_THRESHOLDS,
    Dimension,
    ShapePrior,
    ShapeState,
    TickObservation,
    WhoCandidate,
    WhoPrior,
    WhoState,
    agreement,
    apply_shape_gate,
    apply_who_prior,
    build_scorecard,
    expected_calibration_error,
    expected_who_hits,
    fit_shape_prior,
    lead_times,
    minute_rule,
    selectivity,
    skill_from_auc,
    skill_from_error,
    split_half_agreement,
    split_half_definition,
    split_half_shape_gate,
    who_prior_agreement,
    who_prior_tiers,
)
from app.engine.coach_benchmark.compute import _shape_cell

TICKS = (28.0, 40.0, 55.0, 66.0, 78.0)


def _match(mid: int, flags: dict[float, bool], acted: dict[float, bool]) -> list[TickObservation]:
    return [TickObservation(mid, t, flags.get(t, False), acted.get(t, False)) for t in TICKS]


def _late_sub_matches(n: int, *, engine_perfect: bool) -> list[TickObservation]:
    """Antrenör her maçta 55 ve 66'dan sonra değiştiriyor; motor ya mükemmel ya sessiz."""
    obs: list[TickObservation] = []
    acted = {55.0: True, 66.0: True}
    for mid in range(1, n + 1):
        flags = dict(acted) if engine_perfect else {}
        obs.extend(_match(mid, flags, acted))
    return obs


# --- karışıklık matrisi ------------------------------------------------------ #

def test_agreement_counts_and_rates() -> None:
    obs = [
        TickObservation(1, 55.0, True, True),    # tp
        TickObservation(1, 66.0, True, False),   # fp
        TickObservation(1, 78.0, False, True),   # fn
        TickObservation(1, 28.0, False, False),  # tn
    ]
    a = agreement(obs)
    assert (a.tp, a.fp, a.fn, a.tn) == (1, 1, 1, 1)
    assert a.precision == 0.5 and a.recall == 0.5 and a.f1 == 0.5
    assert a.flag_rate == 0.5 and a.act_rate == 0.5


def test_agreement_undefined_when_no_flags() -> None:
    """Motor hiç bayrak kaldırmadıysa precision/F1 tanımsız — 0 değil."""
    a = agreement([TickObservation(1, 55.0, False, True)])
    assert a.precision is None and a.f1 is None and a.recall == 0.0


def test_minute_rule_ignores_engine() -> None:
    obs = _late_sub_matches(2, engine_perfect=False)
    r = minute_rule(obs, 55.0)
    # 55, 66, 78 bayrak; antrenör 55 ve 66'da yaptı → 78 yanlış alarm
    assert r.recall == 1.0 and r.precision == round(2 / 3, 3)


# --- ayrık yarı --------------------------------------------------------------- #

def test_threshold_chosen_on_other_half() -> None:
    """A yarısında 55 doğru eşik, B yarısında 78 — A'da ölçülen eşik B'den gelmeli."""
    obs: list[TickObservation] = []
    for mid in range(1, 2 * MIN_TICKS_PER_HALF + 1):
        # sıralı kimlik: tek indeks (0,2,4..) → A; mid=1,3,5.. A'da
        in_a = (mid - 1) % 2 == 0
        acted = {55.0: True, 66.0: True, 78.0: True} if in_a else {78.0: True}
        obs.extend(_match(mid, {}, acted))
    sh = split_half_agreement(obs, candidates=(55.0, 78.0))
    assert sh.threshold_for_a == 78.0     # B'de seçildi
    assert sh.threshold_for_b == 55.0     # A'da seçildi
    # Çapraz eşik yarılarda mükemmel değil — hile yapılmadığının kanıtı
    assert sh.baseline_a.recall is not None and sh.baseline_a.recall < 1.0
    assert sh.baseline_b.precision is not None and sh.baseline_b.precision < 1.0


def test_perfect_engine_beats_clock() -> None:
    obs = _late_sub_matches(2 * MIN_TICKS_PER_HALF, engine_perfect=True)
    sh = split_half_agreement(obs)
    assert sh.engine_f1 == 1.0
    assert sh.baseline_f1 is not None and sh.baseline_f1 < 1.0
    assert sh.engine_f1 - sh.baseline_f1 >= MIN_F1_GAIN
    assert sh.verdict == "taban çizgisini geçiyor"


def test_silent_engine_is_insufficient_not_zero() -> None:
    obs = _late_sub_matches(2 * MIN_TICKS_PER_HALF, engine_perfect=False)
    sh = split_half_agreement(obs)
    assert sh.engine_f1 is None
    assert sh.verdict == "yetersiz veri"


def test_too_few_ticks_gives_no_verdict() -> None:
    obs = _late_sub_matches(2, engine_perfect=True)
    assert split_half_agreement(obs).verdict == "yetersiz veri"


def test_clock_matching_engine_is_same_as_baseline() -> None:
    """Motor tam olarak 'dk ≥ 55' diyorsa taban çizgisiyle AYNI olmalı, geçmiş değil."""
    obs: list[TickObservation] = []
    acted = {55.0: True, 66.0: True}
    for mid in range(1, 2 * MIN_TICKS_PER_HALF + 1):
        obs.extend(_match(mid, {55.0: True, 66.0: True, 78.0: True}, acted))
    sh = split_half_agreement(obs)
    assert sh.verdict == "taban çizgisiyle aynı"
    assert sh.engine_f1 == sh.baseline_f1


# --- öncü süre ---------------------------------------------------------------- #

def test_lead_time_takes_earliest_flag_in_lookback() -> None:
    lt = lead_times({1: [60.0, 85.0]}, {1: [40.0, 52.0, 58.0]}, lookback_min=15.0)
    # 60 için pencere [45,60): 52 ve 58 → en erken 52 → 8 dk; 85 için bayrak yok
    assert lt.moves == 2 and lt.covered == 1
    assert lt.coverage == 0.5 and lt.mean_lead_min == 8.0 and lt.median_lead_min == 8.0


def test_lead_time_empty() -> None:
    lt = lead_times({}, {})
    assert lt.moves == 0 and lt.coverage is None and lt.mean_lead_min is None


# --- ölçekler ------------------------------------------------------------------ #

def test_skill_from_auc_scale() -> None:
    assert skill_from_auc(0.5) == 0.0
    assert skill_from_auc(1.0) == 100.0
    assert skill_from_auc(0.75) == 50.0
    assert skill_from_auc(0.3) == 0.0       # TERS ilişki ödüllendirilmez
    assert skill_from_auc(None) is None


def test_ece_perfect_and_overconfident() -> None:
    # Her bin'de güven = isabet → ECE 0
    perfect = [(0.9, True)] * 9 + [(0.9, False)] + [(0.1, False)] * 9 + [(0.1, True)]
    ece, conf, hit = expected_calibration_error(perfect)
    assert ece == 0.0 and conf == 0.5 and hit == 0.5
    # Hep %90 diyor, yarısı tutuyor → ECE 0.4
    over = [(0.9, i % 2 == 0) for i in range(10)]
    ece, conf, hit = expected_calibration_error(over)
    assert ece == 0.4 and conf == 0.9 and hit == 0.5


def test_ece_empty() -> None:
    assert expected_calibration_error([]) == (None, None, None)


# --- karne ---------------------------------------------------------------------- #

def _dim(name: str, verdict: str, *, measurable: bool = True) -> Dimension:
    return Dimension(name, "m", 0.5, 0.5, None, measurable, verdict, "")


def test_scorecard_counts_not_composite() -> None:
    card = build_scorecard([
        _dim("a", "taban çizgisini geçiyor"),
        _dim("b", "taban çizgisiyle aynı"),
        _dim("c", "ölçülemez", measurable=False),
    ])
    assert card.measurable == 2 and card.beating_baseline == 1
    assert "3 boyutun 2'i ölçülebildi; 1'i taban çizgisini geçiyor" in card.headline
    assert "hiçbir boyutta" not in card.headline


def test_scorecard_flags_zero_wins() -> None:
    card = build_scorecard([_dim("a", "ayırmıyor"), _dim("b", "taban çizgisinin altında")])
    assert card.beating_baseline == 0
    assert "hiçbir boyutta" in card.headline


# --- elit zamanlama önseli ----------------------------------------------------- #

def _state(mid: int, minute: float, score: str, subs: int, acted: bool):
    from app.engine.coach_benchmark import TickState
    return TickState(mid, minute, score, subs, acted)


def test_timing_prior_learns_cell_rate_with_laplace() -> None:
    from app.engine.coach_benchmark import fit_timing_prior

    states = [_state(1, 60.0, "trailing", 0, True)] * 3 + [_state(1, 60.0, "trailing", 0, False)]
    prior = fit_timing_prior(states)
    # (3 + 1) / (4 + 2) = 0.667 — Laplace 1
    assert prior.table[(2, "trailing", 0)] == 4 / 6
    assert prior.fitted_on == 4


def test_timing_prior_unseen_cell_is_unknown_not_zero() -> None:
    from app.engine.coach_benchmark import TimingPrior, apply_timing_prior

    prior = TimingPrior(table={}, threshold=0.6, fitted_on=0)
    obs = apply_timing_prior(prior, [_state(1, 70.0, "drawing", 1, True)])
    assert obs[0].engine_flag is False           # 0.5 < 0.6
    prior_low = TimingPrior(table={}, threshold=0.5, fitted_on=0)
    assert apply_timing_prior(prior_low, [_state(1, 70.0, "drawing", 1, True)])[0].engine_flag


def test_timing_prior_split_half_learns_from_other_half() -> None:
    """Skor durumu belirleyici: geride kalınca 45+'ta değişiklik, öndeyken hiç.

    Saat-kuralı skor durumunu bilmez → önsel saati geçmeli.
    """
    from app.engine.coach_benchmark import split_half_timing_prior

    states = []
    for mid in range(1, 2 * MIN_TICKS_PER_HALF + 1):
        score = "trailing" if mid % 3 else "leading"
        for t in TICKS:
            acted = score == "trailing" and t >= 45.0
            states.append(_state(mid, t, score, 0, acted))
    sh = split_half_timing_prior(states)
    assert sh.engine_f1 == 1.0
    assert sh.baseline_f1 is not None and sh.baseline_f1 < 1.0
    assert sh.verdict == "taban çizgisini geçiyor"


# --- "kim" boyutu --------------------------------------------------------------- #

def _who(off: int, cands: tuple[int, ...], pitch: tuple[int, ...] = tuple(range(1, 12))):
    from app.engine.coach_benchmark import WhoSample
    return WhoSample(off, cands, pitch)


def test_who_agreement_hits_and_random_baseline() -> None:
    from app.engine.coach_benchmark import who_agreement

    n = MIN_TICKS_PER_HALF
    # yarısında ilk aday doğru, çeyreğinde 3. aday doğru, kalanında ıska
    rows = ([_who(5, (5, 6, 7))] * (n // 2) + [_who(5, (6, 7, 5))] * (n // 4)
            + [_who(5, (6, 7, 8))] * (n - n // 2 - n // 4))
    w = who_agreement(rows)
    assert w.n == n
    assert w.hit_at_1 == round((n // 2) / n, 3)
    assert w.hit_at_k == round((n // 2 + n // 4) / n, 3)
    assert w.baseline_at_1 == round(1 / 11, 3) and w.baseline_at_k == round(3 / 11, 3)
    assert w.verdict == "taban çizgisini geçiyor"
    assert w.off_pitch_candidate_rate == 0.0


def test_who_agreement_off_pitch_candidates_counted() -> None:
    from app.engine.coach_benchmark import who_agreement

    rows = [_who(5, (99, 98, 5))] * MIN_TICKS_PER_HALF   # 99/98 sahada değil
    w = who_agreement(rows)
    assert w.off_pitch_candidate_rate == round(2 / 3, 3)
    assert w.hit_at_k == 1.0 and w.hit_at_1 == 0.0
    assert "sahada değildi" in w.note


def test_who_agreement_random_level_is_same_and_small_n_no_verdict() -> None:
    from app.engine.coach_benchmark import who_agreement

    n = MIN_TICKS_PER_HALF
    hits = round(3 / 11 * n)
    rows = [_who(5, (5, 6, 7))] * hits + [_who(5, (6, 7, 8))] * (n - hits)
    assert who_agreement(rows).verdict == "taban çizgisiyle aynı"
    assert who_agreement(rows[:3]).verdict == "yetersiz veri"
    assert who_agreement([]).n == 0


# --- "kim" önseli (elit antrenörden öğrenilen) ----------------------------------- #

def _pitch(off_group: str = "FWD"):
    """11 kişilik saha: 1 GK, 4 DEF, 3 MID, 3 FWD; ilk 3 FWD'den biri (id 9) çıkar."""
    from app.engine.coach_benchmark import WhoCandidate
    groups = ["GK"] + ["DEF"] * 4 + ["MID"] * 3 + ["FWD"] * 3
    return tuple(WhoCandidate(i + 1, g, True) for i, g in enumerate(groups))


def test_who_prior_learns_group_and_beats_random_split_half() -> None:
    """Antrenör hep bir forveti çıkarıyor → önsel forvetleri öne alır, isabet@3 = 1."""
    from app.engine.coach_benchmark import WhoState, fit_who_prior, split_half_who_prior

    states = [WhoState(mid, 9 + (mid % 3), _pitch()) for mid in range(1, 2 * MIN_TICKS_PER_HALF + 1)]
    prior = fit_who_prior(states)
    assert prior.table[("FWD", True)] > prior.table[("DEF", True)]
    w = split_half_who_prior(states)
    assert w.hit_at_k == 1.0 and w.baseline_at_k == round(3 / 11, 3)
    assert w.verdict == "taban çizgisini geçiyor"


def test_who_prior_unseen_cell_is_unknown_not_zero() -> None:
    from app.engine.coach_benchmark import WhoCandidate, WhoPrior, WhoState, apply_who_prior

    prior = WhoPrior(table={("DEF", True): 0.2}, fitted_on=1)
    st = WhoState(1, 5, (WhoCandidate(1, "DEF", True), WhoCandidate(2, "MID", False)))
    # MID/sub görülmemiş → 0.5 > 0.2 → önce 2
    assert apply_who_prior(prior, st) == (2, 1)


# --- şekil seçiciliği -------------------------------------------------------- #

def _shape_match(
    mid: int, *, informative: bool, flag_all: bool = True, support: int = 2,
) -> list[ShapeState]:
    """Antrenör yalnız 66+ ve geride kalınca diziliş değiştirir (öğrenilebilir durum).

    `informative=False` ise hamle durumdan bağımsız (aynı tikte sabit) — hiçbir
    önsel öğrenemez.
    """
    out: list[ShapeState] = []
    for i, t in enumerate(TICKS):
        state = "trailing" if t >= 66.0 else "leading"
        acted = (t >= 66.0) if informative else (mid % 5 == 0 and i == 0)
        out.append(ShapeState(
            mid, t, score_state=state, subs_used=0,
            engine_flag=flag_all or t >= 66.0, support_count=support, coach_acted=acted,
        ))
    return out


def test_selectivity_lift_is_one_when_flag_knows_nothing() -> None:
    """Hep-evet: F1 yüksek çıkar ama kaldırma tam 1.0 — cetvel tuzağa düşmüyor."""
    obs = [TickObservation(1, float(i), True, i % 5 == 0) for i in range(50)]
    st = selectivity(obs)
    assert st.flag_rate == 1.0
    assert st.base_rate == pytest.approx(0.2)
    assert st.precision == pytest.approx(0.2)
    assert st.lift == pytest.approx(1.0)
    # aynı veride F1, taban oranından ötürü kaldırmadan yüksek görünür
    assert st.f1 is not None and st.f1 > 0.3


def test_selectivity_lift_rewards_fewer_correct_flags() -> None:
    """Yarısı kadar bayrakla iki kat isabet → kaldırma 2.0, F1 düşse bile."""
    obs = [TickObservation(1, float(i), i % 5 == 0, i % 5 == 0) for i in range(50)]
    st = selectivity(obs)
    assert st.flag_rate == pytest.approx(0.2)
    assert st.precision == pytest.approx(1.0)
    assert st.lift == pytest.approx(5.0)


def test_shape_gate_only_narrows_engine_flag() -> None:
    """Kapı motorun SUSTUĞU tikte bayrak ÜRETEMEZ — yalnız kısar."""
    states = [
        ShapeState(1, 66.0, "trailing", 0, engine_flag=False, support_count=9, coach_acted=True),
        ShapeState(1, 78.0, "trailing", 0, engine_flag=True, support_count=9, coach_acted=True),
    ]
    prior = ShapePrior({}, threshold=0.0, support_threshold=0, fitted_on=0)
    assert [o.engine_flag for o in apply_shape_gate(prior, states)] == [False, True]


def test_shape_gate_support_threshold_filters() -> None:
    states = [
        ShapeState(1, 66.0, "trailing", 0, engine_flag=True, support_count=1, coach_acted=True),
        ShapeState(1, 78.0, "trailing", 0, engine_flag=True, support_count=3, coach_acted=True),
    ]
    prior = ShapePrior({}, threshold=0.0, support_threshold=2, fitted_on=0)
    assert [o.engine_flag for o in apply_shape_gate(prior, states)] == [False, True]


def test_shape_gate_stays_silent_on_unseen_cell() -> None:
    """Görülmemiş hücre kanıt değildir: kapı en gevşek eşikte bile susar.

    Zamanlama/kim önsellerinde "bilinmiyor" 0.5'tir; orada soru sıralama, burada
    seçiciliktir. Bağımsız maçlarda görülmemiş hücre bayraklarının kaldırması
    tam 1.0 ölçüldü — bilgi yok, bütçe var.
    """
    st = ShapeState(9, 55.0, "drawing", 0, engine_flag=True, support_count=5, coach_acted=False)
    for threshold in (min(SHAPE_PRIOR_THRESHOLDS), 0.4, max(SHAPE_PRIOR_THRESHOLDS)):
        prior = ShapePrior({}, threshold=threshold, support_threshold=0, fitted_on=0)
        assert apply_shape_gate(prior, [st])[0].engine_flag is False
    # görülmüş ve eşiği geçen hücre normal şekilde bayrak alır
    seen = ShapePrior({_shape_cell(st): 0.9}, threshold=0.4, support_threshold=0, fitted_on=1)
    assert apply_shape_gate(seen, [st])[0].engine_flag is True


def test_shape_prior_threshold_chosen_by_precision_not_f1() -> None:
    """Bayrak bütçesi eşiğin altına düşen aday seçilemez; kalanların en isabetlisi seçilir."""
    states = [s for mid in range(1, 21) for s in _shape_match(mid, informative=True)]
    prior = fit_shape_prior(states)
    gated = selectivity(apply_shape_gate(prior, states))
    raw = selectivity([TickObservation(s.match_external_id, s.minute, s.engine_flag,
                                       s.coach_acted) for s in states])
    assert gated.flag_rate >= SHAPE_MIN_FLAG_RATE
    assert gated.precision is not None and raw.precision is not None
    assert gated.precision > raw.precision


def test_shape_gate_split_half_learns_from_other_half() -> None:
    """Durum öğrenilebilirse kapı seçici; kapı ÖTEKİ yarıdan gelir."""
    states = [s for mid in range(1, 41) for s in _shape_match(mid, informative=True)]
    gate = split_half_shape_gate(states)
    assert gate.verdict == "seçici"
    assert gate.gated_a.lift is not None and gate.gated_a.lift >= SHAPE_MIN_LIFT
    assert gate.gated_b.lift is not None and gate.gated_b.lift >= SHAPE_MIN_LIFT
    # ham bayrak her tikte yanıyordu: hiçbir şey bilmiyor
    assert gate.raw_a.lift == pytest.approx(1.0)
    assert gate.gated_a.flag_rate < gate.raw_a.flag_rate


def test_shape_gate_noise_is_not_selective() -> None:
    """Hamle durumdan bağımsızsa kapı da kurtaramaz — 'seçici' denmez."""
    states = [s for mid in range(1, 41) for s in _shape_match(mid, informative=False)]
    gate = split_half_shape_gate(states)
    assert gate.verdict in {"seçici değil", "kararsız", "yetersiz veri"}


def test_shape_gate_too_few_ticks_gives_no_verdict() -> None:
    states = _shape_match(1, informative=True)
    gate = split_half_shape_gate(states)
    assert gate.verdict == "yetersiz veri"
    assert gate.prior_for_a.fitted_on == 0


def _sparse_shape_half(mid: int, n: int, flagged: int) -> list[ShapeState]:
    return [ShapeState(mid, 66.0 if i < flagged else 28.0,
                       "trailing" if i < flagged else "leading", 0,
                       i < flagged, 2, i < flagged) for i in range(n)]


def test_shape_gate_rejects_one_hit_per_half() -> None:
    states = _sparse_shape_half(1, 40, 1) + _sparse_shape_half(2, 40, 1)
    gate = split_half_shape_gate(states)
    assert gate.verdict == "yetersiz veri"
    assert gate.prior_for_a.threshold is None
    assert gate.prior_for_b.threshold is None
    assert gate.gated_a.flagged == gate.gated_b.flagged == 0


def test_shape_prior_empty_training_cannot_flag_unseen_state() -> None:
    prior = fit_shape_prior([])
    assert prior.threshold is None
    assert not apply_shape_gate(prior, _sparse_shape_half(1, 1, 1))[0].engine_flag


@pytest.mark.parametrize(("n", "flagged", "eligible"), [(1003, 150, False), (1000, 150, True)])
def test_shape_budget_uses_exact_counts(n: int, flagged: int, eligible: bool) -> None:
    # 150/1003 rounds to .150, but is below the .15 minimum.
    prior = fit_shape_prior(_sparse_shape_half(1, n, flagged))
    assert (prior.threshold is not None) is eligible


def test_shape_gate_needs_enough_flags_in_control_half() -> None:
    # Both training halves have >=15% candidates. B learns support >=2,
    # but that leaves only one flag when evaluated on A.
    a = [ShapeState(1, 66.0, "trailing", 0, True, 2 if i == 0 else 1, i < 20)
         for i in range(40)]
    b = [ShapeState(2, 66.0, "trailing", 0, True, 2 if i < 10 else 1, i < 10)
         for i in range(40)]
    gate = split_half_shape_gate(a + b)
    assert gate.prior_for_a.threshold is not None
    assert gate.prior_for_b.threshold is not None
    assert gate.gated_a.flagged == 1
    assert gate.verdict == "yetersiz veri"


def test_who_prior_tiers_group_equal_candidates_together() -> None:
    """Önsel tablosu kaba: aynı hücredeki adaylar TEK kademede toplanmalı."""
    state = WhoState(1, 7, tuple(
        WhoCandidate(pid, group, True)
        for pid, group in ((7, "FWD"), (8, "FWD"), (9, "MID"), (10, "DEF"))))
    prior = WhoPrior({("FWD", True): 0.21, ("MID", True): 0.14, ("DEF", True): 0.03}, 1)
    assert who_prior_tiers(prior, state) == ((7, 8), (9,), (10,))


def test_expected_who_hits_never_rewards_a_fixed_order_inside_a_tier() -> None:
    """Kademe içinde rastgele seçim varsayılır: iki eşit adayın her biri 1/2."""
    tiers = ((7, 8), (9,), (10,))
    for pid in (7, 8):
        assert expected_who_hits(tiers, pid, k=3) == (pytest.approx(0.5), 1.0)
    assert expected_who_hits(tiers, 9, k=3) == (0.0, 1.0)
    # ilk iki kademe üç yeri doldurdu: 10 numara ilk üçe giremez
    assert expected_who_hits(tiers, 10, k=3) == (0.0, 0.0)
    # ilk üç sınırı kademeyi ortadan bölerse beklenen pay kalan yer / kademe boyu
    straddle = ((7,), (8, 9, 10))
    assert expected_who_hits(straddle, 9, k=3) == (0.0, pytest.approx(2 / 3))


def test_who_prior_agreement_ignores_player_id_order() -> None:
    """Kimlikleri ters çevirmek sonucu DEĞİŞTİRMEMELİ — düzeltilen kusur buydu."""
    def states(flip):
        out = []
        for mid in range(1, 25):
            ids = [40, 30, 20, 10] if flip else [10, 20, 30, 40]
            out.append(WhoState(mid, ids[0], tuple(
                WhoCandidate(pid, "FWD" if i < 2 else "MID", True)
                for i, pid in enumerate(ids))))
        return out

    prior = WhoPrior({("FWD", True): 0.21, ("MID", True): 0.14}, 1)
    duz = who_prior_agreement(prior, states(False))
    ters = who_prior_agreement(prior, states(True))
    assert duz.hit_at_1 == ters.hit_at_1 == pytest.approx(0.5)

    def ranked(flip):
        rows = states(flip)
        return sum(1 for s in rows if apply_who_prior(prior, s)[0] == s.player_off) / len(rows)

    # aynı veride eski yol kimlik sırasına BAĞLI: 1.0 vs 0.0
    assert ranked(False) != ranked(True)


# --- tanım seçiminin bedeli ---------------------------------------------- #

def _defn_obs(flags: list[bool], acted: list[bool]) -> list[TickObservation]:
    """Her tik ayrı maçta — _halves maç bazında böldüğü için tikler dağılsın."""
    return [TickObservation(i, 10.0 + i, f, a)
            for i, (f, a) in enumerate(zip(flags, acted, strict=True))]


def test_definition_choice_picks_in_the_other_half() -> None:
    """Tanım ÖTEKİ yarıda seçilir; iki yarı da aynı tanımı seçerse kararlı."""
    n = 40
    acted = [i % 2 == 0 for i in range(n)]
    iyi = list(acted)                      # hedefi birebir izler
    kotu = [not a for a in acted]          # tam tersi
    pick = split_half_definition({"iyi": _defn_obs(iyi, acted),
                                  "kotu": _defn_obs(kotu, acted)})
    assert pick.chosen_for_a == "iyi"
    assert pick.chosen_for_b == "iyi"
    assert pick.stable is True
    assert pick.engine_f1 == 1.0


def test_definition_choice_charges_the_selection_cost() -> None:
    """Bilgi yokken örneklem-içi en iyi, örneklem-dışıdan YÜKSEK çıkar.

    Eski kod iki tanımın ÖLÇÜLMÜŞ F1'inden büyüğünü sabit bir tabana karşı
    raporluyordu. İki aday arasından en iyisini seçmek, ortada hiçbir sinyal
    olmasa bile tabanın üstüne çıkar — bu depoda altı sinyalle ölçülmüştü
    (taban + 0,056, docs/KARNE-GRUP-ICI-SINYAL.md). Fark seçim bedelidir ve
    örneklem dışı ölçüm onu geri alır.
    """
    acted = [i % 3 == 0 for i in range(60)]
    # İki gürültü tanımı: biri A yarısında şanslı, öteki B yarısında.
    a_sansli = [(i % 3 == 0) if i % 2 == 0 else (i % 5 == 0) for i in range(60)]
    b_sansli = [(i % 5 == 0) if i % 2 == 0 else (i % 3 == 0) for i in range(60)]
    pick = split_half_definition({"a_sansli": _defn_obs(a_sansli, acted),
                                  "b_sansli": _defn_obs(b_sansli, acted)})

    # İki yarı farklı tanım seçti: sonucun gürültü olduğunun işareti.
    assert pick.stable is False
    assert "İKİ YARI FARKLI TANIM SEÇTİ" in pick.note

    en_iyi_ic = max(v for v in pick.in_sample.values() if v is not None)
    assert pick.engine_f1 is not None
    assert en_iyi_ic > pick.engine_f1, "seçim bedeli ödenmemiş"


def test_definition_choice_refuses_mismatched_tick_sets() -> None:
    """Tanımlar farklı tikleri kapsıyorsa taban kayar — kıyas reddedilir."""
    acted = [i % 2 == 0 for i in range(40)]
    tam = _defn_obs(list(acted), acted)
    eksik = _defn_obs(list(acted[:30]), acted[:30])
    pick = split_half_definition({"tam": tam, "eksik": eksik})
    assert pick.verdict == "yetersiz veri"
    assert "aynı tik/hedef kümesini paylaşmıyor" in pick.note
    assert pick.engine_f1 is None


def test_definition_choice_with_one_definition_has_no_cost() -> None:
    """Tek tanım varsa seçim yoktur; sonuç split_half_agreement ile aynı."""
    acted = [i % 2 == 0 for i in range(40)]
    obs = _defn_obs(list(acted), acted)
    pick = split_half_definition({"tek": obs})
    assert pick.stable is True
    assert pick.engine_f1 == split_half_agreement(obs).engine_f1


def test_skill_from_error_is_zero_at_the_baseline() -> None:
    """Hata ölçen boyutta da 'taban = 0' sözleşmesi geçerli.

    Kalibrasyon satırı sabit bir ölçek kullanıyordu (1 − ECE/0.25), yani saf
    tabanla EŞİT hata yapan bir sistem bile pozitif beceri alıyordu — AUC
    tarafındaki `skill_from_auc` (0.5 → 0) ile aynı sözleşmeyi paylaşmıyordu.
    """
    assert skill_from_error(0.20, 0.20) == 0.0      # tabanla aynı → 0
    assert skill_from_error(0.00, 0.20) == 100.0    # hatasız → 100
    assert skill_from_error(0.10, 0.20) == 50.0
    assert skill_from_error(0.30, 0.20) == 0.0      # tabandan kötü → 0'a kırpılır
    # Taban 0 ya da tanımsızsa oran kurulamaz; uydurma ölçek konmaz.
    assert skill_from_error(0.10, 0.0) is None
    assert skill_from_error(None, 0.20) is None
    assert skill_from_error(0.10, None) is None
    # Eski sabit ölçek tabanla eşit sistemi ödüllendiriyordu — bir daha olmasın.
    assert round(max(0.0, 1.0 - 0.20 / 0.25) * 100, 1) == 20.0


def test_lead_time_reports_the_saturated_baseline() -> None:
    """Öncü süre tek başına okunamaz: her tikte bayrak yakmak da 'erken' görünür.

    Ölçüt penceredeki EN ERKEN bayrak. Bu yüzden hiçbir şey bilmeyen, her tikte
    bayrak yakan bir kural azami öncü süreyi alır — sayı öngörüden değil tik
    ızgarasının geometrisinden gelir. Taban yanında raporlanmazsa satır
    yetenek gibi okunur.
    """
    ticks = {1: [50.0, 55.0, 60.0, 65.0]}
    moves = {1: [66.0]}

    # Motor yalnız 65'te bayrak yaktı: 1 dk önce.
    dar = lead_times(moves, {1: [65.0]}, lookback_min=15.0, all_tick_minutes=ticks)
    assert dar.mean_lead_min == 1.0
    # Doygun kural 51+ dakikadaki ilk tikten, yani 55'ten haber verirdi: 11 dk.
    assert dar.saturated_mean_lead_min == 11.0
    assert dar.saturated_coverage == 1.0
    assert "her tikte bayrak yakan kural" in dar.note

    # Motor da her tikte yakarsa öncü süre tabana EŞİT — ve not bunu söyler.
    doygun = lead_times(moves, ticks, lookback_min=15.0, all_tick_minutes=ticks)
    assert doygun.mean_lead_min == doygun.saturated_mean_lead_min
    assert "ızgaranın geometrisi" in doygun.note

    # Izgara verilmezse sayı yorumlanamaz olarak işaretlenir.
    tabansiz = lead_times(moves, {1: [65.0]}, lookback_min=15.0)
    assert tabansiz.saturated_mean_lead_min is None
    assert "tek başına yorumlanamaz" in tabansiz.note
