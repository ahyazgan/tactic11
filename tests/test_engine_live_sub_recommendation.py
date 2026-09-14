"""engine.live_sub_recommendation tests."""

from __future__ import annotations

from app.domain import PassEvent
from app.engine.live_sub_recommendation import compute_live_sub_recommendation


def _p(player: int, minute: float, completed: bool = True) -> PassEvent:
    return PassEvent(
        sport="football", match_external_id=99, player_external_id=player,
        team_external_id=11, minute=minute, period=1,
        start_x=50, start_y=50, end_x=60, end_y=50,
        completed=completed,
    )


def test_high_urgency_when_fatigued_and_losing():
    """Yorgun oyuncu + geride + 75. dakika → high urgency."""
    # Player 100: 15 erken aktif pas, 2 geç başarısız pas → fatigue yüksek
    passes = (
        [_p(100, minute=10.0, completed=True)] * 15
        + [_p(100, minute=65.0, completed=False)] * 2
    )
    r = compute_live_sub_recommendation(
        team_external_id=11, all_passes=passes, all_def_actions=[],
        current_minute=75.0, my_score=0, opponent_score=1,
    ).value
    assert len(r.recommendations) >= 1
    top = r.recommendations[0]
    assert top.player_external_id == 100
    assert top.urgency_label in ("high", "medium")
    assert r.score_state == "losing"


def test_score_state_winning_lower_urgency():
    passes = [_p(100, minute=10.0)] * 5 + [_p(100, minute=70.0)] * 5
    r = compute_live_sub_recommendation(
        team_external_id=11, all_passes=passes, all_def_actions=[],
        current_minute=75.0, my_score=2, opponent_score=0,
    ).value
    assert r.score_state == "winning"


def test_eligible_player_ids_excludes_subbed_off():
    """Faz B: çoktan çıkmış oyuncu (eligible kümede yok) önerilmez —
    event'leri pencerede hâlâ görünse bile."""
    # 100 ve 200 ikisi de yorgun aktör; ama 100 sahadan çıktı (eligible: {200}).
    passes = (
        [_p(100, minute=10.0, completed=True)] * 15
        + [_p(100, minute=65.0, completed=False)] * 2
        + [_p(200, minute=10.0, completed=True)] * 15
        + [_p(200, minute=65.0, completed=False)] * 2
    )
    r = compute_live_sub_recommendation(
        team_external_id=11, all_passes=passes, all_def_actions=[],
        current_minute=75.0, my_score=0, opponent_score=1,
        eligible_player_ids={200},
    ).value
    rec_ids = {rec.player_external_id for rec in r.recommendations}
    assert 100 not in rec_ids            # çıkmış → önerilmez
    assert 200 in rec_ids                # sahada → önerilir


def test_eligible_none_keeps_all_actors():
    """eligible_player_ids=None → eski davranış (tüm event-aktörleri)."""
    passes = (
        [_p(100, minute=10.0, completed=True)] * 15
        + [_p(100, minute=65.0, completed=False)] * 2
    )
    r = compute_live_sub_recommendation(
        team_external_id=11, all_passes=passes, all_def_actions=[],
        current_minute=75.0, my_score=0, opponent_score=1,
    ).value
    assert 100 in {rec.player_external_id for rec in r.recommendations}


def test_low_action_player_filtered():
    """3 aksiyon var (eşik 5) → filtre."""
    passes = [_p(100, minute=10.0)] * 3
    r = compute_live_sub_recommendation(
        team_external_id=11, all_passes=passes, all_def_actions=[],
        current_minute=60.0,
    ).value
    assert len(r.recommendations) == 0


def test_reasons_human_readable():
    passes = (
        [_p(100, minute=10.0, completed=True)] * 15
        + [_p(100, minute=70.0, completed=False)] * 5
    )
    r = compute_live_sub_recommendation(
        team_external_id=11, all_passes=passes, all_def_actions=[],
        current_minute=78.0, my_score=0, opponent_score=1,
    ).value
    assert r.recommendations[0].reasons
    # Türkçe nedenler
    reasons_str = " ".join(r.recommendations[0].reasons)
    assert any(kw in reasons_str for kw in ("yorgunluk", "Geride", "son"))


