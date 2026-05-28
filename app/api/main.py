"""FastAPI app — DB'den okuyan + engine'i tüketen uçlar.

Katman dış kaynağa dokunmaz (sync `scripts/sync_league.py` / `scheduler/`).
Engine pure kalsın diye serileştirme `serialize.py` üzerinden.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import or_, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.ai import ClaudeCommentator
from app.api.admin import router as admin_router
from app.api.live import router as live_router
from app.api.auth import (
    require_api_key,
)
from app.api.auth import (
    router as auth_router,
)
from app.api.errors import register_exception_handlers
from app.api.observability import (
    METRICS,
    PROCESS_STARTED_AT,
    SlidingWindowRateLimiter,
    should_bypass_rate_limit,
)
from app.api.schemas import LeagueOut, MatchOut, TeamOut
from app.api.serialize import engine_result_to_dict
from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.core.request_context import clear_request_id, set_request_id
from app.data.cache import engine_cached
from app.data.predictions import save_prediction
from app.db import models
from app.db.session import get_session
from app.db.tenant_filter import install_tenant_filter
from app.engine.fixture_difficulty import OpponentRating, compute_fixture_difficulty
from app.engine.form import compute_form
from app.engine.load import compute_player_load
from app.engine.matchup import compute_matchup
from app.engine.opponent import compute_head_to_head
from app.engine.predict import compute_predict
from app.engine.rating import compute_team_rating
from app.engine.schedule import compute_schedule
from app.sports import football

setup_logging()

# Multi-tenant filter — global SQLAlchemy event listener
install_tenant_filter()

# Prod modunda zorunlu secret'lar varsa fail-fast (ConfigError → boot durur).
# Dev/staging modlarda kontrol pas geçer; aşağıdaki yumuşak uyarı devam eder.
get_settings().validate_for_production()

if not get_settings().api_auth_key:
    get_logger(__name__).warning(
        "API_AUTH_KEY boş — auth DEVRE DIŞI. Production'da bu değeri set edin "
        "(env-var typosu? .env yüklendi mi?). /health dışında her uç açık."
    )

APP_VERSION = "0.4.0"  # production hardening turunda bumped

# OpenAPI tag metadata — Swagger UI'de endpoint'leri gruplar.
_TAGS_METADATA = [
    {"name": "ops", "description": "Sağlık kontrolü, liveness/readiness."},
    {
        "name": "auth",
        "description": (
            "Multi-tenant JWT auth — login, refresh, logout, me. "
            "Eski X-API-Key backward-compat olarak desteklenir."
        ),
    },
    {"name": "catalog", "description": "Lig + takım + maç kataloğu (read-only)."},
    {
        "name": "team-analysis",
        "description": (
            "Takım-bazlı analiz: form, rating, schedule, fixture difficulty, "
            "head-to-head, player load."
        ),
    },
    {
        "name": "match-analysis",
        "description": (
            "Maç-bazlı analiz: matchup kıyas, preview (form+h2h sentezi), "
            "predict (Poisson+Dixon-Coles)."
        ),
    },
    {"name": "admin", "description": "Operasyonel görünürlük + observability."},
    {
        "name": "assistant",
        "description": (
            "Yardımcı manager — Claude tool_use ile DB'den gerçek veriyle "
            "soruları cevaplar, karar destek sağlar."
        ),
    },
]

app = FastAPI(
    title="football-intelligence",
    version=APP_VERSION,
    description=(
        "Süper Lig odaklı futbol zekası API'si. Tüm uçlar X-API-Key header'ı "
        "ister (/health hariç). Tepkiler ErrorResponse şemasıyla "
        "yapılandırılmış; istekler X-Request-ID ile trace edilir; "
        "rate limit dakika başına (default 120)."
    ),
    openapi_tags=_TAGS_METADATA,
)
register_exception_handlers(app)  # HTTPException → ErrorResponse şeması

# CORS — settings'tan virgülle ayrılmış origin listesi. Boş ise middleware
# kayıtlı olmaz (browser tarafından çağrılan client yok demektir).
_cors_origins = get_settings().cors_origins_list()
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],  # client log eşleştirsin
    )

# Rate limiter — settings'ten okur, tek instance.
_rate_limiter = SlidingWindowRateLimiter(get_settings().rate_limit_per_minute)


_REQUEST_ID_HEADER = "x-request-id"


@app.middleware("http")
async def observability_middleware(request: Request, call_next):
    """Her istek için: request_id + rate limit + duration + metrics counter."""
    # Request ID — varsa gelen header'ı kullan, yoksa uuid4 üret. Hem log'lara
    # contextvar üzerinden enjekte edilir hem response header'ı olarak döner.
    rid = request.headers.get(_REQUEST_ID_HEADER) or uuid.uuid4().hex
    set_request_id(rid)
    request.state.request_id = rid

    path = request.url.path
    try:
        # Rate limit (sadece /health bypass)
        if not should_bypass_rate_limit(path):
            # Key: API key varsa onu, yoksa client IP. Auth disabled olsa bile
            # rate limit IP üzerinden devam eder (DoS koruması).
            key = request.headers.get("x-api-key") or (
                request.client.host if request.client else "unknown"
            )
            if not _rate_limiter.allow(key):
                METRICS.record(
                    method=request.method, path=path, status=429, duration_seconds=0.0
                )
                return JSONResponse(
                    {"detail": "rate limit exceeded (per minute)"},
                    status_code=429,
                    headers={"Retry-After": "60", "X-Request-ID": rid},
                )

        start = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - start
        METRICS.record(
            method=request.method,
            path=path,
            status=response.status_code,
            duration_seconds=duration,
        )
        response.headers["X-Request-ID"] = rid
        return response
    finally:
        clear_request_id()


# /health hariç tüm uçlar bu router üzerinden — auth tek noktada uygulanır.
protected = APIRouter(dependencies=[Depends(require_api_key)])


# ---- yardımcı sorgular ------------------------------------------------------


def _team_matches(
    session: Session,
    team_id: int,
    *,
    before: datetime | None = None,
) -> list[models.Match]:
    """Bir takımın maçları, kickoff desc; `before` verildiyse o tarihten önceki."""
    stmt = select(models.Match).where(
        models.Match.sport == football.SPORT_NAME,
        or_(
            models.Match.home_team_external_id == team_id,
            models.Match.away_team_external_id == team_id,
        ),
    )
    if before is not None:
        stmt = stmt.where(models.Match.kickoff < before)
    return list(session.execute(stmt.order_by(models.Match.kickoff.desc())).scalars())


def _match_pair_filter(a: int, b: int):
    """SQL: (home==a AND away==b) OR (home==b AND away==a)."""
    return or_(
        (models.Match.home_team_external_id == a) & (models.Match.away_team_external_id == b),
        (models.Match.home_team_external_id == b) & (models.Match.away_team_external_id == a),
    )


def _maybe_explain(payload: dict[str, Any], result, explain: bool) -> dict[str, Any]:
    if not explain:
        return payload
    payload["explanation"] = ClaudeCommentator().explain(result)
    return payload


# ---- okuma uçları (Faz 1) ---------------------------------------------------


_DASHBOARD_HTML_PATH = (
    __import__("pathlib").Path(__file__).resolve().parent / "templates" / "dashboard.html"
)


@app.get(
    "/dashboard",
    response_class=HTMLResponse,
    tags=["ops"],
    summary="Minimal operations dashboard (HTML)",
    include_in_schema=False,
)
def dashboard() -> HTMLResponse:
    """Tarayıcı-tarafı dashboard.

    Auth header'ı tarayıcıda kullanıcı girer → localStorage'ta saklanır.
    İçeriği `/health`, `/admin/*`, `/leagues` uçlarından fetch'le çeker;
    Bu endpoint sadece HTML'i static olarak servis eder.
    """
    return HTMLResponse(_DASHBOARD_HTML_PATH.read_text(encoding="utf-8"))


@app.get("/health", tags=["ops"], summary="Liveness + readiness check")
def health(session: Session = Depends(get_session)) -> JSONResponse:
    """Liveness + readiness check.

    DB ping başarısızsa 503 ile döner — orkestrasyon (k8s/docker) bu uca
    bakar. Auth kapsamı dışında: load balancer'lar API key tutmaz.
    `get_session` test ortamında override edilebilir (in-memory SQLite).
    """
    db_status = "ok"
    db_error: str | None = None
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError as e:  # noqa: BLE001 — geniş yakalama bilinçli
        db_status = "error"
        db_error = type(e).__name__

    uptime = round(time.time() - PROCESS_STARTED_AT, 2)
    payload: dict[str, Any] = {
        "status": "ok" if db_status == "ok" else "degraded",
        "version": APP_VERSION,
        "uptime_seconds": uptime,
        "db": db_status,
    }
    if db_error:
        payload["db_error"] = db_error
    status_code = 200 if db_status == "ok" else 503
    return JSONResponse(payload, status_code=status_code)


@protected.get(
    "/teams",
    response_model=list[TeamOut],
    tags=["catalog"],
    summary="Kayıtlı tüm takımları listele (tenant-filtered)",
)
def list_teams(session: Session = Depends(get_session)) -> list[models.Team]:
    """Tüm takımlar. Tenant filter aktifse otomatik current tenant'a kısıtlı."""
    return list(
        session.execute(
            select(models.Team)
            .where(models.Team.sport == football.SPORT_NAME)
            .order_by(models.Team.name)
        ).scalars()
    )


