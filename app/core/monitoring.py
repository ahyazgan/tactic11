"""Hata izleme (Sentry) — opsiyonel, graceful (kütüphane/DSN yoksa no-op).

`SENTRY_DSN` boşsa hiçbir şey yapılmaz (dev/test). DSN set ama `sentry-sdk`
kurulu değilse uyarı loglanır ama boot kırılmaz. Böylece dependency zorunlu
olmadan merkezi exception takibi prod'da aktive edilebilir.
"""
from __future__ import annotations

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)


def init_sentry() -> bool:
    """Sentry'yi koşullu başlat. Aktive olduysa True döner."""
    settings = get_settings()
    if not settings.sentry_dsn:
        return False
    try:
        import sentry_sdk
    except ImportError:
        log.warning("SENTRY_DSN set ama sentry-sdk kurulu değil — hata izleme pasif")
        return False

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        environment=settings.app_env,
    )
    log.info("Sentry başlatıldı (env=%s)", settings.app_env)
    return True
