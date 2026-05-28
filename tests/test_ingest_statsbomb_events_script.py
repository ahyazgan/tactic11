"""scripts/ingest_statsbomb_events.py — CLI ingest tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from app.db import models
from app.sports import football


@pytest.fixture()
def seeded(session):
    """Tenant + 2 maç + ingest fixture."""
    now = datetime.now(UTC)
    session.add(models.Tenant(
        id="t-default", slug="t-default", name="X",
        settings_json="{}", active=True, created_at=now,
    ))
    for mid, days_ago in [(3001, 1), (3002, 5)]:
        session.add(models.Match(
            sport=football.SPORT_NAME, external_id=mid,
            league_external_id=203, season=2024,
            kickoff=now - timedelta(days=days_ago),
            status="FT", home_team_external_id=611,
            away_team_external_id=607, home_score=1, away_score=0,
            tenant_id="t-default",
        ))
    session.commit()
    return session


SB_SAMPLE_EVENTS = [
    {
        "id": "sb-p1", "minute": 5, "period": 1,
        "type": {"id": 30}, "team": {"id": 611}, "player": {"id": 100},
        "location": [40, 30],
        "pass": {"end_location": [80, 35]},
        "possession": 1,
    },
    {
        "id": "sb-s1", "minute": 25, "period": 1,
        "type": {"id": 16}, "team": {"id": 611}, "player": {"id": 100},
        "location": [105, 40],
        "shot": {"outcome": {"id": 97, "name": "Goal"}},
    },
]


def test_candidate_matches_filters_by_team(seeded):
    from scripts.ingest_statsbomb_events import _candidate_matches
    seeded.info["tenant_id"] = "t-default"
    candidates = _candidate_matches(seeded, tenant_id="t-default", team_id=611)
    assert len(candidates) == 2


def test_candidate_matches_filters_by_match(seeded):
    from scripts.ingest_statsbomb_events import _candidate_matches
    seeded.info["tenant_id"] = "t-default"
    candidates = _candidate_matches(seeded, tenant_id="t-default", match_id=3001)
    assert len(candidates) == 1
    assert candidates[0].external_id == 3001


def test_candidate_matches_limit(seeded):
    from scripts.ingest_statsbomb_events import _candidate_matches
    seeded.info["tenant_id"] = "t-default"
    candidates = _candidate_matches(
        seeded, tenant_id="t-default", team_id=611, limit=1,
    )
    assert len(candidates) == 1


def test_already_ingested_false_before_ingest(seeded):
    from scripts.ingest_statsbomb_events import _already_ingested
    assert _already_ingested(seeded, 3001, "t-default") is False


def test_already_ingested_true_after_event_insert(seeded):
    from scripts.ingest_statsbomb_events import _already_ingested
    seeded.add(models.EventRow(
        sport=football.SPORT_NAME, tenant_id="t-default",
        source="statsbomb_open", source_event_id="x1",
        match_external_id=3001, team_external_id=611,
        player_external_id=100, event_type="pass",
        minute=5.0, period=1,
        start_x=40, start_y=30, end_x=80, end_y=35,
        outcome="completed", body_part=None, pattern="regular",
        possession_id=1, is_goal=None, key_pass=False, raw_json=None,
        created_at=datetime.now(UTC),
    ))
    seeded.commit()
    assert _already_ingested(seeded, 3001, "t-default") is True


def test_ingest_dry_run_returns_match_ids_only(seeded):
    from scripts import ingest_statsbomb_events
    with patch("scripts.ingest_statsbomb_events.SessionLocal") as mock_sl:
        mock_sl.return_value.__enter__.return_value = seeded
        report = ingest_statsbomb_events.ingest(
            tenant_id="t-default", team_id=611, dry_run=True,
        )
    assert report["candidates"] == 2
    assert report["processed"] == 0
    assert report["events_written"] == 0
    assert set(report["dry_run_match_ids"]) == {3001, 3002}


def test_ingest_writes_events_for_match(seeded, monkeypatch):
    from scripts import ingest_statsbomb_events
    # Monkeypatch StatsBombOpen._fetch_json
    monkeypatch.setattr(
        "app.data.sources.statsbomb_open.StatsBombOpen._fetch_json",
        lambda self, path: SB_SAMPLE_EVENTS,
    )
    with patch("scripts.ingest_statsbomb_events.SessionLocal") as mock_sl:
        mock_sl.return_value.__enter__.return_value = seeded
        report = ingest_statsbomb_events.ingest(
            tenant_id="t-default", match_id=3001,
        )
    assert report["processed"] == 1
    assert report["events_written"] == 2  # 1 pass + 1 shot
    assert report["failed"] == 0
    # DB'de gerçekten yazıldı mı
    n = seeded.query(models.EventRow).filter_by(match_external_id=3001).count()
    assert n == 2


def test_ingest_skips_already_ingested(seeded, monkeypatch):
    from scripts import ingest_statsbomb_events
    # Önce manuel bir event ekle (zaten ingest sayılsın)
    seeded.add(models.EventRow(
        sport=football.SPORT_NAME, tenant_id="t-default",
        source="statsbomb_open", source_event_id="pre1",
        match_external_id=3001, team_external_id=611,
        player_external_id=100, event_type="pass",
        minute=1.0, period=1, start_x=40, start_y=30, end_x=80, end_y=35,
        outcome="completed", body_part=None, pattern="regular",
        possession_id=1, is_goal=None, key_pass=False, raw_json=None,
        created_at=datetime.now(UTC),
    ))
    seeded.commit()

    monkeypatch.setattr(
        "app.data.sources.statsbomb_open.StatsBombOpen._fetch_json",
        lambda self, path: SB_SAMPLE_EVENTS,
    )
    with patch("scripts.ingest_statsbomb_events.SessionLocal") as mock_sl:
        mock_sl.return_value.__enter__.return_value = seeded
        report = ingest_statsbomb_events.ingest(
            tenant_id="t-default", match_id=3001,
        )
    # Skip — zaten ingest edilmiş
    assert report["skipped"] == 1
    assert report["processed"] == 0
