"""Sprint 5 endpoint testleri — formation matchup + team goals
(Faz 5 #24, #32)."""
from __future__ import annotations

from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.sprint5 import (
    BestAgainstIn,
    FormationMatchupIn,
    FormationRecordIn,
    TeamGoalPayload,
    TeamGoalUpdatePayload,
    create_team_goal,
    formation_matchup,
    formations_best_against,
    list_team_goals,
    update_team_goal,
)
from app.db.base import Base


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


# --------------------------------------------------------------------------- #
# #24 — Formation matchup
# --------------------------------------------------------------------------- #


def _rec(my: str, opp: str, mg: int, og: int) -> FormationRecordIn:
    return FormationRecordIn(
        my_formation=my, opp_formation=opp, my_goals=mg, opp_goals=og,
    )


def test_formation_matchup_basic() -> None:
    payload = FormationMatchupIn(
        my_formation="4-3-3",
        opp_formation="4-4-2",
        records=[
            _rec("4-3-3", "4-4-2", 2, 1),
            _rec("4-3-3", "4-4-2", 3, 0),
            _rec("4-3-3", "4-4-2", 1, 1),
            _rec("4-3-3", "3-5-2", 0, 2),  # filtre dışı
        ],
    )
    out = formation_matchup(payload)
    assert out.matches_played == 3
    assert out.wins == 2
    assert out.draws == 1
    assert out.losses == 0
    assert out.win_rate == pytest.approx(2 / 3, rel=1e-3)


def test_formation_matchup_empty_records_returns_zero() -> None:
    payload = FormationMatchupIn(
        my_formation="4-3-3", opp_formation="4-4-2", records=[],
    )
    out = formation_matchup(payload)
    assert out.matches_played == 0
    assert out.win_rate == 0.0


def test_formations_best_against_min_matches_guard() -> None:
    # 4-3-3 vs 4-4-2 yetersiz örnek (2 maç) → filtre dışı
    # 3-5-2 vs 4-4-2 3 maç → girer
    payload = BestAgainstIn(
        opp_formation="4-4-2",
        records=[
            _rec("4-3-3", "4-4-2", 2, 0),
            _rec("4-3-3", "4-4-2", 1, 0),
            _rec("3-5-2", "4-4-2", 1, 1),
            _rec("3-5-2", "4-4-2", 2, 1),
            _rec("3-5-2", "4-4-2", 3, 2),
        ],
        min_matches=3,
        top_n=5,
    )
    out = formations_best_against(payload)
    formations = [r.my_formation for r in out]
    assert "3-5-2" in formations
    assert "4-3-3" not in formations  # min_matches eşiği


def test_formations_best_against_sorting() -> None:
    # iki formasyon, biri %100 win, biri %33 win → ilk %100 olmalı
    payload = BestAgainstIn(
        opp_formation="4-4-2",
        records=[
            _rec("4-3-3", "4-4-2", 1, 0),
            _rec("4-3-3", "4-4-2", 2, 0),
            _rec("4-3-3", "4-4-2", 3, 0),
            _rec("3-5-2", "4-4-2", 1, 0),
            _rec("3-5-2", "4-4-2", 0, 1),
            _rec("3-5-2", "4-4-2", 0, 2),
        ],
        min_matches=3,
        top_n=5,
    )
    out = formations_best_against(payload)
    assert out[0].my_formation == "4-3-3"
    assert out[0].win_rate == 1.0


# --------------------------------------------------------------------------- #
# #32 — Team season goals
# --------------------------------------------------------------------------- #


def test_team_goal_create_then_list_by_season(session: Session) -> None:
    p1 = TeamGoalPayload(title="İlk 4'te bitir", metric="rank", target_value=4)
    p2 = TeamGoalPayload(title="60 puan", metric="points", target_value=60)
    create_team_goal(team_id=11, season=2024, payload=p1, session=session)
    create_team_goal(team_id=11, season=2025, payload=p2, session=session)

    s2024 = list_team_goals(team_id=11, season=2024, session=session)
    s2025 = list_team_goals(team_id=11, season=2025, session=session)
    assert len(s2024) == 1
    assert s2024[0].title.startswith("İlk")
    assert len(s2025) == 1
    assert s2025[0].metric == "points"


def test_team_goal_status_filter(session: Session) -> None:
    g1 = create_team_goal(
        team_id=11, season=2025,
        payload=TeamGoalPayload(title="A"), session=session,
    )
    g2 = create_team_goal(
        team_id=11, season=2025,
        payload=TeamGoalPayload(title="B"), session=session,
    )
    update_team_goal(
        team_id=11, goal_id=g2.id,
        payload=TeamGoalUpdatePayload(status="achieved"),
        session=session,
    )
    open_only = list_team_goals(
        team_id=11, season=2025, status="open", session=session,
    )
    achieved_only = list_team_goals(
        team_id=11, season=2025, status="achieved", session=session,
    )
    assert [g.id for g in open_only] == [g1.id]
    assert [g.id for g in achieved_only] == [g2.id]


def test_team_goal_invalid_status_rejected(session: Session) -> None:
    out = create_team_goal(
        team_id=11, season=2025,
        payload=TeamGoalPayload(title="x"), session=session,
    )
    with pytest.raises(HTTPException) as exc:
        update_team_goal(
            team_id=11, goal_id=out.id,
            payload=TeamGoalUpdatePayload(status="bogus"),
            session=session,
        )
    assert exc.value.status_code == 400


def test_team_goal_unknown_returns_404(session: Session) -> None:
    with pytest.raises(HTTPException) as exc:
        update_team_goal(
            team_id=11, goal_id=9999,
            payload=TeamGoalUpdatePayload(status="achieved"),
            session=session,
        )
    assert exc.value.status_code == 404
