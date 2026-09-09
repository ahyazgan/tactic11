"""Canlı karar panelinde boşluk haritası: bölge → sinyal → koç kararı.

`test_api_live_decision_tracking_only` şekil DEĞİŞİMİ zincirini korur; bu dosya
YER zincirini korur: tam saha gören kamerada "sol kanat hücum üçte birinde
üstünlük var" bulgusu context_engine'e girip karara dönüşüyor mu.

Kurgu bilinçli olarak tam sahadır (kaleciler dahil): boşluk haritası hücum yönü
çıkarılamazsa çalışmaz, yön de ancak kaleciler/derinlik farkı görününce çıkar.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.db import models
from app.db.session import get_session
from app.sports import football

MATCH, US, THEM = 9830, 9001, 9002
# Bizim kalemiz x=0 → x artan yöne hücum. Sol kanat hücum üçte birinde kalabalığız.
OUR = [(3, 50), (18, 25), (18, 50), (18, 75), (42, 35), (42, 65),
       (70, 12), (72, 20), (76, 26), (74, 50), (70, 55)]
THEIRS = [(97, 50), (80, 45), (80, 55), (82, 70), (80, 62),
          (58, 40), (58, 60), (55, 50), (60, 48), (57, 55), (56, 45)]


@pytest.fixture()
def client(session):
    session.info["tenant_id"] = "t-default"

    def _override():
        yield session
    app.dependency_overrides[get_session] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _players():
    rows = []
    for i, (x, y) in enumerate(OUR):
        rows.append({"player_external_id": 30000 + i, "x": float(x), "y": float(y),
                     "velocity_mps": 1.0, "team_external_id": US,
                     "is_actor": False, "is_keeper": i == 0, "identity_estimated": True})
    for i, (x, y) in enumerate(THEIRS):
        rows.append({"player_external_id": 30100 + i, "x": float(x), "y": float(y),
                     "velocity_mps": 1.0, "team_external_id": THEM,
                     "is_actor": False, "is_keeper": i == 0, "identity_estimated": True})
    return rows


def _seed(session):
    now = datetime.now(UTC)
    session.add(models.Tenant(id="t-default", slug="t-default", name="X",
                              settings_json="{}", active=True, created_at=now))
    session.add(models.Match(
        sport=football.SPORT_NAME, external_id=MATCH, league_external_id=0, season=90,
        kickoff=now - timedelta(hours=1), status="LIVE",
        home_team_external_id=US, away_team_external_id=THEM,
        home_score=0, away_score=0, tenant_id="t-default",
    ))
    meta = json.dumps({"source": "video_tracking", "event_type": "video_sample",
                       "ball_estimated": False,
                       "visible_area": [[0, 0], [100, 0], [100, 100], [0, 100]]})
    for k in range(20):
        session.add(models.TrackingFrameRow(
            sport=football.SPORT_NAME, match_external_id=MATCH,
            timestamp=now + timedelta(seconds=k * 6), period=1, minute=k * 0.1,
            ball_x=60.0, ball_y=30.0, players_json=json.dumps(_players()),
            meta_json=meta, created_at=now, tenant_id="t-default",
        ))
    session.commit()


def test_space_map_reaches_the_coach_decision(session, client):
    _seed(session)
    r = client.get(f"/admin/matches/{MATCH}/live-decision?my_team_id={US}&current_minute=2.0")
    assert r.status_code == 200, r.text
    body = r.json()

    sm = body["space_map"]
    assert sm["note"] is None, sm["note"]
    assert sm["attack_direction"] == 1 and sm["direction_method"] == "keeper"
    assert sm["pitch_coverage"] >= 0.9

    # Sol kanat hücum üçte biri: bizde 3 (70,12) (72,20) (76,26), rakipte 0
    cell = next(z for z in sm["zones"] if z["lane"] == "sol" and z["third"] == "hücum")
    assert cell["ours"] == 3.0 and cell["theirs"] == 0.0

    keys = [f["key"] for f in sm["findings"]]
    assert "overload_sol_hücum" in keys, keys

    # Zincirin asıl noktası: bulgu karar katmanına ulaştı mı
    ctx = body["context"]
    headlines = [f["headline"] for f in sm["findings"]]
    assert ctx["primary"]["headline"] in headlines
    assert "ŞİMDİ:" in ctx["one_liner"]


def test_space_map_absent_for_matches_without_frames(session, client):
    """Kare yoksa alan hiç görünmemeli — event-only maçlar bozulmasın."""
    now = datetime.now(UTC)
    session.add(models.Tenant(id="t-default", slug="t-default", name="X",
                              settings_json="{}", active=True, created_at=now))
    session.add(models.Match(
        sport=football.SPORT_NAME, external_id=MATCH, league_external_id=0, season=90,
        kickoff=now - timedelta(hours=1), status="LIVE",
        home_team_external_id=US, away_team_external_id=THEM,
        home_score=0, away_score=0, tenant_id="t-default",
    ))
    session.commit()
    body = client.get(
        f"/admin/matches/{MATCH}/live-decision?my_team_id={US}&current_minute=2.0"
    ).json()
    assert "space_map" not in body
