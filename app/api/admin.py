"""Operasyonel görünürlük uçları.

`/admin/*` namespace'i altında — kullanıcı/analiz uçlarından semantik olarak
ayrı. Auth aynı protected router üzerinden (X-API-Key); rol/role-based access
multi-tenant (Ufuk 1) ile birlikte gelir.

Hepsi DB'den okur, dış kaynağa dokunmaz. DEPLOYMENT.md'deki psql sorgularının
HTTP karşılığı.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.api.observability import METRICS, PROCESS_STARTED_AT
from app.api.pagination import build_next_cursor, decode_cursor
from app.api.serialize import engine_result_to_dict
from app.core.config import get_settings
from app.db import models
from app.db.session import get_session
from app.engine.calibration import compute_calibration
from app.snapshot import diff_snapshots, get_latest_snapshot, get_snapshot_at_or_before
from app.sports import football

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/jobs")
def recent_jobs(
    response: Response,
    limit: int = Query(20, ge=1, le=200),
    job_name: str | None = None,
    status: Literal["running", "success", "failed"] | None = None,
    since_hours: int = Query(168, ge=1, le=24 * 30),  # default 7 gün
    cursor: str | None = Query(
        None,
        description="Önceki yanıtın X-Next-Cursor header'ından gelen değer.",
    ),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    """Son job run'ları — scheduler sağlığı için.

    Pagination: `limit` döner; daha fazla satır varsa `X-Next-Cursor`
    response header'ı set'lenir. Sonraki sayfa için `?cursor=<value>`.
    """
    since = datetime.now(UTC) - timedelta(hours=since_hours)
    stmt = (
        select(models.JobRun)
        .where(models.JobRun.started_at >= since)
        .order_by(desc(models.JobRun.started_at), desc(models.JobRun.id))
    )
    if job_name is not None:
        stmt = stmt.where(models.JobRun.job_name == job_name)
    if status is not None:
        stmt = stmt.where(models.JobRun.status == status)

    decoded = decode_cursor(cursor)
    if decoded is not None:
        cursor_dt = datetime.fromisoformat(decoded.sort_value)
        # Tuple comparison: (started_at, id) DESC sıralı; cursor'dan sonra
        # devam et (cursor'un atladığı son satır dahil değil)
        stmt = stmt.where(
            (models.JobRun.started_at < cursor_dt)
            | (
                (models.JobRun.started_at == cursor_dt)
                & (models.JobRun.id < decoded.row_id)
            )
        )

    # limit + 1 çek; varsa next_cursor için son satır
    rows = list(session.execute(stmt.limit(limit + 1)).scalars())
    has_next = len(rows) > limit
    items = rows[:limit]

    if has_next:
        nc = build_next_cursor(items, "started_at")
        if nc is not None:
            response.headers["X-Next-Cursor"] = nc

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
        for r in items
    ]


@router.get("/usage")
def usage_summary(
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Bugün/bu ay başına source başına kullanım — kota görünürlüğü."""
    now = datetime.now(UTC)
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


