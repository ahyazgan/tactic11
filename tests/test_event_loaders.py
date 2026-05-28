"""EventRow → domain model loader tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.data.loaders import (
    load_match_events,
    load_player_events,
    load_team_events,
    rows_to_domain,
)
from app.db import models
from app.sports import football


def _seed_tenant(session, tenant_id: str = "t-default"):
    now = datetime.now(UTC)
    session.add(models.Tenant(
        id=tenant_id, slug=tenant_id, name="X",
        settings_json="{}", active=True, created_at=now,
    ))
    session.flush()


def _seed_match(session, *, match_id: int, home: int, away: int,
                tenant_id: str = "t-default", days_ago: int = 1):
    session.add(models.Match(
        sport=football.SPORT_NAME, external_id=match_id,
        league_external_id=203, season=2024,
        kickoff=datetime.now(UTC) - timedelta(days=days_ago),
        status="FT", home_team_external_id=home, away_team_external_id=away,
        home_score=1, away_score=0, tenant_id=tenant_id,
    ))
    session.flush()


def _make_event(*, match_id: int, event_type: str, team: int, player: int = 10,
                sb_id: str = "e1", tenant: str = "t-default",
                pattern: str = "regular", outcome: str = "completed",
                is_goal: bool = False, possession_id: int | None = None) -> models.EventRow:
    return models.EventRow(
        sport=football.SPORT_NAME, tenant_id=tenant,
        source="statsbomb_open", source_event_id=sb_id,
        match_external_id=match_id, team_external_id=team,
        player_external_id=player, event_type=event_type,
        minute=10.0, period=1,
        start_x=50.0, start_y=50.0,
        end_x=60.0, end_y=50.0 if event_type in ("pass", "carry") else None,
        outcome=outcome if event_type != "shot" else ("goal" if is_goal else None),
        body_part="right_foot" if event_type == "shot" else None,
        pattern=pattern,
        possession_id=possession_id,
        is_goal=is_goal if event_type == "shot" else None,
        key_pass=False, raw_json=None,
        created_at=datetime.now(UTC),
    )


@pytest.fixture()
def seeded_session(session):
    _seed_tenant(session)
    _seed_match(session, match_id=1001, home=11, away=22)
    session.add(_make_event(match_id=1001, event_type="pass", team=11, sb_id="p1"))
    session.add(_make_event(match_id=1001, event_type="carry", team=11, sb_id="c1"))
    session.add(_make_event(
        match_id=1001, event_type="defensive_action", team=11, sb_id="d1",
        pattern="tackle", outcome="successful",
    ))
    session.add(_make_event(
        match_id=1001, event_type="shot", team=11, sb_id="s1",
        pattern="open_play", is_goal=True,
    ))
    session.flush()
    return session


def test_load_match_events_separates_4_types(seeded_session):
    loaded = load_match_events(seeded_session, 1001)
    assert len(loaded.passes) == 1
    assert len(loaded.carries) == 1
    assert len(loaded.defensive_actions) == 1
    assert len(loaded.shots) == 1
    assert loaded.total == 4
    assert loaded.match_ids == [1001]


def test_load_team_events_last_n(seeded_session):
    loaded = load_team_events(seeded_session, 11, last_n=10)
    assert loaded.total == 4


def test_load_team_events_no_matches(seeded_session):
    loaded = load_team_events(seeded_session, 9999, last_n=10)
    assert loaded.total == 0


def test_load_player_events_with_meta(seeded_session):
    # PlayerAppearance ekle
    seeded_session.add(models.PlayerAppearance(
        sport=football.SPORT_NAME, tenant_id="t-default",
        match_external_id=1001, team_external_id=11,
        player_external_id=10, minutes=90,
        kickoff=datetime.now(UTC) - timedelta(days=1),
    ))
    seeded_session.flush()
    loaded, meta = load_player_events(seeded_session, 10, last_n=10)
    assert loaded.total == 4
    assert meta["team_external_id"] == 11
    assert meta["minutes_played"] == 90.0
    assert meta["matches_analyzed"] == 1


def test_load_player_events_no_appearances(seeded_session):
    loaded, meta = load_player_events(seeded_session, 9999, last_n=10)
    assert loaded.total == 0
    assert meta["matches_analyzed"] == 0


def test_rows_to_domain_shot_fields_preserved(seeded_session):
    rows = list(seeded_session.query(models.EventRow).all())
    loaded = rows_to_domain(rows)
    shot = loaded.shots[0]
    assert shot.is_goal is True
    assert shot.pattern == "open_play"
    assert shot.body_part == "right_foot"


def test_rows_to_domain_def_action_type(seeded_session):
    rows = list(seeded_session.query(models.EventRow).all())
    loaded = rows_to_domain(rows)
    d = loaded.defensive_actions[0]
    assert d.action_type == "tackle"
    assert d.successful is True
