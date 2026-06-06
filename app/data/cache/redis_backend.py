"""Opsiyonel Redis cache backend — varsa hızlı yol, yoksa DB cache'e düşülür.

reportlab/anthropic ile aynı graceful-degradation felsefesi:
- `redis` paketi kurulu DEĞİLSE → `REDIS_AVAILABLE = False`, backend None.
- `settings.redis_url` BOŞSA → backend None (tek-process pilot DB cache yeter).
- Bağlantı/komut hatası → sessizce None döner; çağıran DB cache'e düşer.

Böylece üretimde `REDIS_URL` set'lenince cache_get/cache_set otomatik
Redis kullanır; deps/infra yoksa sistem aynen çalışmaya devam eder.
"""
from __future__ import annotations

import json
from typing import Any

from app.core.logging import get_logger

log = get_logger(__name__)

try:
    import redis as _redis

    REDIS_AVAILABLE = True
except ImportError:  # pragma: no cover — opsiyonel paket
    _redis = None
    REDIS_AVAILABLE = False


def _redis_key(source: str, key: str) -> str:
    """Namespace'li düz anahtar — DB (source,key) çiftiyle eşdeğer."""
    return f"m2:{source}:{key}"


class RedisCache:
    """Minimal JSON cache — get/set + TTL. SETEX ile süre yönetimi Redis'te."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def get(self, source: str, key: str) -> dict[str, Any] | None:
        try:
            raw = self._client.get(_redis_key(source, key))
        except Exception as e:  # noqa: BLE001 — backend hatası DB'ye düşmeli
            log.warning("redis get hata: %s", e)
            return None
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None

    def set(
        self, source: str, key: str, value: dict[str, Any], ttl_seconds: int,
    ) -> bool:
        try:
            self._client.setex(
                _redis_key(source, key), max(1, ttl_seconds), json.dumps(value),
            )
            return True
        except Exception as e:  # noqa: BLE001
            log.warning("redis set hata: %s", e)
            return False


# Süreç-ömürlü singleton (None = devre dışı). İlk çağrıda kurulur.
_BACKEND: RedisCache | None = None
_INITIALIZED = False


def get_redis_cache() -> RedisCache | None:
    """Yapılandırılmış + erişilebilir Redis backend; aksi halde None.

    İdempotent: ilk çağrıda client kurulur, sonra cache'lenir. Bağlantı
    kurulamazsa None döner (DB cache'e düşülür).
    """
    global _BACKEND, _INITIALIZED
    if _INITIALIZED:
        return _BACKEND

    _INITIALIZED = True
    if not REDIS_AVAILABLE:
        return None

    from app.core.config import get_settings

    url = getattr(get_settings(), "redis_url", "")
    if not url:
        return None

    try:
        client = _redis.from_url(
            url, decode_responses=True, socket_timeout=2.0,
        )
        client.ping()
    except Exception as e:  # noqa: BLE001 — erişilemiyorsa DB cache'e düş
        log.warning("redis bağlanılamadı (%s) — DB cache kullanılacak", e)
        return None

    log.info("redis cache backend aktif")
    _BACKEND = RedisCache(client)
    return _BACKEND


def reset_redis_cache() -> None:
    """Test/yeniden-yapılandırma için singleton'ı sıfırla."""
    global _BACKEND, _INITIALIZED
    _BACKEND = None
    _INITIALIZED = False
