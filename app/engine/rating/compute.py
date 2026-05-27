"""Takım rating'i — basit, formüle dayanan, açıklanabilir.

Karışıklığa kaçmadan form raporundan tek skorlu bir gösterge üretir:
    rating = ppg * PPG_WEIGHT + goal_diff_per_match * GD_WEIGHT

Hedef "doğru" rating değil, açıklanabilir bir baseline. ML-tabanlı rating
ufuk 3'te `engine/predict/`'e taşınacak.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass

from app.audit import AuditRecord, EngineResult
from app.domain import Match
from app.engine.form import compute_form

ENGINE_NAME = "engine.rating"
ENGINE_VERSION = "1"

PPG_WEIGHT = 50.0  # 0–150 aralığı (ppg 0–3)
GD_WEIGHT = 10.0


@dataclass(frozen=True)
class TeamRating:
    rating: float
    points_per_game: float
    goal_diff_per_match: float
    matches_considered: int


def compute_team_rating(
    team_external_id: int,
    matches: Iterable[Match],
    *,
    last_n: int = 10,
) -> EngineResult[TeamRating]:
    form_result = compute_form(team_external_id, matches, last_n=last_n)
    form = form_result.value

    if form.matches_played == 0:
        rating = TeamRating(
            rating=0.0,
            points_per_game=0.0,
            goal_diff_per_match=0.0,
            matches_considered=0,
        )
    else:
        gdpm = form.goal_diff / form.matches_played
        score = form.points_per_game * PPG_WEIGHT + gdpm * GD_WEIGHT
        rating = TeamRating(
            rating=round(score, 3),
            points_per_game=form.points_per_game,
            goal_diff_per_match=round(gdpm, 3),
            matches_considered=form.matches_played,
        )

    audit = AuditRecord(
        engine=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        subject_type="team",
        subject_id=team_external_id,
        metric="team_rating",
        value=asdict(rating),
        inputs={
            "last_n": last_n,
            "form_audit_id": id(form_result.audit),
            "ppg": form.points_per_game,
            "goal_diff": form.goal_diff,
            "matches_played": form.matches_played,
        },
        formula=f"ppg*{PPG_WEIGHT} + (goal_diff/matches)*{GD_WEIGHT}",
    )
    return EngineResult(value=rating, audit=audit)
