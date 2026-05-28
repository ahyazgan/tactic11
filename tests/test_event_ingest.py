"""Event ingest pipeline — StatsBomb event'lerini DB'ye yazma.

Test stratejisi: synthetic event JSON ile StatsBombOpen._fetch_json monkeypatch;
ingest_events_for_match çağrısı DB'ye EventRow yazsın, ikinci çağrı idempotent
(aynı source_event_id varsa skip).
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.data.ingest.event import ingest_events_for_match
from app.data.sources.statsbomb_open import StatsBombOpen
from app.db import models
from app.sports import football

# --------------------------------------------------------------------------- #
# Sample events — StatsBomb real-shape (4 tip karışık)
# --------------------------------------------------------------------------- #

SAMPLE_EVENTS: list[dict] = [
    {
        "id": "sb-pass-1", "minute": 5, "period": 1,
        "type": {"id": 30, "name": "Pass"},
        "team": {"id": 11}, "player": {"id": 5503},
        "location": [40, 30],
        "pass": {"end_location": [80, 35], "type": {"id": 0, "name": "Open Play"}},
        "possession": 42,
    },
    {
        "id": "sb-carry-1", "minute": 6, "period": 1,
        "type": {"id": 43, "name": "Carry"},
        "team": {"id": 11}, "player": {"id": 5503},
        "location": [50, 40],
        "carry": {"end_location": [70, 45]},
        "possession": 42,
    },
    {
        "id": "sb-shot-1", "minute": 25, "period": 1,
        "type": {"id": 16, "name": "Shot"},
        "team": {"id": 11}, "player": {"id": 7000},
        "location": [105, 40],
        "shot": {
            "outcome": {"id": 97, "name": "Goal"},
            "body_part": {"id": 40, "name": "Right Foot"},
            "type": {"id": 87, "name": "Open Play"},
            "statsbomb_xg": 0.45,
        },
    },
    {
        "id": "sb-def-1", "minute": 30, "period": 1,
        "type": {"id": 10, "name": "Interception"},
        "team": {"id": 11}, "player": {"id": 5601},
        "location": [60, 40],
        "possession": 50,
    },
    # Filtered out (not a relevant type)
    {
        "id": "sb-other-1", "minute": 7, "period": 1,
        "type": {"id": 35, "name": "Starting XI"},
    },
]


def _seed_tenant(session, tenant_id: str = "t-default"):
    now = datetime.now(UTC)
    session.add(models.Tenant(
        id=tenant_id, slug=tenant_id, name="X",
        settings_json="{}", active=True, created_at=now,
    ))
    session.flush()


def _make_source(monkeypatch, events) -> StatsBombOpen:
    src = StatsBombOpen()
    monkeypatch.setattr(src, "_fetch_json", lambda path: events)
    return src


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #


def test_ingest_inserts_all_event_types(session, monkeypatch):
    _seed_tenant(session)
    src = _make_source(monkeypatch, SAMPLE_EVENTS)
    report = ingest_events_for_match(
        session, src, match_external_id=99, tenant_id="t-default",
    )
    session.commit()

    rows = session.query(models.EventRow).all()
    assert len(rows) == report.rows_inserted
    types = {r.event_type for r in rows}
    assert types == {"pass", "carry", "shot", "defensive_action"}
    assert report.shots == 1
    assert report.passes == 1
    assert report.carries == 1
    assert report.defensive_actions == 1
    assert report.rows_skipped == 0


def test_ingest_idempotent_second_call_skips(session, monkeypatch):
    _seed_tenant(session)
    src = _make_source(monkeypatch, SAMPLE_EVENTS)
    r1 = ingest_events_for_match(
        session, src, match_external_id=99, tenant_id="t-default",
    )
    session.commit()
    r2 = ingest_events_for_match(
        session, src, match_external_id=99, tenant_id="t-default",
    )
    session.commit()

    assert r1.rows_inserted == 4
    assert r2.rows_inserted == 0
    assert r2.rows_skipped == 4
    # DB'de hâlâ 4 satır olmalı
    assert session.query(models.EventRow).count() == 4


def test_ingest_writes_correct_shot_fields(session, monkeypatch):
    _seed_tenant(session)
    src = _make_source(monkeypatch, SAMPLE_EVENTS)
    ingest_events_for_match(
        session, src, match_external_id=99, tenant_id="t-default",
    )
    session.commit()

    shot = session.query(models.EventRow).filter_by(event_type="shot").one()
    assert shot.player_external_id == 7000
    assert shot.is_goal is True
    assert shot.outcome == "goal"
    assert shot.tenant_id == "t-default"
    assert shot.match_external_id == 99
    assert shot.source == "statsbomb_open"


def test_ingest_writes_correct_pass_fields(session, monkeypatch):
    _seed_tenant(session)
    src = _make_source(monkeypatch, SAMPLE_EVENTS)
    ingest_events_for_match(
        session, src, match_external_id=99, tenant_id="t-default",
    )
    session.commit()

    p = session.query(models.EventRow).filter_by(event_type="pass").one()
    assert p.player_external_id == 5503
    assert p.team_external_id == 11
    assert p.outcome == "completed"
    assert p.possession_id == 42
    assert p.start_x is not None and p.end_x is not None


def test_ingest_tenant_isolation(session, monkeypatch):
    """İki tenant ayrı satırlar — aynı match_id, aynı source_event_id, farklı tenant_id."""
    _seed_tenant(session, tenant_id="t-a")
    _seed_tenant(session, tenant_id="t-b")
    src = _make_source(monkeypatch, SAMPLE_EVENTS)

    ingest_events_for_match(
        session, src, match_external_id=99, tenant_id="t-a",
    )
    session.commit()
    ingest_events_for_match(
        session, src, match_external_id=99, tenant_id="t-b",
    )
    session.commit()

    rows_a = session.query(models.EventRow).filter_by(tenant_id="t-a").count()
    rows_b = session.query(models.EventRow).filter_by(tenant_id="t-b").count()
    assert rows_a == 4
    assert rows_b == 4
    # Toplam 8 — unique key (tenant_id, sport, source, source_event_id) ayrı tutuyor
    assert session.query(models.EventRow).count() == 8


def test_ingest_empty_events_safe(session, monkeypatch):
    _seed_tenant(session)
    src = _make_source(monkeypatch, [])
    report = ingest_events_for_match(
        session, src, match_external_id=99, tenant_id="t-default",
    )
    session.commit()
    assert report.rows_inserted == 0
    assert report.rows_skipped == 0
    assert session.query(models.EventRow).count() == 0


def test_ingest_sets_sport_and_source(session, monkeypatch):
    _seed_tenant(session)
    src = _make_source(monkeypatch, SAMPLE_EVENTS)
    ingest_events_for_match(
        session, src, match_external_id=99, tenant_id="t-default",
    )
    session.commit()

    rows = session.query(models.EventRow).all()
    assert all(r.sport == football.SPORT_NAME for r in rows)
    assert all(r.source == "statsbomb_open" for r in rows)
    assert all(r.created_at is not None for r in rows)


def test_ingest_partial_idempotency_inserts_new_only(session, monkeypatch):
    """İlk ingest 2 event; sonra 4 event geldi → 2 yeni eklenmeli."""
    _seed_tenant(session)
    # İlk: sadece pass + carry
    first_batch = SAMPLE_EVENTS[:2]
    src1 = _make_source(monkeypatch, first_batch)
    r1 = ingest_events_for_match(
        session, src1, match_external_id=99, tenant_id="t-default",
    )
    session.commit()
    assert r1.rows_inserted == 2

    # İkinci: tüm 4 event (2 eski + 2 yeni)
    src2 = _make_source(monkeypatch, SAMPLE_EVENTS)
    r2 = ingest_events_for_match(
        session, src2, match_external_id=99, tenant_id="t-default",
    )
    session.commit()
    assert r2.rows_inserted == 2  # shot + defensive
    assert r2.rows_skipped == 2   # pass + carry
    assert session.query(models.EventRow).count() == 4
