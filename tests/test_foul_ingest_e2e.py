"""StatsBomb foul parser + ingest + loader entegrasyon testleri.

Veri akışı: StatsBomb event JSON → event_to_foul → EventRow (event_type='foul')
→ load_match_events → FoulEvent listesi → foul_pressure engine.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.data.ingest.event import _foul_to_row, ingest_events_for_match
from app.data.loaders import load_match_events
from app.data.sources.statsbomb_event_parser import event_to_foul, is_foul_event
from app.db import models
from app.engine.foul_pressure import compute_foul_pressure
from app.sports import football

# --------------------------------------------------------------------------- #
# Parser — Foul Committed + Bad Behaviour + kart tespiti
# --------------------------------------------------------------------------- #


def test_is_foul_event_type_22():
    """type.id=22 (Foul Committed) → True."""
    assert is_foul_event({"type": {"id": 22, "name": "Foul Committed"}})


def test_is_foul_event_type_24_bad_behaviour():
    """type.id=24 (Bad Behaviour) → True (kart için)."""
    assert is_foul_event({"type": {"id": 24, "name": "Bad Behaviour"}})


def test_is_foul_event_pass_not_foul():
    """type=Pass → foul değil."""
    assert not is_foul_event({"type": {"id": 30}})


def test_event_to_foul_basic_no_card():
    """Lokasyon var + kart yok → foul, card=None."""
    ev = {
        "type": {"id": 22}, "minute": 60, "period": 2,
        "location": [60.0, 40.0],  # StatsBomb 120x80 koord
        "player": {"id": 99, "name": "Joe"},
        "team": {"id": 11, "name": "Team A"},
        "possession": 42,
    }
    f = event_to_foul(ev, match_id=9000)
    assert f is not None
    assert f.player_external_id == 99
    assert f.team_external_id == 11
    assert f.minute == 60.0
    assert f.card is None
    # 60/120 = 0.5 → 50.0 normalize
    assert f.x == 50.0
    assert f.y == 50.0


def test_event_to_foul_with_yellow_card():
    """foul_committed.card.id=5 → yellow."""
    ev = {
        "type": {"id": 22}, "minute": 70, "period": 2,
        "location": [60.0, 40.0],
        "player": {"id": 99}, "team": {"id": 11},
        "foul_committed": {"card": {"id": 5, "name": "Yellow Card"}},
    }
    f = event_to_foul(ev, match_id=9000)
    assert f is not None
    assert f.card == "yellow"
    assert f.advantage_played is False


def test_event_to_foul_with_red_card():
    """card.id=7 → red."""
    ev = {
        "type": {"id": 22}, "minute": 80, "period": 2,
        "location": [60.0, 40.0],
        "player": {"id": 99}, "team": {"id": 11},
        "foul_committed": {"card": {"id": 7, "name": "Red Card"}},
    }
    f = event_to_foul(ev, match_id=9000)
    assert f is not None
    assert f.card == "red"


def test_event_to_foul_advantage_played():
    """foul_committed.advantage=True."""
    ev = {
        "type": {"id": 22}, "minute": 50, "period": 2,
        "location": [60.0, 40.0],
        "player": {"id": 99}, "team": {"id": 11},
        "foul_committed": {"advantage": True},
    }
    f = event_to_foul(ev, match_id=9000)
    assert f is not None
    assert f.advantage_played is True


def test_event_to_foul_bad_behaviour_no_location_uses_default():
    """Bad Behaviour event'inde location yok → default (50, 50)."""
    ev = {
        "type": {"id": 24}, "minute": 90, "period": 2,
        # location yok
        "player": {"id": 99}, "team": {"id": 11},
        "bad_behaviour": {"card": {"id": 5, "name": "Yellow Card"}},
    }
    f = event_to_foul(ev, match_id=9000)
    assert f is not None
    assert f.card == "yellow"
    assert f.x == 50.0 and f.y == 50.0


def test_event_to_foul_missing_player_returns_none():
    ev = {
        "type": {"id": 22}, "minute": 70,
        "location": [60.0, 40.0],
        "player": {}, "team": {},  # player.id=0, team.id=0
    }
    assert event_to_foul(ev, match_id=9000) is None


# --------------------------------------------------------------------------- #
# Ingest — _foul_to_row + ingest_events_for_match (mocked source)
# --------------------------------------------------------------------------- #


class _FakeSource:
    """Minimal source döndüren stub — sadece get_events çağrılır."""
    def __init__(self, events: list[dict]):
        self._events = events

    def get_events(self, match_id: int) -> list[dict]:
        return self._events


def _make_foul_event(
    *, minute: float, team_id: int, player_id: int, card: str | None = None,
    ev_id: str | None = None,
) -> dict:
    card_map = {"yellow": 5, "second_yellow": 6, "red": 7}
    ev: dict = {
        "id": ev_id or f"f-{minute}-{player_id}",
        "type": {"id": 22, "name": "Foul Committed"},
        "minute": minute, "period": 2 if minute >= 45 else 1,
        "location": [60.0, 40.0],
        "player": {"id": player_id}, "team": {"id": team_id},
    }
    if card:
        ev["foul_committed"] = {"card": {"id": card_map[card]}}
    return ev


