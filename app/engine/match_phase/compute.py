"""Match phase analysis — 1H/2H/ET + score-state effects.

Maçı zaman ve skor durumuna göre fazlara ayırır:

1. **Period split:** 1. yarı (1-45) vs 2. yarı (46-90) vs ET (90+)
   - xG, pas, defansif aksiyon her phase için ayrı
2. **Score-state split:** önde / berabere / geride iken davranış
   - "Önde iken xG düşer, pres azalır" gibi standart pattern

Saf hesap. Shot + PassEvent + DefensiveAction listelerinden phase başına
agregat üretir.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from app.audit import AuditRecord, EngineResult
from app.domain import DefensiveAction, PassEvent, Shot
from app.engine.xg import compute_shot_xg

ENGINE_NAME = "engine.match_phase"
ENGINE_VERSION = "1"

PhaseType = Literal["first_half", "second_half", "extra_time"]
ScoreState = Literal["leading", "drawing", "trailing"]


@dataclass(frozen=True)
class PhaseStats:
    """Tek bir faz için takım istatistikleri."""
    phase: str
    team_external_id: int
    minutes_covered: int
    shots_count: int
    total_xg: float
    passes_count: int
    completed_passes: int
    defensive_actions: int


@dataclass(frozen=True)
class MatchPhaseReport:
    """Bir maç için tüm phase'lerin agregat raporu."""
    match_external_id: int
    home_team_id: int
    away_team_id: int
    home_phases: list[PhaseStats]
    away_phases: list[PhaseStats]


@dataclass(frozen=True)
class ScoreStateReport:
    """Skor durumuna göre takım davranışı agregat."""
    team_external_id: int
    matches_analyzed: int
    leading: PhaseStats   # önde iken
    drawing: PhaseStats   # berabere iken
    trailing: PhaseStats  # geride iken


def _classify_phase(minute: float, period: int) -> PhaseType:
    """Period ve minute → phase tipi."""
    if period >= 3:
        return "extra_time"
    if minute <= 45 or period == 1:
        return "first_half"
    return "second_half"


def compute_match_phases(
    match_external_id: int,
    home_team_id: int,
    away_team_id: int,
    home_shots: Iterable[Shot],
    away_shots: Iterable[Shot],
    home_passes: Iterable[PassEvent],
    away_passes: Iterable[PassEvent],
    home_def_actions: Iterable[DefensiveAction],
    away_def_actions: Iterable[DefensiveAction],
) -> EngineResult[MatchPhaseReport]:
    """Bir maç için phase başına agregat (her takım için ayrı)."""
    def _aggregate_for_phase(
        team_id: int, phase: PhaseType,
        shots: Iterable[Shot], passes: Iterable[PassEvent],
        defs: Iterable[DefensiveAction],
    ) -> PhaseStats:
        # Shot domain'de period yok — heuristic minute split
        shot_list = [
            s for s in shots
            if (phase == "first_half" and s.minute <= 45)
            or (phase == "second_half" and 45 < s.minute <= 90)
            or (phase == "extra_time" and s.minute > 90)
        ]
        pass_list = [p for p in passes if _classify_phase(p.minute, p.period) == phase]
        def_list = [d for d in defs if _classify_phase(d.minute, d.period) == phase]
        total_xg = sum(compute_shot_xg(s).value.xg for s in shot_list)
        completed = sum(1 for p in pass_list if p.completed)
        minutes = 45 if phase in ("first_half", "second_half") else 30
        return PhaseStats(
            phase=phase,
            team_external_id=team_id,
            minutes_covered=minutes,
            shots_count=len(shot_list),
            total_xg=round(total_xg, 4),
            passes_count=len(pass_list),
            completed_passes=completed,
            defensive_actions=len(def_list),
        )

    home_list = list(home_shots)
    away_list = list(away_shots)
    home_passes_list = list(home_passes)
    away_passes_list = list(away_passes)
    home_defs = list(home_def_actions)
    away_defs = list(away_def_actions)

    home_phases = [
        _aggregate_for_phase(home_team_id, "first_half", home_list, home_passes_list, home_defs),
        _aggregate_for_phase(home_team_id, "second_half", home_list, home_passes_list, home_defs),
    ]
    away_phases = [
        _aggregate_for_phase(away_team_id, "first_half", away_list, away_passes_list, away_defs),
        _aggregate_for_phase(away_team_id, "second_half", away_list, away_passes_list, away_defs),
    ]
    # ET sadece varsa
    if any(s.minute > 90 for s in home_list + away_list):
        home_phases.append(_aggregate_for_phase(home_team_id, "extra_time", home_list, home_passes_list, home_defs))
        away_phases.append(_aggregate_for_phase(away_team_id, "extra_time", away_list, away_passes_list, away_defs))

    report = MatchPhaseReport(
        match_external_id=match_external_id,
        home_team_id=home_team_id, away_team_id=away_team_id,
        home_phases=home_phases, away_phases=away_phases,
    )
    audit = AuditRecord(
        engine=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        subject_type="match",
        subject_id=match_external_id,
        metric="match_phases",
        value={
            "home_first_xg": home_phases[0].total_xg,
            "home_second_xg": home_phases[1].total_xg,
            "away_first_xg": away_phases[0].total_xg,
            "away_second_xg": away_phases[1].total_xg,
        },
        inputs={
            "phases": [p.phase for p in home_phases],
        },
        formula="split by minute: <=45 first, 45-90 second, >90 ET; xG/passes/defs per phase",
    )
    return EngineResult(value=report, audit=audit)


def compute_score_state_effects(
    team_external_id: int,
    *,
    shots_when_leading: Iterable[Shot],
    shots_when_drawing: Iterable[Shot],
    shots_when_trailing: Iterable[Shot],
    matches_analyzed: int,
) -> EngineResult[ScoreStateReport]:
    """Skor durumuna göre takım xG/şut agregat.

    Caller match'leri zaman bazlı bölüp şutları leading/drawing/trailing'e
    ayrıştırır. (Bu fonksiyon bilmek zorunda değil — saf agregat.)
    """
    def _agg(label: str, shots: Iterable[Shot]) -> PhaseStats:
        slist = list(shots)
        total_xg = sum(compute_shot_xg(s).value.xg for s in slist)
        return PhaseStats(
            phase=label, team_external_id=team_external_id,
            minutes_covered=0,  # bilinmiyor (caller-side)
            shots_count=len(slist), total_xg=round(total_xg, 4),
            passes_count=0, completed_passes=0,
            defensive_actions=0,
        )

    report = ScoreStateReport(
        team_external_id=team_external_id,
        matches_analyzed=matches_analyzed,
        leading=_agg("leading", shots_when_leading),
        drawing=_agg("drawing", shots_when_drawing),
        trailing=_agg("trailing", shots_when_trailing),
    )
    audit = AuditRecord(
        engine=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        subject_type="team",
        subject_id=team_external_id,
        metric="score_state_effects",
        value={
            "leading_xg": report.leading.total_xg,
            "drawing_xg": report.drawing.total_xg,
            "trailing_xg": report.trailing.total_xg,
            "matches": matches_analyzed,
        },
        inputs={"matches_analyzed": matches_analyzed},
        formula="per-shot xG aggregated by score state at moment of shot",
    )
    return EngineResult(value=report, audit=audit)
