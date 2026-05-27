"""Rakip örüntü analizi — head-to-head özet.

İki takımın geçmiş karşılaşmalarındaki sayıları döner: galibiyetler, beraberlik,
goller, son maç. İleride (Faz 2+) örüntü tespiti (örn. "ev sahibi olduğunda
üst alıyor") eklenecek.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass

from app.audit import AuditRecord, EngineResult
from app.engine._protocols import MatchLike
from app.sports import football

ENGINE_NAME = "engine.opponent"
ENGINE_VERSION = "1"


@dataclass(frozen=True)
class HeadToHead:
    team_a_id: int
    team_b_id: int
    matches_played: int
    team_a_wins: int
    draws: int
    team_b_wins: int
    team_a_goals: int
    team_b_goals: int


def compute_head_to_head(
    team_a_id: int,
    team_b_id: int,
    matches: Iterable[MatchLike],
) -> EngineResult[HeadToHead]:
    if team_a_id == team_b_id:
        raise ValueError("aynı takım için head-to-head olmaz")

    pair = sorted([team_a_id, team_b_id])
    relevant = [
        m
        for m in matches
        if m.status in football.FINISHED_STATUSES
        and m.home_score is not None
        and m.away_score is not None
        and sorted([m.home_team_external_id, m.away_team_external_id]) == pair
    ]

    a_wins = draws = b_wins = 0
    a_goals = b_goals = 0
    considered_ids: list[int] = []
    for m in relevant:
        considered_ids.append(m.external_id)
        a_is_home = m.home_team_external_id == team_a_id
        a_goal = m.home_score if a_is_home else m.away_score
        b_goal = m.away_score if a_is_home else m.home_score
        a_goals += a_goal  # type: ignore[operator]
        b_goals += b_goal  # type: ignore[operator]
        if a_goal > b_goal:  # type: ignore[operator]
            a_wins += 1
        elif a_goal < b_goal:  # type: ignore[operator]
            b_wins += 1
        else:
            draws += 1

    h2h = HeadToHead(
        team_a_id=team_a_id,
        team_b_id=team_b_id,
        matches_played=len(relevant),
        team_a_wins=a_wins,
        draws=draws,
        team_b_wins=b_wins,
        team_a_goals=a_goals,
        team_b_goals=b_goals,
    )

    audit = AuditRecord(
        engine=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        subject_type="team_pair",
        subject_id=team_a_id,
        metric="head_to_head",
        value=asdict(h2h),
        inputs={
            "team_b_id": team_b_id,
            "considered_match_ids": considered_ids,
        },
        formula="sum over finished matches between (team_a, team_b)",
    )
    return EngineResult(value=h2h, audit=audit)
