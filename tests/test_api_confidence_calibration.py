"""Canlı karar panelinde güven kalibrasyonu (uçtan uca).

`score_confidence` bir olasılık değil KANIT GÜCÜ üretir; panelde ve karar
kalitesi ölçümünde ise "bu karar tutar" olasılığı gibi okunuyor. Gerçek veride
ölçüldü: sistem ortalama %84 diyor, gerçekleşme %58.

Mevcut geri besleme bunu düzeltemiyordu — `historical_hit_rate` beş terimden
biri, ağırlığı 0.10 ve nötr 0.5'e göre tartılıyor; skoru en fazla ±0.05
oynatabiliyor. Bu dosya, kalibrasyon katmanının gerçekten devrede olduğunu ve
YETERSİZ geçmişte devreye GİRMEDİĞİNİ korur.
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

MATCH, US, THEM = 9850, 9001, 9002


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
    ours = [(3, 50), (18, 25), (18, 50), (18, 75), (42, 35), (42, 65),
            (70, 12), (72, 20), (76, 26), (74, 50), (70, 55)]
    theirs = [(97, 50), (80, 45), (80, 55), (82, 70), (80, 62),
              (58, 40), (58, 60), (55, 50), (60, 48), (57, 55), (56, 45)]
    for i, (x, y) in enumerate(ours):
        rows.append({"player_external_id": 30000 + i, "x": float(x), "y": float(y),
                     "velocity_mps": 1.0, "team_external_id": US,
                     "is_actor": False, "is_keeper": i == 0, "identity_estimated": True})
    for i, (x, y) in enumerate(theirs):
        rows.append({"player_external_id": 30100 + i, "x": float(x), "y": float(y),
                     "velocity_mps": 1.0, "team_external_id": THEM,
                     "is_actor": False, "is_keeper": i == 0, "identity_estimated": True})
    return rows


def _seed(session, *, history: int, hit_rate: float, confidence: float = 0.9):
    """Kare verisi + `history` kadar ölçülmüş geçmiş karar."""
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
    hits = round(history * hit_rate)
    for i in range(history):
        session.add(models.Decision(
            sport=football.SPORT_NAME, tenant_id="t-default",
            match_external_id=MATCH - 100 - i, team_external_id=US,
            minute=60.0, period=2, decision_type="tactical", notes="geçmiş",
            recommended=True, confidence=confidence, created_at=now,
            outcome="positive" if i < hits else "negative",
            outcome_recorded_at=now,
        ))
    session.commit()


def _confidence(client) -> float | None:
    r = client.get(f"/admin/matches/{MATCH}/live-decision"
                   f"?my_team_id={US}&current_minute=2.0")
    assert r.status_code == 200, r.text
    primary = (r.json().get("context") or {}).get("primary")
    return primary["confidence"] if primary else None


def test_overconfidence_is_corrected_toward_reality(session, client) -> None:
    """Geçmişte %90 güvenle verilen kararların %40'ı tuttuysa, panel %90 demez."""
    _seed(session, history=40, hit_rate=0.40, confidence=0.9)
    conf = _confidence(client)
    assert conf is not None, "öneri üretilmedi — kurgu bozuk"
    assert conf < 0.7, f"fazla güven düzeltilmedi: {conf}"
    assert conf > 0.2, f"aşırı düzeltildi: {conf}"


def test_thin_history_leaves_confidence_untouched(session, client) -> None:
    """Az geçmişten kalibrasyon uydurulmaz — ham skor korunur.

    Aksi halde 3 karardan öğrenilen bir 'oran' tüm paneli çarpıtırdı.
    """
    _seed(session, history=5, hit_rate=0.2, confidence=0.9)
    conf = _confidence(client)
    assert conf is not None
    # Kalibre EDİLSEYDİ %20'lik geçmiş oranına yakın çıkardı. Ham kanıt skoru
    # (bu kurguda ~0.69) korunmuş olmalı; eşik ham değere değil DAVRANIŞA bağlı.
    assert conf > 0.6, f"yetersiz geçmişe rağmen kalibre edildi: {conf}"


def test_confidence_label_follows_the_calibrated_value(session, client) -> None:
    """Etiket de yeniden hesaplanmalı — '%55 ama yüksek' çelişkisi olmasın."""
    _seed(session, history=40, hit_rate=0.35, confidence=0.9)
    r = client.get(f"/admin/matches/{MATCH}/live-decision"
                   f"?my_team_id={US}&current_minute=2.0")
    primary = (r.json().get("context") or {}).get("primary")
    assert primary is not None
    assert primary["confidence"] < 0.66
    assert primary["confidence_label"] in ("orta", "düşük"), primary["confidence_label"]
