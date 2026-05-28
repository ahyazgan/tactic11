"""Overperformance — G+A vs xG+xA. "Şanslı mı yetenekli mi?"

Tanım: oyuncunun
- G (gol sayısı, Shot.is_goal=True)
- A (asist sayısı, PassEvent.assist=True)
- xG (compute_shot_xg toplamı)
- xA (PassEvent.assist=True olan paslar için ardındaki şutun xG'si)

Overperformance = (G - xG) + (A - xA). Pozitif = beklenenden fazla
katkı (clinical finisher veya şanslı). Negatif = pozisyona değil bitirişe
güvenilemez.

Tipik elite forvet: ~+5/sezon over (Haaland). Tipik orta seviye: ±2.

Saf hesap. compute_shot_xg'yi engine'den çağırır (zaten saf).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.audit import AuditRecord, EngineResult
from app.domain import PassEvent, Shot
from app.engine.xg import compute_shot_xg

ENGINE_NAME = "engine.overperformance"
ENGINE_VERSION = "1"

# xA için key_pass → shot eşleşme penceresi
KEY_PASS_TO_SHOT_WINDOW = 0.10  # 6 sn


@dataclass(frozen=True)
class OverperformanceReport:
    player_external_id: int
    matches_analyzed: int
    goals: int
    assists: int
    xg: float
    xa: float
    g_minus_xg: float
    a_minus_xa: float
    total_overperformance: float
    label: str    # "clinical" | "neutral" | "underperforming"


def _label(total: float, sample: int) -> str:
    if sample < 5:
        return "insufficient_data"
    if total >= 2.0:
        return "clinical"
    if total <= -2.0:
        return "underperforming"
    return "neutral"


def compute_overperformance(
    *,
    player_external_id: int,
    all_passes: Iterable[PassEvent],
    all_shots: Iterable[Shot],
    matches_analyzed: int = 1,
) -> EngineResult[OverperformanceReport]:
    player_shots = [s for s in all_shots if s.player_external_id == player_external_id]
    sorted_shots = sorted(all_shots, key=lambda s: s.minute)
    player_passes = [p for p in all_passes if p.player_external_id == player_external_id]

    goals = sum(1 for s in player_shots if s.is_goal)
    xg = sum(compute_shot_xg(s, mode="geometric").value.xg for s in player_shots)

    # xA: key_pass=True paslar için ardındaki şutu eşle, o şutun xG'si xA olur
    assists = 0
    xa = 0.0
    for p in player_passes:
        if not p.key_pass:
            continue
        # Eşle: minute aralığı
        for s in sorted_shots:
            if s.minute < p.minute:
                continue
            if s.minute - p.minute > KEY_PASS_TO_SHOT_WINDOW:
                break
            xa += compute_shot_xg(s, mode="geometric").value.xg
            if p.assist:
                assists += 1
            break

    g_minus = goals - xg
    a_minus = assists - xa
    total = g_minus + a_minus
    sample = len(player_shots) + len(
        [p for p in player_passes if p.key_pass]
    )

    report = OverperformanceReport(
        player_external_id=player_external_id,
        matches_analyzed=matches_analyzed,
        goals=goals,
        assists=assists,
        xg=round(xg, 3),
        xa=round(xa, 3),
        g_minus_xg=round(g_minus, 3),
        a_minus_xa=round(a_minus, 3),
        total_overperformance=round(total, 3),
        label=_label(total, sample),
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="player", subject_id=player_external_id,
        metric="overperformance",
        value={
            "goals": goals, "assists": assists,
            "xg": report.xg, "xa": report.xa,
            "total_overperformance": report.total_overperformance,
            "label": report.label,
        },
        inputs={
            "key_pass_to_shot_window_min": KEY_PASS_TO_SHOT_WINDOW,
            "matches_analyzed": matches_analyzed,
        },
        formula="(G - xG) + (A - xA), xG via engine.xg.geometric",
    )
    return EngineResult(value=report, audit=audit)
