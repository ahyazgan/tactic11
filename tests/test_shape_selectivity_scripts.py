"""Karne ölçüm girişleri: sayımları ayır, bağımsız kümeyi koru, önsel sırasını kilitle."""
from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import sessionmaker

from app.data.sources.statsbomb_open import coach_moves_from_events_json
from app.db import models
from app.engine.coach_benchmark import ShapePrior, ShapeState
from app.engine.live_sub_recommendation import ELITE_OFF_PRIOR
from scripts import (
    coach_iq,
    measure_shape_selectivity,
    validate_shape_prior,
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