@protected.get(
    "/leagues",
    response_model=list[LeagueOut],
    tags=["catalog"],
    summary="Kayıtlı tüm ligleri listele",
)
def list_leagues(session: Session = Depends(get_session)) -> list[models.League]:
    return list(
        session.execute(
            select(models.League)
            .where(models.League.sport == football.SPORT_NAME)
            .order_by(models.League.season.desc(), models.League.name)
        ).scalars()
    )


_BATCH_INCLUDABLES: frozenset[str] = frozenset({"form", "rating", "schedule"})


@protected.get(
    "/teams/batch",
    tags=["team-analysis"],
    summary="Birden çok takımın analizi tek istekte (form/rating/schedule)",
)
def teams_batch_analysis(
    ids: str = Query(
        ...,
        description="Virgülle ayrılmış team external_id listesi. Max 20.",
    ),
    include: str = Query(
        "form,rating",
        description="Hangi engine'leri çağır (virgülle ayrı): form, rating, schedule",
    ),
    last_n: int = Query(5, ge=1, le=50),
    session: Session = Depends(get_session),
) -> dict[str, dict[str, Any]]:
    """Birden çok takım için form/rating/schedule tek istekte.

    Browser/mobile client'lar N tane HTTP çağrısı yerine 1 batch yapabilir.
    Response: `{team_id: {form?, rating?, schedule?, error?}}`.

    Maks 20 id (DoS koruması). Bilinmeyen team_id → `{"error": "no_matches"}`
    (404 yerine satır-içi hata, batch akışı bozulmasın).
    """
    try:
        team_ids = [int(x.strip()) for x in ids.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_ids", "message": "ids tamsayı listesi olmalı"},
        ) from None
    if not team_ids:
        raise HTTPException(
            status_code=400,
            detail={"code": "empty_ids", "message": "ids boş olamaz"},
        )
    if len(team_ids) > 20:
        raise HTTPException(
            status_code=400,
            detail={"code": "too_many_ids", "message": "en fazla 20 team_id"},
        )

    requested = {tok.strip() for tok in include.split(",") if tok.strip()}
    unknown = requested - _BATCH_INCLUDABLES
    if unknown:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "invalid_include",
                "message": f"bilinmeyen engine adı: {sorted(unknown)}",
                "details": {"allowed": sorted(_BATCH_INCLUDABLES)},
            },
        )

    out: dict[str, dict[str, Any]] = {}
    for tid in team_ids:
        team_matches = _team_matches(session, tid)
        if not team_matches:
            out[str(tid)] = {"error": "no_matches"}
            continue
        entry: dict[str, Any] = {}
        if "form" in requested:
            entry["form"] = engine_result_to_dict(
                compute_form(tid, team_matches, last_n=last_n)
            )
        if "rating" in requested:
            entry["rating"] = engine_result_to_dict(
                compute_team_rating(tid, team_matches, last_n=last_n)
            )
        if "schedule" in requested:
            ref_tz = team_matches[0].kickoff.tzinfo
            now = datetime.now(ref_tz)
            entry["schedule"] = engine_result_to_dict(
                compute_schedule(tid, team_matches, now=now, horizon_days=30)
            )
        out[str(tid)] = entry
    return out


