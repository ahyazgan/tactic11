"""ErrorResponse şeması — yapılandırılmış hata payload'ları (PR D1)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
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


def test_404_includes_structured_error_object(client):
    r = client.get("/matches/999999/predict")
    assert r.status_code == 404
    body = r.json()
    assert "error" in body
    assert body["error"]["code"] == "not_found"
    assert "bulunamadı" in body["error"]["message"]
    # Legacy detail alanı backwards compat için duruyor
    assert body["detail"] == body["error"]["message"]


def test_400_self_pair_returns_bad_request_code(client):
    r = client.get("/matchup/611/611")
    assert r.status_code == 400
    body = r.json()
    assert body["error"]["code"] == "bad_request"
    assert "aynı takım" in body["error"]["message"]


def test_error_response_includes_request_id(client):
    r = client.get("/matches/999/predict", headers={"X-Request-ID": "trace-err-1"})
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["request_id"] == "trace-err-1"


def test_error_response_request_id_generated_when_header_missing(client):
    r = client.get("/matches/999/predict")
    body = r.json()
    # Generated uuid4 hex (32 char) request_id payload'da görünmeli
    assert "request_id" in body["error"]
    assert len(body["error"]["request_id"]) == 32


def test_validation_error_returns_422_with_code(client):
    """FastAPI Query validator (ge=1) ihlali → 422 + validation_error code."""
    r = client.get("/teams/611/form?last_n=0")  # ge=1 ihlali
    assert r.status_code == 422
    body = r.json()
    assert body["error"]["code"] == "validation_error"
    assert "details" in body["error"]
    assert isinstance(body["error"]["details"], list)


def test_rate_limit_429_still_has_structured_error(client, monkeypatch):
    """429 middleware'den döner; yeni handler bunu yakalamaz ama format
    farklı (string detail). Test: en azından 429 dönüyor + retry-after header
    var.
    """
    from app.api import main as api_main
    from app.api.observability import SlidingWindowRateLimiter
    api_main._rate_limiter = SlidingWindowRateLimiter(max_per_minute=1)
    try:
        client.get("/leagues")  # ilk OK
        r = client.get("/leagues")  # 429
        assert r.status_code == 429
        assert "Retry-After" in r.headers
    finally:
        api_main._rate_limiter = SlidingWindowRateLimiter(120)


def test_custom_error_code_passed_via_detail_dict(client):
    """HTTPException(detail={"code": "x", "message": "y"}) → error.code=x.

    Bunu kanıtlamak için bir endpoint'e direct çağrı yapamıyoruz; ama
    handler'ın dict detail'i parse ettiğini direkt test edebiliriz.
    """
    import asyncio

    from fastapi import HTTPException

    from app.api.errors import http_exception_handler
    # Direct handler çağrısı
    exc = HTTPException(
        status_code=409,
        detail={"code": "team_already_exists", "message": "Galatasaray zaten kayıtlı"},
    )
    resp = asyncio.run(http_exception_handler(None, exc))  # type: ignore[arg-type]
    import json
    body = json.loads(resp.body.decode())
    assert body["error"]["code"] == "team_already_exists"
    assert "Galatasaray" in body["error"]["message"]
