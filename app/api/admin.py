"""Operasyonel görünürlük uçları.

`/admin/*` namespace'i altında — kullanıcı/analiz uçlarından semantik olarak
ayrı. Auth aynı protected router üzerinden (X-API-Key); rol/role-based access
multi-tenant (Ufuk 1) ile birlikte gelir.

Hepsi DB'den okur, dış kaynağa dokunmaz. DEPLOYMENT.md'deki psql sorgularının
HTTP karşılığı.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.db import models
from app.db.session import get_session

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/jobs")
def recent_jobs(
    limit: int = Query(20, ge=1, le=200),
    job_name: str | None = None,
    status: Literal["running", "success", "failed"] | None = None,
    since_hours: int = Query(168, ge=1, le=24 * 30),  # default 7 gün
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    """Son job run'ları — scheduler sağlığı için."""
    since = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    stmt = (
        select(models.JobRun)
        .where(models.JobRun.started_at >= since)
        .order_by(desc(models.JobRun.started_at))
        .limit(limit)
    )
    if job_name is not None:
        stmt = stmt.where(models.JobRun.job_name == job_name)
    if status is not None:
        stmt = stmt.where(models.JobRun.status == status)

    rows = session.execute(stmt).scalars().all()
    return [
        {
            "id": r.id,
            "job_name": r.job_name,
            "args": r.args,
            "status": r.status,
            "attempts": r.attempts,
            "started_at": r.started_at.isoformat(),
            "ended_at": r.ended_at.isoformat() if r.ended_at else None,
            "duration_sec": (
                (r.ended_at - r.started_at).total_seconds()
                if r.ended_at
                else None
            ),
            "error": r.error,
        }
        for r in rows
    ]


@router.get("/usage")
def usage_summary(
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Bugün/bu ay başına source başına kullanım — kota görünürlüğü."""
    now = datetime.now(timezone.utc)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start_of_month = start_of_day.replace(day=1)

    def _agg(since: datetime) -> list[dict[str, Any]]:
        rows = session.execute(
            select(
                models.UsageEvent.source,
                func.count().label("calls"),
                func.coalesce(func.sum(models.UsageEvent.tokens), 0).label("tokens"),
            )
            .where(models.UsageEvent.created_at >= since)
            .group_by(models.UsageEvent.source)
        ).all()
        return [{"source": r.source, "calls": r.calls, "tokens": r.tokens} for r in rows]

    return {
        "now": now.isoformat(),
        "today": _agg(start_of_day),
        "this_month": _agg(start_of_month),
    }


@router.get("/snapshots")
def snapshots(
    scope: str | None = None,
    limit: int = Query(20, ge=1, le=200),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    """Snapshot tarihçesi — tahmin yakıtının birikme oranını izlemek için."""
    stmt = (
        select(models.Snapshot)
        .order_by(desc(models.Snapshot.created_at))
        .limit(limit)
    )
    if scope is not None:
        stmt = stmt.where(models.Snapshot.scope == scope)
    rows = session.execute(stmt).scalars().all()
    return [
        {
            "id": s.id,
            "sport": s.sport,
            "scope": s.scope,
            "created_at": s.created_at.isoformat(),
            "leagues_count": s.leagues_count,
            "teams_count": s.teams_count,
            "matches_count": s.matches_count,
        }
        for s in rows
    ]


@router.get("/db-stats")
def db_stats(session: Session = Depends(get_session)) -> dict[str, int]:
    """Tablo başına satır sayısı — sync ilerlemesini görmek için hızlı bakış."""
    out: dict[str, int] = {}
    for model in (
        models.League,
        models.Team,
        models.Player,
        models.Match,
        models.Snapshot,
        models.UsageEvent,
        models.CacheEntry,
        models.JobRun,
    ):
        out[model.__tablename__] = session.scalar(
            select(func.count()).select_from(model)
        ) or 0
    return out
