"""app.data.ingest.backfill — seçim + quota çekirdeği testleri."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.data.ingest.backfill import current_quota_used, matches_to_backfill
from app.db import models
from app.sports import football

T1 = "t-test-1"


def _match(ext_id: int, *, status: str = "FT", days_ago: int = 3, tenant: str | None = T1):
    now = datetime.now(UTC)
    return models.Match(
        sport=football.SPORT_NAME,
        external_id=ext_id,
        league_external_id=203,
        season=2025,
        kickoff=now - timedelta(days=days_ago),
        status=status,
        home_team_external_id=1,
        away_team_external_id=2,
        home_score=1,
        away_score=0,
        tenant_id=tenant,
    )


def _appearance(match_ext_id: int, *, tenant: str | None = T1):
    return models.PlayerAppearance(
        sport=football.SPORT_NAME,
        player_external_id=99,
        match_external_id=match_ext_id,
        minutes=90,
        kickoff=datetime.now(UTC) - timedelta(days=3),
        tenant_id=tenant,
    )


def test_selection_only_finished_matches(session):
    session.add_all([
        _match(1, status="FT"),
        _match(2, status="NS"),      # oynanmamış — seçilmemeli
        _match(3, status="AET"),
        _match(4, status="PEN"),
    ])
    session.flush()
    picked = matches_to_backfill(session, tenant_id=T1)
    assert {m.external_id for m in picked} == {1, 3, 4}


def test_selection_skips_already_ingested(session):
    session.add_all([_match(1), _match(2), _appearance(1)])
    session.flush()
    picked = matches_to_backfill(session, tenant_id=T1)
    assert {m.external_id for m in picked} == {2}


def test_selection_force_includes_ingested(session):
    session.add_all([_match(1), _match(2), _appearance(1)])
    session.flush()
    picked = matches_to_backfill(session, tenant_id=T1, force=True)
    assert {m.external_id for m in picked} == {1, 2}


def test_selection_limit_newest_first(session):
    session.add_all([
        _match(1, days_ago=10),
        _match(2, days_ago=1),
        _match(3, days_ago=5),
    ])
    session.flush()
    picked = matches_to_backfill(session, tenant_id=T1, limit=2)
    assert [m.external_id for m in picked] == [2, 3]   # en yeni önce


def test_selection_tenant_filter(session):
    session.add_all([_match(1, tenant=T1), _match(2, tenant="t-other")])
    session.flush()
    picked = matches_to_backfill(session, tenant_id=T1)
    assert {m.external_id for m in picked} == {1}


def test_quota_counts_only_today_api_football(session):
    now = datetime.now(UTC)
    session.add_all([
        models.UsageEvent(source="api_football", endpoint="/fixtures", tokens=0, created_at=now),
        models.UsageEvent(source="api_football", endpoint="/fixtures", tokens=0, created_at=now),
        # Dün — sayılmamalı
        models.UsageEvent(source="api_football", endpoint="/fixtures", tokens=0,
                          created_at=now - timedelta(days=1, hours=1)),
        # Başka kaynak — sayılmamalı
        models.UsageEvent(source="anthropic", endpoint="/messages", tokens=10, created_at=now),
    ])
    session.flush()
    assert current_quota_used(session) == 2
    assert current_quota_used(session, today_only=False) == 3


def test_appearance_backfill_job_registered():
    """Scheduler kaydı: appearance_backfill job registry'de olmalı."""
    import app.scheduler  # noqa: F401 — kayıt side-effect'i
    from app.scheduler.registry import get

    spec = get("appearance_backfill")
    assert spec.name == "appearance_backfill"
    assert callable(spec.handler)
