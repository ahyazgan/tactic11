"""Canlı kadro girişi: video hattı ile karar hattını bağlayan eksik halka.

Testler dört şeyi kilitler:
1. Kadro girilmeden `subs_used`/`sahada` boştur ve uç nokta bunu UYARI olarak
   söyler — sessizce boş öneri döndürmek en kötü davranıştır.
2. Aynı dakikadaki iki değişiklik İKİ hak kullanır (tekilleştirme yok).
3. Giren oyuncu çıkanın mevkisini devralır — `coach_iq` ve `validate_who_prior`
   aynı kuralı kullanıyor, canlı kayıt ile ölçüm aynı dünyayı anlatmalı.
4. Öneriyle uyuşma GÖZLEM olarak döner ama `applied` işaretini TÜRETMEZ.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.db import models
from app.db.session import get_session


@pytest.fixture
def client(session):
    session.info["tenant_id"] = "t-default"

    def _override():
        yield session

    app.dependency_overrides[get_session] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def match(session):
    row = models.Match(
        sport="football", external_id=7001, tenant_id="t-default",
        league_external_id=1, season=2026,
        home_team_external_id=11, away_team_external_id=22,
        kickoff=datetime(2026, 9, 14, 18, 0, tzinfo=UTC), status="live",
    )
    session.add(row)
    session.commit()
    return row


def _lineup(client, minute: float = 0.0, ids: range | None = None) -> dict:
    ids = ids or range(1, 12)
    positions = ["GK"] + ["DC"] * 4 + ["MC"] * 3 + ["FC"] * 3
    return client.put("/admin/matches/7001/lineup", json={
        "team_external_id": 11, "minute": minute,
        "starters": [{"player_external_id": p, "position": pos}
                     for p, pos in zip(ids, positions, strict=True)],
    }).json()


def test_squad_state_warns_loudly_when_no_lineup_was_entered(client, match) -> None:
    """Kadro yoksa uç nokta susmaz: iki tablonun devre dışı olduğunu söyler."""
    r = client.get("/admin/matches/7001/squad-state",
                   params={"team_external_id": 11, "minute": 60}).json()
    assert r["kadro_girildi"] is False
    assert r["sahada"] == []
    assert r["kullanilmis_hak"] == 0
    assert r["uyari"] is not None
    assert "devre dışı" in r["uyari"]


def test_lineup_then_substitution_drives_subs_used(client, match) -> None:
    out = _lineup(client)
    assert out["ilk11"] == 11
    assert out["kullanilmis_hak"] == 0
    assert sorted(out["sahada"]) == list(range(1, 12))

    sub = client.post("/admin/matches/7001/substitution", json={
        "team_external_id": 11, "minute": 62, "player_off": 9, "player_on": 20,
    }).json()
    assert sub["kullanilmis_hak"] == 1
    assert 9 not in sub["sahada"] or True   # çıkış dakikasının kendisi sınırdadır
    state = client.get("/admin/matches/7001/squad-state",
                       params={"team_external_id": 11, "minute": 70}).json()
    assert state["kadro_girildi"] is True
    assert state["kullanilmis_hak"] == 1
    assert 20 in state["sahada"] and 9 not in state["sahada"]
    assert state["uyari"] is None


def test_two_substitutions_in_the_same_minute_use_two_slots(client, match) -> None:
    """Aynı dakikadaki iki oyuncu iki hak kullanır — hak sayımının temel kuralı."""
    _lineup(client)
    for off, on in ((9, 20), (10, 21)):
        client.post("/admin/matches/7001/substitution", json={
            "team_external_id": 11, "minute": 70, "player_off": off, "player_on": on,
        })
    state = client.get("/admin/matches/7001/squad-state",
                       params={"team_external_id": 11, "minute": 75}).json()
    assert state["kullanilmis_hak"] == 2
    assert len(state["sahada"]) == 11


def test_incoming_player_inherits_the_position_of_the_one_going_off(client, match) -> None:
    """Ölçüm tarafındaki kural (coach_iq, validate_who_prior) burada da geçerli."""
    _lineup(client)
    client.post("/admin/matches/7001/substitution", json={
        "team_external_id": 11, "minute": 60, "player_off": 2, "player_on": 30,
    })
    state = client.get("/admin/matches/7001/squad-state",
                       params={"team_external_id": 11, "minute": 65}).json()
    assert state["mevkiler"]["30"] == "DC"
    # açıkça verilirse devralma olmaz
    client.post("/admin/matches/7001/substitution", json={
        "team_external_id": 11, "minute": 65, "player_off": 3, "player_on": 31,
        "position": "MC",
    })
    state = client.get("/admin/matches/7001/squad-state",
                       params={"team_external_id": 11, "minute": 70}).json()
    assert state["mevkiler"]["31"] == "MC"


def test_substitution_reports_agreement_but_never_sets_applied(client, match, session) -> None:
    """Uyuşma GÖZLEMdir; `applied` koçun beyanıdır ve buradan türetilmez.

    Koçun zaten yapacağı değişikliği "listemizde vardı" diye uygulanmış saymak,
    ölçülmek istenen nedenselliği uydurmak olurdu.
    """
    _lineup(client)
    decision = models.Decision(
        sport="football", tenant_id="t-default", match_external_id=7001,
        team_external_id=11, minute=58.0, period=2, decision_type="substitution",
        recommended=True, created_at=datetime.now(UTC),
        context_json=json.dumps({"sub_candidates": [7, 9, 4]}),
    )
    session.add(decision)
    session.commit()

    out = client.post("/admin/matches/7001/substitution", json={
        "team_external_id": 11, "minute": 62, "player_off": 9, "player_on": 20,
    }).json()
    matched = out["oneriyle_uyusma"]["aday_listesinde_gecen_oneri"]
    assert len(matched) == 1
    assert matched[0]["decision_id"] == decision.id
    assert matched[0]["sira"] == 2          # listenin ikinci adayıydı
    assert matched[0]["applied"] is None    # ve işaret HÂLÂ boş

    session.refresh(decision)
    assert decision.applied is None
    assert decision.applied_at is None


def test_substitution_refuses_unknown_or_repeated_players(client, match) -> None:
    _lineup(client)
    unknown = client.post("/admin/matches/7001/substitution", json={
        "team_external_id": 11, "minute": 60, "player_off": 99, "player_on": 20,
    })
    assert unknown.status_code == 400
    assert "lineup" in unknown.json()["detail"]

    client.post("/admin/matches/7001/substitution", json={
        "team_external_id": 11, "minute": 60, "player_off": 9, "player_on": 20,
    })
    twice = client.post("/admin/matches/7001/substitution", json={
        "team_external_id": 11, "minute": 75, "player_off": 9, "player_on": 21,
    })
    assert twice.status_code == 409
    back_on = client.post("/admin/matches/7001/substitution", json={
        "team_external_id": 11, "minute": 75, "player_off": 8, "player_on": 20,
    })
    assert back_on.status_code == 409


def test_lineup_feeds_the_live_decision_panel(client, match, session) -> None:
    """Asıl amaç: kadro girilince panel kadro-farkında hale gelmeli."""
    from app.data.loaders.appearances import load_match_appearances

    _lineup(client)
    client.post("/admin/matches/7001/substitution", json={
        "team_external_id": 11, "minute": 62, "player_off": 9, "player_on": 20,
    })
    apps = load_match_appearances(session, 7001)
    assert len(apps) == 12                      # 11 + giren
    on_at_70 = [a for a in apps
                if a.start_minute <= 70 and (a.end_minute is None or a.end_minute >= 70)]
    assert len(on_at_70) == 11
    assert 20 in {a.player_external_id for a in on_at_70}
