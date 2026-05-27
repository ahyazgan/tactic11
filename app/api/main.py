"""FastAPI app — DB'den okuyan + engine'i tüketen uçlar.

Katman dış kaynağa dokunmaz (sync `scripts/sync_league.py` / `scheduler/`).
Engine pure kalsın diye serileştirme `serialize.py` üzerinden.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.ai import ClaudeCommentator
from app.api.admin import router as admin_router
from app.api.auth import require_api_key
from app.api.schemas import LeagueOut, MatchOut, TeamOut
from app.api.serialize import engine_result_to_dict
from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.data.cache import engine_cached
from app.db import models
from app.db.session import get_session
from app.engine.fixture_difficulty import OpponentRating, compute_fixture_difficulty
from app.engine.form import compute_form
from app.engine.matchup import compute_matchup
from app.engine.opponent import compute_head_to_head
from app.engine.predict import compute_predict
from app.engine.rating import compute_team_rating
from app.engine.schedule import compute_schedule
from app.sports import football

setup_logging()

if not get_settings().api_auth_key:
    get_logger(__name__).warning(
        "API_AUTH_KEY boş — auth DEVRE DIŞI. Production'da bu değeri set edin "
        "(env-var typosu? .env yüklendi mi?). /health dışında her uç açık."
    )

app = FastAPI(title="football-intelligence", version="0.3.0")

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
def health() -> dict[str, str]:
    return {"status": "ok"}


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
    explain: bool = False,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    matches = _team_matches(session, team_id)
    if not matches:
        raise HTTPException(status_code=404, detail=f"team {team_id} için maç yok")
    result = compute_team_rating(team_id, matches, last_n=last_n)
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


@protected.get("/matches/{match_id}/predict")
def match_predict(
    match_id: int,
    last_n: int = Query(5, ge=1, le=50),
    explain: bool = False,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Maç için Poisson skor tahmini.

    Form, maçın kickoff'undan ÖNCEKİ maçlardan hesaplanır (leakage yok); bu
    sayede tahmin hem NS maçlar için "pre-game" hem FT maçlar için
    "backtest" anlamı taşır.
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

    # `explain=True` Claude'a hit eder (kendi cache'i AI commentator'da); engine
    # sonucunu yine de tek seferde üret, payload + audit ikisini de elde tut.
    if explain:
        home_form = compute_form(
            home_id, _team_matches(session, home_id, before=match.kickoff), last_n=last_n
        )
        away_form = compute_form(
            away_id, _team_matches(session, away_id, before=match.kickoff), last_n=last_n
        )
        result = compute_predict(
            home_form.value, away_form.value,
            home_team_id=home_id, away_team_id=away_id,
        )
        return _maybe_explain(engine_result_to_dict(result), result, explain=True)

    # explain yoksa snapshot-keyed cache devreye girer
    def _compute() -> dict[str, Any]:
        home_form = compute_form(
            home_id, _team_matches(session, home_id, before=match.kickoff), last_n=last_n
        )
        away_form = compute_form(
            away_id, _team_matches(session, away_id, before=match.kickoff), last_n=last_n
        )
        result = compute_predict(
            home_form.value, away_form.value,
            home_team_id=home_id, away_team_id=away_id,
        )
        return engine_result_to_dict(result)

    payload, _was_cached = engine_cached(
        session,
        sport=football.SPORT_NAME,
        key_parts=("predict", match_id, "last_n", last_n),
        compute_fn=_compute,
    )
    return payload


@protected.get("/matches/{match_id}/preview")
def match_preview(
    match_id: int,
    last_n: int = Query(5, ge=1, le=50),
    explain: bool = False,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Bir maç için ön bakış: ev/dep form + head-to-head.

    Form hesabı maçın kickoff zamanından ÖNCEKİ tamamlanmış maçlar üzerinden
    yapılmalı (sızıntı olmasın); aksi halde maçın sonucu da girer.
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

    home_form = compute_form(home_id, _team_matches(session, home_id, before=match.kickoff), last_n=last_n)
    away_form = compute_form(away_id, _team_matches(session, away_id, before=match.kickoff), last_n=last_n)

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
