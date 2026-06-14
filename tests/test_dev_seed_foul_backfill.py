"""dev_seed _backfill_fouls — eski demo.db'de foul yoksa idempotent re-ingest."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.data.ingest.event import ingest_events_for_match
from app.db import models
from app.sports import football


class _FakeSource:
    def __init__(self, events: list[dict]):
        self._events = events

    def get_events(self, match_id: int) -> list[dict]:
        return self._events


def _foul_ev(minute: float, team: int, pid: int, card: str | None = None,
             ev_id: str | None = None) -> dict:
    card_map = {"yellow": 5, "red": 7}
    ev: dict = {
        "id": ev_id or f"f-{minute}-{pid}",
        "type": {"id": 22, "name": "Foul Committed"},
        "minute": minute, "period": 2 if minute >= 45 else 1,
        "location": [60.0, 40.0],
        "player": {"id": pid}, "team": {"id": team},
    }
    if card:
        ev["foul_committed"] = {"card": {"id": card_map[card]}}
    return ev


def _pass_ev(minute: float, team: int, pid: int, ev_id: str) -> dict:
    return {
        "id": ev_id,
        "type": {"id": 30, "name": "Pass"},
        "minute": minute, "period": 1,
        "location": [50.0, 40.0],
        "player": {"id": pid}, "team": {"id": team},
        "pass": {"end_location": [70.0, 40.0]},
    }


def test_backfill_fouls_adds_only_new_rows(session):
    """Eski demo: pass'lar ingest'li ama foul yok → re-run sadece foul ekler."""
    session.info["tenant_id"] = "t-test"
    now = datetime.now(UTC)
    session.add(models.Tenant(
        id="t-test", slug="t-test", name="T", settings_json="{}",
        active=True, created_at=now,
    ))
    session.add(models.Match(
        sport=football.SPORT_NAME, external_id=8000,
        league_external_id=11, season=2018,
        kickoff=now - timedelta(days=1), status="FT",
        home_team_external_id=11, away_team_external_id=22,
        home_score=1, away_score=1, tenant_id="t-test",
    ))
    session.commit()

    # 1. Tur — eski path: sadece pass ingest et
    pass_events = [
        _pass_ev(10.0, 11, 1, "p1"),
        _pass_ev(20.0, 22, 2, "p2"),
    ]
    src1 = _FakeSource(pass_events)
    r1 = ingest_events_for_match(
        session, source=src1, match_external_id=8000, tenant_id="t-test",
    )
    assert r1.passes == 2
    assert r1.fouls == 0
    session.commit()

    # DB'de pass'lar var, foul yok
    foul_count_pre = session.execute(
        models.EventRow.__table__.select().where(
            models.EventRow.match_external_id == 8000,
            models.EventRow.event_type == "foul",
        )
    ).all()
    assert len(foul_count_pre) == 0

    # 2. Tur — backfill: aynı pass + yeni foul'lar
    mixed = pass_events + [
        _foul_ev(60.0, 22, 100, "yellow", ev_id="f1"),
        _foul_ev(70.0, 22, 101, ev_id="f2"),
    ]
    src2 = _FakeSource(mixed)
    r2 = ingest_events_for_match(
        session, source=src2, match_external_id=8000, tenant_id="t-test",
    )
    # 2 pas zaten var → skip; 2 yeni foul ekleniyor
    assert r2.rows_inserted == 2
    assert r2.rows_skipped >= 2
    assert r2.fouls == 2
    session.commit()

    # DB'de 2 foul var
    foul_count_post = session.execute(
        models.EventRow.__table__.select().where(
            models.EventRow.match_external_id == 8000,
            models.EventRow.event_type == "foul",
        )
    ).all()
    assert len(foul_count_post) == 2
