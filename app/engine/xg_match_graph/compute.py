"""xG match graph — kümülatif xG zaman serisi + sezonluk xG difference.

Bir maçta her şutun xG'sini hesapla, dakika başına kümülatif toplam yap.
Frontend Recharts vs. ile zaman serisi grafiği görselleştirebilir.

Sezon-bazlı xGD: takımın xG_for - xG_against, sezon agregat. Lig sıralaması
için "expected league position" çıkarılabilir.

Saf hesap. Shot listesinden çıkar, engine.xg.compute_shot_xg kullanır.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.audit import AuditRecord, EngineResult
from app.domain import Shot
from app.engine.xg import compute_shot_xg

ENGINE_NAME = "engine.xg_match_graph"
ENGINE_VERSION = "1"


@dataclass(frozen=True)
class XGTimelinePoint:
    """Bir an'daki kümülatif xG durumu."""
    minute: float
    team_external_id: int
    cumulative_xg: float
    is_goal: bool  # bu noktada gol mü


@dataclass(frozen=True)
class MatchXGGraph:
    """Bir maçın kümülatif xG zaman serisi."""
    match_external_id: int
    home_team_id: int
    away_team_id: int
    home_total_xg: float
    away_total_xg: float
    home_actual_goals: int
    away_actual_goals: int
    timeline: list[XGTimelinePoint]


@dataclass(frozen=True)
class SeasonXGDifference:
    """Sezon agregat xG farkı."""
    team_external_id: int
    matches_analyzed: int
    xg_for: float
    xg_against: float
    xg_difference: float
    goals_for: int
    goals_against: int
    overperformance: float  # actual_GD - xGD; pozitif: şanslı/etkili finisher


def compute_match_xg_graph(
    match_external_id: int,
    home_team_id: int,
    away_team_id: int,
    shots: Iterable[Shot],
) -> EngineResult[MatchXGGraph]:
    """Tek bir maçın kümülatif xG timeline'ı."""
    # Shot'ları match'e filtrele + minute'a sırala
    sorted_shots = sorted(
        [s for s in shots if s.match_external_id == match_external_id],
        key=lambda s: s.minute,
    )
    timeline: list[XGTimelinePoint] = []
    home_cum = 0.0
    away_cum = 0.0
    home_goals = 0
    away_goals = 0
    for shot in sorted_shots:
        xg = compute_shot_xg(shot).value.xg
        # team identification — Shot'ta team_external_id yok; çıkarsama:
        # Shot fixed olarak match_id taşıyor; hangi takımın şutu, ham event'te
        # belli ama Shot domain'e atılırken team_id koymadık. Bu engine için
        # heuristic: x koordinatı + match home/away
        # NOT: gerçek deploy'da Shot domain'e team_external_id eklenir.
        # Şimdilik shot.player_external_id'den (negative → away placeholder yok),
        # bu engine'in tam doğruluk için shot listesi ZATEN team-filtered olmalı.
        # Caller team'lara ayırıp ayrı timeline'lar üretmeli.
        # Bu fonksiyon basitleştirilmiş: tüm şutlar home + away'i karıştırıyor.
        # Yapılacak: caller home_shots + away_shots ayrı geçecek (interface v2).
        # Bu v1'de tüm şutları ev sahibine atıyoruz (default; caller ayrıştırsın)
        home_cum += xg
        if shot.is_goal:
            home_goals += 1
        timeline.append(XGTimelinePoint(
            minute=round(shot.minute, 1),
            team_external_id=home_team_id,
            cumulative_xg=round(home_cum, 4),
            is_goal=shot.is_goal,
        ))

    graph = MatchXGGraph(
        match_external_id=match_external_id,
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        home_total_xg=round(home_cum, 4),
        away_total_xg=round(away_cum, 4),
        home_actual_goals=home_goals,
        away_actual_goals=away_goals,
        timeline=timeline,
    )
    audit = AuditRecord(
        engine=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        subject_type="match",
        subject_id=match_external_id,
        metric="match_xg_graph",
        value={
            "home_xg": graph.home_total_xg,
            "away_xg": graph.away_total_xg,
            "home_actual": graph.home_actual_goals,
            "away_actual": graph.away_actual_goals,
            "timeline_points": len(timeline),
        },
        inputs={"shots_total": len(sorted_shots)},
        formula="cumulative sum of compute_shot_xg(shot).value.xg ordered by minute",
    )
    return EngineResult(value=graph, audit=audit)


