"""Karne ölçüm girişleri: sayımları ayır, bağımsız kümeyi koru, önsel sırasını kilitle."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy.orm import sessionmaker

from app.data.sources.statsbomb_open import coach_moves_from_events_json
from app.db import models
from app.engine.coach_benchmark import ShapePrior, ShapeState
from app.engine.live_sub_recommendation import ELITE_OFF_PRIOR
from app.engine.sub_timing.elite_prior import (
    ELITE_SUB_WINDOW_PRIOR,
    MAX_SUBS_CELL,
    MINUTE_BANDS,
    SUB_WINDOW_THRESHOLD,
    UNKNOWN_CELL,
)
from scripts import (
    coach_iq,
    fit_timing_prior,
    measure_shape_selectivity,
    measure_sub_ranking,
    measure_within_group_signal,
    validate_shape_prior,
    validate_timing_prior,
    validate_who_prior,
)


def _events() -> list[dict]:
    return [
        {"type": {"id": 19}, "team": {"id": team}, "minute": minute,
         "player": {"id": i}, "substitution": {"replacement": {"id": i + 10},
                                                  "outcome": {"name": outcome}}}
        for i, (team, minute, outcome) in enumerate([
            (217, 60, "Tactical"), (217, 60, "Injury"),
            (217, 70, "Tactical"), (999, 60, "Tactical"),
        ], 1)
    ]


def test_coach_iq_counts_players_but_deduplicates_action_times() -> None:
    moves = coach_moves_from_events_json(_events())
    assert coach_iq._sub_minutes(moves, 217, tactical_only=False) == [60.0, 70.0]
    assert coach_iq._sub_minutes(moves, 217, tactical_only=False,
                                 unique=False) == [60.0, 60.0, 70.0]
    assert coach_iq._sub_minutes(moves, 217, tactical_only=True,
                                 unique=False) == [60.0, 70.0]


def test_measurement_counts_double_substitution_as_two(session, monkeypatch, tmp_path) -> None:
    for minute in (59.0, 60.0, 69.0, 70.0):
        session.add(models.Decision(
            sport="football", tenant_id="t-default", match_external_id=123,
            team_external_id=217, minute=minute, decision_type="tactical",
            created_at=datetime.now(UTC), context_json='{"theme": "adjust_shape"}',
        ))
    session.commit()
    monkeypatch.setattr(measure_shape_selectivity, "SessionLocal",
                        sessionmaker(bind=session.get_bind(), expire_on_commit=False))
    (tmp_path / "123.json").write_text(json.dumps(_events()), encoding="utf-8")
    rows = measure_shape_selectivity.collect_corpus_ticks(tmp_path, "t-default", 217, 12.0)
    assert {r["minute"]: r["subs_used"] for r in rows} == {
        59.0: 0, 60.0: 2, 69.0: 2, 70.0: 3,
    }


def test_permutation_has_no_p_value_without_eligible_gate() -> None:
    rows = [ShapeState(mid, 66.0, "trailing", 0, i == 0, 2, i == 0)
            for mid in (1, 2) for i in range(40)]
    result = measure_shape_selectivity._permutation(rows, 10, 17)
    assert result["p"] == [None, None]
    assert result["deneme"] == 0


def test_permutation_finite_trials_never_report_zero(monkeypatch) -> None:
    results = iter([[1.0, 1.0], [0.0, 0.0], [0.0, 0.0]])
    monkeypatch.setattr(measure_shape_selectivity, "_gated_precision",
                        lambda rows: next(results))
    result = measure_shape_selectivity._permutation([], 2, 17)
    assert result["karistirilmisin_yakalama_sayisi"] == [0, 0]
    assert result["p"] == pytest.approx([1 / 3, 1 / 3])


@pytest.mark.parametrize("trials", [0, -1])
def test_permutation_requires_positive_trials(trials) -> None:
    with pytest.raises(ValueError, match="pozitif"):
        measure_shape_selectivity._permutation([], trials, 17)


# --- bağımsız doğrulama (validate_shape_prior) ------------------------------- #

def _shift_events(team: int, other: int, *, shift_minutes: tuple[float, ...],
                  sub_minutes: tuple[float, ...] = ()) -> list[dict]:
    """İki takımlı asgari maç: her iki takım da hamle üretsin ki maç geçerli sayılsın."""
    ev: list[dict] = [
        {"type": {"id": 19}, "team": {"id": other}, "minute": 60,
         "player": {"id": 900}, "substitution": {"replacement": {"id": 901},
                                                 "outcome": {"name": "Tactical"}}},
    ]
    ev += [{"type": {"id": 36}, "team": {"id": team}, "minute": m,
            "tactics": {"formation": 433}} for m in shift_minutes]
    ev += [{"type": {"id": 19}, "team": {"id": team}, "minute": m, "player": {"id": 500 + i},
            "substitution": {"replacement": {"id": 600 + i},
                             "outcome": {"name": "Tactical"}}}
           for i, m in enumerate(sub_minutes)]
    return ev


def test_grid_ticks_cover_both_teams_and_window(tmp_path) -> None:
    """Izgara her maç için İKİ takımı üretir; hedef (t, t+pencere] aralığındadır."""
    (tmp_path / "7.json").write_text(
        json.dumps(_shift_events(11, 22, shift_minutes=(63.0,), sub_minutes=(46.0, 46.0))),
        encoding="utf-8")
    rows = validate_shape_prior._grid_ticks(tmp_path, [7], 12.0)
    assert {r["team"] for r in rows} == {11, 22}
    assert len(rows) == 2 * len(validate_shape_prior.GRID_MINUTES)
    ours = {r["minute"]: r for r in rows if r["team"] == 11}
    # 63. dakikadaki değişim yalnız 55 ve 60 tiklerinin penceresine girer
    assert [m for m, r in sorted(ours.items()) if r["coach_shift"]] == [55.0, 60.0]
    # aynı dakikadaki iki değişiklik iki hak sayılır
    assert ours[50.0]["subs_used"] == 2
    assert ours[45.0]["subs_used"] == 0


def test_prior_component_drops_support_threshold_only() -> None:
    """Taşınan nesne önseldir: tablo ve eşik aynı kalır, destek eşiği kapanır."""
    prior = ShapePrior({("x",): 0.9}, threshold=0.3, support_threshold=2, fitted_on=10)
    only = validate_shape_prior._prior_component(prior)
    assert only.table is prior.table
    assert only.threshold == prior.threshold
    assert only.support_threshold == 0


def test_independent_overlap_is_refused(tmp_path, monkeypatch, capsys) -> None:
    """Külliyatla kesişen 'bağımsız' küme ölçüm değildir — script durmalı."""
    ind = tmp_path / "ind"
    ind.mkdir()
    (ind / "123.json").write_text(json.dumps(_shift_events(11, 22, shift_minutes=(63.0,))),
                                  encoding="utf-8")
    monkeypatch.setattr(validate_shape_prior, "collect_corpus_ticks",
                        lambda *a, **k: [{"match": 123, "minute": 60.0}])
    monkeypatch.setattr("sys.argv", [
        "validate_shape_prior", "--events-dir", str(tmp_path), "--independent-dir", str(ind),
        "--out", str(tmp_path / "o.json"),
    ])
    assert validate_shape_prior.main() == 1
    assert "BAĞIMSIZ DEĞİL" in capsys.readouterr().out
    assert not (tmp_path / "o.json").exists()


# --- "kim çıkar" bağımsız doğrulaması ---------------------------------------- #

def _sub_match_events(team: int, other: int) -> list[dict]:
    """İlk 11 + tek taktik değişiklik: 9 numara çıkıyor, 12 giriyor."""
    def xi(t: int, base: int, positions: list[int]) -> dict:
        return {"type": {"id": 35}, "team": {"id": t}, "minute": 0,
                "tactics": {"lineup": [{"player": {"id": base + i},
                                        "position": {"id": p}}
                                       for i, p in enumerate(positions, 1)]}}
    return [
        xi(team, 0, [1, 3, 5, 9, 11, 13, 15, 17, 19, 21, 23]),
        xi(other, 100, [1, 3, 5, 9, 11, 13, 15, 17, 19, 21, 23]),
        {"type": {"id": 19}, "team": {"id": team}, "minute": 65, "player": {"id": 4},
         "substitution": {"replacement": {"id": 12}, "outcome": {"name": "Tactical"}}},
    ]


def test_who_states_use_on_pitch_players_and_starter_flag() -> None:
    states = validate_who_prior.who_states_from_events(_sub_match_events(11, 22), 7)
    assert len(states) == 1
    st = states[0]
    assert st.player_off == 4
    assert len(st.candidates) == 11            # yalnız kendi takımı, o an sahadakiler
    assert all(c.starter for c in st.candidates)
    assert {c.group for c in st.candidates} >= {"GK", "DEF", "MID", "FWD"}
    # takım süzgeci: öteki takım istenirse bu maçta hamlesi yok
    assert validate_who_prior.who_states_from_events(_sub_match_events(11, 22), 7, team=22) == []


def test_who_state_skipped_when_player_off_not_on_pitch() -> None:
    """Kadro kaydı eksikse uydurma aday listesi kurulmaz."""
    ev = [e for e in _sub_match_events(11, 22) if e["type"]["id"] != 35]
    assert validate_who_prior.who_states_from_events(ev, 7) == []


def test_frozen_prior_mirrors_production_table() -> None:
    """Sınanan nesne canlı motorun tablosudur; yalnız anahtar biçimi değişir."""
    table = validate_who_prior._frozen_prior().table
    for group, letter in validate_who_prior.GROUP_TO_LETTER.items():
        for starter in (True, False):
            assert table[(group, starter)] == ELITE_OFF_PRIOR[(letter, starter)]
    # bilinmeyen grup canlı motordaki gibi orta sahaya düşer
    assert table[("UNK", True)] == ELITE_OFF_PRIOR[("M", True)]


def test_production_prior_ranks_forward_over_midfield() -> None:
    """Barcelona-dışı havuzda en çok forvet çıkar; tablo bunu yansıtmalı.

    Eski tablo tek kulüpten geldiği için orta sahayı öne alıyordu
    (docs/KARNE-KIM-BAGIMSIZ.md). Bu test o gerilemeyi kilitler.
    """
    assert ELITE_OFF_PRIOR[("F", True)] > ELITE_OFF_PRIOR[("M", True)]
    assert ELITE_OFF_PRIOR[("M", True)] > ELITE_OFF_PRIOR[("D", True)]
    assert ELITE_OFF_PRIOR[("D", True)] > ELITE_OFF_PRIOR[("G", True)]
    # değişiklikle giren oyuncu her grupta ilk 11'den düşük
    for letter in ("F", "M", "D"):
        assert ELITE_OFF_PRIOR[(letter, False)] < ELITE_OFF_PRIOR[(letter, True)]


# --- sıralama ölçümü: beraberlik tarafsızlığı -------------------------------- #

def _cand(pid: int, prior: float, composite: float) -> tuple[int, float, float]:
    return (pid, prior, composite)


def test_expected_hits_is_exact_when_there_are_no_ties() -> None:
    """Beraberlik yoksa tarafsız ölçüm kesin sonucu bozmaz: 0 ya da 1."""
    cands = [_cand(1, 0.2, 0.9), _cand(2, 0.1, 0.8), _cand(3, 0.05, 0.7),
             _cand(4, 0.01, 0.6)]
    rank = measure_sub_ranking._lexicographic()
    assert measure_sub_ranking._expected_hits(cands, 1, rank, k=3) == (1.0, 1.0)
    assert measure_sub_ranking._expected_hits(cands, 3, rank, k=3) == (0.0, 1.0)
    assert measure_sub_ranking._expected_hits(cands, 4, rank, k=3) == (0.0, 0.0)


def test_expected_hits_splits_a_tie_instead_of_picking_an_order() -> None:
    """Dört oyuncu eşitse ilk sıra 1/4, ilk üç 3/4 — kimlik sırası ödüllendirilmez."""
    cands = [_cand(pid, 0.2, 0.5) for pid in (1, 2, 3, 4)]
    rank = measure_sub_ranking._lexicographic()
    for pid in (1, 2, 3, 4):
        at1, at3 = measure_sub_ranking._expected_hits(cands, pid, rank, k=3)
        assert at1 == pytest.approx(0.25)
        assert at3 == pytest.approx(0.75)


def test_expected_hits_tie_straddling_the_top_three_boundary() -> None:
    """İlk sırada tek oyuncu, kalan iki yeri üç eşit aday paylaşıyor → 2/3."""
    cands = [_cand(1, 0.3, 0.9)] + [_cand(pid, 0.2, 0.5) for pid in (2, 3, 4)]
    rank = measure_sub_ranking._lexicographic()
    assert measure_sub_ranking._expected_hits(cands, 1, rank, k=3) == (1.0, 1.0)
    for pid in (2, 3, 4):
        at1, at3 = measure_sub_ranking._expected_hits(cands, pid, rank, k=3)
        assert at1 == 0.0
        assert at3 == pytest.approx(2 / 3)


def test_reverse_control_flips_only_the_within_group_order() -> None:
    """Ters kontrol grubu değiştirmez, yalnız grup içindeki sırayı çevirir."""
    cands = [_cand(1, 0.2, 0.9), _cand(2, 0.2, 0.1), _cand(3, 0.05, 0.99)]
    fwd = measure_sub_ranking._lexicographic()
    rev = measure_sub_ranking._lexicographic(reverse_secondary=True)
    # düşük önselli oyuncu, bileşiği en yüksek olsa bile iki kuralda da ilk üçte sonda
    assert measure_sub_ranking._expected_hits(cands, 1, fwd, k=1) == (1.0, 1.0)
    assert measure_sub_ranking._expected_hits(cands, 2, rev, k=1) == (1.0, 1.0)
    assert measure_sub_ranking._expected_hits(cands, 3, fwd, k=1)[0] == 0.0
    assert measure_sub_ranking._expected_hits(cands, 3, rev, k=1)[0] == 0.0


# --- zamanlama önseli doğrulaması -------------------------------------------- #

def test_timing_cell_matches_the_engine_prior_keys() -> None:
    """Doğrulama scripti tabloyu motorun anahtar biçimiyle sorgulamalı.

    Bant/skor/hak üçlüsü motordakiyle birebir aynı olmazsa her tik 'görülmemiş'
    hücreye düşer ve ölçüm sessizce anlamsızlaşır.
    """
    row = {"minute": 72.0, "score_state": "trailing", "subs_used": 5}
    band, state, subs = validate_timing_prior._cell(row)
    assert (band, state, subs) == (3, "trailing", MAX_SUBS_CELL)
    assert validate_timing_prior._band(44.9) == 0
    assert validate_timing_prior._band(45.0) == 1
    assert validate_timing_prior._band(89.0) == 4
    # üretim tablosunun anahtarları bu biçimde sorgulanabiliyor
    assert any(validate_timing_prior._cell(
        {"minute": m, "score_state": s, "subs_used": u}) in ELITE_SUB_WINDOW_PRIOR
        for m in (20.0, 50.0, 65.0, 75.0, 85.0)
        for s in ("drawing", "leading", "trailing") for u in (0, 1, 2))


def test_timing_validation_refuses_overlapping_sets(tmp_path, monkeypatch, capsys) -> None:
    """Külliyat maçı bağımsız kümede de varsa ölçüm yapılmaz."""
    corpus, ind = tmp_path / "c", tmp_path / "i"
    corpus.mkdir()
    ind.mkdir()
    for d in (corpus, ind):
        (d / "555.json").write_text("[]", encoding="utf-8")
    monkeypatch.setattr("sys.argv", [
        "validate_timing_prior", "--corpus-dir", str(corpus), "--independent-dir", str(ind),
        "--out", str(tmp_path / "o.json"),
    ])
    assert validate_timing_prior.main() == 1
    assert "BAĞIMSIZ DEĞİL" in capsys.readouterr().out
    assert not (tmp_path / "o.json").exists()


def test_grid_ticks_separate_tactical_subs_from_injury_ones() -> None:
    """Zamanlama hedefi TAKTİK değişikliktir; kullanılan hak sayımı hepsini içerir."""
    events = [
        {"type": {"id": 35}, "team": {"id": 11}, "minute": 0,
         "tactics": {"lineup": [{"player": {"id": i}, "position": {"id": i}}
                                for i in range(1, 12)]}},
        {"type": {"id": 19}, "team": {"id": 11}, "minute": 62, "player": {"id": 5},
         "substitution": {"replacement": {"id": 20}, "outcome": {"name": "Injury"}}},
        {"type": {"id": 19}, "team": {"id": 22}, "minute": 62, "player": {"id": 90},
         "substitution": {"replacement": {"id": 91}, "outcome": {"name": "Tactical"}}},
    ]
    import json as _json
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp)
        (p / "9.json").write_text(_json.dumps(events), encoding="utf-8")
        rows = validate_shape_prior._grid_ticks(p, [9], 12.0)
    ours = {r["minute"]: r for r in rows if r["team"] == 11}
    # sakatlık değişikliği hedefi tetiklemez ama hakkı kullanır
    assert ours[55.0]["coach_sub"] is False
    assert ours[65.0]["subs_used"] == 1
    theirs = {r["minute"]: r for r in rows if r["team"] == 22}
    assert theirs[55.0]["coach_sub"] is True


# --- zamanlama önselinin yeniden fit'i --------------------------------------- #

def _timing_row(minute: float, state: str, used: int, allowed: int, acted: bool) -> dict:
    return {"match": 1, "team": 11, "minute": minute, "score_state": state,
            "subs_used": used, "allowed": allowed, "remaining": max(0, allowed - used),
            "coach_shift": False, "coach_sub": acted}


def test_fit_table_drops_exhausted_ticks_so_regimes_can_be_pooled() -> None:
    """Hak bitmiş tik tabloya GİRMEZ — o bilgi kapıda durur.

    Girmezse "3 kullanılmış" hücresi her rejimde aynı şeyi anlatır (3 yaptı ve
    hakkı var) ve 3-hak ile 5-hak verisi aynı havuza konabilir.
    """
    rows = [
        # 3 haklı maçta 3 kullanılmış → hak bitti, elenmeli
        _timing_row(70.0, "trailing", 3, 3, acted=False),
        _timing_row(75.0, "trailing", 3, 3, acted=False),
        # 5 haklı maçta 3 kullanılmış → hakkı var, tabloya girer
        _timing_row(70.0, "trailing", 3, 5, acted=True),
        _timing_row(75.0, "trailing", 3, 5, acted=True),
    ]
    table, counts = fit_timing_prior.fit_table(rows)
    cell = fit_timing_prior._cell(rows[0])
    assert counts[cell] == (2, 2)              # yalnız 5-hak tikleri sayıldı
    assert table[cell] > 0.5                   # ve oranı yüksek, sıfıra çekilmedi
    # elenen tikler hiçbir hücreye sızmadı
    assert sum(n for _a, n in counts.values()) == 2


def test_evaluate_never_flags_when_substitutions_are_exhausted() -> None:
    """Kapı her zaman açık: tablo ne derse desin, hak bittiyse bayrak yok."""
    cell = (3, "trailing", 3)
    generous = {cell: 0.99}
    exhausted = [_timing_row(75.0, "trailing", 3, 3, acted=True)]
    available = [_timing_row(75.0, "trailing", 3, 5, acted=True)]
    assert fit_timing_prior.evaluate(generous, exhausted, 0.35).flagged == 0
    assert fit_timing_prior.evaluate(generous, available, 0.35).flagged == 1


def test_production_timing_table_covers_the_second_half_completely() -> None:
    """Kararların alındığı her durum tabloda olmalı.

    Görülmemiş hücre `UNKNOWN_CELL = 0.5` sayılır ve bu eşiğin (0.35) ÜSTÜNDEDİR,
    yani eksik bir hücre sessizce bayrak üretir. 45. dakikadan sonra (bant ≥ 1)
    üç skor durumu × dört hak sayısı tam kapsanıyor. İlk yarıda (bant 0) yüksek
    hak sayıları gerçekte oluşmadığı için tabloda da yok.
    """
    assert UNKNOWN_CELL > SUB_WINDOW_THRESHOLD   # eksik hücre konuşur — kapsama şart
    for band in range(1, len(MINUTE_BANDS) + 1):
        for state in ("leading", "drawing", "trailing"):
            for used in range(MAX_SUBS_CELL + 1):
                assert (band, state, used) in ELITE_SUB_WINDOW_PRIOR, (band, state, used)
    # ilk yarıda yalnız düşük hak sayıları görülmüş
    first_half = {c for c in ELITE_SUB_WINDOW_PRIOR if c[0] == 0}
    assert {c[2] for c in first_half} <= {0, 1, 2}


# --- grup içi sinyal ölçümü --------------------------------------------------- #

def _wg_case(mid: int, off: int, peers: dict[int, float | None]) -> object:
    return measure_within_group_signal.Case(
        match_external_id=mid, player_off=off, group="MID", peers=tuple(peers),
        feats={p: {"toplam_pas": v} for p, v in peers.items()},
    )


def test_within_group_hit_splits_ties_instead_of_picking_an_order() -> None:
    """Eşit değerli üç aday ilk sırayı paylaşır → 1/3. Sabit sıra beceri sayılmaz."""
    case = _wg_case(1, off=7, peers={7: 5.0, 8: 5.0, 9: 5.0})
    assert measure_within_group_signal.expected_hit(case, "toplam_pas", +1) == pytest.approx(1 / 3)
    # açık ara önde olan aday tek başına ilk sırada
    clear = _wg_case(1, off=7, peers={7: 9.0, 8: 5.0, 9: 5.0})
    assert measure_within_group_signal.expected_hit(clear, "toplam_pas", +1) == 1.0
    assert measure_within_group_signal.expected_hit(clear, "toplam_pas", -1) == 0.0


def test_within_group_hit_skips_cases_without_a_usable_value() -> None:
    """Sinyali olmayan aday elenir; çıkan oyuncunun değeri yoksa vaka sayılmaz."""
    missing_off = _wg_case(1, off=7, peers={7: None, 8: 5.0, 9: 4.0})
    assert measure_within_group_signal.expected_hit(missing_off, "toplam_pas", +1) is None
    too_few = _wg_case(1, off=7, peers={7: 5.0, 8: None})
    assert measure_within_group_signal.expected_hit(too_few, "toplam_pas", +1) is None


def test_within_group_halves_never_split_one_match() -> None:
    """Aynı maçın değişiklikleri aynı yarıda kalmalı — yoksa seçim sızar."""
    cases = [_wg_case(mid, off=7, peers={7: 1.0, 8: 2.0}) for mid in (10, 10, 11, 11, 12)]
    a, b = measure_within_group_signal._halves(cases)
    a_ids = {c.match_external_id for c in a}
    b_ids = {c.match_external_id for c in b}
    assert a_ids & b_ids == set()
    assert len(a) + len(b) == len(cases)


def test_refit_baseline_is_frozen_not_read_from_the_live_constant():
    """Refit'in "eski tablo" sütunu CANLI sabitten okunmamalı.

    `fit_timing_prior` `ELITE_SUB_WINDOW_PRIOR`'ı değiştirmek için var. Kıyas
    tabanını oradan okursa, refit'ten sonra "eski" tablo yeni tablonun kendisi
    olur — üstelik örnek-içi ölçüldüğü için refit'i gerileme gibi gösterir.
    Bir tur bu şekilde yayımlandı; test tekrarını engelliyor.
    """
    from pathlib import Path

    from scripts import fit_timing_prior as fit

    assert not hasattr(fit, "ELITE_SUB_WINDOW_PRIOR"), (
        "canlı tablo ithal edilmiş — kıyas kendini ölçer"
    )

    base = fit._load_baseline(Path("docs/measurements/timing-prior-baseline.json"))
    assert len(base["tablo"]) == 50, "dondurulmuş taban refit öncesi 50 hücreydi"
    assert base["commit"] == "c0527cd"

    from app.engine.sub_timing.elite_prior import ELITE_SUB_WINDOW_PRIOR

    assert base["tablo"] != ELITE_SUB_WINDOW_PRIOR, "taban ile canlı tablo aynı olamaz"


def test_prior_source_has_one_home():
    """Künye tek yerde; ölçüm scripti kendi kopyasını tutmaz.

    `validate_timing_prior` refit'ten sonra bir tur "Barcelona'nın 100 maçı"
    yazmaya devam etti — tablo yedi kümeden yeniden fit edilmişken.
    """
    from app.engine.sub_timing.elite_prior import PRIOR_SOURCE
    from scripts.validate_timing_prior import PRIOR_SOURCE as imported

    assert imported is PRIOR_SOURCE
    assert "yedi küme" in PRIOR_SOURCE
