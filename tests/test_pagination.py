"""Cursor-based pagination — encode/decode + /admin/jobs entegrasyonu (PR D5)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.api.pagination import Cursor, build_next_cursor, decode_cursor
from app.db import models
from app.db.session import get_session


@pytest.fixture()
def client(session):
    def _override():
        yield session

    app.dependency_overrides[get_session] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


# ---- Cursor encode/decode --------------------------------------------------


def test_cursor_encode_decode_roundtrip():
    c1 = Cursor(sort_value="2026-05-27T10:00:00+00:00", row_id=42)
    encoded = c1.encode()
    c2 = decode_cursor(encoded)
    assert c2 == c1


def test_decode_cursor_invalid_returns_none():
    assert decode_cursor("not-base64!!!") is None
    assert decode_cursor("") is None
    assert decode_cursor(None) is None


def test_decode_cursor_invalid_json_returns_none():
    import base64
    raw = base64.urlsafe_b64encode(b"not-json").decode("ascii")
    assert decode_cursor(raw) is None


def test_decode_cursor_wrong_shape_returns_none():
    import base64
    import json
    payload = json.dumps({"sort": "x", "id": 1}).encode("utf-8")
    raw = base64.urlsafe_b64encode(payload).decode("ascii")
    assert decode_cursor(raw) is None  # dict değil list bekliyoruz


def test_build_next_cursor_empty_returns_none():
    assert build_next_cursor([], "started_at") is None


# ---- /admin/jobs entegrasyonu ---------------------------------------------


def _seed_jobs(session, n: int):
    now = datetime.now(UTC)
    for i in range(n):
        session.add(models.JobRun(
            job_name="sync_league",
            args=f'{{"i": {i}}}',
            started_at=now - timedelta(minutes=i),
            ended_at=now - timedelta(minutes=i) + timedelta(seconds=1),
            status="success", attempts=1, error=None,
        ))
    session.flush()


def test_jobs_pagination_returns_next_cursor_when_more_pages(session, client):
    _seed_jobs(session, n=30)
    r = client.get("/admin/jobs?limit=10")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 10
    # Daha fazla satır var → X-Next-Cursor header set
    assert "X-Next-Cursor" in r.headers
    assert len(r.headers["X-Next-Cursor"]) > 0


def test_jobs_pagination_no_next_cursor_on_last_page(session, client):
    _seed_jobs(session, n=5)
    r = client.get("/admin/jobs?limit=10")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 5
    # 5 satır < limit 10 → daha fazla yok
    assert "X-Next-Cursor" not in r.headers


def test_jobs_pagination_cursor_returns_next_page(session, client):
    _seed_jobs(session, n=25)
    r1 = client.get("/admin/jobs?limit=10")
    cursor = r1.headers.get("X-Next-Cursor")
    assert cursor is not None
    r2 = client.get(f"/admin/jobs?limit=10&cursor={cursor}")
    assert r2.status_code == 200
    body2 = r2.json()
    assert len(body2) == 10
    # İki sayfa arasında ID çakışması olmamalı
    ids1 = {row["id"] for row in r1.json()}
    ids2 = {row["id"] for row in body2}
    assert ids1.isdisjoint(ids2)


def test_jobs_invalid_cursor_returns_full_page_no_filter(session, client):
    """Geçersiz cursor → decode None → filtre yok, full page."""
    _seed_jobs(session, n=5)
    r = client.get("/admin/jobs?limit=10&cursor=invalid-base64!!!")
    assert r.status_code == 200
    assert len(r.json()) == 5  # cursor yok sayıldı
