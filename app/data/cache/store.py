"""Adapter yanıtları için TTL'li DB-destekli cache.

Süresi geçmiş satır cache_get'te yok sayılır; periyodik temizlik şimdilik yok
(tablo küçük kalır; gerekirse cron). Anahtar adapter tarafında (source, key)
ile oluşturulur; bu modül anahtar şemasına karışmaz.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db import models

log = get_logger(__name__)


def _redis():
    """Aktif Redis client'ı (yoksa None). Import maliyetini lazy tut."""
    from app.data.cache.redis_backend import get_redis_client
    return get_redis_client()


def cache_get(session: Session, *, source: str, key: str) -> dict[str, Any] | None:
    client = _redis()
    if client is not None:
        try:
            from app.data.cache.redis_backend import redis_get
            return redis_get(client, source=source, key=key)
        except Exception as e:  # noqa: BLE001 — Redis hatası → DB fallback
            log.warning("Redis cache_get hatası (%s) — DB'ye düşülüyor", type(e).__name__)
    return _db_cache_get(session, source=source, key=key)


def _db_cache_get(session: Session, *, source: str, key: str) -> dict[str, Any] | None:
    row = session.execute(
        select(models.CacheEntry).where(
            models.CacheEntry.source == source,
            models.CacheEntry.key == key,
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    # SQLite tz bilgisini kaybeder; naive geldiyse UTC kabul et (yazılan an UTC idi).
    expires = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=UTC)
    if expires <= datetime.now(UTC):
        return None
    try:
        return json.loads(row.value)
    except json.JSONDecodeError:
        log.warning(
            "cache_entries source=%s key=%s bozuk JSON — miss olarak ele alındı", source, key
        )
        return None


def cache_get_stale(session: Session, *, source: str, key: str) -> dict[str, Any] | None:
    """TTL'i YOK SAYARAK son bilinen cache değerini döner (graceful degradation).

    `cache_get`'in aksine süresi geçmiş satırı da döndürür. Amaç: taze veri
    alınamadığında (kota aşıldı / kaynak düştü) 500 yerine bayatlamış da olsa
    son yanıtı vermek — "degraded" mod. Satır hiç yoksa ya da JSON bozuksa
    None döner (caller gerçek hatayı yükseltir).
    """
    client = _redis()
    if client is not None:
        try:
            from app.data.cache.redis_backend import redis_get_stale
            return redis_get_stale(client, source=source, key=key)
        except Exception as e:  # noqa: BLE001 — Redis hatası → DB fallback
            log.warning("Redis cache_get_stale hatası (%s) — DB'ye düşülüyor", type(e).__name__)
    row = session.execute(
        select(models.CacheEntry).where(
            models.CacheEntry.source == source,
            models.CacheEntry.key == key,
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    try:
        return json.loads(row.value)
    except json.JSONDecodeError:
        log.warning(
            "cache_entries source=%s key=%s bozuk JSON — stale miss", source, key
        )
        return None


def cache_set(
    session: Session,
    *,
    source: str,
    key: str,
    value: dict[str, Any],
    ttl_seconds: int,
) -> None:
    client = _redis()
    if client is not None:
        try:
            from app.data.cache.redis_backend import redis_set
            redis_set(client, source=source, key=key, value=value, ttl_seconds=ttl_seconds)
            return
        except Exception as e:  # noqa: BLE001 — Redis hatası → DB fallback
            log.warning("Redis cache_set hatası (%s) — DB'ye yazılıyor", type(e).__name__)
    expires = datetime.now(UTC) + timedelta(seconds=ttl_seconds)
    serialized = json.dumps(value)
    row = session.execute(
        select(models.CacheEntry).where(
            models.CacheEntry.source == source,
            models.CacheEntry.key == key,
        )
    ).scalar_one_or_none()
    if row is None:
        session.add(
            models.CacheEntry(
                source=source, key=key, value=serialized, expires_at=expires
            )
        )
    else:
        row.value = serialized
        row.expires_at = expires
    session.flush()
