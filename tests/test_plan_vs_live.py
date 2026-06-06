"""Plan-live köprü + scenario enrichment testleri (Faz 5 #27, #28)."""
from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.agents.base import AgentResult
from app.agents.game_plan import SCENARIOS, enrich_scenarios
from app.agents.store import save_agent_output
from app.api.plan import _active_scenario, _estimated_minute, _load_match_plan
from app.db import models
from app.db.base import Base
from app.sports import football

# --------------------------------------------------------------------------- #
# Scenario enrichment (saf fonksiyon — #27)
# --------------------------------------------------------------------------- #


def test_enrich_scenarios_no_matchup_returns_base_clone() -> None:
    out = enrich_scenarios(SCENARIOS, matchup=None)
    assert set(out.keys()) == set(SCENARIOS.keys())
    for k in SCENARIOS:
        assert out[k]["label"] == SCENARIOS[k]["label"]
        assert out[k]["formation_hint"] == SCENARIOS[k]["formation_hint"]
        assert "dynamic_focus" not in out[k]


def test_enrich_scenarios_with_matchup_adds_dynamic_focus() -> None:
    matchup = {"best_channel": "left", "worst_channel": "right"}
    out = enrich_scenarios(SCENARIOS, matchup=matchup)
    assert "dynamic_focus" in out["level"]
    assert "left" in out["level"]["dynamic_focus"]
    assert "dynamic_focus" in out["trailing"]
    assert "left" in out["trailing"]["dynamic_focus"]
    assert "dynamic_focus" in out["leading"]
    assert "right" in out["leading"]["dynamic_focus"]


def test_enrich_scenarios_does_not_mutate_base() -> None:
    matchup = {"best_channel": "central", "worst_channel": "left"}
    before = {k: dict(v) for k, v in SCENARIOS.items()}
    enrich_scenarios(SCENARIOS, matchup=matchup)
    after = {k: dict(v) for k, v in SCENARIOS.items()}
    assert before == after, "SCENARIOS modul-seviyesi dict mutate edildi"


# --------------------------------------------------------------------------- #
# Active scenario seçici (saf — skor + perspektif)
# --------------------------------------------------------------------------- #


def _make_match(
    *, home_id: int, away_id: int,
    home_score: int | None = None, away_score: int | None = None,
    kickoff: datetime | None = None,
    status: str = "1H",
) -> models.Match:
    return models.Match(
        sport=football.SPORT_NAME,
        external_id=9001,
        league_external_id=1,
        season=2024,
        kickoff=kickoff or datetime.now(UTC),
        status=status,
        home_team_external_id=home_id,
        away_team_external_id=away_id,
        home_score=home_score,
        away_score=away_score,
    )


def test_active_scenario_home_leading() -> None:
    m = _make_match(home_id=11, away_id=22, home_score=2, away_score=0)
    s, score = _active_scenario(my_team_id=11, match=m)
    assert s == "leading"
    assert score == {"home": 2, "away": 0}


def test_active_scenario_away_trailing() -> None:
    m = _make_match(home_id=11, away_id=22, home_score=2, away_score=0)
    s, _ = _active_scenario(my_team_id=22, match=m)
    assert s == "trailing"


def test_active_scenario_level_when_equal() -> None:
    m = _make_match(home_id=11, away_id=22, home_score=1, away_score=1)
    s, _ = _active_scenario(my_team_id=11, match=m)
    assert s == "level"


def test_active_scenario_unknown_when_no_score() -> None:
    m = _make_match(home_id=11, away_id=22)
    s, _ = _active_scenario(my_team_id=11, match=m)
    assert s == "unknown"


def test_active_scenario_unknown_when_team_not_in_match() -> None:
    m = _make_match(home_id=11, away_id=22, home_score=1, away_score=0)
    s, _ = _active_scenario(my_team_id=99, match=m)
    assert s == "unknown"


# --------------------------------------------------------------------------- #
# Estimated minute
# --------------------------------------------------------------------------- #


def test_estimated_minute_after_kickoff() -> None:
    now = datetime(2026, 5, 29, 16, 25, tzinfo=UTC)
    m = _make_match(
        home_id=11, away_id=22,
        kickoff=datetime(2026, 5, 29, 16, 0, tzinfo=UTC),
    )
    assert _estimated_minute(m, now) == 25


def test_estimated_minute_negative_before_kickoff_returns_none() -> None:
    now = datetime(2026, 5, 29, 15, 30, tzinfo=UTC)
    m = _make_match(
        home_id=11, away_id=22,
        kickoff=datetime(2026, 5, 29, 16, 0, tzinfo=UTC),
    )
    assert _estimated_minute(m, now) is None


def test_estimated_minute_capped_at_120() -> None:
    now = datetime(2026, 5, 29, 23, 0, tzinfo=UTC)
    m = _make_match(
        home_id=11, away_id=22,
        kickoff=datetime(2026, 5, 29, 16, 0, tzinfo=UTC),
    )
    assert _estimated_minute(m, now) == 120


# --------------------------------------------------------------------------- #
# Round-trip: save_agent_output → _load_match_plan
# --------------------------------------------------------------------------- #


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def test_plan_roundtrip_via_store_helpers(session: Session) -> None:
    match_id = 9001
    # Maç DB'ye
    session.add(_make_match(home_id=11, away_id=22, home_score=1, away_score=0))
    session.flush()

    # Plan kaydet (save_agent_output kullanarak — endpoint'in yaptığı şey)
    result = AgentResult(
        output_json={
            "matchup_grid": {"best_channel": "left", "recommendation": "soldan zorla"},
            "scenario_plan": {
                "leading": {"label": "Öndeyiz", "approach": "kontrollü blok"},
            },
            "set_piece_plan": {
                "top_recommendations": [
                    {"zone": "near-post", "technique": "in-swinger",
                     "rationale": "rakip near zayıf"},
                ],
            },
        },
        summary="test plan",
        subject_type="match",
        subject_id=match_id,
    )
    save_agent_output(
        session, result=result, agent_name="game_plan", agent_version="1",
    )
    session.flush()

    # Load helper
    loaded = _load_match_plan(session, match_id)
    assert loaded is not None
    assert loaded.subject_id == match_id
    data = json.loads(loaded.output_json)
    assert data["matchup_grid"]["best_channel"] == "left"


def test_plan_idempotent_upsert(session: Session) -> None:
    match_id = 9001
    session.add(_make_match(home_id=11, away_id=22))
    session.flush()

    for summary in ("v1", "v2", "v3"):
        save_agent_output(
            session,
            result=AgentResult(
                output_json={"v": summary},
                summary=summary,
                subject_type="match",
                subject_id=match_id,
            ),
            agent_name="game_plan",
            agent_version="1",
        )
    session.flush()

    # Sadece 1 satır kaldı — son sürüm
    loaded = _load_match_plan(session, match_id)
    assert loaded is not None
    assert loaded.summary == "v3"