@pytest.fixture()
def seeded_match(session):
    session.info["tenant_id"] = "t-test"
    now = datetime.now(UTC)
    session.add(models.Tenant(
        id="t-test", slug="t-test", name="T", settings_json="{}",
        active=True, created_at=now,
    ))
    session.add(models.Match(
        sport=football.SPORT_NAME, external_id=9000,
        league_external_id=11, season=2018,
        kickoff=now - timedelta(days=1), status="FT",
        home_team_external_id=11, away_team_external_id=22,
        home_score=1, away_score=1, tenant_id="t-test",
    ))
    session.commit()
    return session


def test_ingest_writes_foul_rows(seeded_match):
    """3 foul event ingest → 3 EventRow (event_type='foul')."""
    events = [
        _make_foul_event(minute=10, team_id=22, player_id=100),
        _make_foul_event(minute=30, team_id=11, player_id=200, card="yellow"),
        _make_foul_event(minute=80, team_id=22, player_id=300, card="red"),
    ]
    src = _FakeSource(events)
    report = ingest_events_for_match(
        seeded_match, source=src, match_external_id=9000, tenant_id="t-test",
    )
    assert report.fouls == 3
    assert report.rows_inserted == 3
    # DB'den çek
    loaded = load_match_events(seeded_match, 9000)
    assert len(loaded.fouls) == 3
    cards = {f.card for f in loaded.fouls}
    assert cards == {None, "yellow", "red"}


def test_ingest_idempotent_skips_existing(seeded_match):
    """İkinci kez çağrı → 0 yeni satır (aynı source_event_id)."""
    events = [_make_foul_event(minute=10, team_id=22, player_id=100, ev_id="f1")]
    src = _FakeSource(events)
    r1 = ingest_events_for_match(
        seeded_match, source=src, match_external_id=9000, tenant_id="t-test",
    )
    r2 = ingest_events_for_match(
        seeded_match, source=src, match_external_id=9000, tenant_id="t-test",
    )
    assert r1.rows_inserted == 1
    assert r2.rows_inserted == 0
    assert r2.rows_skipped >= 1


def test_foul_to_row_card_in_outcome(seeded_match):
    """_foul_to_row: yellow → outcome='yellow', advantage → pattern='advantage'."""
    from app.domain import FoulEvent
    f = FoulEvent(
        sport="football", match_external_id=9000,
        player_external_id=99, team_external_id=11,
        minute=70.0, period=2, x=50.0, y=50.0,
        card="yellow", advantage_played=True,
    )
    row = _foul_to_row(f, "t-test", "f-99", datetime.now(UTC))
    assert row.event_type == "foul"
    assert row.outcome == "yellow"
    assert row.pattern == "advantage"


# --------------------------------------------------------------------------- #
# End-to-end: ingest → loader → engine
# --------------------------------------------------------------------------- #


def test_engine_consumes_loaded_fouls(seeded_match):
    """Ingest sonrası foul_pressure engine FoulEvent listesini doğrudan tüketir."""
    # 5 rakip + 2 bizim faul, 1 sarı bizimkilerden
    events = [
        _make_foul_event(minute=62, team_id=22, player_id=100, ev_id="o1"),
        _make_foul_event(minute=64, team_id=22, player_id=101, ev_id="o2"),
        _make_foul_event(minute=66, team_id=22, player_id=100, ev_id="o3"),
        _make_foul_event(minute=68, team_id=22, player_id=102, ev_id="o4"),
        _make_foul_event(minute=70, team_id=22, player_id=100, ev_id="o5"),
        _make_foul_event(minute=60, team_id=11, player_id=200,
                          card="yellow", ev_id="u1"),
        _make_foul_event(minute=65, team_id=11, player_id=200, ev_id="u2"),
    ]
    src = _FakeSource(events)
    ingest_events_for_match(
        seeded_match, source=src, match_external_id=9000, tenant_id="t-test",
    )
    loaded = load_match_events(seeded_match, 9000)
    assert len(loaded.fouls) == 7
    result = compute_foul_pressure(
        team_external_id=11, opponent_external_id=22,
        foul_events=loaded.fouls, current_minute=75.0, window_min=15.0,
    ).value
    # Rakip 5 faul / 15 dk → 3.33/10dk → tactical_fouling_alert
    assert result.tactical_fouling_alert is True
    # 1 sarı toplam → low (eşik moderate=4)
    assert result.referee_card_pressure == "low"


def test_engine_auto_counts_yellows_from_events():
    """Payload mode: total_yellows_match verilmez → event'lerden sayılır."""
    from app.domain import FoulEvent
    fouls = [
        FoulEvent(sport="football", match_external_id=1, player_external_id=p,
                  team_external_id=t, minute=60.0, period=2,
                  x=50.0, y=50.0, card="yellow")
        for p, t in [(1, 11), (2, 11), (3, 22), (4, 22), (5, 22), (6, 22), (7, 22)]
    ]
    r = compute_foul_pressure(
        team_external_id=11, opponent_external_id=22,
        foul_events=fouls, current_minute=70.0, window_min=15.0,
    ).value
    # 7 sarı toplam → high
    assert r.total_yellows_match == 7
    assert r.referee_card_pressure == "high"
    # Bizim 2 oyuncu sarı → kart riski flag (1-2 faul + sarı = warning)
    assert any(f.has_yellow for f in r.player_flags)
