"""Kulüp senaryosu: event beslemesi YOK, yalnız video kareleri var.

Bu yol daha önce sessizce boş dönüyordu (`decisions/live` event yoksa erken
çıkıyordu) ve `_safe_assign`'ın geniş except'i bir ImportError'ı yutunca
tracking sinyalleri hiç üretilmiyordu — ikisi de testsizdi. Burası o zinciri
uçtan uca tutar: kare → şekil farkı → sinyal → context_engine birincil kararı.

Kurgu: rakip iki pencere arasında 30 m daralıyor → "kanatlar boş, oyunu genişlet".
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

MATCH, US, THEM = 9820, 9001, 9002
# Saha metre cinsinden (105 × 68) — players_json gerçek video ingest'iyle aynı biçim
OUR_XY = [(20.0 + i * 4.0, 14.0 + i * 4.0) for i in range(11)]
THEIR_WIDE = [(60.0 + (i % 3) * 5.0, 4.0 + i * 6.0) for i in range(11)]     # y 4..64 → ~60 m
THEIR_NARROW = [(60.0 + (i % 3) * 5.0, 19.0 + i * 3.0) for i in range(11)]  # y 19..49 → ~30 m


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


def _players(their_xy):
    rows = []
    for i, (x, y) in enumerate(OUR_XY):
        rows.append({"player_external_id": 30000 + i, "x": x, "y": y, "velocity_mps": 1.0,
                     "team_external_id": US, "is_actor": False, "is_keeper": i == 0,
                     "identity_estimated": True})
    for i, (x, y) in enumerate(their_xy):
        rows.append({"player_external_id": 30100 + i, "x": x, "y": y, "velocity_mps": 1.0,
                     "team_external_id": THEM, "is_actor": False, "is_keeper": i == 0,
                     "identity_estimated": True})
    return rows


def _seed(session, *, frames: bool = True):
    now = datetime.now(UTC)
    session.add(models.Tenant(id="t-default", slug="t-default", name="X",
                              settings_json="{}", active=True, created_at=now))
    session.add(models.Match(
        sport=football.SPORT_NAME, external_id=MATCH, league_external_id=0, season=90,
        kickoff=now - timedelta(hours=1), status="LIVE",
        home_team_external_id=US, away_team_external_id=THEM,
        home_score=0, away_score=0, tenant_id="t-default",
    ))
    if frames:
        meta = json.dumps({"source": "video_tracking", "event_type": "video_sample",
                           "ball_estimated": False,
                           "visible_area": [[0, 0], [100, 0], [100, 100], [0, 100]]})
        # Pencere 1 (0.0–0.9 dk): rakip geniş · Pencere 2 (1.0–1.9 dk): rakip dar
        for k in range(20):
            minute = k * 0.1
            their = THEIR_WIDE if minute < 1.0 else THEIR_NARROW
            session.add(models.TrackingFrameRow(
                sport=football.SPORT_NAME, match_external_id=MATCH,
                timestamp=now + timedelta(seconds=k * 6), period=1, minute=minute,
                ball_x=52.0, ball_y=34.0,
                players_json=json.dumps(_players(their)),
                meta_json=meta, created_at=now, tenant_id="t-default",
            ))
    session.commit()


def test_video_only_match_still_produces_a_coaching_decision(session, client):
    _seed(session)
    r = client.get(f"/admin/matches/{MATCH}/live-decision?my_team_id={US}&current_minute=2.0")
    assert r.status_code == 200, r.text
    body = r.json()

    # Event yok ama panel çalışıyor — erken dönüş yok
    assert body["events_loaded"] == 0
    assert "Event ingest yok" in body["note"]

    ts = body["tracking_signals"]
    assert ts["frames_used"] > 0 and ts["players_seen"] >= 8.0
    keys = [f["key"] for f in ts["findings"]]
    assert "opponent_narrowed" in keys, keys
    narrowed = next(f for f in ts["findings"] if f["key"] == "opponent_narrowed")
    assert "genişlet" in narrowed["headline"]

    # Sinyal karar katmanına ulaştı mı — asıl mesele bu
    ctx = body["context"]
    assert ctx["primary"]["headline"] == narrowed["headline"]
    assert "ŞİMDİ:" in ctx["one_liner"]


def test_no_frames_and_no_events_reports_instead_of_pretending(session, client):
    _seed(session, frames=False)
    r = client.get(f"/admin/matches/{MATCH}/live-decision?my_team_id={US}&current_minute=2.0")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["events_loaded"] == 0
    # Kare de yoksa uydurma karar üretilmez
    assert "tracking_signals" not in body or not body["tracking_signals"].get("findings")
    assert body.get("context") is None or not body["context"].get("primary")
