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
from app.data.cache.store import cache_get, cache_set
from app.db import models
from app.db.session import get_session
from app.engine.calibration import compute_calibration
from app.snapshot import diff_snapshots, get_latest_snapshot, get_snapshot_at_or_before
from app.sports import football

router = APIRouter(prefix="/admin", tags=["admin"])

# Tactical profile/trend cache: 1 saat TTL (event ingest sonrası
# /admin/tactical-cache/clear ile manuel invalidate)
TACTICAL_CACHE_SOURCE = "tactical_profile"
TACTICAL_CACHE_TTL_SECONDS = 3600


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


@router.get("/leagues-summary")
def leagues_summary(session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    """Her lig için: takım sayısı, maç sayısı (toplam + FT + NS), en son
    snapshot zamanı. Multi-league deploy'da hangi ligin ne kadar dolu
    olduğunu tek istekte görmek için.

    Pre-existing /admin/db-stats global toplamı verir; bu endpoint
    her lig için ayrıştırır.
    """
    leagues = session.execute(
        select(models.League).order_by(
            models.League.sport, models.League.external_id, models.League.season
        )
    ).scalars().all()

    out: list[dict[str, Any]] = []
    for lg in leagues:
        # Bu lig + sezona ait maç sayımları
        match_base = select(func.count()).select_from(models.Match).where(
            models.Match.sport == lg.sport,
            models.Match.league_external_id == lg.external_id,
            models.Match.season == lg.season,
        )
        total_matches = session.scalar(match_base) or 0
        ft_matches = session.scalar(
            match_base.where(models.Match.status.in_(football.FINISHED_STATUSES))
        ) or 0
        ns_matches = total_matches - ft_matches

        # Bu lig + sezona ait takım sayımı (matches'taki home/away id'lerinin distinct'i)
        home_ids = (
            select(models.Match.home_team_external_id)
            .where(
                models.Match.sport == lg.sport,
                models.Match.league_external_id == lg.external_id,
                models.Match.season == lg.season,
            ).distinct()
        )
        away_ids = (
            select(models.Match.away_team_external_id)
            .where(
                models.Match.sport == lg.sport,
                models.Match.league_external_id == lg.external_id,
                models.Match.season == lg.season,
            ).distinct()
        )
        team_count = len({row[0] for row in session.execute(home_ids.union(away_ids)).all()})

        # Son snapshot
        scope = f"league:{lg.external_id}:season:{lg.season}"
        last_snap = session.execute(
            select(models.Snapshot)
            .where(models.Snapshot.sport == lg.sport, models.Snapshot.scope == scope)
            .order_by(desc(models.Snapshot.created_at))
            .limit(1)
        ).scalar_one_or_none()

        out.append({
            "sport": lg.sport,
            "league_external_id": lg.external_id,
            "name": lg.name,
            "season": lg.season,
            "country": lg.country,
            "team_count": team_count,
            "match_count_total": total_matches,
            "match_count_ft": ft_matches,
            "match_count_ns": ns_matches,
            "last_snapshot_at": last_snap.created_at.isoformat() if last_snap else None,
            "last_snapshot_id": last_snap.id if last_snap else None,
        })
    return out


@router.get("/agent-outputs")
def agent_outputs(
    agent_name: str | None = Query(None, description="Belirli bir agent için filtre."),
    subject_type: str | None = Query(None, description="match | team | player"),
    subject_id: int | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    """Agent çıktıları — dashboard için (PR G2: PreMatchReportAgent)."""
    import json as _json

    stmt = (
        select(models.AgentOutput)
        .order_by(desc(models.AgentOutput.updated_at))
        .limit(limit)
    )
    if agent_name is not None:
        stmt = stmt.where(models.AgentOutput.agent_name == agent_name)
    if subject_type is not None:
        stmt = stmt.where(models.AgentOutput.subject_type == subject_type)
    if subject_id is not None:
        stmt = stmt.where(models.AgentOutput.subject_id == subject_id)

    rows = list(session.execute(stmt).scalars())
    return [
        {
            "id": r.id,
            "agent_name": r.agent_name,
            "agent_version": r.agent_version,
            "subject_type": r.subject_type,
            "subject_id": r.subject_id,
            "summary": r.summary,
            "output": _json.loads(r.output_json),
            "created_at": r.created_at.isoformat(),
            "updated_at": r.updated_at.isoformat(),
        }
        for r in rows
    ]


@router.get("/ml-model-status")
def ml_model_status(session: Session = Depends(get_session)) -> dict[str, Any]:
    """engine.predict_ml train job son çalıştırma durumu.

    cache_entries(source='ml_predict_model', key='best_rho_v1') okur:
    - Hiç train edilmediyse: {status: "untrained"}
    - Cache var ama expires_at geçmişse: {status: "stale", ...}
    - Fresh: {status: "fresh", best_rho, sample_count, best_log_loss, ...}

    Inference yolu (/predict?use_ml=true) bu status'a göre fallback yapar.
    """
    from app.data.cache.store import cache_get
    from app.engine.predict_ml import CACHE_KEY, CACHE_SOURCE

    # cache_get TTL'i otomatik kontrol eder — expired ise None döner.
    cached = cache_get(session, source=CACHE_SOURCE, key=CACHE_KEY)
    if cached is None:
        # Stale veya hiç yok ayırt et: row var ama expired mi?
        from sqlalchemy import select as _select
        row = session.execute(
            _select(models.CacheEntry).where(
                models.CacheEntry.source == CACHE_SOURCE,
                models.CacheEntry.key == CACHE_KEY,
            )
        ).scalar_one_or_none()
        if row is None:
            return {"status": "untrained"}
        return {
            "status": "stale",
            "expires_at": row.expires_at.isoformat(),
        }
    return {
        "status": "fresh",
        "best_rho": cached.get("best_rho"),
        "sample_count": cached.get("sample_count"),
        "best_log_loss": cached.get("best_log_loss"),
        "rho_grid": cached.get("rho_grid"),
        "log_loss_per_rho": cached.get("log_loss_per_rho"),
    }


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


# --------------------------------------------------------------------------- #
# Faz M — Manager performance dashboard (C9)
# --------------------------------------------------------------------------- #


@router.get(
    "/manager-performance",
    tags=["admin"],
    summary="TD performans değerlendirmesi — xPts vs actual points",
)
def manager_performance(
    team_external_id: int,
    days: int = 90,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """`predictions` tablosundaki tahminlerden xPts hesaplayıp gerçek puanla kıyaslar.

    xPts = sum(prob_win * 3 + prob_draw * 1) tahmin başına.
    Actual = gerçek sonuçtan o takımın puanı.
    overperformance = actual - xPts (>0: TD ortalamadan iyi sonuç çıkarıyor).
    """
    import json as _json

    from app.sports import football

    cutoff = datetime.now(UTC) - timedelta(days=days)
    rows = list(
        session.execute(
            select(models.Prediction).where(
                models.Prediction.engine == "engine.predict",
                models.Prediction.actual_outcome.is_not(None),
                models.Prediction.reconciled_at.is_not(None),
                models.Prediction.reconciled_at >= cutoff,
            )
        ).scalars()
    )
    # Hangi maçların team_external_id ile ilgili olduğunu bul
    match_ids = {r.match_external_id for r in rows}
    matches = {
        m.external_id: m for m in session.execute(
            select(models.Match).where(
                models.Match.sport == football.SPORT_NAME,
                models.Match.external_id.in_(match_ids),
                (models.Match.home_team_external_id == team_external_id)
                | (models.Match.away_team_external_id == team_external_id),
            )
        ).scalars()
    }
    relevant = [r for r in rows if r.match_external_id in matches]
    if not relevant:
        return {
            "team_id": team_external_id,
            "days": days, "matches_considered": 0,
            "xpts": 0.0, "actual_points": 0,
            "overperformance": 0.0,
            "per_match": [],
        }

    total_xpts = 0.0
    total_actual = 0
    per_match: list[dict[str, Any]] = []
    for r in relevant:
        try:
            p = _json.loads(r.predicted_value_json)
        except _json.JSONDecodeError:
            continue
        m = matches[r.match_external_id]
        is_home = m.home_team_external_id == team_external_id
        # Bu takımın bakış açısından prob_win, prob_draw, prob_loss
        if is_home:
            p_win = float(p.get("prob_home_win", 0.0))
            p_loss = float(p.get("prob_away_win", 0.0))
        else:
            p_win = float(p.get("prob_away_win", 0.0))
            p_loss = float(p.get("prob_home_win", 0.0))
        p_draw = float(p.get("prob_draw", 0.0))
        xpts_match = p_win * 3 + p_draw * 1
        # Actual points
        if r.actual_outcome == "draw":
            actual = 1
        elif (r.actual_outcome == "home" and is_home) or (r.actual_outcome == "away" and not is_home):
            actual = 3
        else:
            actual = 0
        total_xpts += xpts_match
        total_actual += actual
        per_match.append({
            "match_id": r.match_external_id,
            "is_home": is_home,
            "xpts": round(xpts_match, 3),
            "actual_pts": actual,
            "delta": round(actual - xpts_match, 3),
            "p_win": round(p_win, 3),
            "p_draw": round(p_draw, 3),
            "p_loss": round(p_loss, 3),
        })

    return {
        "team_id": team_external_id,
        "days": days,
        "matches_considered": len(per_match),
        "xpts": round(total_xpts, 3),
        "actual_points": total_actual,
        "overperformance": round(total_actual - total_xpts, 3),
        "ppg_xpts": round(total_xpts / len(per_match), 3) if per_match else 0.0,
        "ppg_actual": round(total_actual / len(per_match), 3) if per_match else 0.0,
        "per_match": per_match,
    }


# --------------------------------------------------------------------------- #
# Faz M — Scout watchlist CRUD
# --------------------------------------------------------------------------- #


@router.get(
    "/scout/watchlist",
    tags=["admin"],
    summary="Scout izleme listesi",
)
def scout_watchlist_list(
    user_id: str = "default",
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    from app.scout import list_watchlist

    entries = list_watchlist(session, user_id=user_id)
    return {
        "user_id": user_id,
        "count": len(entries),
        "players": [
            {
                "id": e.id, "player_external_id": e.player_external_id,
                "notes": e.notes,
                "created_at": e.created_at.isoformat(),
                "updated_at": e.updated_at.isoformat(),
            }
            for e in entries
        ],
    }


@router.post(
    "/scout/watchlist",
    tags=["admin"],
    summary="Scout izleme listesine oyuncu ekle (idempotent)",
)
def scout_watchlist_add(
    body: dict[str, Any],
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    from app.scout import add_to_watchlist

    player_id = body.get("player_external_id")
    if not isinstance(player_id, int):
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="player_external_id (int) gerekli")
    user_id = body.get("user_id", "default")
    notes = body.get("notes")
    entry = add_to_watchlist(
        session, player_external_id=player_id, user_id=user_id, notes=notes,
    )
    session.commit()
    return {
        "id": entry.id,
        "player_external_id": entry.player_external_id,
        "user_id": entry.user_id,
    }


@router.delete(
    "/scout/watchlist/{player_external_id}",
    tags=["admin"],
    summary="Scout izleme listesinden oyuncu çıkar",
)
def scout_watchlist_remove(
    player_external_id: int,
    user_id: str = "default",
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    from app.scout import remove_from_watchlist

    deleted = remove_from_watchlist(
        session, player_external_id=player_external_id, user_id=user_id,
    )
    session.commit()
    return {"ok": True, "deleted": deleted}


# --------------------------------------------------------------------------- #
# Player similarity (B6) — scout aracı
# --------------------------------------------------------------------------- #


@router.get(
    "/scout/similar/{player_external_id}",
    tags=["admin"],
    summary="Hedef oyuncuya benzer top-N oyuncu (cosine similarity)",
)
def scout_similar_players(
    player_external_id: int,
    top_n: int = Query(10, ge=1, le=50),
    min_minutes: int = Query(270, ge=0),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """player_appearances'tan per-90 stat vektörleri → cosine similarity.

    Aday havuzu: tenant filter aktifse current tenant'ın oyuncuları.
    """
    from app.engine.player_similarity import compute_similar_players
    from app.sports import football

    target_apps = list(
        session.execute(
            select(models.PlayerAppearance).where(
                models.PlayerAppearance.sport == football.SPORT_NAME,
                models.PlayerAppearance.player_external_id == player_external_id,
            )
        ).scalars()
    )
    if not target_apps:
        raise HTTPException(
            status_code=404,
            detail=f"player {player_external_id} için appearance yok",
        )
    all_apps = list(
        session.execute(
            select(models.PlayerAppearance).where(
                models.PlayerAppearance.sport == football.SPORT_NAME,
            )
        ).scalars()
    )
    candidates_by_pid: dict[int, list[Any]] = {}
    for a in all_apps:
        if a.player_external_id == player_external_id:
            continue
        candidates_by_pid.setdefault(a.player_external_id, []).append(a)
    result = compute_similar_players(
        player_external_id, target_apps, candidates_by_pid,
        top_n=top_n, min_minutes=min_minutes,
    )
    return engine_result_to_dict(result)


# --------------------------------------------------------------------------- #
# Prompt 2 — xG model status
# --------------------------------------------------------------------------- #


@router.get(
    "/xg-model-status",
    tags=["admin"],
    summary="xG modeli artifact durumu (trained/untrained + metrikler)",
)
def xg_model_status() -> dict[str, Any]:
    from app.engine.xg.model_loader import get_model_status

    return get_model_status()


# --------------------------------------------------------------------------- #
# Prompt 3 — Daily decision brief manual trigger + notifications
# --------------------------------------------------------------------------- #


@router.post(
    "/trigger-daily-brief",
    tags=["admin"],
    summary="Daily decision brief job'unu manuel tetikle (test için)",
)
def trigger_daily_brief(
    horizon_days: int = Query(7, ge=1, le=30),
    force: bool = Query(False, description="Idempotency bypass — aynı gün tekrar çalıştır"),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    from app.scheduler.daily_brief import run_daily_brief

    result = run_daily_brief(
        session, horizon_days=horizon_days, force=force,
    )
    return {
        "run_at": result.run_at.isoformat(),
        "tenants_processed": result.tenants_processed,
        "tenants_skipped": result.tenants_skipped,
        "total_succeeded": result.total_succeeded,
        "total_failed": result.total_failed,
        "per_tenant": [
            {
                "tenant_id": r.tenant_id,
                "tenant_slug": r.tenant_slug,
                "matches_processed": r.matches_processed,
                "agents_succeeded": r.agents_succeeded,
                "agents_failed": r.agents_failed,
                "errors": r.errors,
            }
            for r in result.per_tenant
        ],
    }


# --------------------------------------------------------------------------- #
# Faz N — Profesyonel taktiksel modüller (read-only stubs)
#
# Bu endpoint'ler engine'leri HTTP'ye expose eder. Şu an parser/ingest pipeline
# event tablosuna yazmadığı için (Sprint 3 migration 0014 TODO), caller
# StatsBomb adapter'dan event'leri çekip parse_all_events ile geçer.
# Production'da events tablosu dolu olunca DB'den okur.
# --------------------------------------------------------------------------- #


@router.get(
    "/scout/player-role/{player_id}",
    tags=["admin"],
    summary="Oyuncu rol typology (engine.player_role v1)",
)
def scout_player_role(
    player_id: int,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Player_appearances'tan per-90 stat → 8-rol etiketi."""
    from app.engine.player_role import compute_player_role
    from app.sports import football

    apps = list(
        session.execute(
            select(models.PlayerAppearance).where(
                models.PlayerAppearance.sport == football.SPORT_NAME,
                models.PlayerAppearance.player_external_id == player_id,
            )
        ).scalars()
    )
    if not apps:
        raise HTTPException(
            status_code=404,
            detail=f"player {player_id} için appearance yok",
        )
    result = compute_player_role(player_id, apps)
    return engine_result_to_dict(result)


@router.get(
    "/teams/{team_id}/xg-difference",
    tags=["admin"],
    summary="Sezon xG farkı + overperformance (engine.xg_match_graph)",
)
def team_xg_difference(
    team_id: int,
    days: int = Query(90, ge=7, le=365),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Predictions tablosundaki tahminlerden xG farkı.

    NOT: Bu basitleştirilmiş — Shot domain'imizde team_id yok, predictions'tan
    expected goals okuyoruz. Real-event tabanlı sürüm Sprint 3 events ingest'iyle
    gelir.
    """
    import json as _json

    from app.sports import football

    cutoff = datetime.now(UTC) - timedelta(days=days)
    predictions = list(
        session.execute(
            select(models.Prediction).where(
                models.Prediction.engine == "engine.predict",
                models.Prediction.actual_outcome.is_not(None),
                models.Prediction.reconciled_at >= cutoff,
            )
        ).scalars()
    )
    matches = {
        m.external_id: m for m in session.execute(
            select(models.Match).where(
                models.Match.sport == football.SPORT_NAME,
                models.Match.external_id.in_({p.match_external_id for p in predictions}),
                (models.Match.home_team_external_id == team_id)
                | (models.Match.away_team_external_id == team_id),
            )
        ).scalars()
    }
    relevant = [p for p in predictions if p.match_external_id in matches]
    xg_for = 0.0
    xg_against = 0.0
    goals_for = 0
    goals_against = 0
    for p in relevant:
        try:
            pred = _json.loads(p.predicted_value_json)
        except _json.JSONDecodeError:
            continue
        m = matches[p.match_external_id]
        is_home = m.home_team_external_id == team_id
        if is_home:
            xg_for += float(pred.get("expected_home_goals", 0))
            xg_against += float(pred.get("expected_away_goals", 0))
            goals_for += int(m.home_score or 0)
            goals_against += int(m.away_score or 0)
        else:
            xg_for += float(pred.get("expected_away_goals", 0))
            xg_against += float(pred.get("expected_home_goals", 0))
            goals_for += int(m.away_score or 0)
            goals_against += int(m.home_score or 0)
    xgd = xg_for - xg_against
    actual_gd = goals_for - goals_against
    overperf = actual_gd - xgd
    return {
        "team_id": team_id,
        "days": days,
        "matches_analyzed": len(relevant),
        "xg_for": round(xg_for, 3),
        "xg_against": round(xg_against, 3),
        "xg_difference": round(xgd, 3),
        "goals_for": goals_for,
        "goals_against": goals_against,
        "actual_goal_difference": actual_gd,
        "overperformance": round(overperf, 3),
    }


@router.get(
    "/tactical/xt-info",
    tags=["admin"],
    summary="xT engine bilgisi (Karun Singh 2019 grid)",
)
def xt_engine_info() -> dict[str, Any]:
    """Engine'in 12x8 grid değerlerini döndürür (debug + UI ısı haritası için)."""
    from app.engine.xt import GRID_X, GRID_Y, XT_MATRIX
    return {
        "engine": "engine.xt",
        "version": "1",
        "source": "Karun Singh 2019 (Opta-trained)",
        "grid_x": GRID_X,
        "grid_y": GRID_Y,
        "matrix": [list(row) for row in XT_MATRIX],
    }


@router.get(
    "/tactical/ppda-info",
    tags=["admin"],
    summary="PPDA engine bilgisi (pres zone + literatür referans)",
)
def ppda_engine_info() -> dict[str, Any]:
    from app.engine.ppda import PRESS_ZONE_X_MIN
    return {
        "engine": "engine.ppda",
        "version": "1",
        "press_zone_x_min": PRESS_ZONE_X_MIN,
        "literature_reference": {
            "klopp_liverpool_2018_2019": 8.5,
            "guardiola_city_2018_2019": 10.0,
            "league_average": 14.0,
            "low_block_team": 18.0,
        },
        "interpretation": (
            "PPDA = rakip pasları (hücum yarısı) / takım defansif aksiyonları "
            "(hücum yarısı). Düşük = yüksek pres."
        ),
    }


@router.get(
    "/tactical/match-phase/{match_id}",
    tags=["admin"],
    summary="Maç phase analizi (1H/2H/ET split — engine.match_phase)",
)
def match_phase_analysis(
    match_id: int,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Bir maç için phase başına agregat.

    Şu an event ingest pipeline yok → boş response. Production'da
    events tablosundan okur (Sprint 3+).
    """
    from app.sports import football

    match = session.execute(
        select(models.Match).where(
            models.Match.sport == football.SPORT_NAME,
            models.Match.external_id == match_id,
        )
    ).scalar_one_or_none()
    if match is None:
        raise HTTPException(status_code=404, detail=f"match {match_id} yok")
    return {
        "match_id": match_id,
        "home_team_id": match.home_team_external_id,
        "away_team_id": match.away_team_external_id,
        "status": match.status,
        "home_score": match.home_score,
        "away_score": match.away_score,
        "note": (
            "Phase analysis production'da events tablosu (Sprint 3+) ile aktif olur. "
            "Bu endpoint şu an match info döndürüyor; engine.match_phase saf hesap "
            "çağrısı için caller event listeleri geçer."
        ),
    }


# --------------------------------------------------------------------------- #
# Tactical Profile — events tablosu üstünde 30 engine'in batch çağırımı
# --------------------------------------------------------------------------- #


@router.get(
    "/teams/{team_id}/tactical-profile",
    tags=["admin"],
    summary="Takım taktiksel profil (20+ engine birleşik)",
)
def team_tactical_profile(
    team_id: int,
    last_n: int = Query(default=10, ge=1, le=50),
    opponent_id: int | None = Query(default=None,
        description="Field tilt / coaching identity için rakip referansı"),
    use_cache: bool = Query(default=True),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Bir takımın son N maçındaki olaylardan 20+ engine'in batch çıktısı.

    Events tablosu boşsa `events_loaded=0` döner ve ana metrikler `null` olur —
    ingest pipeline çalıştırılması beklenir.
    `use_cache=true` (default): 1 saat TTL; geçersiz kıl
    `/admin/tactical-cache/clear`.
    """
    cache_key = f"team_profile:{team_id}:{last_n}:{opponent_id or 'none'}"
    if use_cache:
        cached = cache_get(session, source=TACTICAL_CACHE_SOURCE, key=cache_key)
        if cached is not None:
            cached["_cached"] = True
            return cached
    from app.data.loaders import load_team_events
    from app.engine.build_up_pattern import compute_build_up_pattern
    from app.engine.channel_preference import compute_channel_preference
    from app.engine.coaching_identity import compute_coaching_identity
    from app.engine.compactness import compute_compactness
    from app.engine.counter_press_triggers import compute_counter_press_triggers
    from app.engine.cross_effectiveness import compute_cross_effectiveness
    from app.engine.cutback_frequency import compute_cutback_frequency
    from app.engine.defensive_duels import compute_defensive_duels
    from app.engine.defensive_line import compute_defensive_line
    from app.engine.direct_play import compute_direct_play
    from app.engine.field_tilt import compute_field_tilt
    from app.engine.final_third_entries import compute_final_third_entries
    from app.engine.possession_quality import compute_possession_quality
    from app.engine.ppda import compute_ppda
    from app.engine.press_resistance import compute_press_resistance
    from app.engine.pressing_trigger import compute_pressing_trigger
    from app.engine.recovery_zone_heat import compute_recovery_zone_heat
    from app.engine.set_piece_zones import compute_set_piece_zones
    from app.engine.tempo import compute_tempo
    from app.engine.transition import compute_transition
    from app.engine.xt import compute_team_xt

    loaded = load_team_events(session, team_id, last_n=last_n)
    if loaded.total == 0:
        return {
            "team_id": team_id,
            "last_n": last_n,
            "events_loaded": 0,
            "matches_analyzed": [],
            "note": "events tablosunda bu takım için kayıt yok; ingest pipeline çağırın.",
        }

    matches_n = len(loaded.match_ids)
    p = loaded.passes
    c = loaded.carries
    d = loaded.defensive_actions
    s = loaded.shots
    # Şutu takım filtre etmek gerekiyor — Shot.team yok; bu metriklerde
    # caller event teamlerini varsayıyor: aynı maçtaki tüm şutları gönderiyoruz,
    # set_piece için takım-spesifik filtreyi pas sahibiyle yapamayız → tüm şut.
    # Konservatif: takım filtresiz pass'ı tüm passes; team_xt için sadece
    # bizim takım pasları zaten içeride filtre ediliyor.

    def _safe(fn):
        try:
            return engine_result_to_dict(fn())
        except (ValueError, ZeroDivisionError, IndexError, KeyError, TypeError) as e:
            return {"error": str(e)}

    profile = {
        "ppda": _safe(lambda: compute_ppda(team_id, p, d, matches_analyzed=matches_n)),
        "pressing_trigger": _safe(lambda: compute_pressing_trigger(
            team_id, p, d, matches_analyzed=matches_n)),
        "defensive_line": _safe(lambda: compute_defensive_line(
            team_id, d, matches_analyzed=matches_n)),
        "compactness": _safe(lambda: compute_compactness(
            team_id, p, d, matches_analyzed=matches_n)),
        "transition": _safe(lambda: compute_transition(
            team_id, d, s, matches_analyzed=matches_n)),
        "recovery_zone_heat": _safe(lambda: compute_recovery_zone_heat(
            team_id, d, matches_analyzed=matches_n)),
        "counter_press_triggers": _safe(lambda: compute_counter_press_triggers(
            team_id, p, d, matches_analyzed=matches_n)),
        "direct_play": _safe(lambda: compute_direct_play(
            team_id, p, matches_analyzed=matches_n)),
        "tempo": _safe(lambda: compute_tempo(
            team_id, p, matches_analyzed=matches_n)),
        "possession_quality": _safe(lambda: compute_possession_quality(
            team_id, p, s, matches_analyzed=matches_n)),
        "channel_preference": _safe(lambda: compute_channel_preference(
            team_id, p, matches_analyzed=matches_n)),
        "final_third_entries": _safe(lambda: compute_final_third_entries(
            team_id, p, c, matches_analyzed=matches_n)),
        "cross_effectiveness": _safe(lambda: compute_cross_effectiveness(
            team_id, p, s, matches_analyzed=matches_n)),
        "cutback_frequency": _safe(lambda: compute_cutback_frequency(
            team_id, p, s, matches_analyzed=matches_n)),
        "defensive_duels": _safe(lambda: compute_defensive_duels(
            team_external_id=team_id, all_def_actions=d, matches_analyzed=matches_n)),
        "press_resistance": _safe(lambda: compute_press_resistance(
            team_external_id=team_id, all_passes=p, all_def_actions=d,
            matches_analyzed=matches_n)),
        "set_piece_zones": _safe(lambda: compute_set_piece_zones(
            team_id, s, matches_analyzed=matches_n)),
        "build_up_pattern": _safe(lambda: compute_build_up_pattern(
            team_id, p, s, matches_analyzed=matches_n)),
        "team_xt": _safe(lambda: compute_team_xt(team_id, p, c)),
    }

    # Field tilt + coaching identity rakip gerektirir
    if opponent_id is not None:
        profile["field_tilt"] = _safe(lambda: compute_field_tilt(team_id, opponent_id, p))
        profile["coaching_identity"] = _safe(lambda: compute_coaching_identity(
            team_id, opponent_id, p, d, s, matches_analyzed=matches_n))

    response = {
        "team_id": team_id,
        "last_n": last_n,
        "matches_analyzed": loaded.match_ids,
        "events_loaded": loaded.total,
        "event_counts": {
            "passes": len(p), "carries": len(c),
            "defensive_actions": len(d), "shots": len(s),
        },
        "tactical_profile": profile,
        "_cached": False,
    }
    if use_cache:
        cache_set(
            session, source=TACTICAL_CACHE_SOURCE, key=cache_key,
            value=response, ttl_seconds=TACTICAL_CACHE_TTL_SECONDS,
        )
        session.commit()
    return response


@router.post(
    "/tactical-cache/clear",
    tags=["admin"],
    summary="Tactical profile/trend cache temizle (event ingest sonrası)",
)
def tactical_cache_clear(
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """tactical_profile source'lu tüm cache satırlarını sil."""
    rows = session.execute(
        select(models.CacheEntry).where(
            models.CacheEntry.source == TACTICAL_CACHE_SOURCE,
        )
    ).scalars().all()
    n = 0
    for r in rows:
        session.delete(r)
        n += 1
    session.commit()
    return {"deleted": n}


@router.get(
    "/players/{player_id}/tactical-profile",
    tags=["admin"],
    summary="Oyuncu taktiksel profil (8 engine birleşik)",
)
def player_tactical_profile(
    player_id: int,
    last_n: int = Query(default=10, ge=1, le=50),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Bir oyuncunun son N maçındaki engine'leri batchle."""
    from app.data.loaders import load_player_events
    from app.engine.carries_into_final_third import compute_carries_into_final_third
    from app.engine.off_ball_runs import compute_off_ball_runs
    from app.engine.overperformance import compute_overperformance
    from app.engine.press_resistance import compute_press_resistance
    from app.engine.progressive_passes import compute_progressive_passes
    from app.engine.vaep import compute_vaep
    from app.engine.xa import compute_player_xa
    from app.engine.xt import compute_player_xt

    loaded, meta = load_player_events(session, player_id, last_n=last_n)
    if loaded.total == 0:
        return {
            "player_id": player_id,
            "events_loaded": 0,
            "meta": meta,
            "note": "events tablosunda bu oyuncu için kayıt yok.",
        }

    p = loaded.passes
    c = loaded.carries
    d = loaded.defensive_actions
    s = loaded.shots
    minutes = meta.get("minutes_played", 0.0)
    team_id = meta.get("team_external_id")
    matches_n = meta.get("matches_analyzed", 1)

    def _safe(fn):
        try:
            return engine_result_to_dict(fn())
        except (ValueError, ZeroDivisionError, IndexError, KeyError, TypeError) as e:
            return {"error": str(e)}

    profile = {
        "player_xt": _safe(lambda: compute_player_xt(player_id, p, c)),
        "player_xa": _safe(lambda: compute_player_xa(
            player_id, p, s, minutes_played=int(minutes))),
        "press_resistance": _safe(lambda: compute_press_resistance(
            player_external_id=player_id, all_passes=p, all_def_actions=d,
            matches_analyzed=matches_n)),
        "overperformance": _safe(lambda: compute_overperformance(
            player_external_id=player_id, all_passes=p, all_shots=s,
            matches_analyzed=matches_n)),
        "progressive_passes": _safe(lambda: compute_progressive_passes(
            player_external_id=player_id, all_passes=p,
            player_minutes_played=minutes, matches_analyzed=matches_n)),
        "carries_into_final_third": _safe(lambda: compute_carries_into_final_third(
            player_external_id=player_id, all_carries=c,
            player_minutes_played=minutes, matches_analyzed=matches_n)),
        "vaep": _safe(lambda: compute_vaep(
            player_external_id=player_id, all_passes=p, all_carries=c, all_shots=s,
            minutes_played=minutes, matches_analyzed=matches_n)),
    }
    if team_id is not None:
        profile["off_ball_runs"] = _safe(lambda: compute_off_ball_runs(
            player_external_id=player_id, team_external_id=team_id,
            all_carries=c, all_passes=p,
            player_minutes_played=minutes, matches_analyzed=matches_n))

    return {
        "player_id": player_id,
        "meta": meta,
        "events_loaded": loaded.total,
        "tactical_profile": profile,
    }


@router.get(
    "/teams/{team_id}/tactical-trend",
    tags=["admin"],
    summary="Takım sezon-boyu trend (PPDA, field_tilt, dominance, xT, possession)",
)
def team_tactical_trend(
    team_id: int,
    last_n: int = Query(default=10, ge=2, le=50),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Bir takımın son N maçındaki 5 ana metriğin maç-başı zaman serisi + trend.

    Tek-maç tactical-profile'den farklı: aynı engine'i her maça ayrı uygulayıp
    çıkan değerleri zaman serisi olarak gösterir + linear regression slope.

    Metrikler:
    - PPDA            (lower is better — düşük = yoğun pres)
    - Field tilt %     (higher is better için biz, opponent yokken 0.5 baseline)
    - xT total        (higher is better)
    - Possession %     (higher is better)
    - Match dominance score (higher is better)
    """
    from app.data.loaders import load_match_events
    from app.engine.field_tilt import compute_field_tilt
    from app.engine.match_dominance import compute_match_dominance
    from app.engine.ppda import compute_ppda
    from app.engine.tactical_trend import compute_tactical_trend
    from app.engine.xt import compute_team_xt

    # Son N maçı al (FINISHED), kronolojik sıralı (eski → yeni)
    matches = list(session.execute(
        select(models.Match).where(
            models.Match.sport == football.SPORT_NAME,
            (models.Match.home_team_external_id == team_id)
            | (models.Match.away_team_external_id == team_id),
            models.Match.status.in_(football.FINISHED_STATUSES),
        ).order_by(models.Match.kickoff.desc()).limit(last_n)
    ).scalars())
    if not matches:
        return {
            "team_id": team_id, "last_n": last_n,
            "matches_analyzed": 0,
            "note": "Bu takımın FINISHED maçı yok",
        }
    matches.reverse()  # kronolojik

    series: dict[str, list[float]] = {
        "ppda": [], "field_tilt": [], "team_xt": [],
        "possession_share": [], "dominance_score": [],
    }
    match_meta: list[dict[str, Any]] = []
    for m in matches:
        loaded = load_match_events(session, m.external_id)
        if loaded.total == 0:
            continue
        opp_id = (
            m.away_team_external_id if m.home_team_external_id == team_id
            else m.home_team_external_id
        )
        try:
            ppda = compute_ppda(team_id, loaded.passes, loaded.defensive_actions).value
            tilt = compute_field_tilt(team_id, opp_id, loaded.passes).value
            xt = compute_team_xt(team_id, loaded.passes, loaded.carries).value
            team_pass = sum(1 for p in loaded.passes if p.team_external_id == team_id)
            opp_pass = sum(1 for p in loaded.passes if p.team_external_id == opp_id)
            poss = team_pass / (team_pass + opp_pass) if (team_pass + opp_pass) else 0.5
            from app.data.loaders import shots_by_team
            team_s = shots_by_team(loaded.shots, team_id)
            opp_s = shots_by_team(loaded.shots, opp_id)
            dom = compute_match_dominance(
                team_external_id=team_id, opponent_team_external_id=opp_id,
                team_shots=team_s, opponent_shots=opp_s,
                all_passes=loaded.passes, team_carries=loaded.carries,
                opponent_carries=loaded.carries,
            ).value
        except (ValueError, ZeroDivisionError, KeyError, TypeError):
            continue
        series["ppda"].append(ppda.ppda)
        series["field_tilt"].append(tilt.team_a_tilt)
        series["team_xt"].append(xt.total_xt)
        series["possession_share"].append(round(poss, 3))
        series["dominance_score"].append(dom.dominance_score)
        match_meta.append({
            "match_id": m.external_id,
            "kickoff": m.kickoff.isoformat() if m.kickoff else None,
            "opp_id": opp_id,
            "score": f"{m.home_score}-{m.away_score}",
        })

    if not match_meta:
        return {
            "team_id": team_id, "last_n": last_n,
            "matches_analyzed": 0,
            "note": "Hiçbir maç için event ingest yapılmamış",
        }

    higher_better = {
        "ppda": False, "field_tilt": True, "team_xt": True,
        "possession_share": True, "dominance_score": True,
    }
    trends: dict[str, dict[str, Any]] = {}
    for metric, vals in series.items():
        trend = compute_tactical_trend(
            metric, vals,
            higher_is_better=higher_better[metric],
            subject_type="team", subject_id=team_id,
        ).value
        trends[metric] = {
            "series": list(trend.series),
            "mean": trend.mean,
            "slope": trend.slope,
            "direction": trend.direction,
            "biggest_shift": trend.biggest_match_to_match_shift,
            "biggest_shift_match_idx": trend.biggest_shift_match_idx,
            "biggest_shift_match_id": (
                match_meta[trend.biggest_shift_match_idx]["match_id"]
                if trend.biggest_shift_match_idx < len(match_meta) else None
            ),
        }

    return {
        "team_id": team_id, "last_n": last_n,
        "matches_analyzed": len(match_meta),
        "matches": match_meta,
        "trends": trends,
    }


# --------------------------------------------------------------------------- #
# Decision Audit Log — TD'nin maç-içi hamleleri (Faz P)
# --------------------------------------------------------------------------- #


@router.post(
    "/matches/{match_id}/decisions",
    tags=["admin"],
    summary="TD hamlesi kaydet (substitution / formation_change / tactical_instruction)",
)
def create_decision(
    match_id: int,
    payload: dict[str, Any],
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Bir kararı audit log'a yaz.

    Beklenen payload:
    {
        "team_external_id": int,
        "minute": float,
        "period": int (default 1),
        "decision_type": "substitution" | "formation_change" | "tactical_instruction" | "other",
        "subject_player_external_id": int | null,
        "related_player_external_id": int | null,
        "notes": str (optional),
        "payload_json": dict (optional)
    }
    """
    import json as _json
    from datetime import UTC
    from datetime import datetime as _datetime

    required = ("team_external_id", "minute", "decision_type")
    missing = [k for k in required if k not in payload]
    if missing:
        raise HTTPException(
            status_code=400, detail=f"eksik alan: {missing}",
        )
    allowed_types = {"substitution", "formation_change",
                     "tactical_instruction", "other"}
    if payload["decision_type"] not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"decision_type {allowed_types} içinde olmalı",
        )

    row = models.Decision(
        sport=football.SPORT_NAME,
        match_external_id=match_id,
        team_external_id=int(payload["team_external_id"]),
        minute=float(payload["minute"]),
        period=int(payload.get("period", 1)),
        decision_type=payload["decision_type"],
        subject_player_external_id=payload.get("subject_player_external_id"),
        related_player_external_id=payload.get("related_player_external_id"),
        notes=payload.get("notes"),
        payload_json=_json.dumps(payload.get("payload_json"))
            if payload.get("payload_json") else None,
        by_user_id=payload.get("by_user_id"),
        created_at=_datetime.now(UTC),
        # Faz 8 #4 — öneri kaynaklı mıydı + o anki güven + bağlam
        recommended=bool(payload.get("recommended", False)),
        confidence=(float(payload["confidence"])
                    if payload.get("confidence") is not None else None),
        context_json=_json.dumps(payload.get("context_json"))
            if payload.get("context_json") else None,
        outcome="pending",
    )
    session.add(row)
    session.commit()
    return {
        "id": row.id, "match_id": match_id,
        "decision_type": row.decision_type, "minute": row.minute,
        "recommended": row.recommended, "outcome": row.outcome,
        "created_at": row.created_at.isoformat(),
    }


@router.get(
    "/matches/{match_id}/decisions",
    tags=["admin"],
    summary="Bir maçtaki kayıtlı TD kararlarını listele",
)
def list_decisions(
    match_id: int,
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    rows = list(session.execute(
        select(models.Decision).where(
            models.Decision.sport == football.SPORT_NAME,
            models.Decision.match_external_id == match_id,
        ).order_by(models.Decision.minute)
    ).scalars())
    return [
        {
            "id": r.id,
            "team_id": r.team_external_id,
            "minute": r.minute,
            "period": r.period,
            "decision_type": r.decision_type,
            "subject_player_id": r.subject_player_external_id,
            "related_player_id": r.related_player_external_id,
            "notes": r.notes,
            "recommended": r.recommended,
            "confidence": r.confidence,
            "outcome": r.outcome,
            "outcome_value": r.outcome_value,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@router.post(
    "/decisions/{decision_id}/outcome",
    tags=["admin"],
    summary="Karar sonucunu kaydet (Faz 8 #4 — feedback loop)",
)
def record_decision_outcome(
    decision_id: int,
    payload: dict[str, Any],
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Bir kararın uygulandıktan sonraki sonucunu işle.

    payload: {"outcome": "positive"|"negative"|"neutral",
              "outcome_value": float (opt), "outcome_notes": str (opt)}
    Bu skor `decisions.feedback` üzerinden güven skoruna (#2) geri beslenir.
    """
    from datetime import UTC
    from datetime import datetime as _datetime

    allowed = {"positive", "negative", "neutral", "pending"}
    outcome = payload.get("outcome")
    if outcome not in allowed:
        raise HTTPException(
            status_code=400, detail=f"outcome {allowed} içinde olmalı",
        )
    row = session.get(models.Decision, decision_id)
    if row is None:
        raise HTTPException(status_code=404,
                            detail=f"decision {decision_id} yok")
    row.outcome = outcome
    if payload.get("outcome_value") is not None:
        row.outcome_value = float(payload["outcome_value"])
    row.outcome_notes = payload.get("outcome_notes")
    row.outcome_recorded_at = _datetime.now(UTC)
    session.commit()
    return {
        "id": row.id, "outcome": row.outcome,
        "outcome_value": row.outcome_value,
        "recorded_at": row.outcome_recorded_at.isoformat(),
    }


@router.get(
    "/teams/{team_id}/decisions/feedback",
    tags=["admin"],
    summary="Karar tipine göre geçmiş isabet oranı (Faz 8 #4 → güven skoru)",
)
def decisions_feedback(
    team_id: int,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Bu takımın geçmiş kararlarının decision_type bazlı isabet oranı.
    context_engine güven skorunu (#2) bu oranla kalibre eder."""
    rows = list(session.execute(
        select(models.Decision).where(
            models.Decision.sport == football.SPORT_NAME,
            models.Decision.team_external_id == team_id,
            models.Decision.outcome.in_(("positive", "negative")),
        )
    ).scalars())
    by_type: dict[str, dict[str, int]] = {}
    for r in rows:
        b = by_type.setdefault(r.decision_type, {"positive": 0, "negative": 0})
        if r.outcome in ("positive", "negative"):
            b[r.outcome] += 1
    summary = {
        dtype: {
            "n": b["positive"] + b["negative"],
            "hit_rate": round(b["positive"] / (b["positive"] + b["negative"]), 3),
        }
        for dtype, b in by_type.items()
    }
    return {"team_id": team_id, "evaluated": len(rows), "by_decision_type": summary}


@router.get(
    "/matches/{match_id}/decisions/learning",
    tags=["admin"],
    summary="Post-match learning: TD kararının sonuca etkisi (causal proxy)",
)
def decisions_learning(
    match_id: int,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Bir maçtaki tüm kararlardan sonra ne oldu? Basit causal proxy:
    karar dakikasından sonra takımın xT, possession, dominance score'u
    nasıl değişti.

    Algoritma: her karar için pre-window (karar-15dk..karar) vs
    post-window (karar..karar+15dk) takım metric'leri karşılaştır.
    """
    from app.data.loaders import load_match_events
    from app.engine.match_dominance import compute_match_dominance
    from app.engine.xt import compute_team_xt

    match = session.execute(
        select(models.Match).where(
            models.Match.sport == football.SPORT_NAME,
            models.Match.external_id == match_id,
        )
    ).scalar_one_or_none()
    if match is None:
        raise HTTPException(status_code=404, detail=f"match {match_id} yok")
    loaded = load_match_events(session, match_id)
    if loaded.total == 0:
        return {"match_id": match_id, "events_loaded": 0,
                "note": "Event ingest yapılmamış"}

    decisions = list(session.execute(
        select(models.Decision).where(
            models.Decision.sport == football.SPORT_NAME,
            models.Decision.match_external_id == match_id,
        ).order_by(models.Decision.minute)
    ).scalars())
    if not decisions:
        return {"match_id": match_id, "decisions": 0,
                "note": "Bu maç için decision log yok"}

    WIN = 15.0
    impacts = []
    for d in decisions:
        team_id = d.team_external_id
        opp_id = (match.away_team_external_id if team_id == match.home_team_external_id
                  else match.home_team_external_id)
        pre_passes = [p for p in loaded.passes
                       if d.minute - WIN <= p.minute < d.minute]
        post_passes = [p for p in loaded.passes
                        if d.minute <= p.minute < d.minute + WIN]
        pre_carries = [c for c in loaded.carries
                        if d.minute - WIN <= c.minute < d.minute]
        post_carries = [c for c in loaded.carries
                         if d.minute <= c.minute < d.minute + WIN]
        pre_shots = [s for s in loaded.shots
                      if d.minute - WIN <= s.minute < d.minute]
        post_shots = [s for s in loaded.shots
                       if d.minute <= s.minute < d.minute + WIN]
        try:
            pre_xt = compute_team_xt(team_id, pre_passes, pre_carries).value.total_xt
            post_xt = compute_team_xt(team_id, post_passes, post_carries).value.total_xt
            pre_dom = compute_match_dominance(
                team_external_id=team_id, opponent_team_external_id=opp_id,
                team_shots=pre_shots, opponent_shots=pre_shots,
                all_passes=pre_passes, team_carries=pre_carries,
                opponent_carries=pre_carries,
            ).value.dominance_score
            post_dom = compute_match_dominance(
                team_external_id=team_id, opponent_team_external_id=opp_id,
                team_shots=post_shots, opponent_shots=post_shots,
                all_passes=post_passes, team_carries=post_carries,
                opponent_carries=post_carries,
            ).value.dominance_score
        except (ValueError, ZeroDivisionError, KeyError, TypeError):
            continue
        impacts.append({
            "decision_id": d.id,
            "minute": d.minute,
            "decision_type": d.decision_type,
            "pre_xt": round(pre_xt, 3),
            "post_xt": round(post_xt, 3),
            "xt_delta": round(post_xt - pre_xt, 3),
            "pre_dominance": pre_dom,
            "post_dominance": post_dom,
            "dominance_delta": round(post_dom - pre_dom, 2),
            "verdict": (
                "positive" if post_xt - pre_xt > 0.1 and post_dom - pre_dom > 0
                else "negative" if post_xt - pre_xt < -0.1 and post_dom - pre_dom < 0
                else "neutral"
            ),
        })
    return {
        "match_id": match_id,
        "decisions_analyzed": len(impacts),
        "window_minutes": WIN,
        "impacts": impacts,
    }


@router.get(
    "/teams/{team_id}/set-piece-pattern-history",
    tags=["admin"],
    summary="Rakibin geçmiş set-piece pattern'leri (canlı maç alert için)",
)
def team_set_piece_pattern_history(
    team_id: int,
    last_n: int = Query(default=5, ge=1, le=20),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Bir takımın (genelde rakip) son N maçındaki set-piece şutlarını
    pattern olarak özetler. Canlı maçta rakip korner kazandığında bu
    alert_text'i gösterir."""
    from app.data.loaders import load_team_events
    from app.engine.set_piece_pattern_history import (
        compute_set_piece_pattern_history,
    )
    loaded = load_team_events(session, team_id, last_n=last_n)
    if loaded.total == 0:
        return {
            "team_id": team_id, "last_n": last_n, "events_loaded": 0,
            "note": "events tablosunda kayıt yok",
        }
    result = compute_set_piece_pattern_history(
        team_id, loaded.shots, matches_analyzed=len(loaded.match_ids),
    )
    return engine_result_to_dict(result)


@router.get(
    "/matches/{match_id}/live-sub-recommendation",
    tags=["admin"],
    summary="Canlı maç oyuncu değişikliği önerisi (retrospective demo da)",
)
def match_live_sub_recommendation(
    match_id: int,
    my_team_id: int = Query(...),
    current_minute: float = Query(..., ge=0, le=120),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Belirli bir maç dakikasında top 3 sub önerisi (fatigue + skor + dakika)."""
    from app.data.loaders import load_match_events
    from app.engine.live_sub_recommendation import compute_live_sub_recommendation

    match = session.execute(
        select(models.Match).where(
            models.Match.sport == football.SPORT_NAME,
            models.Match.external_id == match_id,
        )
    ).scalar_one_or_none()
    if match is None:
        raise HTTPException(status_code=404, detail=f"match {match_id} yok")

    loaded = load_match_events(session, match_id)
    if loaded.total == 0:
        return {"match_id": match_id, "events_loaded": 0,
                "note": "Bu maç için event ingest yapılmamış"}

    home_id = match.home_team_external_id
    my_score = match.home_score if my_team_id == home_id else match.away_score
    opp_score = match.away_score if my_team_id == home_id else match.home_score
    passes = [p for p in loaded.passes if p.minute <= current_minute]
    defs = [d for d in loaded.defensive_actions if d.minute <= current_minute]
    result = compute_live_sub_recommendation(
        my_team_id, passes, defs,
        current_minute=current_minute,
        my_score=my_score or 0, opponent_score=opp_score or 0,
    )
    return engine_result_to_dict(result)


@router.get(
    "/players/{player_id}/tactical-trend",
    tags=["admin"],
    summary="Oyuncu sezon-boyu trend (xT, xA, VAEP, prog_passes, press_resistance)",
)
def player_tactical_trend(
    player_id: int,
    last_n: int = Query(default=10, ge=2, le=50),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Bir oyuncunun son N maçındaki 5 metric zaman serisi + trend."""
    from app.data.loaders import load_match_events
    from app.engine.press_resistance import compute_press_resistance
    from app.engine.progressive_passes import compute_progressive_passes
    from app.engine.tactical_trend import compute_tactical_trend
    from app.engine.vaep import compute_vaep
    from app.engine.xa import compute_player_xa
    from app.engine.xt import compute_player_xt

    # PlayerAppearance üzerinden son N maçı al (kronolojik için tersine çevir)
    appearances = list(session.execute(
        select(models.PlayerAppearance).where(
            models.PlayerAppearance.sport == football.SPORT_NAME,
            models.PlayerAppearance.player_external_id == player_id,
        ).order_by(models.PlayerAppearance.kickoff.desc()).limit(last_n)
    ).scalars())
    if not appearances:
        return {
            "player_id": player_id, "last_n": last_n,
            "matches_analyzed": 0,
            "note": "Bu oyuncu için PlayerAppearance yok",
        }
    appearances.reverse()  # kronolojik

    series: dict[str, list[float]] = {
        "xt_added": [], "xa_total": [], "vaep_per_90": [],
        "progressive_per_90": [], "press_resistance": [],
    }
    match_meta: list[dict[str, Any]] = []
    for a in appearances:
        loaded = load_match_events(session, a.match_external_id)
        if loaded.total == 0:
            continue
        try:
            xt = compute_player_xt(player_id, loaded.passes, loaded.carries).value
            xa = compute_player_xa(
                player_id, loaded.passes, loaded.shots,
                minutes_played=a.minutes or 90,
            ).value
            vaep = compute_vaep(
                player_external_id=player_id, all_passes=loaded.passes,
                all_carries=loaded.carries, all_shots=loaded.shots,
                minutes_played=float(a.minutes or 90),
            ).value
            prog = compute_progressive_passes(
                player_external_id=player_id, all_passes=loaded.passes,
                player_minutes_played=float(a.minutes or 90),
            ).value
            press = compute_press_resistance(
                player_external_id=player_id, all_passes=loaded.passes,
                all_def_actions=loaded.defensive_actions,
            ).value
        except (ValueError, ZeroDivisionError, KeyError, TypeError):
            continue
        series["xt_added"].append(xt.xt_per_90)
        series["xa_total"].append(xa.xa_per_90)
        series["vaep_per_90"].append(vaep.vaep_per_90 or 0.0)
        series["progressive_per_90"].append(prog.progressive_per_90 or 0.0)
        series["press_resistance"].append(press.completion_rate_under_press)
        match_meta.append({
            "match_id": a.match_external_id,
            "kickoff": a.kickoff.isoformat() if a.kickoff else None,
            "minutes": a.minutes,
        })

    if not match_meta:
        return {
            "player_id": player_id, "last_n": last_n,
            "matches_analyzed": 0,
            "note": "Hiçbir maç için event ingest yapılmamış",
        }

    higher_better = {
        "xt_added": True, "xa_total": True, "vaep_per_90": True,
        "progressive_per_90": True, "press_resistance": True,
    }
    trends: dict[str, dict[str, Any]] = {}
    for metric, vals in series.items():
        trend = compute_tactical_trend(
            metric, vals,
            higher_is_better=higher_better[metric],
            subject_type="player", subject_id=player_id,
        ).value
        trends[metric] = {
            "series": list(trend.series),
            "mean": trend.mean,
            "slope": trend.slope,
            "direction": trend.direction,
            "biggest_shift": trend.biggest_match_to_match_shift,
            "biggest_shift_match_idx": trend.biggest_shift_match_idx,
            "biggest_shift_match_id": (
                match_meta[trend.biggest_shift_match_idx]["match_id"]
                if trend.biggest_shift_match_idx < len(match_meta) else None
            ),
        }

    return {
        "player_id": player_id, "last_n": last_n,
        "matches_analyzed": len(match_meta),
        "matches": match_meta,
        "trends": trends,
    }


@router.get(
    "/matches/{match_id}/halftime-brief",
    tags=["admin"],
    summary="Devre arası analiz brief (1. yarı event'leri üzerinde 7 engine + AI)",
)
def match_halftime_brief(
    match_id: int,
    my_team_id: int = Query(..., description="Brief'in hangi takım için olacağı"),
    persist: bool = Query(default=True, description="agent_outputs'a kaydet"),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Devre arası bilgi paneli — 1. yarı event'lerinden 7+ engine + AI brief.

    `persist=true` (default): sonucu agent_outputs tablosuna idempotent yaz
    (aynı match + team için tekrar çağırılırsa update). History endpoint
    `/admin/halftime-brief-history` aynı satırları döner.
    """
    from app.agents import HalftimeAnalysisAgent
    from app.agents.store import save_agent_output

    agent = HalftimeAnalysisAgent()
    try:
        result = agent.run(
            session,
            context={
                "match_external_id": match_id,
                "my_team_external_id": my_team_id,
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    if persist:
        # my_team_id'yi agent_version'a encode et — iki takım için ayrı satır
        save_agent_output(
            session, result=result,
            agent_name=agent.name,
            agent_version=f"{agent.version}-team{my_team_id}",
        )
        session.commit()

    return result.output_json


@router.get(
    "/halftime-brief-history",
    tags=["admin"],
    summary="Kaydedilmiş devre arası brief'lerin listesi",
)
def halftime_brief_history(
    limit: int = Query(default=20, ge=1, le=100),
    match_id: int | None = Query(default=None),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    """agent_outputs'tan halftime_analysis tipindeki kayıtları döner."""
    stmt = select(models.AgentOutput).where(
        models.AgentOutput.agent_name == "halftime_analysis",
    )
    if match_id is not None:
        stmt = stmt.where(models.AgentOutput.subject_id == match_id)
    stmt = stmt.order_by(desc(models.AgentOutput.updated_at)).limit(limit)
    rows = list(session.execute(stmt).scalars())
    return [
        {
            "id": r.id,
            "agent_version": r.agent_version,
            "match_id": r.subject_id,
            "summary": r.summary,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }
        for r in rows
    ]


@router.post(
    "/vaep/train",
    tags=["admin"],
    summary="VAEP tabular model train (events tablosundan zone-bin lookup öğren)",
)
def vaep_train(
    min_samples: int = Query(default=100, ge=10),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """VAEP v2-tabular modelini train et + cache'e yaz."""
    from app.engine.vaep import NotEnoughTrainingData, train_vaep_model

    tenant_id = session.info.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id session.info'da yok")
    try:
        report = train_vaep_model(
            session, tenant_id=tenant_id, min_samples=min_samples,
        )
    except NotEnoughTrainingData as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    session.commit()
    return {
        "sample_count": report.sample_count,
        "matches_used": report.matches_used,
        "zones": report.zones,
        "cache_written": report.cache_written,
        "score_lookup_top3": sorted(
            report.score_lookup.items(), key=lambda x: -x[1],
        )[:3],
        "concede_lookup_top3": sorted(
            report.concede_lookup.items(), key=lambda x: -x[1],
        )[:3],
    }


@router.get(
    "/matches/{match_id}/dominance",
    tags=["admin"],
    summary="Tek maç dominance + match_phase (composite + split)",
)
def match_dominance_endpoint(
    match_id: int,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Bir maç için composite dominance skoru + 1H/2H phase split."""
    from app.data.loaders import load_match_events
    from app.engine.match_dominance import compute_match_dominance
    from app.engine.match_phase import compute_match_phases

    match = session.execute(
        select(models.Match).where(
            models.Match.sport == football.SPORT_NAME,
            models.Match.external_id == match_id,
        )
    ).scalar_one_or_none()
    if match is None:
        raise HTTPException(status_code=404, detail=f"match {match_id} yok")

    loaded = load_match_events(session, match_id)
    if loaded.total == 0:
        return {
            "match_id": match_id,
            "events_loaded": 0,
            "note": "events tablosunda bu maç için kayıt yok.",
        }

    home_id = match.home_team_external_id
    away_id = match.away_team_external_id
    # Shot domain'inde team yok — minute'a göre yakın pas'ın takımıyla yaklaşık
    # eşleştirmedense burada tüm şutları her iki tarafa da gönderiyoruz; bu
    # şutsuz takım için xg=0 anlamına gelir, çünkü mesafe etkisi azalmaz.
    # Pragmatik: home_shots = all shots; away_shots = all shots — caller bunu bilir.
    def _safe(fn):
        try:
            return engine_result_to_dict(fn())
        except (ValueError, ZeroDivisionError, IndexError, KeyError, TypeError) as e:
            return {"error": str(e)}

    from app.data.loaders import shots_by_team
    home_s = shots_by_team(loaded.shots, home_id)
    away_s = shots_by_team(loaded.shots, away_id)
    dominance = _safe(lambda: compute_match_dominance(
        team_external_id=home_id, opponent_team_external_id=away_id,
        team_shots=home_s, opponent_shots=away_s,
        all_passes=loaded.passes, team_carries=loaded.carries,
        opponent_carries=loaded.carries,
    ))
    home_pass = [pp for pp in loaded.passes if pp.team_external_id == home_id]
    away_pass = [pp for pp in loaded.passes if pp.team_external_id == away_id]
    home_def = [dd for dd in loaded.defensive_actions if dd.team_external_id == home_id]
    away_def = [dd for dd in loaded.defensive_actions if dd.team_external_id == away_id]
    phases = _safe(lambda: compute_match_phases(
        match_id, home_id, away_id,
        home_s, away_s,
        home_pass, away_pass,
        home_def, away_def,
    ))

    return {
        "match_id": match_id,
        "home_team_id": home_id,
        "away_team_id": away_id,
        "events_loaded": loaded.total,
        "match_dominance": dominance,
        "match_phases": phases,
    }


# --------------------------------------------------------------------------- #
# Saha-içi uygulanabilir özellikler (Faz Q)
# --------------------------------------------------------------------------- #


@router.get(
    "/matches/{match_id}/players/{player_id}/feedback",
    tags=["admin"],
    summary="Bireysel oyuncu maç-sonu coach feedback (sınıf 2)",
)
def player_feedback_endpoint(
    match_id: int,
    player_id: int,
    persist: bool = Query(default=True),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Bir oyuncunun bir maçtaki performansı için 200 kelime kişisel feedback +
    top 3 alt-optimal pas örneği (frame koordinatlarıyla)."""
    from app.agents import PlayerFeedbackAgent
    from app.agents.store import save_agent_output

    agent = PlayerFeedbackAgent()
    try:
        result = agent.run(
            session,
            context={
                "match_external_id": match_id,
                "player_external_id": player_id,
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    if persist:
        save_agent_output(
            session, result=result,
            agent_name=agent.name,
            agent_version=f"{agent.version}-match{match_id}",
        )
        session.commit()
    return result.output_json


@router.get(
    "/teams/{team_id}/training-plan",
    tags=["admin"],
    summary="Haftalık antrenman planı — rakip profilinden (sınıf 3)",
)
def training_plan_endpoint(
    team_id: int,
    opponent_id: int = Query(...),
    persist: bool = Query(default=True),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Rakibin son 5 maç profilinden (PPDA + pres + arketip + kanal) drill
    önerileri + 200-250 kelime hafta planı."""
    from app.agents import TrainingPlanAgent
    from app.agents.store import save_agent_output

    agent = TrainingPlanAgent()
    try:
        result = agent.run(
            session,
            context={
                "my_team_external_id": team_id,
                "opponent_external_id": opponent_id,
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    if persist:
        save_agent_output(
            session, result=result,
            agent_name=agent.name,
            agent_version=f"{agent.version}-vs{opponent_id}",
        )
        session.commit()
    return result.output_json


@router.get(
    "/matches/{match_id}/substitution-chess",
    tags=["admin"],
    summary="Sub kombinasyonları forward projection (sınıf 1)",
)
def substitution_chess_endpoint(
    match_id: int,
    my_team_id: int = Query(...),
    current_minute: float = Query(..., ge=0, le=120),
    match_total_minutes: float = Query(default=90.0, ge=45, le=120),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Mevcut maç dakikasında top 3 sub senaryosu + projeksiyon."""
    from app.data.loaders import load_match_events
    from app.engine.substitution_chess import compute_substitution_chess

    match = session.execute(
        select(models.Match).where(
            models.Match.sport == football.SPORT_NAME,
            models.Match.external_id == match_id,
        )
    ).scalar_one_or_none()
    if match is None:
        raise HTTPException(status_code=404, detail=f"match {match_id} yok")

    loaded = load_match_events(session, match_id)
    if loaded.total == 0:
        return {"match_id": match_id, "events_loaded": 0,
                "note": "Event ingest yok"}

    home_id = match.home_team_external_id
    my_score = match.home_score if my_team_id == home_id else match.away_score
    opp_score = match.away_score if my_team_id == home_id else match.home_score
    passes = [p for p in loaded.passes if p.minute <= current_minute]
    defs = [d for d in loaded.defensive_actions if d.minute <= current_minute]

    result = compute_substitution_chess(
        my_team_id, passes, defs,
        current_minute=current_minute,
        match_total_minutes=match_total_minutes,
        my_score=my_score or 0, opponent_score=opp_score or 0,
    )
    return engine_result_to_dict(result)


@router.get(
    "/teams/{team_id}/set-piece-routine",
    tags=["admin"],
    summary="Set-piece routine builder — rakibin zayıf zone'una göre (sınıf 4)",
)
def set_piece_routine_endpoint(
    team_id: int,
    opponent_id: int = Query(...),
    last_n: int = Query(default=5, ge=1, le=20),
    set_piece_type: str = Query(default="all"),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Bizim ofansif + rakip defansif + rakip ofansif set-piece pattern
    kesişiminden top 3 zone + technique önerisi."""
    from app.data.loaders import load_team_events
    from app.engine.set_piece_routine import compute_set_piece_routine

    my_events = load_team_events(session, team_id, last_n=last_n)
    opp_events = load_team_events(session, opponent_id, last_n=last_n)
    if my_events.total == 0 or opp_events.total == 0:
        return {
            "team_id": team_id, "opponent_id": opponent_id,
            "my_events": my_events.total,
            "opp_events": opp_events.total,
            "note": "Yeterli event yok (iki takım için ingest gerekli)",
        }

    result = compute_set_piece_routine(
        my_team_external_id=team_id,
        opponent_team_external_id=opponent_id,
        my_offensive_shots=my_events.shots,
        opponent_defensive_shots=opp_events.shots,
        opponent_offensive_shots=opp_events.shots,
        set_piece_type=set_piece_type,
        matches_analyzed=min(len(my_events.match_ids), len(opp_events.match_ids)),
    )
    return engine_result_to_dict(result)


# --------------------------------------------------------------------------- #
# Faz 5 Sprint 2 — maç hazırlık / game-plan / proaktif uyarı
# --------------------------------------------------------------------------- #


@router.get(
    "/teams/{team_id}/matchup-grid",
    tags=["admin"],
    summary="Rakip zaaf × bizim güç eşleştirme (3 kanal) — Faz 5 #21",
)
def matchup_grid_endpoint(
    team_id: int,
    opponent_id: int = Query(...),
    last_n: int = Query(default=5, ge=1, le=20),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Bizim son N maç atak gücü × rakip son N maç savunma zayıflığı."""
    from app.data.loaders import load_team_events
    from app.engine.matchup_grid import compute_matchup_grid

    my_events = load_team_events(session, team_id, last_n=last_n)
    opp_events = load_team_events(session, opponent_id, last_n=last_n)
    if my_events.total == 0 or opp_events.total == 0:
        return {
            "team_id": team_id, "opponent_id": opponent_id,
            "my_events": my_events.total, "opp_events": opp_events.total,
            "note": "Yeterli event yok (iki takım için ingest gerekli)",
        }
    result = compute_matchup_grid(
        my_team_external_id=team_id,
        opponent_team_external_id=opponent_id,
        our_passes=my_events.passes,
        our_carries=my_events.carries,
        opponent_def_actions=opp_events.defensive_actions,
        matches_analyzed=len(my_events.match_ids),
    )
    return engine_result_to_dict(result)


@router.post(
    "/teams/{team_id}/game-plan",
    tags=["admin"],
    summary="Birleşik maç-hazırlık game-plan dokümanı — Faz 5 #22/#25/#27/#29",
)
def game_plan_endpoint(
    team_id: int,
    payload: dict[str, Any],
    persist: bool = Query(default=True),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Matchup grid + set-piece routine + senaryo planı + müsait kadro + AI.

    Beklenen payload:
    {
        "opponent_external_id": int,
        "match_external_id"?: int,
        "squad"?: [{player_id, injured?, suspended?, risk_level?}]
    }
    """
    from app.agents import GamePlanAgent
    from app.agents.store import save_agent_output

    opp = payload.get("opponent_external_id")
    if opp is None:
        raise HTTPException(status_code=400, detail="opponent_external_id zorunlu")

    agent = GamePlanAgent()
    try:
        result = agent.run(session, context={
            "my_team_external_id": team_id,
            "opponent_external_id": int(opp),
            "match_external_id": payload.get("match_external_id"),
            "squad": payload.get("squad", []),
        })
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    if persist:
        save_agent_output(
            session, result=result,
            agent_name=agent.name,
            agent_version=f"{agent.version}-vs{opp}",
        )
        session.commit()
    return result.output_json


@router.post(
    "/teams/{team_id}/available-squad",
    tags=["admin"],
    summary="Müsait kadro ön-filtre (sakat/cezalı/yük) — Faz 5 #23",
)
def available_squad_endpoint(
    team_id: int,
    payload: dict[str, Any],
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Squad listesinden müsaitlik raporu.

    payload: {"squad": [{player_id, position?, injured?, suspended?, risk_level?}]}
    """
    from app.engine.available_squad import compute_available_squad

    squad = payload.get("squad", [])
    if not squad:
        raise HTTPException(status_code=400, detail="squad listesi boş")
    result = compute_available_squad(team_id, squad)
    return engine_result_to_dict(result)


@router.get(
    "/teams/{team_id}/proactive-alerts",
    tags=["admin"],
    summary="Yük/risk/fikstür uyarı listesi — Faz 5 #14",
)
def proactive_alerts_endpoint(
    team_id: int,
    last_n: int = Query(default=5, ge=1, le=20),
    horizon_days: int = Query(default=14, ge=1, le=60),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Takımın oyuncu yük raporlarından + fikstür yoğunluğundan uyarı listesi."""
    from datetime import UTC, datetime

    from app.engine.load import compute_player_load
    from app.engine.proactive_alerts import compute_proactive_alerts
    from app.engine.schedule import compute_schedule

    # Takımın oyuncularını + appearance'larını çek
    apps = list(session.execute(
        select(models.PlayerAppearance).where(
            models.PlayerAppearance.sport == football.SPORT_NAME,
            models.PlayerAppearance.team_external_id == team_id,
        )
    ).scalars())
    player_ids = {a.player_external_id for a in apps}
    # SQLite tz-strip: now'u appearance tzinfo'suna göre türet
    _ref_tz = apps[0].kickoff.tzinfo if apps else None
    now = datetime.now(_ref_tz) if _ref_tz else datetime.now(UTC).replace(tzinfo=None)
    player_loads: list[dict[str, Any]] = []
    for pid in player_ids:
        try:
            pl = compute_player_load(pid, apps, now=now).value
        except (ValueError, ZeroDivisionError):
            continue
        player_loads.append({
            "player_external_id": pid,
            "risk_level": pl.risk_level,
            "minutes_per_week": pl.minutes_per_week,
            "back_to_back_count": pl.back_to_back_count,
        })

    # Fikstür yoğunluğu
    upcoming_count = 0
    dense = False
    team_matches = list(session.execute(
        select(models.Match).where(
            models.Match.sport == football.SPORT_NAME,
            (models.Match.home_team_external_id == team_id)
            | (models.Match.away_team_external_id == team_id),
        )
    ).scalars())
    if team_matches:
        ref_tz = team_matches[0].kickoff.tzinfo
        sched = compute_schedule(
            team_id, team_matches,
            now=datetime.now(ref_tz) if ref_tz else now,
            horizon_days=horizon_days,
        ).value
        upcoming_count = sched.upcoming_count
        dense = sched.dense_schedule

    result = compute_proactive_alerts(
        team_id,
        player_loads=player_loads,
        upcoming_count=upcoming_count,
        dense_schedule=dense,
        horizon_days=horizon_days,
        contract_warnings=[],  # caller ileride sözleşme verisi ekler
    )
    return engine_result_to_dict(result)


@router.get(
    "/daily-briefing",
    tags=["admin"],
    summary="Rol bazlı 'bugün ne yapmalıyım' özeti — Faz 5 #15",
)
def daily_briefing_endpoint(
    team_id: int = Query(...),
    role: str = Query(default="coach"),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Role göre günün öncelik listesini compose eder.

    coach → proaktif uyarı + sıradaki rakip + müsait kadro özeti
    analyst → tactical trend + son maç + scout digest
    admin → job durumu + kota + db stats özeti
    """
    sections: dict[str, Any] = {"team_id": team_id, "role": role}

    if role in ("coach", "admin"):
        # Proaktif uyarılar (en kritik 5)
        try:
            alerts_resp = proactive_alerts_endpoint(team_id, session=session)
            sections["alerts"] = {
                "critical_count": alerts_resp.get("value", {}).get("critical_count", 0),
                "warning_count": alerts_resp.get("value", {}).get("warning_count", 0),
                "top": alerts_resp.get("value", {}).get("alerts", [])[:5],
            }
        except Exception as e:  # noqa: BLE001
            sections["alerts"] = {"error": str(e)[:80]}

    if role == "admin":
        # Job + kota özeti
        n_jobs = session.scalar(
            select(func.count()).select_from(models.JobRun)
        ) or 0
        sections["ops"] = {"total_jobs": int(n_jobs)}

    if role == "analyst":
        # Son ingest edilen maç sayısı
        n_events_matches = session.scalar(
            select(func.count(func.distinct(models.EventRow.match_external_id)))
            .where(models.EventRow.sport == football.SPORT_NAME)
        ) or 0
        sections["data"] = {"matches_with_events": int(n_events_matches)}

    sections["todo"] = _daily_todo(role, sections)
    return sections


def _daily_todo(role: str, sections: dict[str, Any]) -> list[str]:
    """Role göre yapılacaklar listesi (heuristic)."""
    todo: list[str] = []
    alerts = sections.get("alerts", {})
    crit = alerts.get("critical_count", 0)
    warn = alerts.get("warning_count", 0)
    if role == "coach":
        if crit:
            todo.append(f"{crit} kritik uyarı var — yük/sakatlık kararı ver")
        if warn:
            todo.append(f"{warn} uyarı izlemede — antrenman yükünü ayarla")
        todo.append("Sıradaki rakip için game-plan oluştur")
        todo.append("Müsait kadroyu kontrol et")
    elif role == "analyst":
        todo.append("Son maç tactical-trend incele")
        todo.append("Scout watchlist digest güncelle")
        todo.append("Rakip set-piece pattern hazırla")
    elif role == "admin":
        todo.append("Job durumlarını kontrol et")
        todo.append("API kota kullanımını izle")
        todo.append("Eksik maç event'lerini ingest et")
    else:  # viewer
        todo.append("Takım form ve sıralama özetini gör")
    return todo


# --------------------------------------------------------------------------- #
# Faz 5 Sprint 3-5 — sezon / kadro / sağlık
# --------------------------------------------------------------------------- #


@router.get(
    "/players/{player_id}/injury-risk",
    tags=["admin"],
    summary="Sakatlık risk skoru (yük + yaş + sıklık) — Faz 5 #42",
)
def injury_risk_endpoint(
    player_id: int,
    age: int | None = Query(default=None, ge=15, le=45),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Oyuncunun load raporundan + yaştan sakatlık risk skoru."""
    from datetime import UTC, datetime

    from app.engine.injury_risk import compute_injury_risk
    from app.engine.load import compute_player_load

    apps = list(session.execute(
        select(models.PlayerAppearance).where(
            models.PlayerAppearance.sport == football.SPORT_NAME,
            models.PlayerAppearance.player_external_id == player_id,
        )
    ).scalars())
    if not apps:
        raise HTTPException(
            status_code=404, detail=f"player {player_id} için appearance yok",
        )
    # SQLite tz-strip: now'u appearance tzinfo'suna göre türet
    ref_tz = apps[0].kickoff.tzinfo
    now = datetime.now(ref_tz) if ref_tz else datetime.now(UTC).replace(tzinfo=None)
    pl = compute_player_load(player_id, apps, now=now).value
    result = compute_injury_risk(
        player_id,
        minutes_per_week=pl.minutes_per_week,
        back_to_back_count=pl.back_to_back_count,
        age=age,
    )
    return engine_result_to_dict(result)


@router.post(
    "/teams/{team_id}/squad-depth",
    tags=["admin"],
    summary="Pozisyon bazlı kadro derinliği + yaşlanma — Faz 5 #33",
)
def squad_depth_endpoint(
    team_id: int,
    payload: dict[str, Any],
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """payload: {"squad": [{player_id, position, age?}]}"""
    from app.engine.squad_depth import compute_squad_depth

    squad = payload.get("squad", [])
    if not squad:
        raise HTTPException(status_code=400, detail="squad listesi boş")
    result = compute_squad_depth(team_id, squad)
    return engine_result_to_dict(result)


@router.get(
    "/teams/{team_id}/rotation-plan",
    tags=["admin"],
    summary="Yük periyotlama / rotasyon önerisi — Faz 5 #31",
)
def rotation_plan_endpoint(
    team_id: int,
    horizon_days: int = Query(default=14, ge=1, le=60),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Takım yük raporları + fikstür yoğunluğundan rotasyon önerisi."""
    from datetime import UTC, datetime

    from app.engine.load import compute_player_load
    from app.engine.rotation_plan import compute_rotation_plan
    from app.engine.schedule import compute_schedule

    apps = list(session.execute(
        select(models.PlayerAppearance).where(
            models.PlayerAppearance.sport == football.SPORT_NAME,
            models.PlayerAppearance.team_external_id == team_id,
        )
    ).scalars())
    _ref_tz = apps[0].kickoff.tzinfo if apps else None
    now = datetime.now(_ref_tz) if _ref_tz else datetime.now(UTC).replace(tzinfo=None)
    player_loads: list[dict[str, Any]] = []
    for pid in {a.player_external_id for a in apps}:
        try:
            pl = compute_player_load(pid, apps, now=now).value
        except (ValueError, ZeroDivisionError):
            continue
        player_loads.append({
            "player_external_id": pid, "risk_level": pl.risk_level,
            "minutes_per_week": pl.minutes_per_week,
            "back_to_back_count": pl.back_to_back_count,
        })

    upcoming, dense = 0, False
    team_matches = list(session.execute(
        select(models.Match).where(
            models.Match.sport == football.SPORT_NAME,
            (models.Match.home_team_external_id == team_id)
            | (models.Match.away_team_external_id == team_id),
        )
    ).scalars())
    if team_matches:
        tz = team_matches[0].kickoff.tzinfo
        sched = compute_schedule(
            team_id, team_matches,
            now=datetime.now(tz) if tz else now, horizon_days=horizon_days,
        ).value
        upcoming, dense = sched.upcoming_count, sched.dense_schedule

    result = compute_rotation_plan(
        team_id, player_loads,
        upcoming_matches=upcoming, dense_schedule=dense,
    )
    return engine_result_to_dict(result)


@router.get(
    "/teams/{team_id}/season-calendar",
    tags=["admin"],
    summary="Sezon takvimi + fikstür zorluğu — Faz 5 #30",
)
def season_calendar_endpoint(
    team_id: int,
    horizon_days: int = Query(default=60, ge=7, le=180),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Sıradaki maçlar + her birinin zorluk değerlendirmesi."""
    from datetime import UTC, datetime

    from app.engine.fixture_difficulty import (
        OpponentRating,
        compute_fixture_difficulty,
    )
    from app.engine.rating import compute_team_rating
    from app.engine.schedule import compute_schedule

    team_matches = list(session.execute(
        select(models.Match).where(
            models.Match.sport == football.SPORT_NAME,
            (models.Match.home_team_external_id == team_id)
            | (models.Match.away_team_external_id == team_id),
        )
    ).scalars())
    if not team_matches:
        return {"team_id": team_id, "note": "Bu takımın maçı yok"}

    tz = team_matches[0].kickoff.tzinfo
    now = datetime.now(tz) if tz else datetime.now(UTC).replace(tzinfo=None)

    # Rakip rating'leri (fixture difficulty için)
    from datetime import timedelta
    horizon = now + timedelta(days=horizon_days)
    scoped = [m for m in team_matches if m.kickoff <= horizon]
    # Tüm rakiplerin rating'i
    ratings: dict[int, OpponentRating] = {}
    opp_ids = set()
    for m in scoped:
        opp = (m.away_team_external_id if m.home_team_external_id == team_id
               else m.home_team_external_id)
        opp_ids.add(opp)
    for opp in opp_ids:
        opp_matches = [
            m for m in team_matches
            if m.home_team_external_id == opp or m.away_team_external_id == opp
        ]
        rr = compute_team_rating(opp, opp_matches, last_n=10).value
        if rr.matches_considered:
            ratings[opp] = OpponentRating(
                home_rating=rr.home_rating if rr.home_matches else None,
                away_rating=rr.away_rating if rr.away_matches else None,
                overall_rating=rr.rating,
            )
    difficulty = compute_fixture_difficulty(team_id, scoped, ratings, now=now)
    return {
        "team_id": team_id,
        "horizon_days": horizon_days,
        "schedule": engine_result_to_dict(
            compute_schedule(team_id, team_matches, now=now, horizon_days=horizon_days)
        )["value"],
        "fixture_difficulty": engine_result_to_dict(difficulty)["value"],
    }


@router.get(
    "/players/{player_id}/transfer-targets",
    tags=["admin"],
    summary="Benzer profilde transfer hedefleri — Faz 5 #35",
)
def transfer_targets_endpoint(
    player_id: int,
    top_n: int = Query(default=5, ge=1, le=20),
    min_minutes: int = Query(default=180, ge=0),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Hedef oyuncuya benzer profilde adaylar (tüm appearance havuzundan)."""
    from app.engine.player_similarity import compute_similar_players

    all_apps = list(session.execute(
        select(models.PlayerAppearance).where(
            models.PlayerAppearance.sport == football.SPORT_NAME,
        )
    ).scalars())
    by_pid: dict[int, list] = {}
    for a in all_apps:
        by_pid.setdefault(a.player_external_id, []).append(a)
    target_apps = by_pid.get(player_id, [])
    if not target_apps:
        raise HTTPException(
            status_code=404, detail=f"player {player_id} için appearance yok",
        )
    candidates = {p: apps for p, apps in by_pid.items() if p != player_id}
    if not candidates:
        return {"player_id": player_id, "targets": [], "note": "aday havuzu boş"}
    result = compute_similar_players(
        player_id, target_apps, candidates,
        top_n=top_n, min_minutes=min_minutes,
    )
    return {
        "player_id": player_id,
        "targets": [
            {"player_id": m.player_external_id, "similarity": m.similarity,
             "minutes": m.total_minutes}
            for m in result.value.top_matches
        ],
    }


@router.get(
    "/teams/{team_id}/decision-dashboard",
    tags=["admin"],
    summary="Karar geçmişi + isabet özeti (tüm maçlar) — Faz 5 #39",
)
def decision_dashboard_endpoint(
    team_id: int,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Bir takımın tüm maçlarındaki kararların verdict dağılımı + isabet."""
    # Takımın maçlarındaki tüm decision'ları topla
    team_matches = list(session.execute(
        select(models.Match.external_id).where(
            models.Match.sport == football.SPORT_NAME,
            (models.Match.home_team_external_id == team_id)
            | (models.Match.away_team_external_id == team_id),
        )
    ).scalars())
    if not team_matches:
        return {"team_id": team_id, "note": "maç yok"}

    decisions = list(session.execute(
        select(models.Decision).where(
            models.Decision.sport == football.SPORT_NAME,
            models.Decision.team_external_id == team_id,
            models.Decision.match_external_id.in_(team_matches),
        ).order_by(models.Decision.match_external_id, models.Decision.minute)
    ).scalars())

    by_type: dict[str, int] = {}
    for d in decisions:
        by_type[d.decision_type] = by_type.get(d.decision_type, 0) + 1

    return {
        "team_id": team_id,
        "total_decisions": len(decisions),
        "by_type": by_type,
        "matches_with_decisions": len({d.match_external_id for d in decisions}),
        "recent": [
            {
                "match_id": d.match_external_id, "minute": d.minute,
                "type": d.decision_type,
                "subject_player": d.subject_player_external_id,
                "notes": d.notes,
            }
            for d in decisions[-20:]
        ],
    }


# --------------------------------------------------------------------------- #
# Faz 6 — maç-içi karar mekanizması (live decision)
# --------------------------------------------------------------------------- #


@router.get(
    "/matches/{match_id}/live-decision",
    tags=["admin"],
    summary="Maç-içi karar paneli (momentum/sub/tactical/risk + spatial/matchup/score-time) — Faz 6+7",
)
def live_decision_endpoint(
    match_id: int,
    my_team_id: int = Query(...),
    current_minute: float = Query(..., ge=0, le=120),
    star_player_id: int | None = Query(default=None),
    draw_is_enough: bool = Query(default=False),
    must_win: bool = Query(default=False),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Bir maç dakikasında tam karar paneli: momentum + sub timing +
    tactical trigger + risk monitor (Faz 6) + spatial control + live matchup +
    score-time matrix (Faz 7) — 8 engine birleşik."""
    from app.data.loaders import load_match_events
    from app.engine.live_risk_monitor import compute_live_risk_monitor
    from app.engine.live_tactical_trigger import compute_live_tactical_trigger
    from app.engine.momentum_tracker import compute_momentum
    from app.engine.sub_timing import compute_sub_timing

    match = session.execute(
        select(models.Match).where(
            models.Match.sport == football.SPORT_NAME,
            models.Match.external_id == match_id,
        )
    ).scalar_one_or_none()
    if match is None:
        raise HTTPException(status_code=404, detail=f"match {match_id} yok")

    loaded = load_match_events(session, match_id)
    if loaded.total == 0:
        return {"match_id": match_id, "events_loaded": 0,
                "note": "Event ingest yok"}

    home_id = match.home_team_external_id
    opp_id = (match.away_team_external_id if my_team_id == home_id
              else home_id)
    my_score = match.home_score if my_team_id == home_id else match.away_score
    opp_score = match.away_score if my_team_id == home_id else match.home_score

    p = [x for x in loaded.passes if x.minute <= current_minute]
    d = [x for x in loaded.defensive_actions if x.minute <= current_minute]
    s = [x for x in loaded.shots if x.minute <= current_minute]

    out: dict[str, Any] = {
        "match_id": match_id, "my_team_id": my_team_id,
        "current_minute": current_minute,
        "score": f"{match.home_score}-{match.away_score}",
    }

    def _safe(key: str, fn):
        try:
            out[key] = engine_result_to_dict(fn())["value"]
        except (ValueError, ZeroDivisionError, KeyError, TypeError) as e:
            out[key] = {"error": str(e)[:80]}

    mom_result = compute_momentum(
        my_team_id, opp_id, p, d, s, current_minute=current_minute,
    )
    out["momentum"] = engine_result_to_dict(mom_result)["value"]
    momentum_score = mom_result.value.momentum_score

    _safe("sub_timing", lambda: compute_sub_timing(
        my_team_id, p, d, current_minute=current_minute,
        my_score=my_score or 0, opponent_score=opp_score or 0,
    ))
    _safe("tactical_triggers", lambda: compute_live_tactical_trigger(
        my_team_id, current_minute=current_minute,
        my_score=my_score or 0, opponent_score=opp_score or 0,
        momentum_score=momentum_score,
    ))
    # Risk monitor — player states event'lerden türetilemez (sarı/düello yok);
    # boş liste ile zaman yönetimi reçetesi yine de döner
    _safe("risk_monitor", lambda: compute_live_risk_monitor(
        my_team_id, [], current_minute=current_minute,
        my_score=my_score or 0, opponent_score=opp_score or 0,
    ))

    # Faz 7: event/pure türetilebilen sinyaller (F spatial, G matchup, K score-time)
    from app.engine.live_matchup import compute_live_matchup
    from app.engine.score_time_matrix import compute_score_time_matrix
    from app.engine.spatial_control import compute_spatial_control

    star_id = int(star_player_id) if star_player_id is not None else None
    _safe("spatial_control", lambda: compute_spatial_control(
        my_team_id, opp_id, p, d, current_minute=current_minute,
    ))
    _safe("live_matchup", lambda: compute_live_matchup(
        my_team_id, opp_id, p, d, current_minute=current_minute,
        star_player_id=star_id,
    ))
    _safe("score_time_matrix", lambda: compute_score_time_matrix(
        my_team_id, current_minute=current_minute,
        my_score=my_score or 0, opponent_score=opp_score or 0,
        draw_is_enough=draw_is_enough, must_win=must_win,
    ))

    # Faz 8: bağlam motoru (orkestra şefi) — 8 sinyali tek karara indirger
    from app.api.context_pipeline import run_context_pipeline
    out.update(run_context_pipeline(
        session, match, my_team_id, current_minute, out, p, d, s,
        my_score=my_score or 0, opp_score=opp_score or 0,
    ))
    return out


@router.post(
    "/matches/{match_id}/opponent-reaction",
    tags=["admin"],
    summary="Rakip sub okuma + momentum kırma önerisi — Faz 6 #13/#14",
)
def opponent_reaction_endpoint(
    match_id: int,
    my_team_id: int = Query(...),
    payload: dict[str, Any] | None = None,
    current_minute: float = Query(..., ge=0, le=120),
    momentum_score: float = Query(default=0.0, ge=-1.0, le=1.0),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Rakip değişikliklerini yorumla.

    payload: {"opponent_subs": [{position_in, minute}]}
    """
    from app.engine.opponent_reaction import compute_opponent_reaction

    match = session.execute(
        select(models.Match).where(
            models.Match.sport == football.SPORT_NAME,
            models.Match.external_id == match_id,
        )
    ).scalar_one_or_none()
    if match is None:
        raise HTTPException(status_code=404, detail=f"match {match_id} yok")
    home_id = match.home_team_external_id
    opp_id = (match.away_team_external_id if my_team_id == home_id else home_id)
    subs = (payload or {}).get("opponent_subs", [])
    result = compute_opponent_reaction(
        my_team_id, opp_id, subs,
        current_minute=current_minute, momentum_score=momentum_score,
    )
    return engine_result_to_dict(result)


@router.post(
    "/matches/{match_id}/live-risk",
    tags=["admin"],
    summary="Canlı kart/sakatlık/zaman riski — Faz 6 #10/#11/#12",
)
def live_risk_endpoint(
    match_id: int,
    my_team_id: int = Query(...),
    current_minute: float = Query(..., ge=0, le=120),
    payload: dict[str, Any] | None = None,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Oyuncu durum listesinden kart + sakatlık + zaman yönetimi.

    payload: {"player_states": [{player_id, yellow_card?, duel_count?, fatigue?}]}
    """
    from app.engine.live_risk_monitor import compute_live_risk_monitor

    match = session.execute(
        select(models.Match).where(
            models.Match.sport == football.SPORT_NAME,
            models.Match.external_id == match_id,
        )
    ).scalar_one_or_none()
    if match is None:
        raise HTTPException(status_code=404, detail=f"match {match_id} yok")
    home_id = match.home_team_external_id
    my_score = match.home_score if my_team_id == home_id else match.away_score
    opp_score = match.away_score if my_team_id == home_id else match.home_score
    states = (payload or {}).get("player_states", [])
    result = compute_live_risk_monitor(
        my_team_id, states, current_minute=current_minute,
        my_score=my_score or 0, opponent_score=opp_score or 0,
    )
    return engine_result_to_dict(result)


# --------------------------------------------------------------------------- #
# Faz 7 — payload-reçete endpoint'leri (set-piece / friction / referee)
# --------------------------------------------------------------------------- #


def _require_match(session: Session, match_id: int) -> models.Match:
    match = session.execute(
        select(models.Match).where(
            models.Match.sport == football.SPORT_NAME,
            models.Match.external_id == match_id,
        )
    ).scalar_one_or_none()
    if match is None:
        raise HTTPException(status_code=404, detail=f"match {match_id} yok")
    return match


@router.post(
    "/matches/{match_id}/set-piece",
    tags=["admin"],
    summary="Duran top fırsatı + penaltı atıcı durumu — Faz 7 #7/#8",
)
def set_piece_endpoint(
    match_id: int,
    my_team_id: int = Query(...),
    current_minute: float = Query(..., ge=0, le=120),
    payload: dict[str, Any] | None = None,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """payload: {"set_piece_won": "corner"|"free_kick",
    "opponent_weak_zones": ["far_post"], "penalty_taker": {player_id, fatigue, recent_accuracy}}"""
    from app.engine.set_piece_timing import compute_set_piece_timing

    _require_match(session, match_id)
    pl = payload or {}
    result = compute_set_piece_timing(
        my_team_id, current_minute=current_minute,
        set_piece_won=pl.get("set_piece_won"),
        opponent_weak_zones=pl.get("opponent_weak_zones"),
        penalty_taker=pl.get("penalty_taker"),
    )
    return engine_result_to_dict(result)


@router.post(
    "/matches/{match_id}/game-friction",
    tags=["admin"],
    summary="Faul biriktirme + ofsayt tuzağı — Faz 7 #9/#10",
)
def game_friction_endpoint(
    match_id: int,
    my_team_id: int = Query(...),
    current_minute: float = Query(..., ge=0, le=120),
    payload: dict[str, Any] | None = None,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """payload: {"opponent_foul_zones": ["left_wing", ...]}.
    Ofsayt tuzağı rakip defansif aksiyon event'lerinden türetilir."""
    from app.data.loaders import load_match_events
    from app.engine.game_friction import compute_game_friction

    match = _require_match(session, match_id)
    home_id = match.home_team_external_id
    opp_id = match.away_team_external_id if my_team_id == home_id else home_id
    loaded = load_match_events(session, match_id)
    defs = [d for d in loaded.defensive_actions if d.minute <= current_minute]
    result = compute_game_friction(
        my_team_id, opp_id, defs, current_minute=current_minute,
        opponent_foul_zones=(payload or {}).get("opponent_foul_zones"),
    )
    return engine_result_to_dict(result)


@router.post(
    "/matches/{match_id}/referee-context",
    tags=["admin"],
    summary="Hakem eğilimi + avantaj penceresi — Faz 7 #11/#12",
)
def referee_context_endpoint(
    match_id: int,
    my_team_id: int = Query(...),
    current_minute: float = Query(..., ge=0, le=120),
    payload: dict[str, Any] | None = None,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """payload: {"cards_per_game": 5.0, "fouls_per_game": 27.0,
    "opponent_card_edge_players": [{player_id, position_zone}]}"""
    from app.engine.referee_context import compute_referee_context

    _require_match(session, match_id)
    pl = payload or {}
    result = compute_referee_context(
        my_team_id, current_minute=current_minute,
        cards_per_game=float(pl.get("cards_per_game", 0.0)),
        fouls_per_game=float(pl.get("fouls_per_game", 0.0)),
        opponent_card_edge_players=pl.get("opponent_card_edge_players"),
    )
    return engine_result_to_dict(result)


# --------------------------------------------------------------------------- #
# Faz 10 — saf analiz engine'leri API'ye açılır (what-if / backtest / anomaly /
# development-curve). Hepsi DB'siz: payload → engine → sonuç.
# --------------------------------------------------------------------------- #


@router.post(
    "/analysis/what-if",
    tags=["admin"],
    summary="Karşı-olgu: oyuncu çıkarınca takım metriği nasıl değişir (A)",
)
def analysis_what_if(payload: dict[str, Any]) -> dict[str, Any]:
    """payload: {"baseline_team_metric": float, "contributions": [{player_id,
    contribution}], "remove_player_id": int (ops), "replacement_contribution": float (ops)}.
    remove_player_id yoksa tüm oyuncular için sıralama döner."""
    from dataclasses import asdict

    from app.engine.what_if import (
        PlayerContribution,
        rank_removals,
        simulate_removal,
    )

    baseline = float(payload.get("baseline_team_metric", 0.0))
    contribs = [
        PlayerContribution(int(c["player_id"]), float(c["contribution"]))
        for c in payload.get("contributions", [])
    ]
    replacement = float(payload.get("replacement_contribution", 0.0))
    remove_id = payload.get("remove_player_id")
    if remove_id is None:
        return asdict(rank_removals(
            baseline_team_metric=baseline, contributions=contribs,
            replacement_contribution=replacement,
        ))
    return asdict(simulate_removal(
        baseline_team_metric=baseline, contributions=contribs,
        remove_player_id=int(remove_id), replacement_contribution=replacement,
    ))


@router.post(
    "/analysis/backtest",
    tags=["admin"],
    summary="Olasılıksal motor değerlendirme: hit-rate + Brier + kalibrasyon (B)",
)
def analysis_backtest(payload: dict[str, Any]) -> dict[str, Any]:
    """payload: {"samples": [[predicted_prob, actual_bool], ...],
    "decision_threshold": float (ops), "n_bins": int (ops)}."""
    from dataclasses import asdict

    from app.engine.backtest import backtest

    samples = [(float(p), bool(a)) for p, a in payload.get("samples", [])]
    report = backtest(
        samples,
        decision_threshold=float(payload.get("decision_threshold", 0.5)),
        n_bins=int(payload.get("n_bins", 5)),
    )
    return asdict(report)


@router.post(
    "/analysis/anomaly",
    tags=["admin"],
    summary="Metrik serisinde aykırı değer + form kırılması (C)",
)
def analysis_anomaly(payload: dict[str, Any]) -> dict[str, Any]:
    """payload: {"series": [float, ...], "z_threshold": float (ops)}."""
    from dataclasses import asdict

    from app.engine.anomaly import detect_anomalies

    series = [float(x) for x in payload.get("series", [])]
    report = detect_anomalies(
        series, z_threshold=float(payload.get("z_threshold", 2.0)),
    )
    return asdict(report)


@router.post(
    "/analysis/development-curve",
    tags=["admin"],
    summary="Gelişim eğimi + oynaklık + projeksiyon (E)",
)
def analysis_development_curve(payload: dict[str, Any]) -> dict[str, Any]:
    """payload: {"values": [float, ...], "recent_window": int (ops)}."""
    from dataclasses import asdict

    from app.engine.development_curve import development_curve

    values = [float(x) for x in payload.get("values", [])]
    report = development_curve(
        values, recent_window=int(payload.get("recent_window", 3)),
    )
    return asdict(report)


# --------------------------------------------------------------------------- #
# Sports Science — performans testi modülü: protokol oku / skorla / yorumla.
# Saf engine, DB'siz payload endpoint'leri (mevcut analiz kalıbı).
# --------------------------------------------------------------------------- #


@router.get(
    "/performance/protocols",
    deprecated=True,  # → /physical-tests (B) ile birleştirildi
    tags=["admin"],
    summary="Performans test protokol kütüphanesi (nasıl yapılır + normlar)",
)
def performance_protocols() -> dict[str, Any]:
    """Tester'ın okuyabileceği protokol tanımları."""
    from dataclasses import asdict

    from app.engine.performance_test import PROTOCOLS

    return {"protocols": [asdict(p) for p in PROTOCOLS.values()]}


@router.post(
    "/performance/score",
    deprecated=True,  # → /physical-tests (B) ile birleştirildi
    tags=["admin"],
    summary="Tek test sonucunu norm + kadro yüzdeliğiyle skorla",
)
def performance_score(payload: dict[str, Any]) -> dict[str, Any]:
    """payload: {"protocol_key": str, "raw_value": float,
    "reference_values": [float] (ops kadro)}."""
    from dataclasses import asdict

    from app.engine.performance_test import score_test

    refs = payload.get("reference_values")
    try:
        score = score_test(
            str(payload["protocol_key"]), float(payload["raw_value"]),
            reference_values=[float(x) for x in refs] if refs else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return asdict(score)


@router.post(
    "/performance/battery",
    deprecated=True,  # → /physical-tests (B) ile birleştirildi
    tags=["admin"],
    summary="Bir test gününün tüm sonuçları → atlet profili (güçlü/zayıf)",
)
def performance_battery(payload: dict[str, Any]) -> dict[str, Any]:
    """payload: {"player_id": int, "results": [[protocol_key, raw], ...],
    "squad_references": {protocol_key: [float]} (ops)}."""
    from dataclasses import asdict

    from app.engine.performance_test import evaluate_battery

    results = [(str(k), float(v)) for k, v in payload.get("results", [])]
    refs = {
        str(k): [float(x) for x in v]
        for k, v in (payload.get("squad_references") or {}).items()
    }
    try:
        report = evaluate_battery(
            int(payload.get("player_id", 0)), results,
            squad_references=refs or None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return asdict(report)


@router.post(
    "/performance/progression",
    deprecated=True,  # → /physical-tests (B) ile birleştirildi
    tags=["admin"],
    summary="Bir protokolün tarihsel serisi → gelişim + regresyon uyarısı",
)
def performance_progression(payload: dict[str, Any]) -> dict[str, Any]:
    """payload: {"protocol_key": str, "values": [float, ...]} (eski→yeni)."""
    from dataclasses import asdict

    from app.engine.performance_test import interpret_progression

    try:
        report = interpret_progression(
            str(payload["protocol_key"]),
            [float(x) for x in payload.get("values", [])],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return asdict(report)


@router.post(
    "/performance/workload",
    deprecated=True,  # → /physical-tests (B) ile birleştirildi
    tags=["admin"],
    summary="ACWR (sakatlık riski) + monotony/strain — günlük yük serisinden",
)
def performance_workload(payload: dict[str, Any]) -> dict[str, Any]:
    """payload: {"daily_loads": [float, ...] (kronolojik, RPE×dk ya da GPS yükü)}."""
    from dataclasses import asdict

    from app.engine.workload import compute_workload

    report = compute_workload([float(x) for x in payload.get("daily_loads", [])])
    return asdict(report)


@router.post(
    "/performance/assess-change",
    tags=["admin"],
    summary="Yeni ölçüm bireysel baseline'a göre ANLAMLI mı (SWC) — gürültü filtresi",
)
def performance_assess_change(payload: dict[str, Any]) -> dict[str, Any]:
    """payload: {"current": float, "baseline_values": [float], "higher_is_better": bool}."""
    from dataclasses import asdict

    from app.engine.performance_test import assess_change

    report = assess_change(
        float(payload["current"]),
        [float(x) for x in payload.get("baseline_values", [])],
        higher_is_better=bool(payload.get("higher_is_better", True)),
    )
    return asdict(report)


@router.post(
    "/performance/gps-load",
    tags=["admin"],
    summary="GPS/wearable seansı → iç-yük (AU, ACWR'ye beslenir) — sports science",
)
def performance_gps_load(payload: dict[str, Any]) -> dict[str, Any]:
    """payload: {duration_min, total_distance_m, hsr_distance_m?, sprint_distance_m?,
    accelerations?, decelerations?, player_load?, rpe?}."""
    from dataclasses import asdict

    from app.engine.gps_load import GpsSession, compute_gps_load

    s = GpsSession(
        duration_min=float(payload["duration_min"]),
        total_distance_m=float(payload["total_distance_m"]),
        hsr_distance_m=float(payload.get("hsr_distance_m", 0.0)),
        sprint_distance_m=float(payload.get("sprint_distance_m", 0.0)),
        accelerations=int(payload.get("accelerations", 0)),
        decelerations=int(payload.get("decelerations", 0)),
        player_load=(float(payload["player_load"])
                     if payload.get("player_load") is not None else None),
        rpe=float(payload["rpe"]) if payload.get("rpe") is not None else None,
    )
    return asdict(compute_gps_load(s))


@router.post(
    "/performance/wellness",
    tags=["admin"],
    summary="Subjektif wellness anketi → readiness skoru — sports science",
)
def performance_wellness(payload: dict[str, Any]) -> dict[str, Any]:
    """payload: {sleep_quality, fatigue, muscle_soreness, stress, mood (her biri
    1-7, yüksek=iyi), baseline_totals?: [int]}."""
    from dataclasses import asdict

    from app.engine.wellness import WellnessInput, compute_wellness

    w = WellnessInput(
        sleep_quality=int(payload["sleep_quality"]),
        fatigue=int(payload["fatigue"]),
        muscle_soreness=int(payload["muscle_soreness"]),
        stress=int(payload["stress"]),
        mood=int(payload["mood"]),
    )
    bt = payload.get("baseline_totals")
    return asdict(compute_wellness(
        w, baseline_totals=[int(x) for x in bt] if bt else None,
    ))


# --------------------------------------------------------------------------- #
# KVKK — hassas veri erişim denetimi (DataAccessLog + anomali tespiti).
# --------------------------------------------------------------------------- #


def record_data_access(
    session: Session,
    *,
    subject_id: int,
    data_category: str,
    user_id: str | None = None,
    subject_type: str = "player",
    action: str = "read",
    endpoint: str | None = None,
) -> None:
    """Bir hassas-veri erişimini denetim loguna yaz (KVKK izlenebilirlik).

    Sensitivity engine ile sınıflandırılır; tenant_id auto-fill ile dolar.
    Hata-toleranslı: loglama asıl isteği bozmaz."""
    from datetime import UTC
    from datetime import datetime as _dt

    from sqlalchemy.exc import SQLAlchemyError

    from app.engine.compliance import classify_sensitivity

    try:
        session.add(models.DataAccessLog(
            user_id=user_id, subject_type=subject_type, subject_id=subject_id,
            data_category=data_category,
            sensitivity=classify_sensitivity(data_category),
            action=action, endpoint=endpoint, created_at=_dt.now(UTC),
        ))
        session.commit()
    except SQLAlchemyError:
        session.rollback()


@router.get(
    "/compliance/access-log",
    tags=["admin"],
    summary="KVKK denetim izi — bir oyuncunun verisine kim erişti (DPO için)",
)
def compliance_access_log(
    subject_id: int | None = Query(default=None),
    days: int = Query(default=30, ge=1, le=3650),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    from datetime import UTC, timedelta
    from datetime import datetime as _dt

    cutoff = _dt.now(UTC) - timedelta(days=days)
    q = select(models.DataAccessLog).where(
        models.DataAccessLog.created_at >= cutoff,
    )
    if subject_id is not None:
        q = q.where(models.DataAccessLog.subject_id == subject_id)
    rows = list(session.execute(
        q.order_by(models.DataAccessLog.created_at.desc())
    ).scalars())
    return {
        "subject_id": subject_id, "days": days, "total": len(rows),
        "entries": [
            {
                "user_id": r.user_id, "subject_type": r.subject_type,
                "subject_id": r.subject_id, "data_category": r.data_category,
                "sensitivity": r.sensitivity, "action": r.action,
                "endpoint": r.endpoint,
                "at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows[:500]
        ],
    }


@router.get(
    "/compliance/audit",
    tags=["admin"],
    summary="Olağandışı toplu hassas-veri erişimi (olası sızıntı) tespiti",
)
def compliance_audit(
    days: int = Query(default=7, ge=1, le=365),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Son N günün erişim loglarından şüpheli toplu erişim çıkar."""
    from dataclasses import asdict
    from datetime import UTC, timedelta
    from datetime import datetime as _dt

    from app.engine.compliance import AccessEvent, detect_access_anomalies

    cutoff = _dt.now(UTC) - timedelta(days=days)
    rows = list(session.execute(
        select(models.DataAccessLog).where(
            models.DataAccessLog.created_at >= cutoff,
        )
    ).scalars())
    events = [
        AccessEvent(
            user_id=r.user_id, subject_id=r.subject_id,
            data_category=r.data_category,
            minute=r.created_at.timestamp() / 60.0 if r.created_at else 0.0,
        )
        for r in rows
    ]
    return asdict(detect_access_anomalies(events))
