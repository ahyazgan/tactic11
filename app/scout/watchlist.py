"""Scout watchlist CRUD — `scout_watchlist` tablosu üstünde minimal işlemler.

Multi-tenant gelmeden user_id "default" — kulübün scout şefi tek kullanıcı
varsayılıyor. Tenant migration'ı geldiğinde user_id JWT'den geçecek.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models


@dataclass(frozen=True)
class WatchlistEntry:
    id: int
    user_id: str
    player_external_id: int
    notes: str | None
    created_at: datetime
    updated_at: datetime


def add_to_watchlist(
    session: Session, *,
    player_external_id: int,
    user_id: str = "default",
    notes: str | None = None,
) -> WatchlistEntry:
    """Idempotent: aynı (user_id, player_id) → notes update + updated_at refresh."""
    now = datetime.now(UTC)
    existing = session.execute(
        select(models.ScoutWatchlist).where(
            models.ScoutWatchlist.user_id == user_id,
            models.ScoutWatchlist.player_external_id == player_external_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        if notes is not None:
            existing.notes = notes
        existing.updated_at = now
        session.flush()
        return _to_entry(existing)
    row = models.ScoutWatchlist(
        user_id=user_id,
        player_external_id=player_external_id,
        notes=notes,
        created_at=now, updated_at=now,
    )
    session.add(row)
    session.flush()
    return _to_entry(row)


def remove_from_watchlist(
    session: Session, *, player_external_id: int, user_id: str = "default",
) -> bool:
    row = session.execute(
        select(models.ScoutWatchlist).where(
            models.ScoutWatchlist.user_id == user_id,
            models.ScoutWatchlist.player_external_id == player_external_id,
        )
    ).scalar_one_or_none()
    if row is None:
        return False
    session.delete(row)
    session.flush()
    return True


def update_watchlist_notes(
    session: Session, *,
    player_external_id: int,
    notes: str,
    user_id: str = "default",
) -> bool:
    row = session.execute(
        select(models.ScoutWatchlist).where(
            models.ScoutWatchlist.user_id == user_id,
            models.ScoutWatchlist.player_external_id == player_external_id,
        )
    ).scalar_one_or_none()
    if row is None:
        return False
    row.notes = notes
    row.updated_at = datetime.now(UTC)
    session.flush()
    return True


def list_watchlist(
    session: Session, *, user_id: str = "default", limit: int = 100,
) -> list[WatchlistEntry]:
    rows = list(
        session.execute(
            select(models.ScoutWatchlist)
            .where(models.ScoutWatchlist.user_id == user_id)
            .order_by(models.ScoutWatchlist.updated_at.desc())
            .limit(limit)
        ).scalars()
    )
    return [_to_entry(r) for r in rows]


def _to_entry(row: models.ScoutWatchlist) -> WatchlistEntry:
    return WatchlistEntry(
        id=row.id, user_id=row.user_id,
        player_external_id=row.player_external_id, notes=row.notes,
        created_at=row.created_at, updated_at=row.updated_at,
    )
