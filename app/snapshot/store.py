"""Snapshot deposu.

Her sync sonunda durum özetini biriktir. Üzerine yazılmaz; her çağrı yeni
satır ekler. Geçmiş üzerinde "geçen hafta vs şimdi" karşılaştırmasına /
tahmin kalibrasyonuna yakıt olur.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.db import models


def build_scope(league_id: int, season: int) -> str:
    return f"league:{league_id}:season:{season}"


def save_snapshot(
    session: Session,
    *,
    sport: str,
    league_id: int,
    season: int,
) -> models.Snapshot:
    leagues_count = session.scalar(
        select(func.count())
        .select_from(models.League)
        .where(
            models.League.sport == sport,
            models.League.external_id == league_id,
            models.League.season == season,
        )
    ) or 0

    home_q = (
        select(models.Match.home_team_external_id)
        .where(
            models.Match.sport == sport,
            models.Match.league_external_id == league_id,
            models.Match.season == season,
        )
        .distinct()
    )
    away_q = (
        select(models.Match.away_team_external_id)
        .where(
            models.Match.sport == sport,
            models.Match.league_external_id == league_id,
            models.Match.season == season,
        )
        .distinct()
    )
    teams_count = len({row[0] for row in session.execute(home_q.union(away_q)).all()})

    matches_count = session.scalar(
        select(func.count())
        .select_from(models.Match)
        .where(
            models.Match.sport == sport,
            models.Match.league_external_id == league_id,
            models.Match.season == season,
        )
    ) or 0

    snap = models.Snapshot(
        sport=sport,
        scope=build_scope(league_id, season),
        created_at=datetime.now(UTC),
        leagues_count=leagues_count,
        teams_count=teams_count,
        matches_count=matches_count,
    )
    session.add(snap)
    session.flush()
    return snap


def get_latest_snapshot(
    session: Session, *, sport: str, scope: str
) -> models.Snapshot | None:
    return session.execute(
        select(models.Snapshot)
        .where(models.Snapshot.sport == sport, models.Snapshot.scope == scope)
        .order_by(desc(models.Snapshot.created_at))
        .limit(1)
    ).scalar_one_or_none()


def get_snapshot_at_or_before(
    session: Session, *, sport: str, scope: str, ts: datetime
) -> models.Snapshot | None:
    """`ts` zamanındaki ya da ondan önceki en yeni snapshot — diff için baseline."""
    return session.execute(
        select(models.Snapshot)
        .where(
            models.Snapshot.sport == sport,
            models.Snapshot.scope == scope,
            models.Snapshot.created_at <= ts,
        )
        .order_by(desc(models.Snapshot.created_at))
        .limit(1)
    ).scalar_one_or_none()


def diff_snapshots(
    earlier: models.Snapshot, later: models.Snapshot
) -> dict[str, Any]:
    """İki snapshot arasındaki delta — "ne değişti" özeti."""
    return {
        "from": {
            "id": earlier.id,
            "created_at": earlier.created_at.isoformat(),
            "leagues_count": earlier.leagues_count,
            "teams_count": earlier.teams_count,
            "matches_count": earlier.matches_count,
        },
        "to": {
            "id": later.id,
            "created_at": later.created_at.isoformat(),
            "leagues_count": later.leagues_count,
            "teams_count": later.teams_count,
            "matches_count": later.matches_count,
        },
        "delta": {
            "leagues_count": later.leagues_count - earlier.leagues_count,
            "teams_count": later.teams_count - earlier.teams_count,
            "matches_count": later.matches_count - earlier.matches_count,
            "elapsed_seconds": (later.created_at - earlier.created_at).total_seconds(),
        },
    }
