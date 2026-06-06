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


def cache_get(session: Session, *, source: str, key: str) -> dict[str, Any] | None:
    # Hızlı yol: Redis yapılandırılmışsa önce oraya bak (yoksa None → DB).
    from app.data.cache.redis_backend import get_redis_cache

    backend = get_redis_cache()
    if backend is not None:
        hit = backend.get(source, key)
        if hit is not None:
            return hit

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


def cache_set(
    session: Session,
    *,
    source: str,
    key: str,
    value: dict[str, Any],
    ttl_seconds: int,
) -> None:
    expires = datetime.now(UTC) + timedelta(seconds=ttl_seconds)
    serialized = json.dumps(value)

    # Write-through: Redis varsa oraya da yaz (TTL Redis tarafında yönetilir).
    from app.data.cache.redis_backend import get_redis_cache

    backend = get_redis_cache()
    if backend is not None:
        backend.set(source, key, value, ttl_seconds)

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