@protected.get(
    "/teams/{league_id}",
    response_model=list[TeamOut],
    tags=["catalog"],
    summary="Lig içindeki takımları listele",
)
def teams_in_league(
    league_id: int, session: Session = Depends(get_session)
) -> list[models.Team]:
    home_ids = (
        select(models.Match.home_team_external_id)
        .where(
            models.Match.sport == football.SPORT_NAME,
            models.Match.league_external_id == league_id,
        )
        .distinct()
    )
    away_ids = (
        select(models.Match.away_team_external_id)
        .where(
            models.Match.sport == football.SPORT_NAME,
            models.Match.league_external_id == league_id,
        )
        .distinct()
    )
    team_ids = {row[0] for row in session.execute(home_ids.union(away_ids)).all()}
    if not team_ids:
        raise HTTPException(status_code=404, detail=f"league {league_id} için takım bulunamadı")

    return list(
        session.execute(
            select(models.Team)
            .where(
                models.Team.sport == football.SPORT_NAME,
                models.Team.external_id.in_(team_ids),
            )
            .order_by(models.Team.name)
        ).scalars()
    )


@protected.get(
    "/teams/{team_id}/matches",
    response_model=list[MatchOut],
    tags=["catalog"],
    summary="Takımın tüm maçları (kickoff desc)",
)
def matches_for_team(
    team_id: int, session: Session = Depends(get_session)
) -> list[models.Match]:
    return _team_matches(session, team_id)


# ---- analiz uçları (Faz 5) --------------------------------------------------


