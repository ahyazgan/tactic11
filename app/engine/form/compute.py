"""Form analizi — son N maçtaki sonuçlar, gol farkı, ev/deplasman ayrımı.

SAF FONKSİYON: girdi `list[Match]`, çıktı `EngineResult[FormReport]`. DB/API'ye
dokunmaz. Maç tamamlandı sayılan statüler `sports/football.py`'den gelir.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass
from typing import Literal

from app.audit import AuditRecord, EngineResult
from app.domain import Match
from app.sports import football

ENGINE_NAME = "engine.form"
ENGINE_VERSION = "1"

Outcome = Literal["W", "D", "L"]


@dataclass(frozen=True)
class FormReport:
    matches_played: int
    wins: int
    draws: int
    losses: int
    goals_for: int
    goals_against: int
    goal_diff: int
    points: int
    points_per_game: float
    home_wins: int
    home_draws: int
    home_losses: int
    away_wins: int
    away_draws: int
    away_losses: int
    last_results: list[Outcome]


def _outcome_for(team_id: int, match: Match) -> Outcome:
    is_home = match.home_team_external_id == team_id
    gf = match.home_score if is_home else match.away_score
    ga = match.away_score if is_home else match.home_score
    assert gf is not None and ga is not None  # finished maçlarda garanti
    if gf > ga:
        return "W"
    if gf < ga:
        return "L"
    return "D"


def compute_form(
    team_external_id: int,
    matches: Iterable[Match],
    *,
    last_n: int = 5,
) -> EngineResult[FormReport]:
    """Bir takımın son N tamamlanmış maçındaki form raporu.

    `matches` o takımı içeren maç listesi olmalı; engine takımın hangi tarafta
    olduğunu kendisi anlar.
    """
    if last_n <= 0:
        raise ValueError("last_n > 0 olmalı")

    team_matches = [
        m
        for m in matches
        if m.status in football.FINISHED_STATUSES
        and m.home_score is not None
        and m.away_score is not None
        and team_external_id in (m.home_team_external_id, m.away_team_external_id)
    ]
    team_matches.sort(key=lambda m: m.kickoff, reverse=True)
    window = team_matches[:last_n]

    wins = draws = losses = 0
    home_w = home_d = home_l = 0
    away_w = away_d = away_l = 0
    gf_total = ga_total = 0
    last_results: list[Outcome] = []

    for m in window:
        is_home = m.home_team_external_id == team_external_id
        gf = m.home_score if is_home else m.away_score
        ga = m.away_score if is_home else m.home_score
        gf_total += gf  # type: ignore[operator]
        ga_total += ga  # type: ignore[operator]

        outcome = _outcome_for(team_external_id, m)
        last_results.append(outcome)
        if outcome == "W":
            wins += 1
            if is_home:
                home_w += 1
            else:
                away_w += 1
        elif outcome == "D":
            draws += 1
            if is_home:
                home_d += 1
            else:
                away_d += 1
        else:
            losses += 1
            if is_home:
                home_l += 1
            else:
                away_l += 1

    played = len(window)
    points = wins * 3 + draws
    ppg = points / played if played else 0.0

    report = FormReport(
        matches_played=played,
        wins=wins,
        draws=draws,
        losses=losses,
        goals_for=gf_total,
        goals_against=ga_total,
        goal_diff=gf_total - ga_total,
        points=points,
        points_per_game=round(ppg, 3),
        home_wins=home_w,
        home_draws=home_d,
        home_losses=home_l,
        away_wins=away_w,
        away_draws=away_d,
        away_losses=away_l,
        last_results=last_results,
    )

    audit = AuditRecord(
        engine=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        subject_type="team",
        subject_id=team_external_id,
        metric="form_report",
        value=asdict(report),
        inputs={
            "last_n": last_n,
            "considered_match_ids": [m.external_id for m in window],
        },
        formula="W=3, D=1, L=0; ppg=points/matches; window=last_n finished matches",
    )
    return EngineResult(value=report, audit=audit)