@router.get("/quota-status")
def quota_status(session: Session = Depends(get_session)) -> dict[str, Any]:
    """Mevcut kullanımın limit'lere oranı + uyarı seviyesi.

    `usage_events` üzerinden günlük/aylık sayım; `Settings`'teki limit'lerle
    yüzde olarak döner. UI/dashboard tek seferde "ne kadar daldık"ı görsün.
    """
    s = get_settings()
    now = datetime.now(UTC)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start_of_month = start_of_day.replace(day=1)

    def _calls(source: str, since: datetime) -> int:
        return session.scalar(
            select(func.count())
            .select_from(models.UsageEvent)
            .where(
                models.UsageEvent.source == source,
                models.UsageEvent.created_at >= since,
            )
        ) or 0

    def _tokens(source: str, since: datetime) -> int:
        return session.scalar(
            select(func.coalesce(func.sum(models.UsageEvent.tokens), 0))
            .select_from(models.UsageEvent)
            .where(
                models.UsageEvent.source == source,
                models.UsageEvent.created_at >= since,
            )
        ) or 0

    def _level(fraction: float) -> str:
        if fraction >= 1.0:
            return "exceeded"
        if fraction >= s.quota_warn_fraction:
            return "warn"
        return "ok"

    af_day = _calls("api_football", start_of_day)
    af_month = _calls("api_football", start_of_month)
    an_tokens = _tokens("anthropic", start_of_day)

    af_day_frac = af_day / s.api_football_daily_limit if s.api_football_daily_limit else 0.0
    af_month_frac = af_month / s.api_football_monthly_limit if s.api_football_monthly_limit else 0.0
    an_frac = an_tokens / s.anthropic_daily_token_limit if s.anthropic_daily_token_limit else 0.0

    return {
        "now": now.isoformat(),
        "warn_fraction": s.quota_warn_fraction,
        "api_football": {
            "daily": {
                "used": af_day,
                "limit": s.api_football_daily_limit,
                "fraction": round(af_day_frac, 3),
                "level": _level(af_day_frac),
            },
            "monthly": {
                "used": af_month,
                "limit": s.api_football_monthly_limit,
                "fraction": round(af_month_frac, 3),
                "level": _level(af_month_frac),
            },
        },
        "anthropic": {
            "daily_tokens": {
                "used": an_tokens,
                "limit": s.anthropic_daily_token_limit,
                "fraction": round(an_frac, 3),
                "level": _level(an_frac),
            },
        },
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


@router.get("/snapshots/diff")
def snapshot_diff(
    scope: str = Query(..., description="örn: league:203:season:2024"),
    days: int = Query(7, ge=1, le=365, description="kaç gün öncesiyle karşılaştır"),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """En son snapshot vs `days` gün öncesindeki snapshot — ne değişti.

    "Geçen hafta vs şimdi": tahmin yakıtı spec'inin ilk somut kullanımı.
    Sport şimdilik sabit (football); ileride scope'tan parse edilir.
    """
    latest = get_latest_snapshot(session, sport=football.SPORT_NAME, scope=scope)
    if latest is None:
        raise HTTPException(
            status_code=404,
            detail=f"scope '{scope}' için snapshot yok",
        )
    baseline_ts = latest.created_at - timedelta(days=days)
    earlier = get_snapshot_at_or_before(
        session, sport=football.SPORT_NAME, scope=scope, ts=baseline_ts
    )
    if earlier is None:
        return {
            "scope": scope,
            "requested_days_back": days,
            "note": (
                f"baseline ({days} gün öncesi) bulunamadı — kayıtlı en eski "
                f"snapshot {latest.created_at.isoformat()}"
            ),
            "latest": {
                "id": latest.id,
                "created_at": latest.created_at.isoformat(),
                "leagues_count": latest.leagues_count,
                "teams_count": latest.teams_count,
                "matches_count": latest.matches_count,
            },
        }
    if earlier.id == latest.id:
        return {
            "scope": scope,
            "requested_days_back": days,
            "note": "baseline ve latest aynı snapshot — diff yok",
            "snapshot": {
                "id": latest.id,
                "created_at": latest.created_at.isoformat(),
                "leagues_count": latest.leagues_count,
                "teams_count": latest.teams_count,
                "matches_count": latest.matches_count,
            },
        }
    return {"scope": scope, **diff_snapshots(earlier, latest)}


@router.get("/metrics")
def request_metrics() -> dict[str, Any]:
    """Bu process'in request sayaçları + p50 latency.

    In-memory; process restart'ta sıfırlanır. Tek process için yeterli;
    multi-process / multi-pod deploy'da Prometheus/StatsD ile değiştirilir.
    """
    snap = METRICS.snapshot()
    uptime = round(time.time() - PROCESS_STARTED_AT, 2)
    return {
        "uptime_seconds": uptime,
        "total_requests": snap.total_requests,
        "counts": snap.counts,
        "p50_latency_ms": snap.latency_p50_ms,
    }


@router.get("/predict-accuracy")
def predict_accuracy(
    engine: str = Query("engine.predict"),
    engine_version: str = Query("2"),
    days: int = Query(30, ge=1, le=365),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Reconciled tahminler üzerinde Brier + log loss + ECE raporu.

    `(engine, engine_version)` filter — version'lar arası A/B karşılaştırma
    için. `days`: son N gün içinde reconcile edilmiş tahminler.
    """
    import json as _json

    since = datetime.now(UTC) - timedelta(days=days)
    rows = list(
        session.execute(
            select(models.Prediction).where(
                models.Prediction.engine == engine,
                models.Prediction.engine_version == engine_version,
                models.Prediction.actual_outcome.is_not(None),
                models.Prediction.reconciled_at >= since,
            )
        ).scalars()
    )

    samples: list[tuple[float, float, float, str]] = []
    for r in rows:
        try:
            v = _json.loads(r.predicted_value_json)
        except _json.JSONDecodeError:
            continue
        ph = v.get("prob_home_win")
        pd = v.get("prob_draw")
        pa = v.get("prob_away_win")
        if ph is None or pd is None or pa is None or r.actual_outcome is None:
            continue
        samples.append((float(ph), float(pd), float(pa), r.actual_outcome))

    result = compute_calibration(
        samples, engine=engine, engine_version=engine_version
    )
    payload = engine_result_to_dict(result)
    payload["filter"] = {
        "engine": engine,
        "engine_version": engine_version,
        "days": days,
        "since": since.isoformat(),
        "reconciled_count": len(rows),
        "valid_samples": len(samples),
    }
    return payload


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
