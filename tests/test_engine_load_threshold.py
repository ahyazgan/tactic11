"""engine.load — threshold parametrikleşmesi tests (PROMPT_BACKEND_LOAD_THRESHOLD).

Mevcut test_engine_load.py + test_engine_load_risk.py'a dokunmadan
yeni keyword arg davranışını doğrular.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.db import models
from app.db.session import get_session
from app.domain import PlayerAppearance
from app.engine.load import compute_player_load
from app.engine.load.compute import HIGH_LOAD_MINUTES_PER_WEEK
from app.sports import football


def _app(player_id, match_id, minutes, days_ago, *, now: datetime):
    return PlayerAppearance(
        sport=football.SPORT_NAME,
        player_external_id=player_id,
        match_external_id=match_id,
        minutes=minutes,
        kickoff=now - timedelta(days=days_ago),
    )


# --------------------------------------------------------------------------- #
# Engine-level: threshold override behavior
# --------------------------------------------------------------------------- #


def test_threshold_override_changes_high_load_flag():
    """Aynı appearance listesi: default eşikte high_load=True, override 600'de False."""
    now = datetime.now(UTC)
    # 6 maç × 90 dk = 540 dk; 14 günde → 270 dk/hafta → default eşikte sınırda True
    apps = [_app(7, i, 90, days_ago=i, now=now) for i in range(1, 7)]

    r_default = compute_player_load(7, apps, window_days=14, now=now)
    assert r_default.value.high_load is True

    r_high = compute_player_load(
        7, apps, window_days=14, now=now,
        threshold_minutes_per_week=600,
    )
    assert r_high.value.high_load is False
    # Aynı veri, sadece bayrak değişti
    assert r_high.value.minutes_per_week == r_default.value.minutes_per_week
    assert r_high.value.matches_in_window == r_default.value.matches_in_window


def test_audit_records_effective_threshold_and_override_flag():
    """Override edildiğinde audit'te effective + default + flag görünür."""
    now = datetime.now(UTC)
    apps = [_app(7, 1, 90, days_ago=1, now=now)]

    r_override = compute_player_load(
        7, apps, window_days=14, now=now,
        threshold_minutes_per_week=500,
    )
    assert r_override.audit.inputs["high_load_threshold_minutes_per_week"] == 500
    assert r_override.audit.inputs["default_threshold_minutes_per_week"] == 270
    assert r_override.audit.inputs["threshold_overridden"] is True

    r_default = compute_player_load(7, apps, window_days=14, now=now)
    assert r_default.audit.inputs["high_load_threshold_minutes_per_week"] == 270
    assert r_default.audit.inputs["default_threshold_minutes_per_week"] == 270
    assert r_default.audit.inputs["threshold_overridden"] is False


def test_backward_compat_old_import_path_still_works():
    """`from app.engine.load.compute import HIGH_LOAD_MINUTES_PER_WEEK` — eski API."""
    assert HIGH_LOAD_MINUTES_PER_WEEK == 270
    assert HIGH_LOAD_MINUTES_PER_WEEK == football.DEFAULT_HIGH_LOAD_MINUTES_PER_WEEK


# --------------------------------------------------------------------------- #
# Endpoint-level: query param validation + behavior
# --------------------------------------------------------------------------- #


@pytest.fixture()
def client(session):
    def _override():
        yield session
    app.dependency_overrides[get_session] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _seed_player_with_appearances(session, player_id: int = 42):
    """6 maç × 90 dk son 14 günde — default eşikte high_load=True."""
    now = datetime.now(UTC)
    session.add(models.Tenant(
        id="t-default", slug="t-default", name="X",
        settings_json="{}", active=True, created_at=now,
    ))
    for i in range(1, 7):
        session.add(models.PlayerAppearance(
            sport=football.SPORT_NAME, tenant_id="t-default",
            player_external_id=player_id,
            match_external_id=100 + i,
            minutes=90,
            kickoff=now - timedelta(days=i),
        ))
    session.commit()


def test_endpoint_threshold_below_minimum_rejected(session, client):
    """ge=60 sınırı → 30 ile 422."""
    _seed_player_with_appearances(session)
    r = client.get("/players/42/load?threshold_minutes_per_week=30")
    assert r.status_code == 422


def test_endpoint_threshold_above_maximum_rejected(session, client):
    """le=900 sınırı → 1000 ile 422."""
    _seed_player_with_appearances(session)
    r = client.get("/players/42/load?threshold_minutes_per_week=1000")
    assert r.status_code == 422


def test_endpoint_default_threshold_high_load_true(session, client):
    """Param yokken default 270 → high_load=True (6 maç × 90 dk = 270/hafta)."""
    _seed_player_with_appearances(session)
    r = client.get("/players/42/load")
    assert r.status_code == 200
    body = r.json()
    assert body["value"]["high_load"] is True


def test_endpoint_high_threshold_high_load_false(session, client):
    """Yüksek override (500) → high_load=False, default ile sonuç farklı."""
    _seed_player_with_appearances(session)
    r = client.get("/players/42/load?threshold_minutes_per_week=500")
    assert r.status_code == 200
    body = r.json()
    assert body["value"]["high_load"] is False
    # Audit override'ı yansıtsın
    assert body["audit"]["inputs"]["high_load_threshold_minutes_per_week"] == 500
    assert body["audit"]["inputs"]["threshold_overridden"] is True
