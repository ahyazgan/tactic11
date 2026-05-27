"""FastAPI app — DB'den okuyan + engine'i tüketen uçlar.

Katman dış kaynağa dokunmaz (sync `scripts/sync_league.py` / `scheduler/`).
Engine pure kalsın diye serileştirme `serialize.py` üzerinden.
"""

from __future__ import annotations

from datetime import datetime  # noqa: F401  type hint only
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
from app.db import models
from app.db.session import get_session
from app.engine.form import compute_form
from app.engine.opponent import compute_head_to_head
from app.engine.rating import compute_team_rating
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
    before: "datetime | None" = None,
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
    explain: bool = False,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    matches = _team_matches(session, team_id)
    if not matches:
        raise HTTPException(status_code=404, detail=f"team {team_id} için maç yok")
    result = compute_form(team_id, matches, last_n=last_n)
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
