"""engine.coach_benchmark — koç zekâ karnesi.

Testler üç şeyi kilitler:
1. Taban çizgisi eşiği AYRIK yarıda seçilir: A'da ölçülen eşik B'den gelir.
   Aynı yarıda seçip ölçmek saat-kuralını haksız parlatırdı.
2. Bir kol boşsa F1 tanımsızdır ve hüküm "yetersiz veri"dir — sayı uydurulmaz.
3. Beceri ölçekleri sabit: AUC 0.5 → 0, TERS ilişki 0'a kırpılır; ECE tanımı.
"""
from __future__ import annotations

from app.engine.coach_benchmark import (
    MIN_F1_GAIN,
    MIN_TICKS_PER_HALF,
    Dimension,
    TickObservation,
    agreement,
    build_scorecard,
    expected_calibration_error,
    lead_times,
    minute_rule,
    skill_from_auc,
    split_half_agreement,
)

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
