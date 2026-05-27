"""Adapter yanıtları için TTL'li DB-destekli cache.

Süresi geçmiş satır cache_get'te yok sayılır; periyodik temizlik şimdilik yok
(tablo küçük kalır; gerekirse cron). Anahtar adapter tarafında (source, key)
ile oluşturulur; bu modül anahtar şemasına karışmaz.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db import models

log = get_logger(__name__)


def cache_get(session: Session, *, source: str, key: str) -> dict[str, Any] | None:
    row = session.execute(
        select(models.CacheEntry).where(
            models.CacheEntry.source == source,
            models.CacheEntry.key == key,
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    # SQLite tz bilgisini kaybeder; naive geldiyse UTC kabul et (yazılan an UTC idi).
    expires = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=timezone.utc)
    if expires <= datetime.now(timezone.utc):
        return None
    return json.loads(row.value)


def cache_set(
    session: Session,
    *,
    source: str,
    key: str,
    value: dict[str, Any],
    ttl_seconds: int,
) -> None:
    expires = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
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
