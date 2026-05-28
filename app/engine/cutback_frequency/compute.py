"""Cutback Frequency — City/Brighton modern hücum patterni.

Cutback: kale yan çizgisine yakın (x ≥ 90, y ≤ 25 veya y ≥ 75) pozisyondan
gelip ceza sahasındaki bir oyuncuya (y 33-67, x 85-95) GERİ pas. "Geri" =
end_x ≤ start_x (top kaleye doğru gitmiyor, geri yatay yarıya doğru).

Pep Guardiola Manchester City'nin sembol patterni; modern futbolun en yüksek
xG/şut'larından biri (yaklaşık 0.30 xG her şut).

Saf hesap. PassEvent listesi → CutbackReport.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.audit import AuditRecord, EngineResult
from app.domain import PassEvent, Shot

ENGINE_NAME = "engine.cutback_frequency"
ENGINE_VERSION = "1"

# Cutback başlangıç: yan çizgiye yakın + ceza sahası seviyesinde
CUTBACK_START_X_MIN = 88.0
CUTBACK_START_WIDE_MAX = 25.0   # sol kanat sınırı (simetrik 75+)
# Cutback bitiş: ceza sahası ortası
CUTBACK_END_X_MIN = 83.0
CUTBACK_END_X_MAX = 96.0
CUTBACK_END_Y_MIN = 30.0
CUTBACK_END_Y_MAX = 70.0
# Cutback'tan şuta zaman penceresi
CUTBACK_TO_SHOT_WINDOW = 0.10  # 6 sn


@dataclass(frozen=True)
class CutbackReport:
    team_external_id: int
    matches_analyzed: int
    cutbacks: int
    cutbacks_per_match: float
    shots_from_cutbacks: int
    goals_from_cutbacks: int
    conversion_rate: float


def _is_cutback(p: PassEvent) -> bool:
    # Start kanat çizgisine yakın + ceza sahası seviyesinde
    on_left = p.start_y <= CUTBACK_START_WIDE_MAX
    on_right = p.start_y >= (100 - CUTBACK_START_WIDE_MAX)
    if not (p.start_x >= CUTBACK_START_X_MIN and (on_left or on_right)):
        return False
    # End ceza sahası ortası
    if not (CUTBACK_END_X_MIN <= p.end_x <= CUTBACK_END_X_MAX):
        return False
    if not (CUTBACK_END_Y_MIN <= p.end_y <= CUTBACK_END_Y_MAX):
        return False
    # "Geri" pas: end_x <= start_x (top kaleye doğru gitmiyor)
    return p.end_x <= p.start_x


def compute_cutback_frequency(
    team_external_id: int,
    all_passes: Iterable[PassEvent],
    all_shots: Iterable[Shot],
    *,
    matches_analyzed: int = 1,
) -> EngineResult[CutbackReport]:
    cutbacks = [
        p for p in all_passes
        if p.team_external_id == team_external_id and _is_cutback(p)
    ]
    shots = sorted(all_shots, key=lambda s: s.minute)

    shots_from = 0
    goals_from = 0
    for c in cutbacks:
        for s in shots:
            if s.minute < c.minute:
                continue
            if s.minute - c.minute > CUTBACK_TO_SHOT_WINDOW:
                break
            shots_from += 1
            if s.is_goal:
                goals_from += 1
            break

    n = len(cutbacks)
    report = CutbackReport(
        team_external_id=team_external_id,
        matches_analyzed=matches_analyzed,
        cutbacks=n,
        cutbacks_per_match=round(n / matches_analyzed, 2) if matches_analyzed else 0.0,
        shots_from_cutbacks=shots_from,
        goals_from_cutbacks=goals_from,
        conversion_rate=round(goals_from / n, 3) if n else 0.0,
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="team", subject_id=team_external_id,
        metric="cutback_frequency",
        value={
            "cutbacks": n,
            "cutbacks_per_match": report.cutbacks_per_match,
            "shots_from_cutbacks": shots_from,
            "goals_from_cutbacks": goals_from,
        },
        inputs={
            "cutback_start_x_min": CUTBACK_START_X_MIN,
            "cutback_start_wide_max": CUTBACK_START_WIDE_MAX,
            "cutback_to_shot_window_min": CUTBACK_TO_SHOT_WINDOW,
            "matches_analyzed": matches_analyzed,
        },
        formula="cutback = byline pass with end_x <= start_x into box center",
    )
    return EngineResult(value=report, audit=audit)