def test_top_3_ranked():
    """3 oyuncudan biri çok yorgun → o ilk sırada."""
    passes = (
        # Player 100: yüksek fatigue
        [_p(100, minute=10.0, completed=True)] * 15
        + [_p(100, minute=70.0, completed=False)] * 2
        # Player 200: normal
        + [_p(200, minute=10.0, completed=True)] * 8
        + [_p(200, minute=70.0, completed=True)] * 8
        # Player 300: az aksiyon
        + [_p(300, minute=10.0, completed=True)] * 5
        + [_p(300, minute=70.0, completed=True)] * 5
    )
    r = compute_live_sub_recommendation(
        team_external_id=11, all_passes=passes, all_def_actions=[],
        current_minute=75.0,
    ).value
    assert len(r.recommendations) <= 3
    # Player 100 ilk olmalı (en yorgun)
    assert r.recommendations[0].player_external_id == 100


def test_off_prior_reorders_candidates_and_explains():
    """Aynı yorgunlukta iki oyuncu: elit önsel orta sahayı stoperin önüne alır."""
    from app.engine.live_sub_recommendation import ELITE_OFF_PRIOR, elite_off_prior

    passes = ([_p(1, 10.0)] * 15 + [_p(1, 65.0, False)] * 2
              + [_p(2, 10.0)] * 15 + [_p(2, 65.0, False)] * 2)
    base = compute_live_sub_recommendation(
        team_external_id=11, all_passes=passes, all_def_actions=[], current_minute=70.0,
    ).value
    assert {r.player_external_id for r in base.recommendations} == {1, 2}
    prior = {1: elite_off_prior("DC", True), 2: elite_off_prior("MC", True)}
    assert prior[2] == ELITE_OFF_PRIOR[("M", True)] > prior[1]
    r = compute_live_sub_recommendation(
        team_external_id=11, all_passes=passes, all_def_actions=[], current_minute=70.0,
        off_prior=prior,
    ).value
    assert r.recommendations[0].player_external_id == 2
    assert any("elit önsel" in x for x in r.recommendations[0].reasons)
    # bilinmeyen mevki → orta saha/ilk 11 varsayımı; değişiklikle giren düşük
    assert elite_off_prior(None, True) == ELITE_OFF_PRIOR[("M", True)]
    assert elite_off_prior("FC", False) < elite_off_prior("FC", True)


def test_sub_timing_elite_window_needs_subs_used():
    """subs_used yoksa pencere kapalı; verilince elit önsel olasılığı ve bayrak döner."""
    from app.engine.sub_timing import compute_sub_timing
    from app.engine.sub_timing.elite_prior import (
        SUB_WINDOW_THRESHOLD,
        elite_sub_window_probability,
    )

    passes = [_p(1, 10.0)] * 15 + [_p(1, 65.0, False)] * 2
    off = compute_sub_timing(11, passes, [], current_minute=66.0, my_score=1, opponent_score=0).value
    assert off.elite_window_probability is None and off.elite_window is False
    on = compute_sub_timing(11, passes, [], current_minute=66.0, my_score=1, opponent_score=0,
                            subs_used=0).value
    assert on.elite_window_probability == round(elite_sub_window_probability(66.0, "leading", 0), 3)
    assert on.elite_window is (on.elite_window_probability >= SUB_WINDOW_THRESHOLD)
    # 20. dakika berabere, hak kullanılmamış → pencere kapalı; 3 hak bitmişse geç dakikada da düşük
    early = compute_sub_timing(11, passes, [], current_minute=20.0, subs_used=0).value
    assert early.elite_window is False
    assert elite_sub_window_probability(85.0, "trailing", 3) < SUB_WINDOW_THRESHOLD
    assert elite_sub_window_probability(66.0, "trailing", 0) > elite_sub_window_probability(20.0, "trailing", 0)