@protected.get(
    "/teams/{team_id}/form",
    tags=["team-analysis"],
    summary="Son N maçtaki form (engine.form v4)",
)
def team_form(
    team_id: int,
    last_n: int = Query(5, ge=1, le=50),
    time_decay_rate: float = Query(
        0.0,
        ge=0.0,
        le=1.0,
        description="0 = uniform; 0.0077 ≈ 90g half-life; 0.023 ≈ 30g; 0.069 ≈ 10g",
    ),
    explain: bool = False,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    # Team lookup ÖNCE — cross-tenant 404'ü garanti eder (loader_criteria
    # filter aktifse current tenant'ın takımı değilse Team yok → 404)
    team = session.execute(
        select(models.Team).where(
            models.Team.sport == football.SPORT_NAME,
            models.Team.external_id == team_id,
        )
    ).scalar_one_or_none()
    if team is None:
        raise HTTPException(status_code=404, detail=f"team {team_id} bulunamadı")
    matches = _team_matches(session, team_id)
    if not matches:
        # Team var ama maç yok — yine 404 (eski semantik)
        raise HTTPException(status_code=404, detail=f"team {team_id} için maç yok")
    result = compute_form(team_id, matches, last_n=last_n, time_decay_rate=time_decay_rate)
    return _maybe_explain(engine_result_to_dict(result), result, explain)


@protected.get(
    "/teams/{team_id}/rating",
    tags=["team-analysis"],
    summary="Takım rating'i — overall + ev/dep (engine.rating v2)",
)
def team_rating(
    team_id: int,
    last_n: int = Query(10, ge=1, le=50),
    time_decay_rate: float = Query(
        0.0,
        ge=0.0,
        le=1.0,
        description="0 = uniform; 0.0077 ≈ 90g half-life; 0.023 ≈ 30g",
    ),
    explain: bool = False,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    matches = _team_matches(session, team_id)
    if not matches:
        raise HTTPException(status_code=404, detail=f"team {team_id} için maç yok")
    result = compute_team_rating(
        team_id, matches, last_n=last_n, time_decay_rate=time_decay_rate
    )
    return _maybe_explain(engine_result_to_dict(result), result, explain)


@protected.get(
    "/teams/{a}/vs/{b}",
    tags=["team-analysis"],
    summary="İki takım arası head-to-head özet (engine.opponent v3)",
)
def head_to_head(
    a: int,
    b: int,
    explain: bool = False,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    if a == b:
        raise HTTPException(status_code=400, detail="aynı takım için head-to-head olmaz")
    matches = list(
        session.execute(
            select(models.Match).where(
                models.Match.sport == football.SPORT_NAME,
                _match_pair_filter(a, b),
            )
        ).scalars()
    )
    result = compute_head_to_head(a, b, matches)
    return _maybe_explain(engine_result_to_dict(result), result, explain)


@protected.get(
    "/players/{player_id}/load",
    tags=["team-analysis"],
    summary="Oyuncu yük raporu (engine.load)",
)
def player_load(
    player_id: int,
    window_days: int = Query(14, ge=1, le=90),
    explain: bool = False,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Oyuncu yük raporu — son N gündeki dakika + maç sıklığı.

    Veri kaynağı `player_appearances` tablosu (lineup adapter Faz 6'da
    dolduracak; şimdilik boş — endpoint 404 döner). high_load eşiği
    haftalık 270 dakika (~3 maçlık yük).
    """
    appearances = list(
        session.execute(
            select(models.PlayerAppearance).where(
                models.PlayerAppearance.sport == football.SPORT_NAME,
                models.PlayerAppearance.player_external_id == player_id,
            )
        ).scalars()
    )
    if not appearances:
        raise HTTPException(
            status_code=404, detail=f"player {player_id} için appearance yok"
        )
    # SQLite tz-strip (engine.schedule ile aynı pattern); engine içeride
    # kickoff'u cutoff ile karşılaştırıyor
    ref_tz = appearances[0].kickoff.tzinfo
    now = datetime.now(ref_tz)
    result = compute_player_load(
        player_id, appearances, window_days=window_days, now=now
    )
    return _maybe_explain(engine_result_to_dict(result), result, explain)


@protected.get(
    "/players/{player_id}/form",
    tags=["team-analysis"],
    summary="Oyuncu form snapshot — Z-score baseline'la (engine.player_form)",
)
def player_form(
    player_id: int,
    recent_n: int = Query(5, ge=1, le=20),
    baseline_window_days: int = Query(365, ge=30, le=730),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Son N maç oyuncu formu vs son 1 yılın baseline'ı.

    Z-score ≥ 1.0 → "belirgin yüksek dakika", "rising" trend → form yükseliyor.
    Veri kaynağı player_appearances; lineup adapter zenginleştiğinde (key_passes,
    shot_accuracy v.b.) engine sözleşmesi aynı, snapshot alanları artar.
    """
    from app.engine.player_form import compute_player_form

    appearances = list(
        session.execute(
            select(models.PlayerAppearance).where(
                models.PlayerAppearance.sport == football.SPORT_NAME,
                models.PlayerAppearance.player_external_id == player_id,
            )
        ).scalars()
    )
    if not appearances:
        raise HTTPException(
            status_code=404, detail=f"player {player_id} için appearance yok"
        )
    ref_tz = appearances[0].kickoff.tzinfo
    now = datetime.now(ref_tz)
    result = compute_player_form(
        player_id, appearances,
        recent_n=recent_n,
        baseline_window_days=baseline_window_days,
        now=now,
    )
    return engine_result_to_dict(result)


@protected.get(
    "/teams/{team_id}/schedule",
    tags=["team-analysis"],
    summary="Fikstür yoğunluğu — ufuk içi maç sayımı (engine.schedule)",
)
def team_schedule(
    team_id: int,
    horizon_days: int = Query(30, ge=1, le=180),
    explain: bool = False,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    matches = _team_matches(session, team_id)
    if not matches:
        raise HTTPException(status_code=404, detail=f"team {team_id} için maç yok")
    # SQLite, DateTime(timezone=True) sütunlarını naive döndürür; engine
    # Python seviyesinde m.kickoff <= now karşılaştırması yapıyor → `now`'u
    # kickoff'un tz'ine eşitle. PG'de tz-aware, SQLite'da naive — aynı yol.
    ref_tz = matches[0].kickoff.tzinfo
    now = datetime.now(ref_tz)
    result = compute_schedule(team_id, matches, now=now, horizon_days=horizon_days)
    return _maybe_explain(engine_result_to_dict(result), result, explain)


@protected.get(
    "/teams/{team_id}/fixture-difficulty",
    tags=["team-analysis"],
    summary="Önündeki rakiplerin gücü (side-aware rating, engine.fixture_difficulty v2)",
)
def team_fixture_difficulty(
    team_id: int,
    horizon_days: int = Query(30, ge=1, le=180),
    last_n: int = Query(10, ge=1, le=50),
    explain: bool = False,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Önümüzdeki maçlardaki rakip zorluğu (rating-ağırlıklı).

    Rakip rating'leri `engine.rating` ile rakibin geçmiş `last_n` maçından
    hesaplanır. Bilinmeyen rakipler rapor'da `matches_unknown_opponent`
    olarak işaretlenir (rotasyon kararı için kapsam sinyali).
    """
    matches = _team_matches(session, team_id)
    if not matches:
        raise HTTPException(status_code=404, detail=f"team {team_id} için maç yok")

    # SQLite tz-strip workaround (engine.schedule ile aynı).
    ref_tz = matches[0].kickoff.tzinfo
    now = datetime.now(ref_tz)
    horizon_cutoff = now + timedelta(days=horizon_days)

    upcoming_opponents: set[int] = {
        (m.away_team_external_id if m.home_team_external_id == team_id else m.home_team_external_id)
        for m in matches
        if m.kickoff > now
        and m.kickoff <= horizon_cutoff
        and m.status not in football.FINISHED_STATUSES
        and team_id in (m.home_team_external_id, m.away_team_external_id)
    }

    opponent_ratings: dict[int, OpponentRating] = {}
    for opp_id in upcoming_opponents:
        opp_matches = _team_matches(session, opp_id)
        if not opp_matches:
            continue
        rating = compute_team_rating(opp_id, opp_matches, last_n=last_n).value
        if rating.matches_considered == 0:
            continue
        # Side-aware: rakibin ev/dep profili farklı olabilir → her ikisini
        # de besleyelim, engine maç başına uygunu seçer. Boş subset (0 maç)
        # için side-specific'i None bırak; overall fallback devreye girer.
        opponent_ratings[opp_id] = OpponentRating(
            home_rating=rating.home_rating if rating.home_matches > 0 else None,
            away_rating=rating.away_rating if rating.away_matches > 0 else None,
            overall_rating=rating.rating,
        )

    # Engine kendi içinde horizon'u uygulamıyor; önceden filtreyi yukarıda
    # yaptık zaten — engine'e ufuk içi maçların hepsini geçiyoruz.
    horizon_matches = [m for m in matches if m.kickoff <= horizon_cutoff]
    result = compute_fixture_difficulty(team_id, horizon_matches, opponent_ratings, now=now)
    return _maybe_explain(engine_result_to_dict(result), result, explain)


@protected.get(
    "/matchup/{home}/{away}",
    tags=["match-analysis"],
    summary="İki takım kıyas raporu (engine.matchup)",
)
def matchup(
    home: int,
    away: int,
    last_n: int = Query(5, ge=1, le=50),
    explain: bool = False,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    if home == away:
        raise HTTPException(status_code=400, detail="aynı takım için matchup olmaz")

    home_matches = _team_matches(session, home)
    away_matches = _team_matches(session, away)
    if not home_matches:
        raise HTTPException(status_code=404, detail=f"team {home} için maç yok")
    if not away_matches:
        raise HTTPException(status_code=404, detail=f"team {away} için maç yok")

    home_form = compute_form(home, home_matches, last_n=last_n)
    away_form = compute_form(away, away_matches, last_n=last_n)
    h2h_matches = list(
        session.execute(
            select(models.Match).where(
                models.Match.sport == football.SPORT_NAME,
                _match_pair_filter(home, away),
            )
        ).scalars()
    )
    h2h = compute_head_to_head(home, away, h2h_matches)

    result = compute_matchup(
        home_form.value,
        away_form.value,
        h2h.value,
        home_team_id=home,
        away_team_id=away,
    )
    return _maybe_explain(engine_result_to_dict(result), result, explain)


# Shadow tahminler için sabit ρ seti — A/B karşılaştırma:
# 0.0 saf Poisson (PR #17'den önceki baseline), -0.18 daha agresif DC
_SHADOW_RHOS: tuple[float, ...] = (0.0, -0.18)


@protected.get(
    "/matches/{match_id}/predict",
    tags=["match-analysis"],
    summary="Skor tahmini (Poisson + Dixon-Coles, engine.predict v2)",
)
def match_predict(
    match_id: int,
    last_n: int = Query(5, ge=1, le=50),
    time_decay_rate: float = Query(
        0.0, ge=0.0, le=1.0,
        description="Form gf/ga için zaman ağırlığı; engine.predict λ'yı bu form'dan alır",
    ),
    explain: bool = False,
    shadow: bool = Query(
        False,
        description="True → birincilin yanına ρ=0 ve ρ=-0.18 shadow tahminleri de kaydeder (A/B accuracy için).",
    ),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Maç için Poisson skor tahmini.

    Form, maçın kickoff'undan ÖNCEKİ maçlardan hesaplanır (leakage yok); bu
    sayede tahmin hem NS maçlar için "pre-game" hem FT maçlar için
    "backtest" anlamı taşır.

    `time_decay_rate>0` ise form'un goals_for/against per-match averages
    zaman-ağırlıklı (engine.form v4); λ değerleri buna göre değişir.

    `shadow=true` ise birincil tahminin yanına ρ=0 (saf Poisson) ve
    ρ=-0.18 (agresif DC) shadow tahminleri de saklanır (rapor B3'te
    `engine_version` aynı ama params farklı → ayrı satırlar).
    """
    match = session.execute(
        select(models.Match).where(
            models.Match.sport == football.SPORT_NAME,
            models.Match.external_id == match_id,
        )
    ).scalar_one_or_none()
    if match is None:
        raise HTTPException(status_code=404, detail=f"match {match_id} bulunamadı")

    home_id = match.home_team_external_id
    away_id = match.away_team_external_id
    params = {"last_n": last_n, "time_decay_rate": time_decay_rate}

    def _forms():
        home_form = compute_form(
            home_id, _team_matches(session, home_id, before=match.kickoff),
            last_n=last_n, time_decay_rate=time_decay_rate,
        )
        away_form = compute_form(
            away_id, _team_matches(session, away_id, before=match.kickoff),
            last_n=last_n, time_decay_rate=time_decay_rate,
        )
        return home_form, away_form

    def _build_result():
        home_form, away_form = _forms()
        return compute_predict(
            home_form.value, away_form.value,
            home_team_id=home_id, away_team_id=away_id,
        )

    def _save_shadows() -> None:
        """Birincilin yanına ρ=0 ve ρ=-0.18 shadow'larını kaydet."""
        home_form, away_form = _forms()
        for rho in _SHADOW_RHOS:
            shadow_result = compute_predict(
                home_form.value, away_form.value,
                home_team_id=home_id, away_team_id=away_id, rho=rho,
            )
            save_prediction(
                session, sport=football.SPORT_NAME,
                match_external_id=match_id, result=shadow_result,
                params={**params, "rho": rho},  # params_hash farklı
            )

    # `explain=True` Claude'a hit eder (kendi cache'i AI commentator'da);
    # cache atlanır, prediction her zaman saklanır (kalibrasyon).
    if explain:
        result = _build_result()
        save_prediction(
            session, sport=football.SPORT_NAME,
            match_external_id=match_id, result=result, params=params,
        )
        if shadow:
            _save_shadows()
        session.commit()
        return _maybe_explain(engine_result_to_dict(result), result, explain=True)

    # explain yoksa snapshot-keyed cache devreye girer; ilk miss'te
    # save_prediction da burada çalışır (idempotent upsert)
    def _compute() -> dict[str, Any]:
        result = _build_result()
        save_prediction(
            session, sport=football.SPORT_NAME,
            match_external_id=match_id, result=result, params=params,
        )
        if shadow:
            _save_shadows()
        return engine_result_to_dict(result)

    payload, _was_cached = engine_cached(
        session,
        sport=football.SPORT_NAME,
        key_parts=(
            "predict", match_id, "last_n", last_n,
            "decay", str(time_decay_rate), "shadow", int(shadow),
        ),
        compute_fn=_compute,
    )
    return payload


@protected.get(
    "/matches/{match_id}/preview",
    tags=["match-analysis"],
    summary="Maç öncesi brief: form + head-to-head sentezi",
)
def match_preview(
    match_id: int,
    last_n: int = Query(5, ge=1, le=50),
    time_decay_rate: float = Query(0.0, ge=0.0, le=1.0),
    explain: bool = False,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Bir maç için ön bakış: ev/dep form + head-to-head.

    Form hesabı maçın kickoff zamanından ÖNCEKİ tamamlanmış maçlar üzerinden
    yapılmalı (sızıntı olmasın); aksi halde maçın sonucu da girer.
    `time_decay_rate>0` ise form gf/ga per_match zaman-ağırlıklı.
    """
    match = session.execute(
        select(models.Match).where(
            models.Match.sport == football.SPORT_NAME,
            models.Match.external_id == match_id,
        )
    ).scalar_one_or_none()
    if match is None:
        raise HTTPException(status_code=404, detail=f"match {match_id} bulunamadı")

    home_id = match.home_team_external_id
    away_id = match.away_team_external_id

    home_form = compute_form(
        home_id, _team_matches(session, home_id, before=match.kickoff),
        last_n=last_n, time_decay_rate=time_decay_rate,
    )
    away_form = compute_form(
        away_id, _team_matches(session, away_id, before=match.kickoff),
        last_n=last_n, time_decay_rate=time_decay_rate,
    )

    h2h_matches = list(
        session.execute(
            select(models.Match).where(
                models.Match.sport == football.SPORT_NAME,
                models.Match.kickoff < match.kickoff,
                _match_pair_filter(home_id, away_id),
            )
        ).scalars()
    )
    h2h = compute_head_to_head(home_id, away_id, h2h_matches)

    payload: dict[str, Any] = {
        "match": {
            "external_id": match.external_id,
            "kickoff": match.kickoff.isoformat(),
            "status": match.status,
            "home_team_external_id": home_id,
            "away_team_external_id": away_id,
        },
        "home_form": engine_result_to_dict(home_form),
        "away_form": engine_result_to_dict(away_form),
        "head_to_head": engine_result_to_dict(h2h),
    }
    if explain:
        payload["explanation"] = ClaudeCommentator().explain_match_preview(
            home_form=home_form,
            away_form=away_form,
            h2h=h2h,
            home_team_id=home_id,
            away_team_id=away_id,
            kickoff_iso=match.kickoff.isoformat(),
        )
    return payload


# ---- assistant chat (Faz K1 + Faz L1 persist) ------------------------------


@protected.post(
    "/assistant/chat",
    tags=["assistant"],
    summary="Yardımcı manager — soru sor, Claude tool'larla cevap verir",
)
def assistant_chat(
    body: dict[str, Any],
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """`{"message": str, "conversation_id"?: int, "team_external_id"?: int}` →
    asistan cevabı + tool trace + conversation_id (yeni oluşturulduysa).

    `conversation_id` verilirse o konuşmanın tüm geçmişi DB'den okunup
    Claude'a history olarak verilir. Yoksa yeni konuşma yaratılır.
    `team_external_id` ile assistant_memory enjekte edilir.
    """
    from app.assistant import (
        append_message,
        create_conversation,
        get_conversation_history,
    )
    from app.assistant import (
        chat as assistant_chat_fn,
    )

    message = body.get("message")
    if not isinstance(message, str) or not message.strip():
        raise HTTPException(status_code=422, detail="message gerekli (non-empty str)")
    team_id = body.get("team_external_id")
    if team_id is not None and not isinstance(team_id, int):
        raise HTTPException(status_code=422, detail="team_external_id int olmalı")
    conversation_id = body.get("conversation_id")
    if conversation_id is not None and not isinstance(conversation_id, int):
        raise HTTPException(status_code=422, detail="conversation_id int olmalı")

    # Konuşma yarat ya da geçmişi yükle
    if conversation_id is None:
        conv = create_conversation(
            session, team_external_id=team_id, title=message[:80],
        )
        conversation_id = conv.id
        history: list[dict[str, Any]] = []
    else:
        history = get_conversation_history(session, conversation_id)

    # User mesajını kaydet
    append_message(
        session, conversation_id=conversation_id,
        role="user", content=message,
    )

    result = assistant_chat_fn(
        session, user_message=message, history=history,
        team_external_id=team_id,
    )

    # Assistant cevabını kaydet
    append_message(
        session, conversation_id=conversation_id,
        role="assistant", content=result.text,
        tool_traces=[
            {"name": t.name, "input": t.input, "output_preview": t.output[:300]}
            for t in result.tool_traces
        ],
        total_tokens=result.total_tokens,
    )
    session.commit()

    return {
        "conversation_id": conversation_id,
        "text": result.text,
        "tool_traces": [
            {"name": t.name, "input": t.input, "output_preview": t.output[:300]}
            for t in result.tool_traces
        ],
        "iterations": result.iterations,
        "total_tokens": result.total_tokens,
        "stub": result.stub,
    }


@protected.get(
    "/assistant/conversations",
    tags=["assistant"],
    summary="Geçmiş konuşmaları listele",
)
def list_assistant_conversations(
    team_external_id: int | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    from app.assistant import list_conversations

    rows = list_conversations(
        session, team_external_id=team_external_id, limit=limit,
    )
    return {
        "conversations": [
            {
                "id": r.id, "team_external_id": r.team_external_id,
                "title": r.title,
                "created_at": r.created_at.isoformat(),
                "updated_at": r.updated_at.isoformat(),
            }
            for r in rows
        ],
    }


@protected.get(
    "/assistant/conversations/{conversation_id}",
    tags=["assistant"],
    summary="Bir konuşmanın tüm mesajlarını döndür",
)
def get_assistant_conversation(
    conversation_id: int,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    from app.assistant import get_conversation_history

    history = get_conversation_history(session, conversation_id)
    if not history:
        # Konuşma yok ya da boş — caller ayırt edebilsin diye sade dönüyoruz
        return {"conversation_id": conversation_id, "messages": []}
    return {"conversation_id": conversation_id, "messages": history}


# ---- assistant memory (Faz K3) ---------------------------------------------


@protected.get(
    "/assistant/memory/{subject_type}/{subject_id}",
    tags=["assistant"],
    summary="Saklı asistan hafızasını listele",
)
def list_assistant_memory(
    subject_type: str, subject_id: int,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    from app.assistant import memory_list

    return {
        "subject_type": subject_type,
        "subject_id": subject_id,
        "memory": memory_list(session, subject_type=subject_type, subject_id=subject_id),
    }


@protected.put(
    "/assistant/memory/{subject_type}/{subject_id}/{key}",
    tags=["assistant"],
    summary="Asistan hafızasında bir anahtarı kaydet/güncelle",
)
def set_assistant_memory(
    subject_type: str, subject_id: int, key: str,
    body: dict[str, Any],
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Body: `{"value": <any>}` — value JSON-serializable olmalı."""
    from app.assistant import memory_set

    if "value" not in body:
        raise HTTPException(status_code=422, detail="value gerekli")
    memory_set(
        session, subject_type=subject_type, subject_id=subject_id,
        key=key, value=body["value"],
    )
    session.commit()
    return {"ok": True, "key": key}


@protected.delete(
    "/assistant/memory/{subject_type}/{subject_id}/{key}",
    tags=["assistant"],
    summary="Asistan hafızasından bir anahtarı sil",
)
def delete_assistant_memory(
    subject_type: str, subject_id: int, key: str,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    from app.assistant import memory_delete

    deleted = memory_delete(
        session, subject_type=subject_type, subject_id=subject_id, key=key,
    )
    session.commit()
    return {"ok": True, "deleted": deleted}


# ---- match simulator (Faz K4) ----------------------------------------------


@protected.post(
    "/matches/{match_id}/simulate",
    tags=["match-analysis"],
    summary="Karşı-olgu (counterfactual) tahmin: form override'larıyla simüle et",
)
def simulate_match(
    match_id: int,
    body: dict[str, Any],
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """`{"home_form_override"?: {goals_for_per_match, goals_against_per_match},
        "away_form_override"?: {...}, "rho"?: float}` → simüle predict.

    Use case: "ev sahibi takım 1 yerine 2.5 gol attığı bir senaryoda olasılık
    nasıl değişir?" → counterfactual karar destek.
    """
    from app.engine.form import FormReport

    match = session.execute(
        select(models.Match).where(
            models.Match.sport == football.SPORT_NAME,
            models.Match.external_id == match_id,
        )
    ).scalar_one_or_none()
    if match is None:
        raise HTTPException(status_code=404, detail=f"match {match_id} yok")

    # Baseline form'ları al
    def _prior(tid: int):
        return list(
            session.execute(
                select(models.Match).where(
                    models.Match.sport == football.SPORT_NAME,
                    models.Match.kickoff < match.kickoff,
                    or_(
                        models.Match.home_team_external_id == tid,
                        models.Match.away_team_external_id == tid,
                    ),
                )
            ).scalars()
        )

    home_baseline = compute_form(match.home_team_external_id, _prior(match.home_team_external_id), last_n=5).value
    away_baseline = compute_form(match.away_team_external_id, _prior(match.away_team_external_id), last_n=5).value

    def _apply_override(baseline: FormReport, override: dict[str, Any] | None) -> FormReport:
        if not override:
            return baseline
        # dataclass.replace; sadece sayısal alanlar override edilebilir
        from dataclasses import replace
        kw: dict[str, Any] = {}
        if "goals_for_per_match" in override:
            kw["goals_for_per_match"] = float(override["goals_for_per_match"])
        if "goals_against_per_match" in override:
            kw["goals_against_per_match"] = float(override["goals_against_per_match"])
        return replace(baseline, **kw) if kw else baseline

    home_form = _apply_override(home_baseline, body.get("home_form_override"))
    away_form = _apply_override(away_baseline, body.get("away_form_override"))
    rho = float(body.get("rho", -0.12))

    p = compute_predict(
        home_form, away_form,
        home_team_id=match.home_team_external_id,
        away_team_id=match.away_team_external_id,
        rho=rho,
    ).value
    return {
        "match_id": match_id,
        "rho_used": rho,
        "baseline_form": {
            "home": {
                "goals_for_per_match": home_baseline.goals_for_per_match,
                "goals_against_per_match": home_baseline.goals_against_per_match,
            },
            "away": {
                "goals_for_per_match": away_baseline.goals_for_per_match,
                "goals_against_per_match": away_baseline.goals_against_per_match,
            },
        },
        "applied_form": {
            "home": {
                "goals_for_per_match": home_form.goals_for_per_match,
                "goals_against_per_match": home_form.goals_against_per_match,
            },
            "away": {
                "goals_for_per_match": away_form.goals_for_per_match,
                "goals_against_per_match": away_form.goals_against_per_match,
            },
        },
        "simulated_prediction": {
            "expected_home_goals": p.expected_home_goals,
            "expected_away_goals": p.expected_away_goals,
            "prob_home_win": p.prob_home_win,
            "prob_draw": p.prob_draw,
            "prob_away_win": p.prob_away_win,
            "most_likely_score": list(p.most_likely_score),
        },
    }


# Auth endpoint'leri PROTECTED router'a değil app'e — login/refresh
# bearer header gerektirmez (login'in kendisi token üretir).
app.include_router(auth_router)

protected.include_router(admin_router)
app.include_router(protected)
# WebSocket router — auth FastAPI WebSocket'ta header bazlı; pilot demo
# için public route (production'da Cookie/Header-based auth eklenir).
app.include_router(live_router)
