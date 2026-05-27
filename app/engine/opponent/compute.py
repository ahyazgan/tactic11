"""Rakip örüntü analizi — head-to-head özet + ev/dep parite + clean sheet'ler.

İki takımın geçmiş karşılaşmalarındaki sayılar. v2'de "last_meeting", ev/dep
ayrımı ve clean sheet; v3'te recent trend (son 3 maç ayrı sayım), goal margin
records, avg goals per match.

`recent_*` alanları geçmiş 3 maçın trend'ini izole eder — "10 maçta dengeli
ama son 3'te A dominant" gibi insight'lar preview brief'inde fark yaratır.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass

from app.audit import AuditRecord, EngineResult
from app.engine._protocols import MatchLike
from app.sports import football

ENGINE_NAME = "engine.opponent"
ENGINE_VERSION = "3"  # v2 → v3: recent trend + goal margins + avg goals

_RECENT_WINDOW = 3


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

    # v3 eklemeleri — trend + margin
    avg_goals_per_match: float  # (a_goals + b_goals) / matches_played; 0 maç=0
    biggest_a_win_margin: int  # A'nın en büyük galibiyet farkı; yoksa 0
    biggest_b_win_margin: int
    recent_a_wins: int  # son _RECENT_WINDOW h2h maçında A galibiyet
    recent_draws: int
    recent_b_wins: int


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
    biggest_a_margin = 0  # A galibiyetlerindeki en büyük fark
    biggest_b_margin = 0
    considered_ids: list[int] = []
    last: MatchLike | None = None
    # Trend için match-bazlı sonuç listesi (kronolojik)
    outcomes: list[str] = []  # "a", "draw", "b"

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
            margin = a_goal - b_goal
            if margin > biggest_a_margin:
                biggest_a_margin = margin
            outcomes.append("a")
        elif a_goal < b_goal:
            b_wins += 1
            margin = b_goal - a_goal
            if margin > biggest_b_margin:
                biggest_b_margin = margin
            outcomes.append("b")
        else:
            draws += 1
            outcomes.append("draw")
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

    n = len(relevant)
    avg_goals = (a_goals + b_goals) / n if n else 0.0
    # Recent trend: son _RECENT_WINDOW maç (kronolojik, en yeni en sonda)
    recent_slice = outcomes[-_RECENT_WINDOW:]
    recent_a = sum(1 for o in recent_slice if o == "a")
    recent_draws_count = sum(1 for o in recent_slice if o == "draw")
    recent_b = sum(1 for o in recent_slice if o == "b")

    h2h = HeadToHead(
        team_a_id=team_a_id,
        team_b_id=team_b_id,
        matches_played=n,
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
        avg_goals_per_match=round(avg_goals, 3),
        biggest_a_win_margin=biggest_a_margin,
        biggest_b_win_margin=biggest_b_margin,
        recent_a_wins=recent_a,
        recent_draws=recent_draws_count,
        recent_b_wins=recent_b,
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
            "recent_window": _RECENT_WINDOW,
        },
        formula=(
            "sum over finished matches between (team_a, team_b); "
            "clean sheet = rakip gol atamamış; last_meeting = en geç kickoff; "
            f"recent_* = son {_RECENT_WINDOW} maç ayrı sayım; "
            "biggest_*_win_margin = en büyük gol farkı"
        ),
    )
    return EngineResult(value=h2h, audit=audit)
