"""Progressive Passes per 90 — FiveThirtyEight / FBRef metriği.

Tanım: bir pas "progressive" kabul edilir eğer:
1. Top KENDİ savunma yarısında başladıysa: ≥30 birim kale yönünde ilerletti
2. Saha ortasında başladıysa: ≥15 birim kale yönünde ilerletti
3. Hücum yarısında başladıysa: ≥10 birim kale yönünde ilerletti
4. Hücum 1/3'üne çıktıysa (start < 66.7, end ≥ 66.7): otomatik prog

Oyuncu profili için kritik metrik (deep_playmaker, ball_playing_cb).

Saf hesap.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.audit import AuditRecord, EngineResult
from app.domain import PassEvent

ENGINE_NAME = "engine.progressive_passes"
ENGINE_VERSION = "1"

OWN_HALF_X_MAX = 50.0
MIDDLE_X_MAX = 66.7
# İlerleme eşikleri (saha birimleri 100×100)
OWN_HALF_PROGRESSION = 30.0
MIDDLE_PROGRESSION = 15.0
ATTACKING_PROGRESSION = 10.0


def _is_progressive(p: PassEvent) -> bool:
    if not p.completed:
        return False
    dx = p.end_x - p.start_x
    if dx <= 0:
        return False
    # Final third otomatik
    if p.start_x < MIDDLE_X_MAX and p.end_x >= MIDDLE_X_MAX:
        return True
    if p.start_x < OWN_HALF_X_MAX:
        return dx >= OWN_HALF_PROGRESSION
    if p.start_x < MIDDLE_X_MAX:
        return dx >= MIDDLE_PROGRESSION
    return dx >= ATTACKING_PROGRESSION


@dataclass(frozen=True)
class ProgressivePassesReport:
    player_external_id: int | None
    team_external_id: int | None
    matches_analyzed: int
    player_minutes_played: float | None
    total_passes: int
    progressive_passes: int
    progressive_share: float
    progressive_per_90: float | None


def compute_progressive_passes(
    *,
    team_external_id: int | None = None,
    player_external_id: int | None = None,
    all_passes: Iterable[PassEvent],
    player_minutes_played: float | None = None,
    matches_analyzed: int = 1,
) -> EngineResult[ProgressivePassesReport]:
    if team_external_id is None and player_external_id is None:
        raise ValueError("team_external_id veya player_external_id verilmeli")

    def _match(p: PassEvent) -> bool:
        if player_external_id is not None:
            return p.player_external_id == player_external_id
        return p.team_external_id == team_external_id

    subject_passes = [p for p in all_passes if _match(p)]
    progressive = [p for p in subject_passes if _is_progressive(p)]

    per_90: float | None = None
    if player_external_id is not None and player_minutes_played and player_minutes_played > 0:
        per_90 = round((len(progressive) / player_minutes_played) * 90, 2)

    report = ProgressivePassesReport(
        player_external_id=player_external_id,
        team_external_id=team_external_id,
        matches_analyzed=matches_analyzed,
        player_minutes_played=player_minutes_played,
        total_passes=len(subject_passes),
        progressive_passes=len(progressive),
        progressive_share=round(len(progressive) / len(subject_passes), 3)
            if subject_passes else 0.0,
        progressive_per_90=per_90,
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="player" if player_external_id else "team",
        subject_id=player_external_id or team_external_id or 0,
        metric="progressive_passes",
        value={
            "total_passes": report.total_passes,
            "progressive_passes": report.progressive_passes,
            "progressive_share": report.progressive_share,
            "progressive_per_90": report.progressive_per_90,
        },
        inputs={
            "own_half_progression": OWN_HALF_PROGRESSION,
            "middle_progression": MIDDLE_PROGRESSION,
            "attacking_progression": ATTACKING_PROGRESSION,
            "matches_analyzed": matches_analyzed,
        },
        formula="zone-tiered forward progression threshold; auto-prog if enters final third",
    )
    return EngineResult(value=report, audit=audit)
