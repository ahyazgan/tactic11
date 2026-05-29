"""Dış HTTP çağrıları için retry + circuit breaker (saf Python, thread-safe).

API-Football kısa süre düşse tüm analiz patlamasın diye:
- Geçici hatalarda (timeout, 5xx, transport) exponential backoff ile yeniden dene.
- Üst üste başarısızlık eşiği aşılırsa devreyi AÇ (fail-fast), cooldown sonra
  half-open ile bir deneme yap. Başarı → kapat, başarısız → tekrar aç.

Saf: zaman kaynağı ve sleep enjekte edilebilir (deterministik test). httpx/dış
bağımlılık import etmez — retryable kararı caller'ın predicate'ine bırakılır.
"""
from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


class CircuitOpenError(RuntimeError):
    """Devre açık — kaynak düşük kabul edildi, çağrı denenmeden reddedildi."""


class CircuitBreaker:
    """Ardışık başarısızlık eşiğinde açılan basit devre kesici."""

    def __init__(
        self,
        *,
        failure_threshold: int = 5,
        cooldown_seconds: float = 30.0,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold >= 1 olmalı")
        self._threshold = failure_threshold
        self._cooldown = cooldown_seconds
        self._now = now
        self._failures = 0
        self._opened_at: float | None = None
        self._lock = threading.Lock()

    @property
    def is_open(self) -> bool:
        with self._lock:
            return self._opened_at is not None and (
                self._now() - self._opened_at < self._cooldown
            )

    def before_call(self) -> None:
        """Devre açık + cooldown dolmamışsa CircuitOpenError fırlat."""
        with self._lock:
            if self._opened_at is None:
                return
            if self._now() - self._opened_at >= self._cooldown:
                return  # half-open: bir deneme hakkı
            raise CircuitOpenError(
                f"circuit open ({self._failures} ardışık hata, cooldown aktif)"
            )

    def record_success(self) -> None:
        with self._lock:
            self._failures = 0
            self._opened_at = None

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._failures >= self._threshold:
                self._opened_at = self._now()


def call_with_retry(
    fn: Callable[[], T],
    *,
    attempts: int = 3,
    breaker: CircuitBreaker | None = None,
    is_retryable: Callable[[Exception], bool] = lambda _e: True,
    backoff_base: float = 0.5,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """`fn`'i retry + (opsiyonel) breaker ile çağır.

    - breaker açıksa CircuitOpenError fırlar (fn hiç çağrılmaz).
    - is_retryable(e) False ise (örn. 4xx) anında re-raise; breaker etkilenmez.
    - retryable hatalarda exponential backoff (base·2^i), `attempts` kez dene.
    - tüm denemeler tükenirse breaker'a bir başarısızlık yaz ve son hatayı fırlat.
    """
    if attempts < 1:
        raise ValueError("attempts >= 1 olmalı")
    if breaker is not None:
        breaker.before_call()

    last_exc: Exception | None = None
    for i in range(attempts):
        try:
            result = fn()
            if breaker is not None:
                breaker.record_success()
            return result
        except Exception as e:  # noqa: BLE001 — caller predicate'i sınıflandırır
            if not is_retryable(e):
                raise
            last_exc = e
            if i < attempts - 1:
                sleep(backoff_base * (2**i))

    if breaker is not None:
        breaker.record_failure()
    assert last_exc is not None  # attempts>=1 + döngü buraya ancak hatayla düşer
    raise last_exc
