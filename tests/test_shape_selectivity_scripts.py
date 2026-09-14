"""Karne ölçüm girişlerinde oyuncu sayısı ile hamle anını ayır."""
from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import sessionmaker

from app.data.sources.statsbomb_open import coach_moves_from_events_json
from app.db import models
from app.engine.coach_benchmark import ShapeState
from scripts import coach_iq, measure_shape_selectivity


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
    rows = measure_shape_selectivity._collect(tmp_path, "t-default", 217, 12.0)
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
