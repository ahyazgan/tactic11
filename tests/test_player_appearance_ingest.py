"""Player appearance ingest — lineup + per-player stats (Prompt 4)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.data.ingest import ingest_appearances_for_match
from app.data.sources.api_football import APIFootball
from app.db import models
from app.sports import football


@pytest.fixture()
def adapter(monkeypatch):
    """Fixture mode (USE_FIXTURES=true) ile API'ya gitmeyen adapter."""
    monkeypatch.setenv("USE_FIXTURES", "true")
    from app.core.config import get_settings
    get_settings.cache_clear()  # type: ignore[attr-defined]
    return APIFootball()


def _seed_match(session, *, match_id: int = 1234140, tenant_id: str = "t-default"):
    now = datetime.now(UTC)
    session.add(models.Tenant(
        id=tenant_id, slug=tenant_id, name="X",
        settings_json="{}", active=True, created_at=now,
    ))
    session.add(models.Match(
        sport=football.SPORT_NAME, external_id=match_id,
        league_external_id=203, season=2024,
        kickoff=now - timedelta(days=1), status="FT",
        home_team_external_id=611, away_team_external_id=607,
        home_score=2, away_score=1, tenant_id=tenant_id,
    ))
    session.flush()


def test_adapter_get_fixture_lineups_returns_22_entries(adapter):
    lineups = adapter.get_fixture_lineups(1234140)
    # 11 starter × 2 takım + 3+3 sub = 28; fixture'da 11+3 = 14 her takım = 28 toplam
    assert len(lineups) == 28
    starters = [li for li in lineups if li.is_starter]
    assert len(starters) == 22  # 11 × 2 takım
    # Captain'ler set'li
    captains = [li for li in lineups if li.captain]
    assert len(captains) == 2  # Her takımda 1 captain
    # Formation set'li
    assert any(li.formation_played == "4-3-3" for li in lineups)
    assert any(li.formation_played == "4-2-3-1" for li in lineups)


def test_adapter_get_fixture_player_stats_returns_only_played(adapter):
    stats = adapter.get_fixture_player_stats(1234140)
    # Fixture'da 4 oyuncu var (3 Gala + 1 Fener)
    assert len(stats) == 4
    # Icardi'nin rating'i 8.5
    icardi = next(s for s in stats if s.player_external_id == 6120)
    assert icardi.rating == 8.5
    assert icardi.shots_total == 5
    assert icardi.passes_total == 22


def test_ingest_appearances_inserts_rows(session, adapter):
    _seed_match(session)
    report = ingest_appearances_for_match(
        session, adapter,
        match_external_id=1234140, tenant_id="t-default",
    )
    session.commit()
    # 28 lineup entries + 1 ekstra "oynayan ama lineup'ta yok" yok (sample temiz)
    # 28 lineup → 28 inserted
    assert report.rows_inserted >= 22
    assert report.players_in_lineup == 28
    assert report.players_with_stats == 4


def test_ingest_idempotent_second_call_updates(session, adapter):
    _seed_match(session)
    r1 = ingest_appearances_for_match(
        session, adapter,
        match_external_id=1234140, tenant_id="t-default",
    )
    session.commit()
    r2 = ingest_appearances_for_match(
        session, adapter,
        match_external_id=1234140, tenant_id="t-default",
    )
    session.commit()
    assert r1.rows_inserted >= 1
    assert r2.rows_inserted == 0
    assert r2.rows_updated == r1.rows_inserted


def test_ingest_writes_full_stats_for_played_player(session, adapter):
    _seed_match(session)
    ingest_appearances_for_match(
        session, adapter,
        match_external_id=1234140, tenant_id="t-default",
    )
    session.commit()
    # Icardi: 90 dk, rating 8.5, 5 şut
    icardi_row = session.query(models.PlayerAppearance).filter_by(
        player_external_id=6120,
    ).one()
    assert icardi_row.minutes == 90
    assert icardi_row.rating_apifootball == 8.5
    assert icardi_row.shots_total == 5
    assert icardi_row.team_external_id == 611
    assert icardi_row.tenant_id == "t-default"
    assert icardi_row.position_played == "F"  # lineup'tan
    assert icardi_row.formation_played == "4-3-3"


def test_ingest_marks_captain(session, adapter):
    _seed_match(session)
    ingest_appearances_for_match(
        session, adapter,
        match_external_id=1234140, tenant_id="t-default",
    )
    session.commit()
    # Ndombele (Gala captain) + Djiku (Fener captain)
    captains = session.query(models.PlayerAppearance).filter_by(captain=True).all()
    assert len(captains) == 2


def test_ingest_missing_match_raises(session, adapter):
    with pytest.raises(ValueError, match="DB'de yok"):
        ingest_appearances_for_match(
            session, adapter,
            match_external_id=9999999, tenant_id="t-default",
        )


def test_ingest_tenant_isolation(session, adapter):
    """İki tenant'a aynı match için ingest → ayrı satırlar."""
    _seed_match(session, tenant_id="t-a")
    _seed_match(session, match_id=1234141, tenant_id="t-b")  # farklı match id
    # tenant a için match 1234140
    ingest_appearances_for_match(
        session, adapter,
        match_external_id=1234140, tenant_id="t-a",
    )
    session.commit()
    rows_a = session.query(models.PlayerAppearance).filter_by(tenant_id="t-a").count()
    rows_b = session.query(models.PlayerAppearance).filter_by(tenant_id="t-b").count()
    assert rows_a > 0
    assert rows_b == 0  # B için ingest yapmadık
