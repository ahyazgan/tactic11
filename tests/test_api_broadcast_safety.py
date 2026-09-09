"""Yayın görüntüsü güvenliği: hareketli kamerada sahte taktik sinyal üretilmemeli.

Takip hattı TEK ve SABİT homografi kullanır. Yayın kamerası çevirdiğinde oyuncular
sahada kaymış görünür (ölçüldü: 100 px ≈ 3.6 m) ve şekil sinyali eşikleri 2.5–4 m
olduğu için **kamera hareketi tek başına "geri hat 4 m yükseldi" gibi sinyal
uydurur**. `app/tracking/camera.py` bunu videoda tespit edip karelere
`broadcast_tracking` etiketi koyar; bu test o etiketin motorlara kadar gidip
tam-saha analizini gerçekten kapattığını doğrular.

Kurgu: iki pencere arasında takım şekli BÜYÜK ölçüde değişiyor (kamera kaymış
gibi). Sabit kamera etiketiyle sinyal üretilmeli, yayın etiketiyle ÜRETİLMEMELİ.
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

MATCH, US, THEM = 9840, 9001, 9002

# Pencere 1 → 2 arasında rakip bloğu 20 m "kayıyor" (gerçekte kamera kaymış olabilir)
THEIRS_A = [(78, 30), (78, 42), (78, 54), (78, 66), (62, 35), (62, 50),
            (62, 65), (50, 40), (50, 60), (50, 50), (95, 50)]
THEIRS_B = [(58, 30), (58, 42), (58, 54), (58, 66), (42, 35), (42, 50),
            (42, 65), (30, 40), (30, 60), (30, 50), (75, 50)]
OURS = [(5, 50), (22, 25), (22, 50), (22, 75), (45, 30), (45, 50),
        (45, 70), (66, 35), (66, 50), (66, 65), (70, 45)]


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


def _players(theirs):
    rows = []
    for i, (x, y) in enumerate(OURS):
        rows.append({"player_external_id": 30000 + i, "x": float(x), "y": float(y),
                     "velocity_mps": 1.0, "team_external_id": US,
                     "is_actor": False, "is_keeper": i == 0, "identity_estimated": True})
    for i, (x, y) in enumerate(theirs):
        rows.append({"player_external_id": 30100 + i, "x": float(x), "y": float(y),
                     "velocity_mps": 1.0, "team_external_id": THEM,
                     "is_actor": False, "is_keeper": i == len(theirs) - 1,
                     "identity_estimated": True})
    return rows


def _seed(session, *, source: str):
    now = datetime.now(UTC)
    session.add(models.Tenant(id="t-default", slug="t-default", name="X",
                              settings_json="{}", active=True, created_at=now))
    session.add(models.Match(
        sport=football.SPORT_NAME, external_id=MATCH, league_external_id=0, season=90,
        kickoff=now - timedelta(hours=1), status="LIVE",
        home_team_external_id=US, away_team_external_id=THEM,
        home_score=0, away_score=0, tenant_id="t-default",
    ))
    meta = json.dumps({"source": source, "event_type": "video_sample",
                       "ball_estimated": False,
                       "visible_area": [[0, 0], [100, 0], [100, 100], [0, 100]]})
    for k in range(20):
        minute = k * 0.1
        theirs = THEIRS_A if minute < 1.0 else THEIRS_B
        session.add(models.TrackingFrameRow(
            sport=football.SPORT_NAME, match_external_id=MATCH,
            timestamp=now + timedelta(seconds=k * 6), period=1, minute=minute,
            ball_x=52.0, ball_y=50.0, players_json=json.dumps(_players(theirs)),
            meta_json=meta, created_at=now, tenant_id="t-default",
        ))
    session.commit()


SHAPE_KEYS = {"opponent_block_opened", "opponent_block_tightened",
              "opponent_line_pushed", "opponent_line_dropped", "opponent_narrowed"}


def _live(client, minute: float = 2.0):
    r = client.get(f"/admin/matches/{MATCH}/live-decision"
                   f"?my_team_id={US}&current_minute={minute}")
    assert r.status_code == 200, r.text
    return r.json()


def test_static_camera_label_produces_shape_signals(session, client):
    """Referans: sabit kamerada bu şekil değişimi gerçek sayılır ve sinyal üretir."""
    _seed(session, source="video_tracking")
    body = _live(client)
    keys = {f["key"] for f in body["tracking_signals"]["findings"]}
    assert keys & SHAPE_KEYS, keys


def test_broadcast_label_suppresses_shape_signals(session, client):
    """Asıl koruma: aynı veri yayın etiketiyle gelince şekil sinyali ÜRETİLMEMELİ.

    Aksi halde kameranın kayması "rakip hattı 20 m düştü" diye rapor edilirdi.
    """
    _seed(session, source="broadcast_tracking")
    body = _live(client)
    ts = body["tracking_signals"]
    keys = {f["key"] for f in ts["findings"]}
    assert not (keys & SHAPE_KEYS), f"yayın görüntüsünde şekil sinyali çıktı: {keys}"
    assert "event-çapalı" in (ts.get("note") or ""), ts.get("note")


def test_broadcast_label_closes_the_space_map(session, client):
    """Bölge haritası da tam-saha iddiasıdır — yayında kapalı olmalı."""
    _seed(session, source="broadcast_tracking")
    sm = _live(client)["space_map"]
    assert sm["zones"] == [] and sm["findings"] == []
    assert "event-çapalı" in (sm.get("note") or ""), sm.get("note")


def test_static_camera_space_map_stays_open(session, client):
    _seed(session, source="video_tracking")
    sm = _live(client)["space_map"]
    assert sm["zones"], sm.get("note")
