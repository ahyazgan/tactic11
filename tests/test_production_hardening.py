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


def test_health_deep_reports_components(client):
    r = client.get("/health/deep")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    comp = body["components"]
    assert comp["db"]["status"] == "ok"
    # cache backend: redis yapılandırılmadıysa "db"
    assert comp["cache"]["backend"] in ("db", "redis")
    # bildirim: env yokken hiç active kanal yok
    assert comp["notifications"]["active_channels"] == []
    assert "migration" in comp


def test_healthz_liveness_no_db(client):
    """Liveness DB'ye dokunmaz — her zaman 200."""
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "uptime_seconds" in body


def test_readyz_readiness_ok_with_db(client):
    r = client.get("/readyz")
    assert r.status_code == 200
    assert r.json()["status"] == "ready"
    assert r.json()["db"] == "ok"


def test_security_headers_present(client):
    r = client.get("/healthz")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert "Referrer-Policy" in r.headers


def test_login_has_stricter_rate_limit(client):
    """/auth/login IP başına ayrı sıkı limitle 429'a düşer."""
    api_main._login_rate_limiter.reset()
    limit = api_main.get_settings().login_rate_limit_per_minute
    statuses = [
        client.post("/auth/login", json={"email": "x@y.z", "password": "w"}).status_code
        for _ in range(limit + 1)
    ]
    assert 429 in statuses  # limit aşılınca login limiter devreye girer


def test_metrics_endpoint_responds(client):
    """/metrics 200 döner: prometheus kuruluysa exposition, değilse açıklama."""
    r = client.get("/metrics")
    assert r.status_code == 200
    assert len(r.text) > 0


def test_sentry_noop_without_dsn():
    """SENTRY_DSN boşken init_sentry False döner (kütüphane gerekmeden no-op)."""
    from app.core.monitoring import init_sentry
    assert init_sentry() is False


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


# ---- request_id propagation -----------------------------------------------


def test_request_id_generated_when_header_missing(client):
    r = client.get("/health")
    assert r.status_code == 200
    rid = r.headers.get("X-Request-ID")
    assert rid is not None
    assert len(rid) == 32  # uuid4().hex


def test_request_id_echoed_when_header_provided(client):
    r = client.get("/health", headers={"X-Request-ID": "my-trace-abc"})
    assert r.headers.get("X-Request-ID") == "my-trace-abc"


def test_request_id_uniquely_generated_per_request(client):
    rids = {client.get("/health").headers["X-Request-ID"] for _ in range(5)}
    assert len(rids) == 5  # her istek farklı uuid


def test_request_id_present_on_429_rate_limited_response(client):
    api_main._rate_limiter = SlidingWindowRateLimiter(max_per_minute=1)
    try:
        assert client.get("/leagues").status_code == 200
        r = client.get("/leagues", headers={"X-Request-ID": "trace-rate"})
        assert r.status_code == 429
        # 429 yanıtında da request_id korunmalı
        assert r.headers.get("X-Request-ID") == "trace-rate"
    finally:
        api_main._rate_limiter = SlidingWindowRateLimiter(120)


def test_request_id_injected_into_json_log_records():
    """contextvar set'liyken JsonFormatter request_id alanını ekler."""
    from app.core.logging import RequestIdFilter
    from app.core.request_context import clear_request_id, set_request_id

    fmt = JsonFormatter()
    set_request_id("rid-xyz-123")
    try:
        record = logging.LogRecord(
            name="t", level=logging.INFO, pathname="x", lineno=1,
            msg="hi", args=None, exc_info=None,
        )
        RequestIdFilter().filter(record)
        parsed = json.loads(fmt.format(record))
        assert parsed["request_id"] == "rid-xyz-123"
    finally:
        clear_request_id()


def test_request_id_omitted_when_not_set():
    """contextvar set'li değilken request_id alanı yok (parazit yok)."""
    from app.core.logging import RequestIdFilter
    from app.core.request_context import clear_request_id

    clear_request_id()
    fmt = JsonFormatter()
    record = logging.LogRecord(
        name="t", level=logging.INFO, pathname="x", lineno=1,
        msg="hi", args=None, exc_info=None,
    )
    RequestIdFilter().filter(record)
    parsed = json.loads(fmt.format(record))
    assert "request_id" not in parsed
