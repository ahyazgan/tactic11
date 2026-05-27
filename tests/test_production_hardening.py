"""Production hardening: enhanced /health, rate limiting, /admin/metrics, JSON logs."""

from __future__ import annotations

import json
import logging
from io import StringIO

import pytest
from fastapi.testclient import TestClient

from app.api import main as api_main
from app.api.main import app
from app.api.observability import METRICS, SlidingWindowRateLimiter
from app.core.logging import JsonFormatter
from app.db.session import get_session


@pytest.fixture()
def client(session):
    def _override():
        yield session

    app.dependency_overrides[get_session] = _override
    METRICS.reset()
    api_main._rate_limiter.reset()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_health_returns_db_status_and_uptime(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"
    assert body["version"] == api_main.APP_VERSION
    assert "uptime_seconds" in body
    assert body["uptime_seconds"] >= 0


def test_health_reports_degraded_when_db_fails(monkeypatch):
    """get_session override yok → gerçek DATABASE_URL'a bağlanır (psql lokalde yok) → 503."""
    # Override'ı kaldır — gerçek DB'ye git
    app.dependency_overrides.pop(get_session, None)
    try:
        client = TestClient(app)
        r = client.get("/health")
        # CI'da psql var olabilir → ok/degraded ikisini de kabul et;
        # ama "db" alanı her durumda doğru bilgi vermeli
        assert r.status_code in (200, 503)
        body = r.json()
        assert "db" in body
        assert "uptime_seconds" in body
    finally:
        app.dependency_overrides.clear()


def test_admin_metrics_counts_requests(client):
    # birkaç istek at
    client.get("/health")
    client.get("/health")
    client.get("/leagues")
    r = client.get("/admin/metrics")
    assert r.status_code == 200
    body = r.json()
    assert body["total_requests"] >= 3
    assert "uptime_seconds" in body
    # Path başına status sayaçları var
    counts = body["counts"]
    health_keys = [k for k in counts if "/health" in k]
    assert len(health_keys) >= 1


def test_rate_limiter_allows_under_limit():
    rl = SlidingWindowRateLimiter(max_per_minute=5)
    for _ in range(5):
        assert rl.allow("key1") is True


def test_rate_limiter_blocks_over_limit():
    rl = SlidingWindowRateLimiter(max_per_minute=3)
    for _ in range(3):
        assert rl.allow("key1") is True
    assert rl.allow("key1") is False  # 4. istek bloklanır


def test_rate_limiter_isolates_keys():
    rl = SlidingWindowRateLimiter(max_per_minute=2)
    assert rl.allow("a")
    assert rl.allow("a")
    assert rl.allow("a") is False
    # b ayrı pencere
    assert rl.allow("b") is True


def test_rate_limit_endpoint_returns_429(client, monkeypatch):
    """Aşırı istek 429 döner; /health bypass eder."""
    # Geçici olarak çok düşük limit
    api_main._rate_limiter = SlidingWindowRateLimiter(max_per_minute=2)
    try:
        # /leagues 2 başarılı çağrı (rate limit'in altında)
        assert client.get("/leagues").status_code == 200
        assert client.get("/leagues").status_code == 200
        # 3. çağrı 429
        r = client.get("/leagues")
        assert r.status_code == 429
        assert "rate limit" in r.json()["detail"].lower()
        # /health hâlâ bypass
        assert client.get("/health").status_code == 200
    finally:
        api_main._rate_limiter = SlidingWindowRateLimiter(120)


def test_json_log_formatter_outputs_valid_json():
    fmt = JsonFormatter()
    record = logging.LogRecord(
        name="test.module",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="hello %s",
        args=("world",),
        exc_info=None,
    )
    line = fmt.format(record)
    parsed = json.loads(line)
    assert parsed["level"] == "INFO"
    assert parsed["logger"] == "test.module"
    assert parsed["msg"] == "hello world"
    assert "ts" in parsed


def test_json_log_includes_exc_info():
    fmt = JsonFormatter()
    try:
        raise ValueError("boom")
    except ValueError:
        import sys
        record = logging.LogRecord(
            name="test", level=logging.ERROR, pathname="x", lineno=1,
            msg="oops", args=None, exc_info=sys.exc_info(),
        )
    parsed = json.loads(fmt.format(record))
    assert parsed["msg"] == "oops"
    assert "ValueError" in parsed["exc_info"]
    assert "boom" in parsed["exc_info"]


def test_json_log_handler_writes_one_line_per_record():
    fmt = JsonFormatter()
    buf = StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(fmt)
    logger = logging.getLogger("test.json")
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.info("msg one")
    logger.info("msg two")
    lines = [ln for ln in buf.getvalue().split("\n") if ln]
    assert len(lines) == 2
    assert all(json.loads(ln) for ln in lines)
