"""Rakip örüntü analizi — head-to-head özet + ev/dep parite + clean sheet'ler.

İki takımın geçmiş karşılaşmalarındaki sayılar. v2'de "last_meeting", ev/dep
ayrımı ve clean sheet kayıtları da eklendi — preview brief'i için sentez
malzemesi.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass

from app.audit import AuditRecord, EngineResult
from app.engine._protocols import MatchLike
from app.sports import football

ENGINE_NAME = "engine.opponent"
ENGINE_VERSION = "2"  # v1 → v2: last_meeting, ev/dep, clean sheets


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

    # v2 eklemeleri
    team_a_clean_sheets: int  # A'nın gol yemediği maç sayısı
    team_b_clean_sheets: int
    team_a_home_wins: int  # A ev sahibiyken galibiyet
    team_a_away_wins: int  # A deplasmandayken galibiyet
    last_meeting_kickoff: str | None  # ISO; oynanmış maç yoksa None
    last_meeting_result: str | None  # "team_a", "draw", "team_b", veya None


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
    relevant.sort(key=lambda m: m.kickoff)  # eski → yeni

    a_wins = draws = b_wins = 0
    a_goals = b_goals = 0
    a_clean = b_clean = 0
    a_home_wins = a_away_wins = 0
    considered_ids: list[int] = []
    last: MatchLike | None = None

    for m in relevant:
        considered_ids.append(m.external_id)
        a_is_home = m.home_team_external_id == team_a_id
        a_goal = m.home_score if a_is_home else m.away_score
        b_goal = m.away_score if a_is_home else m.home_score
        assert a_goal is not None and b_goal is not None
        a_goals += a_goal
        b_goals += b_goal
        if b_goal == 0:
            a_clean += 1
        if a_goal == 0:
            b_clean += 1
        if a_goal > b_goal:
            a_wins += 1
            if a_is_home:
                a_home_wins += 1
            else:
                a_away_wins += 1
        elif a_goal < b_goal:
            b_wins += 1
        else:
            draws += 1
        last = m

    if last is not None:
        a_is_home_last = last.home_team_external_id == team_a_id
        a_last = last.home_score if a_is_home_last else last.away_score
        b_last = last.away_score if a_is_home_last else last.home_score
        assert a_last is not None and b_last is not None
        if a_last > b_last:
            last_result = "team_a"
        elif a_last < b_last:
            last_result = "team_b"
        else:
            last_result = "draw"
        last_kickoff: str | None = last.kickoff.isoformat()
    else:
        last_result = None
        last_kickoff = None

    h2h = HeadToHead(
        team_a_id=team_a_id,
        team_b_id=team_b_id,
        matches_played=len(relevant),
        team_a_wins=a_wins,
        draws=draws,
        team_b_wins=b_wins,
        team_a_goals=a_goals,
        team_b_goals=b_goals,
        team_a_clean_sheets=a_clean,
        team_b_clean_sheets=b_clean,
        team_a_home_wins=a_home_wins,
        team_a_away_wins=a_away_wins,
        last_meeting_kickoff=last_kickoff,
        last_meeting_result=last_result,
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
        formula=(
            "sum over finished matches between (team_a, team_b); "
            "clean sheet = rakip gol atamamış; last_meeting = en geç kickoff"
        ),
    )
    return EngineResult(value=h2h, audit=audit)
