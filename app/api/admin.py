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
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Bir takımın son N maçındaki olaylardan 20+ engine'in batch çıktısı.

    Events tablosu boşsa `events_loaded=0` döner ve ana metrikler `null` olur —
    ingest pipeline çalıştırılması beklenir.
    """
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

    return {
        "team_id": team_id,
        "last_n": last_n,
        "matches_analyzed": loaded.match_ids,
        "events_loaded": loaded.total,
        "event_counts": {
            "passes": len(p), "carries": len(c),
            "defensive_actions": len(d), "shots": len(s),
        },
        "tactical_profile": profile,
    }


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
            dom = compute_match_dominance(
                team_external_id=team_id, opponent_team_external_id=opp_id,
                team_shots=loaded.shots, opponent_shots=loaded.shots,
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


@router.get(
    "/matches/{match_id}/halftime-brief",
    tags=["admin"],
    summary="Devre arası analiz brief (1. yarı event'leri üzerinde 7 engine + AI)",
)
def match_halftime_brief(
    match_id: int,
    my_team_id: int = Query(..., description="Brief'in hangi takım için olacağı"),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Devre arası bilgi paneli — 1. yarı event'lerinden 7+ engine + AI brief."""
    from app.agents import HalftimeAnalysisAgent

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
    return result.output_json


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

    dominance = _safe(lambda: compute_match_dominance(
        team_external_id=home_id, opponent_team_external_id=away_id,
        team_shots=loaded.shots, opponent_shots=loaded.shots,
        all_passes=loaded.passes, team_carries=loaded.carries,
        opponent_carries=loaded.carries,
    ))
    # match_phases home/away ayrımı bekliyor — pas team_id'ye göre böl
    home_pass = [pp for pp in loaded.passes if pp.team_external_id == home_id]
    away_pass = [pp for pp in loaded.passes if pp.team_external_id == away_id]
    home_def = [dd for dd in loaded.defensive_actions if dd.team_external_id == home_id]
    away_def = [dd for dd in loaded.defensive_actions if dd.team_external_id == away_id]
    # Shot domain'inde team yok → tüm şutları her iki tarafa ver (yaklaşık)
    phases = _safe(lambda: compute_match_phases(
        match_id, home_id, away_id,
        loaded.shots, loaded.shots,
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
