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
from fastapi.responses import JSONResponse
from sqlalchemy import or_, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.ai import ClaudeCommentator
from app.api.admin import router as admin_router
from app.api.auth import require_api_key
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

# Prod modunda zorunlu secret'lar varsa fail-fast (ConfigError → boot durur).
# Dev/staging modlarda kontrol pas geçer; aşağıdaki yumuşak uyarı devam eder.
get_settings().validate_for_production()

if not get_settings().api_auth_key:
    get_logger(__name__).warning(
        "API_AUTH_KEY boş — auth DEVRE DIŞI. Production'da bu değeri set edin "
        "(env-var typosu? .env yüklendi mi?). /health dışında her uç açık."
    )

APP_VERSION = "0.4.0"  # production hardening turunda bumped
app = FastAPI(title="football-intelligence", version=APP_VERSION)
register_exception_handlers(app)  # HTTPException → ErrorResponse şeması

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


@app.get("/health")
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


@protected.get("/leagues", response_model=list[LeagueOut])
def list_leagues(session: Session = Depends(get_session)) -> list[models.League]:
    return list(
        session.execute(
            select(models.League)
            .where(models.League.sport == football.SPORT_NAME)
            .order_by(models.League.season.desc(), models.League.name)
        ).scalars()
    )


@protected.get("/teams/{league_id}", response_model=list[TeamOut])
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


@protected.get("/teams/{team_id}/matches", response_model=list[MatchOut])
def matches_for_team(
    team_id: int, session: Session = Depends(get_session)
) -> list[models.Match]:
    return _team_matches(session, team_id)


# ---- analiz uçları (Faz 5) --------------------------------------------------


@protected.get("/teams/{team_id}/form")
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
    matches = _team_matches(session, team_id)
    if not matches:
        raise HTTPException(status_code=404, detail=f"team {team_id} için maç yok")
    result = compute_form(team_id, matches, last_n=last_n, time_decay_rate=time_decay_rate)
    return _maybe_explain(engine_result_to_dict(result), result, explain)


@protected.get("/teams/{team_id}/rating")
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


@protected.get("/teams/{a}/vs/{b}")
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


@protected.get("/players/{player_id}/load")
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


@protected.get("/teams/{team_id}/schedule")
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


@protected.get("/teams/{team_id}/fixture-difficulty")
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


@protected.get("/matchup/{home}/{away}")
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


@protected.get("/matches/{match_id}/predict")
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


@protected.get("/matches/{match_id}/preview")
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


protected.include_router(admin_router)
app.include_router(protected)
