"""StatsBomb adapter — retry + circuit breaker integration."""
from __future__ import annotations

import httpx
import pytest

from app.data.sources._resilience import CircuitBreaker, CircuitOpenError
from app.data.sources.statsbomb_open import StatsBombOpen


@pytest.fixture(autouse=True)
def _reset_breaker():
    """Her test kendi temiz devre kesicisiyle başlasın."""
    StatsBombOpen._breaker = None
    yield
    StatsBombOpen._breaker = None


def test_retries_on_timeout_then_succeeds(monkeypatch):
    """İlk 2 attempt timeout, 3.'sünde başarılı → retry recovery."""
    src = StatsBombOpen()
    calls = {"n": 0}

    class _FakeClient:
        def __init__(self, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, url, **k):
            calls["n"] += 1
            if calls["n"] < 3:
                raise httpx.TimeoutException("simulated", request=None)
            r = httpx.Response(200, json={"ok": True}, request=httpx.Request("GET", url))
            return r

    monkeypatch.setattr(
        "app.data.sources.statsbomb_open.httpx.Client",
        _FakeClient,
    )
    out = src._fetch_json("test.json")
    assert out == {"ok": True}
    assert calls["n"] == 3


def test_does_not_retry_on_404():
    """4xx retry edilmez — _is_retryable False."""
    err = httpx.HTTPStatusError(
        "404", request=httpx.Request("GET", "/x"),
        response=httpx.Response(404),
    )
    assert StatsBombOpen._is_retryable(err) is False


def test_breaker_opens_after_threshold(monkeypatch):
    """5 ardışık başarısızlık → 6. çağrı CircuitOpenError."""
    src = StatsBombOpen()
    # Manual breaker — düşük eşik
    src.__class__._breaker = CircuitBreaker(failure_threshold=2,
                                              cooldown_seconds=30)

    class _AlwaysFail:
        def __init__(self, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, url, **k):
            raise httpx.TimeoutException("fail", request=None)

    monkeypatch.setattr(
        "app.data.sources.statsbomb_open.httpx.Client",
        _AlwaysFail,
    )
    # İlk birkaç çağrı timeout → retry tükenince RuntimeError/Exception
    with pytest.raises(Exception):  # noqa: B017
        src._fetch_json("x.json")
    with pytest.raises(Exception):  # noqa: B017
        src._fetch_json("x.json")
    # 3. çağrı breaker açık → CircuitOpenError
    with pytest.raises(CircuitOpenError):
        src._fetch_json("x.json")
