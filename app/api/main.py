"""FastAPI app — Faz 1 okuma uçları.

Bu katman DB'den okur, dış kaynağa dokunmaz. Sync `scripts/sync_league.py`
veya ileride `scheduler/` üzerinden çalışır.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.schemas import LeagueOut, MatchOut, TeamOut
from app.core.logging import setup_logging
from app.db import models
from app.db.session import get_session
from app.sports import football

setup_logging()

app = FastAPI(title="football-intelligence", version="0.1.0")


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
    """Bu ligin maçlarında görünen takımlar.

    Sezon bazlı katılım (faz 2+) için ayrı bir join tablosu gerekecek; faz 1
    boyunca maç verisi üzerinden türetiyoruz.
    """
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
