"""Retry + circuit breaker birim testleri (saf, deterministik saat + sleep)."""
from __future__ import annotations

import pytest

from app.data.sources._resilience import (
    CircuitBreaker,
    CircuitOpenError,
    call_with_retry,
)


class _Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def _always_retryable(_e: Exception) -> bool:
    return True


def test_retry_returns_on_first_success():
    calls = []
    out = call_with_retry(lambda: calls.append(1) or "ok", attempts=3,
                          sleep=lambda _s: None)
    assert out == "ok"
    assert len(calls) == 1


def test_retry_then_success():
    state = {"n": 0}

    def fn():
        state["n"] += 1
        if state["n"] < 3:
            raise TimeoutError("geçici")
        return "ok"

    out = call_with_retry(fn, attempts=3, is_retryable=_always_retryable,
                          sleep=lambda _s: None)
    assert out == "ok"
    assert state["n"] == 3


def test_non_retryable_raises_immediately():
    state = {"n": 0}

    def fn():
        state["n"] += 1
        raise ValueError("client error")

    with pytest.raises(ValueError):
        call_with_retry(fn, attempts=3, is_retryable=lambda _e: False,
                        sleep=lambda _s: None)
    assert state["n"] == 1  # retry edilmedi


def test_exhausted_retries_raise_last():
    def fn():
        raise TimeoutError("hep düşük")

    with pytest.raises(TimeoutError):
        call_with_retry(fn, attempts=3, is_retryable=_always_retryable,
                        sleep=lambda _s: None)


def test_breaker_opens_after_threshold():
    clock = _Clock()
    breaker = CircuitBreaker(failure_threshold=2, cooldown_seconds=30, now=clock)

    def fail():
        raise TimeoutError("x")

    # İki tükenmiş çağrı → 2 failure → devre açılır
    for _ in range(2):
        with pytest.raises(TimeoutError):
            call_with_retry(fail, attempts=1, breaker=breaker,
                            is_retryable=_always_retryable, sleep=lambda _s: None)
    assert breaker.is_open
    # Üçüncü çağrı denenmeden CircuitOpenError
    with pytest.raises(CircuitOpenError):
        call_with_retry(fail, attempts=1, breaker=breaker,
                        is_retryable=_always_retryable, sleep=lambda _s: None)


def test_breaker_half_open_after_cooldown():
    clock = _Clock()
    breaker = CircuitBreaker(failure_threshold=1, cooldown_seconds=30, now=clock)

    with pytest.raises(TimeoutError):
        call_with_retry(lambda: (_ for _ in ()).throw(TimeoutError()),
                        attempts=1, breaker=breaker,
                        is_retryable=_always_retryable, sleep=lambda _s: None)
    assert breaker.is_open
    # Cooldown sonrası half-open → çağrı denenir; başarı → kapanır
    clock.t = 31.0
    out = call_with_retry(lambda: "recovered", attempts=1, breaker=breaker)
    assert out == "recovered"
    assert not breaker.is_open