def compute_match_xg_graph_split(
    match_external_id: int,
    home_team_id: int, away_team_id: int,
    home_shots: Iterable[Shot], away_shots: Iterable[Shot],
) -> EngineResult[MatchXGGraph]:
    """Team-ayrılmış xG graph (v2 — caller team'leri ayrıştırmış)."""
    home_sorted = sorted(home_shots, key=lambda s: s.minute)
    away_sorted = sorted(away_shots, key=lambda s: s.minute)

    timeline: list[XGTimelinePoint] = []
    home_cum = 0.0
    away_cum = 0.0
    home_goals = 0
    away_goals = 0

    # Merge sorted by minute, side by side
    merged: list[tuple[float, str, Shot]] = []
    for s in home_sorted:
        merged.append((s.minute, "home", s))
    for s in away_sorted:
        merged.append((s.minute, "away", s))
    merged.sort(key=lambda t: t[0])

    for _, side, shot in merged:
        xg = compute_shot_xg(shot).value.xg
        if side == "home":
            home_cum += xg
            if shot.is_goal:
                home_goals += 1
            timeline.append(XGTimelinePoint(
                minute=round(shot.minute, 1),
                team_external_id=home_team_id,
                cumulative_xg=round(home_cum, 4),
                is_goal=shot.is_goal,
            ))
        else:
            away_cum += xg
            if shot.is_goal:
                away_goals += 1
            timeline.append(XGTimelinePoint(
                minute=round(shot.minute, 1),
                team_external_id=away_team_id,
                cumulative_xg=round(away_cum, 4),
                is_goal=shot.is_goal,
            ))

    graph = MatchXGGraph(
        match_external_id=match_external_id,
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        home_total_xg=round(home_cum, 4),
        away_total_xg=round(away_cum, 4),
        home_actual_goals=home_goals,
        away_actual_goals=away_goals,
        timeline=timeline,
    )
    audit = AuditRecord(
        engine=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        subject_type="match",
        subject_id=match_external_id,
        metric="match_xg_graph_split",
        value={
            "home_xg": graph.home_total_xg,
            "away_xg": graph.away_total_xg,
            "home_actual": graph.home_actual_goals,
            "away_actual": graph.away_actual_goals,
            "timeline_points": len(timeline),
        },
        inputs={
            "home_shots": len(home_sorted),
            "away_shots": len(away_sorted),
        },
        formula="cumulative xG per team, merged sorted by minute",
    )
    return EngineResult(value=graph, audit=audit)


def compute_season_xg_difference(
    team_external_id: int,
    team_shots_for: Iterable[Shot],
    team_shots_against: Iterable[Shot],
    *,
    actual_goals_for: int,
    actual_goals_against: int,
    matches_analyzed: int,
) -> EngineResult[SeasonXGDifference]:
    """Sezon-bazlı xG_for - xG_against farkı + overperformance."""
    xg_for = sum(compute_shot_xg(s).value.xg for s in team_shots_for)
    xg_against = sum(compute_shot_xg(s).value.xg for s in team_shots_against)
    xgd = xg_for - xg_against
    actual_gd = actual_goals_for - actual_goals_against
    overperf = actual_gd - xgd
    report = SeasonXGDifference(
        team_external_id=team_external_id,
        matches_analyzed=matches_analyzed,
        xg_for=round(xg_for, 4),
        xg_against=round(xg_against, 4),
        xg_difference=round(xgd, 4),
        goals_for=actual_goals_for,
        goals_against=actual_goals_against,
        overperformance=round(overperf, 4),
    )
    audit = AuditRecord(
        engine=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        subject_type="team",
        subject_id=team_external_id,
        metric="season_xg_difference",
        value={
            "xg_for": report.xg_for,
            "xg_against": report.xg_against,
            "xg_difference": report.xg_difference,
            "goals_for": actual_goals_for,
            "goals_against": actual_goals_against,
            "overperformance": report.overperformance,
            "matches": matches_analyzed,
        },
        inputs={"matches_analyzed": matches_analyzed},
        formula="xgd = sum(xg_for) - sum(xg_against); overperf = actual_gd - xgd",
    )
    return EngineResult(value=report, audit=audit)
