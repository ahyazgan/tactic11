"""Lig sync orkestrasyonu: adapter → doğrula → upsert.

Snapshot ve usage Faz 1'in geri kalanında dolacak; bu modülün arayüzü stabil
kalır.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.data.sources.base import DataSource
from app.data.validation import validate_leagues, validate_matches, validate_teams
from app.db import models
from app.domain import League, Match, Team

log = get_logger(__name__)

DEFAULT_MATCHES_PER_TEAM = 10


@dataclass(frozen=True)
class SyncReport:
    leagues_written: int
    teams_written: int
    matches_written: int
    rejected_count: int


def sync_league(
    session: Session,
    source: DataSource,
    league_id: int,
    season: int,
    matches_per_team: int = DEFAULT_MATCHES_PER_TEAM,
) -> SyncReport:
    rejected = 0

    leagues = source.get_leagues()
    lg_res = validate_leagues(leagues)
    rejected += len(lg_res.rejected)
    target_leagues = [lg for lg in lg_res.accepted if lg.external_id == league_id]
    for lg in target_leagues:
        _upsert_league(session, lg, season=season)
    log.info("league upsert: %d kayıt", len(target_leagues))

    teams = source.get_teams(league_id=league_id, season=season)
    t_res = validate_teams(teams)
    rejected += len(t_res.rejected)
    for t in t_res.accepted:
        _upsert_team(session, t)
    log.info("team upsert: %d kayıt", len(t_res.accepted))

    matches_written = 0
    for t in t_res.accepted:
        try:
            matches = source.get_team_matches(team_id=t.external_id, last_n=matches_per_team)
        except FileNotFoundError:
            log.info("matches fixture yok, atlanıyor: team=%d", t.external_id)
            continue
        m_res = validate_matches(matches)
        rejected += len(m_res.rejected)
        for m in m_res.accepted:
            _upsert_match(session, m)
        matches_written += len(m_res.accepted)
    log.info("match upsert: %d kayıt", matches_written)

    session.commit()
    return SyncReport(
        leagues_written=len(target_leagues),
        teams_written=len(t_res.accepted),
        matches_written=matches_written,
        rejected_count=rejected,
    )


def _upsert_league(session: Session, lg: League, *, season: int) -> None:
    # Hedef sezon ile gelen sezon farklıysa ingest tarafında sezonu sabitliyoruz.
    target_season = lg.season if lg.season else season
    row = session.execute(
        select(models.League).where(
            models.League.sport == lg.sport,
            models.League.external_id == lg.external_id,
            models.League.season == target_season,
        )
    ).scalar_one_or_none()
    if row is None:
        session.add(
            models.League(
                sport=lg.sport,
                external_id=lg.external_id,
                name=lg.name,
                season=target_season,
                country=lg.country,
            )
        )
    else:
        row.name = lg.name
        row.country = lg.country


def _upsert_team(session: Session, t: Team) -> None:
    row = session.execute(
        select(models.Team).where(
            models.Team.sport == t.sport,
            models.Team.external_id == t.external_id,
        )
    ).scalar_one_or_none()
    if row is None:
        session.add(
            models.Team(
                sport=t.sport,
                external_id=t.external_id,
                name=t.name,
                country=t.country,
                founded=t.founded,
            )
        )
    else:
        row.name = t.name
        row.country = t.country
        row.founded = t.founded


def _upsert_match(session: Session, m: Match) -> None:
    row = session.execute(
        select(models.Match).where(
            models.Match.sport == m.sport,
            models.Match.external_id == m.external_id,
        )
    ).scalar_one_or_none()
    if row is None:
        session.add(
            models.Match(
                sport=m.sport,
                external_id=m.external_id,
                league_external_id=m.league_external_id,
                season=m.season,
                kickoff=m.kickoff,
                status=m.status,
                home_team_external_id=m.home_team_external_id,
                away_team_external_id=m.away_team_external_id,
                home_score=m.home_score,
                away_score=m.away_score,
            )
        )
    else:
        row.league_external_id = m.league_external_id
        row.season = m.season
        row.kickoff = m.kickoff
        row.status = m.status
        row.home_team_external_id = m.home_team_external_id
        row.away_team_external_id = m.away_team_external_id
        row.home_score = m.home_score
        row.away_score = m.away_score
