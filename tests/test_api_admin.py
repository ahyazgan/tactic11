"""/admin/* operasyonel görünürlük uçları."""

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


def test_db_stats_returns_zero_for_empty_db(client):
    r = client.get("/admin/db-stats")
    assert r.status_code == 200
    body = r.json()
    assert body["leagues"] == 0
    assert body["matches"] == 0
    assert body["job_runs"] == 0


def test_jobs_filters_by_status_and_since(session, client):
    now = datetime.now(UTC)
    session.add_all(
        [
            models.JobRun(
                job_name="sync_league", args='{"league_id":203}',
                started_at=now - timedelta(hours=2), ended_at=now - timedelta(hours=2),
                status="success", attempts=1, error=None,
            ),
            models.JobRun(
                job_name="sync_league", args='{"league_id":203}',
                started_at=now - timedelta(hours=1), ended_at=now - timedelta(hours=1),
                status="failed", attempts=3, error="RuntimeError: down",
            ),
            models.JobRun(
                job_name="sync_league", args='{"league_id":203}',
                started_at=now - timedelta(days=10), ended_at=now - timedelta(days=10),
                status="success", attempts=1, error=None,
            ),
        ]
    )
    session.flush()

    r = client.get("/admin/jobs?since_hours=24")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 2  # 10 günlük olan dışarıda

    r2 = client.get("/admin/jobs?status=failed&since_hours=24")
    assert r2.status_code == 200
    body2 = r2.json()
    assert len(body2) == 1
    assert body2[0]["error"] == "RuntimeError: down"
    assert body2[0]["attempts"] == 3
    assert body2[0]["duration_sec"] is not None


def test_usage_aggregates_by_source(session, client):
    now = datetime.now(UTC)
    session.add_all(
        [
            models.UsageEvent(source="api_football", endpoint="leagues", tokens=0, created_at=now),
            models.UsageEvent(source="api_football", endpoint="teams", tokens=0, created_at=now),
            models.UsageEvent(source="anthropic", endpoint="messages", tokens=722, created_at=now),
            models.UsageEvent(source="anthropic", endpoint="messages", tokens=528, created_at=now),
        ]
    )
    session.flush()

    r = client.get("/admin/usage")
    assert r.status_code == 200
    body = r.json()
    today = {row["source"]: row for row in body["today"]}
    assert today["api_football"]["calls"] == 2
    assert today["api_football"]["tokens"] == 0
    assert today["anthropic"]["calls"] == 2
    assert today["anthropic"]["tokens"] == 1250


def test_snapshots_filter_by_scope(session, client):
    now = datetime.now(UTC)
    session.add_all(
        [
            models.Snapshot(
                sport=football.SPORT_NAME, scope="league:203:season:2024",
                created_at=now - timedelta(days=1),
                leagues_count=1, teams_count=20, matches_count=100,
            ),
            models.Snapshot(
                sport=football.SPORT_NAME, scope="league:203:season:2024",
                created_at=now, leagues_count=1, teams_count=20, matches_count=110,
            ),
            models.Snapshot(
                sport=football.SPORT_NAME, scope="league:39:season:2024",
                created_at=now, leagues_count=1, teams_count=20, matches_count=80,
            ),
        ]
    )
    session.flush()

    r = client.get("/admin/snapshots?scope=league:203:season:2024")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 2  # En yeni önce
    assert body[0]["matches_count"] == 110
    assert body[1]["matches_count"] == 100

    r_all = client.get("/admin/snapshots")
    assert r_all.status_code == 200
    assert len(r_all.json()) == 3


def test_snapshots_diff_endpoint(session, client):
    now = datetime.now(UTC)
    scope = "league:203:season:2024"
    session.add_all([
        models.Snapshot(
            sport=football.SPORT_NAME, scope=scope, created_at=now - timedelta(days=10),
            leagues_count=1, teams_count=18, matches_count=80,
        ),
        models.Snapshot(
            sport=football.SPORT_NAME, scope=scope, created_at=now - timedelta(days=3),
            leagues_count=1, teams_count=19, matches_count=100,
        ),
        models.Snapshot(
            sport=football.SPORT_NAME, scope=scope, created_at=now,
            leagues_count=1, teams_count=20, matches_count=140,
        ),
    ])
    session.flush()

    # 7 gün geri → baseline 10 gün önceki snapshot (en yakın <= now-7days)
    r = client.get(f"/admin/snapshots/diff?scope={scope}&days=7")
    assert r.status_code == 200
    body = r.json()
    assert body["scope"] == scope
    assert body["delta"]["teams_count"] == 2  # 18 → 20
    assert body["delta"]["matches_count"] == 60  # 80 → 140
    assert body["delta"]["leagues_count"] == 0


def test_snapshots_diff_404_when_scope_empty(client):
    r = client.get("/admin/snapshots/diff?scope=league:999:season:2099&days=7")
    assert r.status_code == 404


def test_snapshots_diff_handles_no_baseline(session, client):
    """Çok geriye gidildiyse baseline yok — note dön, hata değil."""
    now = datetime.now(UTC)
    session.add(models.Snapshot(
        sport=football.SPORT_NAME, scope="league:203:season:2024",
        created_at=now, leagues_count=1, teams_count=20, matches_count=140,
    ))
    session.flush()

    r = client.get("/admin/snapshots/diff?scope=league:203:season:2024&days=30")
    assert r.status_code == 200
    body = r.json()
    assert "note" in body
    assert "bulunamadı" in body["note"]
    assert "latest" in body


def test_quota_status_empty_db_returns_ok_levels(client):
    """Boş usage_events → tüm fraction'lar 0, level ok."""
    r = client.get("/admin/quota-status")
    assert r.status_code == 200
    body = r.json()
    assert body["api_football"]["daily"]["used"] == 0
    assert body["api_football"]["daily"]["level"] == "ok"
    assert body["api_football"]["monthly"]["level"] == "ok"
    assert body["anthropic"]["daily_tokens"]["level"] == "ok"
    assert "warn_fraction" in body


def test_quota_status_reports_warn_level_at_80_percent(session, client):
    """api_football_daily_limit default 100; 80 çağrı → fraction 0.8, level warn."""
    now = datetime.now(UTC)
    session.add_all([
        models.UsageEvent(source="api_football", endpoint="fixtures", tokens=0, created_at=now)
        for _ in range(80)
    ])
    session.flush()
    r = client.get("/admin/quota-status")
    body = r.json()
    daily = body["api_football"]["daily"]
    assert daily["used"] == 80
    assert daily["fraction"] == 0.8
    assert daily["level"] == "warn"


def test_quota_status_reports_exceeded_at_limit(session, client):
    """100 çağrı = limit → fraction 1.0, level exceeded."""
    now = datetime.now(UTC)
    session.add_all([
        models.UsageEvent(source="api_football", endpoint="fixtures", tokens=0, created_at=now)
        for _ in range(100)
    ])
    session.flush()
    r = client.get("/admin/quota-status")
    body = r.json()
    daily = body["api_football"]["daily"]
    assert daily["fraction"] == 1.0
    assert daily["level"] == "exceeded"


def test_quota_status_anthropic_token_sum(session, client):
    """anthropic_daily_token_limit default 200000; 100000 token → 0.5 fraction."""
    now = datetime.now(UTC)
    session.add(models.UsageEvent(
        source="anthropic", endpoint="messages", tokens=100_000, created_at=now,
    ))
    session.flush()
    r = client.get("/admin/quota-status")
    body = r.json()
    an = body["anthropic"]["daily_tokens"]
    assert an["used"] == 100_000
    assert an["fraction"] == 0.5
    assert an["level"] == "ok"