def test_recommendation_order_is_deterministic_not_set_iteration_order():
    """Eşit aciliyette sıra AÇIK kurala göre: aciliyet → yorgunluk → oyuncu kimliği.

    Önceden eşitlik `my_player_ids` kümesinin yineleme sırasıyla çözülüyordu,
    yani koça gösterilen 1. öneri oyuncu kimliğinin hash'ine bağlıydı — tekrar
    üretilemez. Ölçüm grup içi sıranın bilgi taşımadığını gösteriyor
    (docs/KARNE-SIRALAMA.md); bu test isabeti değil, çıktının açıklanabilir
    olmasını kilitler.
    """
    passes = [_p(pid, minute) for pid in (901, 902, 903)
              for minute in (5.0, 10.0, 15.0, 20.0, 25.0, 60.0)]
    first = compute_live_sub_recommendation(
        team_external_id=11, all_passes=passes, all_def_actions=[], current_minute=70.0,
    ).value
    # Girdi sırası değişse de çıktı sırası aynı kalmalı
    second = compute_live_sub_recommendation(
        team_external_id=11, all_passes=list(reversed(passes)), all_def_actions=[],
        current_minute=70.0,
    ).value
    assert [r.player_external_id for r in first.recommendations] ==            [r.player_external_id for r in second.recommendations]
    keys = [(-r.urgency_score, -r.fatigue_score, r.player_external_id)
            for r in first.recommendations]
    assert keys == sorted(keys)


def test_sub_window_probability_is_zero_when_substitutions_are_exhausted():
    """Hak bittiyse olasılık ÖĞRENİLMEZ, 0'dır — değişiklik kural gereği imkânsız.

    Tablo 3-hak ve 5-hak maçlarının karışımından fit edildi, bu yüzden
    "3 kullanılmış" hücresi iki zıt gerçeği harmanlıyor (3-hak döneminde gerçek
    oran 0.000, 5-hak döneminde 0.672 — docs/KARNE-DEGISIKLIK-HAKKI.md).
    """
    from app.engine.sub_timing import DEFAULT_SUBS_ALLOWED, elite_sub_window_probability

    # 3 haklı bir maçta 3 değişiklik yapıldıysa pencere KAPALI
    assert elite_sub_window_probability(70.0, "trailing", 3, subs_allowed=3) == 0.0
    # aynı durum 5 haklı maçta öğrenilen değeri verir ve pozitiftir
    assert elite_sub_window_probability(70.0, "trailing", 3, subs_allowed=5) > 0.0
    # varsayılan bugünün kuralıdır ve GÜVENLİ yöndedir: 3-hak maçında hiç
    # ateşlenmez, yani yanlışlıkla öneri bastırmaz
    assert DEFAULT_SUBS_ALLOWED == 5
    assert elite_sub_window_probability(70.0, "trailing", 3) > 0.0
    assert elite_sub_window_probability(70.0, "trailing", 5) == 0.0


def test_sub_timing_passes_allowance_to_the_window():
    """compute_sub_timing hak sayısını önsele geçirir; hak bitince pencere kapanır."""
    from app.engine.sub_timing import compute_sub_timing

    passes = [_p(pid, minute) for pid in (11, 12, 13)
              for minute in (5.0, 10.0, 15.0, 20.0, 25.0, 60.0)]
    kwargs = dict(all_passes=passes, all_def_actions=[], current_minute=70.0,
                  my_score=0, opponent_score=1)
    open_window = compute_sub_timing(11, subs_used=2, subs_allowed=5, **kwargs).value
    shut = compute_sub_timing(11, subs_used=3, subs_allowed=3, **kwargs).value
    assert open_window.elite_window_probability is not None
    assert open_window.elite_window_probability > 0.0
    assert shut.elite_window_probability == 0.0
    assert shut.elite_window is False
