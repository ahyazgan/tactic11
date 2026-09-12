"""ingest_statsbomb_appearances — StatsBomb kadrosu → player_appearances.

Kilitlenen davranış: ilk 11 in=None, değişiklikle giren in=dk, çıkan out=dk,
dakika = çıkış−giriş (maç sonu = son olay dakikası), mevki kodu giren oyuncuya
çıkanınkinden devredilir; ikinci çağrı satır eklemez (idempotent).
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from app.data.ingest.statsbomb_appearance import ingest_statsbomb_appearances
from app.data.loaders.appearances import load_match_appearances
from app.db import models

TEAM_A, TEAM_B, MATCH = 217, 206, 555


def _xi(team: int, players: list[tuple[int, int]]) -> dict:
    return {
        "type": {"id": 35}, "team": {"id": team}, "minute": 0,
        "tactics": {"lineup": [{"player": {"id": p}, "position": {"id": pos}}
                               for p, pos in players]},
    }


def _sub(team: int, minute: int, off: int, on: int) -> dict:
    return {
        "type": {"id": 19}, "team": {"id": team}, "minute": minute,
        "player": {"id": off},
        "substitution": {"replacement": {"id": on}, "outcome": {"name": "Tactical"}},
    }


def _events() -> list[dict]:
    return [
        _xi(TEAM_A, [(1, 1), (2, 5), (3, 13)]),      # GK, DEF, MID
        _xi(TEAM_B, [(50, 1)]),
        _sub(TEAM_A, 60, 3, 4),                        # 4 orta sahanın yerine
        {"type": {"id": 30}, "team": {"id": TEAM_A}, "minute": 93},   # son olay → maç sonu 93
    ]


def test_ingest_writes_windows_positions_and_is_idempotent(session) -> None:
    session.add(models.Tenant(id="t-x", slug="t-x", name="t-x", settings_json="{}",
                                 active=True, created_at=datetime.now(UTC)))
    session.add(models.Match(
        sport="football", external_id=MATCH, league_external_id=11, season=2019,
        kickoff=datetime(2019, 1, 1, tzinfo=UTC), status="FT",
        home_team_external_id=TEAM_A, away_team_external_id=TEAM_B,
        home_score=1, away_score=0, tenant_id="t-x",
    ))
    session.flush()

    rep = ingest_statsbomb_appearances(
        session, match_external_id=MATCH, tenant_id="t-x", events_json=_events(),
    )
    assert (rep.rows_inserted, rep.rows_updated) == (5, 0)
    rows = {r.player_external_id: r for r in session.execute(
        select(models.PlayerAppearance).where(models.PlayerAppearance.match_external_id == MATCH)
    ).scalars()}
    assert rows[1].substituted_in_minute is None and rows[1].minutes == 93
    assert rows[1].position_played == "GK" and rows[2].position_played == "DC"
    assert rows[3].substituted_out_minute == 60 and rows[3].minutes == 60
    assert rows[4].substituted_in_minute == 60 and rows[4].minutes == 33
    assert rows[4].position_played == "MC"            # çıkanın mevkisini devraldı
    assert rows[50].team_external_id == TEAM_B

    rep2 = ingest_statsbomb_appearances(
        session, match_external_id=MATCH, tenant_id="t-x", events_json=_events(),
    )
    assert (rep2.rows_inserted, rep2.rows_updated) == (0, 5)

    apps = load_match_appearances(session, MATCH)
    by_id = {a.player_external_id: a for a in apps}
    assert by_id[4].start_minute == 60.0 and by_id[4].position == "MC"
    assert by_id[3].end_minute == 60.0 and by_id[1].end_minute is None
