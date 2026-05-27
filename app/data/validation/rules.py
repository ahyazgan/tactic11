"""Doğrulama kuralları.

Her kural saf fonksiyon: domain modelini alır, hata mesajı listesi döner
(boş = geçti). Yeni kural eklemek için ilgili tuple'a fonksiyon ekleyin.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from app.domain import League, Match, Team
from app.sports import football


def _league_name_required(item: League) -> list[str]:
    return [] if item.name.strip() else ["league.name boş"]


def _league_season_sane(item: League) -> list[str]:
    if item.season < 1900 or item.season > 2100:
        return [f"league.season anormal: {item.season}"]
    return []


def _team_name_required(item: Team) -> list[str]:
    return [] if item.name.strip() else ["team.name boş"]


def _team_founded_sane(item: Team) -> list[str]:
    if item.founded is not None and (item.founded < 1800 or item.founded > 2100):
        return [f"team.founded anormal: {item.founded}"]
    return []


def _match_teams_distinct(item: Match) -> list[str]:
    if item.home_team_external_id == item.away_team_external_id:
        return ["maç: home == away"]
    return []


def _match_no_future_finished(item: Match) -> list[str]:
    if item.status in football.FINISHED_STATUSES and item.kickoff > datetime.now(UTC):
        return ["maç gelecekte ama status 'finished'"]
    return []


def _match_score_when_finished(item: Match) -> list[str]:
    if item.status in football.FINISHED_STATUSES and (item.home_score is None or item.away_score is None):
        return ["finished maçta skor None"]
    return []


LEAGUE_RULES: tuple[Callable[[League], list[str]], ...] = (
    _league_name_required,
    _league_season_sane,
)

TEAM_RULES: tuple[Callable[[Team], list[str]], ...] = (
    _team_name_required,
    _team_founded_sane,
)

MATCH_RULES: tuple[Callable[[Match], list[str]], ...] = (
    _match_teams_distinct,
    _match_no_future_finished,
    _match_score_when_finished,
)
