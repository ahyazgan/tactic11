"""FastAPI app — DB'den okuyan + engine'i tüketen uçlar.

Katman dış kaynağa dokunmaz (sync `scripts/sync_league.py` / `scheduler/`).
Engine pure kalsın diye serileştirme `serialize.py` üzerinden.
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.ai import ClaudeCommentator
from app.api.schemas import LeagueOut, MatchOut, TeamOut
from app.api.serialize import engine_result_to_dict
from app.core.logging import setup_logging
from app.db import models
from app.db.session import get_session
from app.engine.form import compute_form
from app.engine.opponent import compute_head_to_head
from app.engine.rating import compute_team_rating
from app.sports import football

setup_logging()

app = FastAPI(title="football-intelligence", version="0.2.0")


# ---- yardımcı sorgular ------------------------------------------------------


def _team_matches(session: Session, team_id: int) -> list[models.Match]:
    return list(
        session.execute(
            select(models.Match)
            .where(
                models.Match.sport == football.SPORT_NAME,
                or_(
                    models.Match.home_team_external_id == team_id,
                    models.Match.away_team_external_id == team_id,
                ),
            )
            .order_by(models.Match.kickoff.desc())
        ).scalars()
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


@app.get("/leagues", response_model=list[LeagueOut])
def list_leagues(session: Session = Depends(get_session)) -> list[models.League]:
    return list(
        session.execute(
            select(models.League)
            .where(models.League.sport == football.SPORT_NAME)
            .order_by(models.League.season.desc(), models.League.name)
        ).scalars()
    )


@app.get("/teams/{league_id}", response_model=list[TeamOut])
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


@app.get("/teams/{team_id}/matches", response_model=list[MatchOut])
def matches_for_team(
    team_id: int, session: Session = Depends(get_session)
) -> list[models.Match]:
    return _team_matches(session, team_id)


# ---- analiz uçları (Faz 5) --------------------------------------------------


@app.get("/teams/{team_id}/form")
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


@app.get("/teams/{team_id}/rating")
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


@app.get("/teams/{a}/vs/{b}")
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
                or_(
                    (models.Match.home_team_external_id == a)
                    & (models.Match.away_team_external_id == b),
                    (models.Match.home_team_external_id == b)
                    & (models.Match.away_team_external_id == a),
                ),
            )
        ).scalars()
    )
    result = compute_head_to_head(a, b, matches)
    return _maybe_explain(engine_result_to_dict(result), result, explain)


@app.get("/matches/{match_id}/preview")
def match_preview(
    match_id: int,
    last_n: int = Query(5, ge=1, le=50),
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

    def _prior(team_id: int) -> list[models.Match]:
        return list(
            session.execute(
                select(models.Match)
                .where(
                    models.Match.sport == football.SPORT_NAME,
                    models.Match.kickoff < match.kickoff,
                    or_(
                        models.Match.home_team_external_id == team_id,
                        models.Match.away_team_external_id == team_id,
                    ),
                )
                .order_by(models.Match.kickoff.desc())
            ).scalars()
        )

    home_form = compute_form(home_id, _prior(home_id), last_n=last_n)
    away_form = compute_form(away_id, _prior(away_id), last_n=last_n)

    h2h_matches = list(
        session.execute(
            select(models.Match).where(
                models.Match.sport == football.SPORT_NAME,
                models.Match.kickoff < match.kickoff,
                or_(
                    (models.Match.home_team_external_id == home_id)
                    & (models.Match.away_team_external_id == away_id),
                    (models.Match.home_team_external_id == away_id)
                    & (models.Match.away_team_external_id == home_id),
                ),
            )
        ).scalars()
    )
    h2h = compute_head_to_head(home_id, away_id, h2h_matches)

    return {
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
