"""/admin/teams/{id}/tactical-trend endpoint tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.db import models
from app.db.session import get_session
from app.sports import football


@pytest.fixture()
def client(session):
    def _override():
        yield session
    app.dependency_overrides[get_session] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _seed_match(session, *, match_id: int, days_ago: int,
                home: int = 11, away: int = 22, score: str = "1-0"):
    hs, as_ = score.split("-")
    session.add(models.Match(
        sport=football.SPORT_NAME, external_id=match_id,
        league_external_id=203, season=2024,
        kickoff=datetime.now(UTC) - timedelta(days=days_ago),
        status="FT",
        home_team_external_id=home, away_team_external_id=away,
        home_score=int(hs), away_score=int(as_),
        tenant_id="t-default",
    ))


def _add_event(session, *, match_id: int, ev_type: str, team: int,
               sb_id: str, start_x: float = 50, end_x: float = 70,
               outcome: str = "completed", pattern: str = "regular",
               minute: float = 10.0, poss: int = 1, player: int = 1,
               is_goal: bool = False):
    session.add(models.EventRow(
        sport=football.SPORT_NAME, tenant_id="t-default",
        source="statsbomb_open", source_event_id=sb_id,
        match_external_id=match_id, team_external_id=team,
        player_external_id=player, event_type=ev_type,
        minute=minute, period=1,
        start_x=start_x, start_y=50.0, end_x=end_x, end_y=50.0,
        outcome=outcome if ev_type != "shot" else ("goal" if is_goal else None),
        body_part="right_foot" if ev_type == "shot" else None,
        pattern=pattern, possession_id=poss,
        is_goal=is_goal if ev_type == "shot" else None,
        key_pass=False, raw_json=None,
        created_at=datetime.now(UTC),
    ))


def test_trend_endpoint_empty_returns_note(client):
    r = client.get("/admin/teams/11/tactical-trend")
    assert r.status_code == 200
    body = r.json()
    assert body["matches_analyzed"] == 0


def test_trend_with_3_matches(session, client):
    """3 maç event'i ekle → 3 noktalı series + slope üretiyor mu."""
    session.add(models.Tenant(
        id="t-default", slug="t-default", name="X",
        settings_json="{}", active=True, created_at=datetime.now(UTC),
    ))
    for mid, days_ago, score in [(2001, 10, "1-0"), (2002, 5, "2-1"), (2003, 1, "3-0")]:
        _seed_match(session, match_id=mid, days_ago=days_ago, score=score)
        # Her maça birkaç event
        for i in range(8):
            _add_event(session, match_id=mid, ev_type="pass", team=11,
                       sb_id=f"m{mid}_p{i}", outcome="completed")
            _add_event(session, match_id=mid, ev_type="pass", team=22,
                       sb_id=f"m{mid}_op{i}", start_x=40, end_x=60,
                       outcome="completed")
        for i in range(3):
            _add_event(session, match_id=mid, ev_type="defensive_action",
                       team=11, sb_id=f"m{mid}_d{i}", pattern="tackle",
                       outcome="successful")
        for i in range(2):
            _add_event(session, match_id=mid, ev_type="shot", team=11,
                       sb_id=f"m{mid}_s{i}", start_x=90, pattern="open_play",
                       is_goal=(i == 0))
    session.commit()

    r = client.get("/admin/teams/11/tactical-trend?last_n=10")
    assert r.status_code == 200
    body = r.json()
    assert body["team_id"] == 11
    assert body["matches_analyzed"] == 3
    assert len(body["matches"]) == 3
    # Kronolojik sıra: eski → yeni
    assert body["matches"][0]["match_id"] == 2001
    assert body["matches"][-1]["match_id"] == 2003
    # 5 metric var
    trends = body["trends"]
    assert set(trends.keys()) == {
        "ppda", "field_tilt", "team_xt", "possession_share", "dominance_score",
    }
    for _m, t in trends.items():
        assert len(t["series"]) == 3
        assert "direction" in t
        assert t["direction"] in (
            "improving", "stable", "worsening", "insufficient_data",
        )


def test_trend_no_finished_matches(session, client):
    """Hiç FINISHED maç yok → not."""
    session.add(models.Tenant(
        id="t-default", slug="t-default", name="X",
        settings_json="{}", active=True, created_at=datetime.now(UTC),
    ))
    session.commit()
    r = client.get("/admin/teams/9999/tactical-trend")
    body = r.json()
    assert body["matches_analyzed"] == 0
    assert "Bu takımın FINISHED maçı yok" in body.get("note", "")


def test_trend_skips_matches_without_events(session, client):
    """Match var ama event yok → skip."""
    session.add(models.Tenant(
        id="t-default", slug="t-default", name="X",
        settings_json="{}", active=True, created_at=datetime.now(UTC),
    ))
    _seed_match(session, match_id=3001, days_ago=5)
    session.commit()
    r = client.get("/admin/teams/11/tactical-trend")
    body = r.json()
    assert body["matches_analyzed"] == 0
    assert "Hiçbir maç" in body.get("note", "")
