"""Request gözlemleme + rate limiting altyapısı.

İki amaç tek modülde:
1. Her HTTP isteği için durum, süre, endpoint sayacı tut → /admin/metrics
2. API key (yoksa client IP) başına 1 dakikalık sliding-window quota → 429

İkisi de in-memory + thread-safe. Tek-process deployment için yeterli;
multi-process'te (gunicorn workers > 1) Redis benzeri merkezi state lazım
olur ama o noktada bu modül arayüzü stabil kalır, backend swap edilir.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass

# Modül yüklendiğinde process başlangıcı — /health uptime'ı için referans.
PROCESS_STARTED_AT = time.time()

# --- Prometheus (opsiyonel) -------------------------------------------------
# prometheus-client kuruluysa /metrics aktif; değilse no-op. Label kardinalitesi
# düşük tutuldu (method + status; path YOK — id'li path'ler kardinaliteyi patlatır).
try:
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        Counter,
        Histogram,
        generate_latest,
    )

    _PROM_REQUESTS = Counter(
        "http_requests_total", "Toplam HTTP istek sayısı", ["method", "status"]
    )
    _PROM_LATENCY = Histogram(
        "http_request_duration_seconds", "HTTP istek süresi (s)", ["method"]
    )
    _PROM_AVAILABLE = True
except ImportError:  # pragma: no cover — kütüphane yoksa
    _PROM_AVAILABLE = False
    CONTENT_TYPE_LATEST = "text/plain"


def _record_prometheus(method: str, status: int, duration_seconds: float) -> None:
    """Best-effort prometheus kaydı — hiçbir koşulda istek yolunu kırmaz."""
    if not _PROM_AVAILABLE:
        return
    try:
        _PROM_REQUESTS.labels(method=method, status=str(status)).inc()
        _PROM_LATENCY.labels(method=method).observe(duration_seconds)
    except Exception:  # noqa: BLE001 — metrik kaydı asla request'i bozmasın
        pass


def prometheus_available() -> bool:
    return _PROM_AVAILABLE


def prometheus_text() -> tuple[bytes, str] | None:
    """(payload, content_type) ya da kütüphane yoksa None."""
    if not _PROM_AVAILABLE:
        return None
    return generate_latest(), CONTENT_TYPE_LATEST

# Rate limit bypass'i: yalnız /health (k8s/load balancer liveness probe).
_RATE_LIMIT_BYPASS_PATHS: frozenset[str] = frozenset(
    {"/health", "/healthz", "/readyz", "/metrics"}
)
# Endpoint başına saklanan latency örneği sayısı (p50 hesabı için yeterli).
_LATENCY_SAMPLE_LIMIT = 100


@dataclass(frozen=True)
class MetricsSnapshot:
    counts: dict[str, int]  # "METHOD path:status" → count
    latency_p50_ms: dict[str, float]  # "METHOD path" → p50
    total_requests: int


class RequestMetrics:
    """Endpoint başına sayı + p50 latency (in-memory, thread-safe)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counts: dict[str, int] = defaultdict(int)
        self._latencies: dict[str, deque[float]] = defaultdict(
            lambda: deque(maxlen=_LATENCY_SAMPLE_LIMIT)
        )
        self._total = 0

    def record(self, *, method: str, path: str, status: int, duration_seconds: float) -> None:
        key = f"{method} {path}"
        with self._lock:
            self._counts[f"{key}:{status}"] += 1
            self._latencies[key].append(duration_seconds)
            self._total += 1
        # Prometheus'a da yaz (kuruluysa; değilse no-op).
        _record_prometheus(method, status, duration_seconds)

    def snapshot(self) -> MetricsSnapshot:
        with self._lock:
            counts = dict(self._counts)
            p50: dict[str, float] = {}
            for k, samples in self._latencies.items():
                if not samples:
                    continue
                ordered = sorted(samples)
                mid = ordered[len(ordered) // 2]
                p50[k] = round(mid * 1000, 2)
            return MetricsSnapshot(counts=counts, latency_p50_ms=p50, total_requests=self._total)

    def reset(self) -> None:
        """Test izolasyonu için — production'da kullanılmaz."""
        with self._lock:
            self._counts.clear()
            self._latencies.clear()
            self._total = 0


class SlidingWindowRateLimiter:
    """1 dakikalık sliding window; key başına `max_per_minute` istek izinli.

    `allow(key)` True dönerse istek geçer; False dönerse 429.
    """

    def __init__(self, max_per_minute: int) -> None:
        if max_per_minute < 1:
            raise ValueError("max_per_minute >= 1 olmalı")
        self._max = max_per_minute
        self._window: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.time()
        cutoff = now - 60.0
        with self._lock:
            q = self._window[key]
            while q and q[0] < cutoff:
                q.popleft()
            if len(q) >= self._max:
                return False
            q.append(now)
            return True

    def reset(self) -> None:
        """Test izolasyonu için."""
        with self._lock:
            self._window.clear()


def should_bypass_rate_limit(path: str) -> bool:
    return path in _RATE_LIMIT_BYPASS_PATHS


# Module-level singletons — process boyunca tek instance.
METRICS = RequestMetrics()
