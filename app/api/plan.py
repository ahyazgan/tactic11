"""Plan-live köprü endpoint'leri (Faz 5 #28).

`POST /matches/{match_id}/plan` — game_plan agent çıktısını maçla ilişkilendir
ve kaydet (idempotent upsert). Pratikte CLI/UI önce `GamePlanAgent.run()`
çağırır, sonucu buraya gönderir.

`GET /matches/{match_id}/plan/vs-live` — kaydedilmiş planı yükle, mevcut maç
skor + dakika durumuyla karşılaştır, aktif senaryoyu seç, planın o senaryo
reçetesini geri döndür. Pre-match plan ile canlı durum arasında köprü.

Köprü pure-data: tahmin/engine çağrısı yok; mevcut planın senaryo
seçicisi + skor okuyucu. Gelecekte live tactical_profile snapshot
karşılaştırması eklenebilir.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.base import AgentResult
from app.agents.store import save_agent_output
from app.db import models
from app.db.session import get_session
from app.sports import football

router = APIRouter(prefix="/matches", tags=["plan"])

AGENT_NAME = "game_plan"
AGENT_VERSION = "1"


# --------------------------------------------------------------------------- #
# Şemalar
# --------------------------------------------------------------------------- #


class PlanPayload(BaseModel):
    """GamePlanAgent çıktısı + özet — endpoint bunu olduğu gibi store'a yazar."""

    output_json: dict[str, Any] = Field(..., description="GamePlanAgent.output_json")
    summary: str = Field(..., description="GamePlanAgent.summary")


class PlanSaved(BaseModel):
    match_id: int
    saved: bool
    updated_at: str


class PlanVsLive(BaseModel):
    match_id: int
    plan_age_seconds: float
    score: dict[str, int | None]
    minute: int | None
    status: str | None
    active_scenario: str            # leading | level | trailing | unknown
    scenario_recipe: dict[str, Any] | None
    matchup_recommendation: str | None
    set_piece_hint: str | None
    notes: list[str]


# --------------------------------------------------------------------------- #
# Yardımcılar
# --------------------------------------------------------------------------- #


def _load_match_plan(session: Session, match_id: int) -> models.AgentOutput | None:
    return session.execute(
        select(models.AgentOutput).where(
            models.AgentOutput.agent_name == AGENT_NAME,
            models.AgentOutput.agent_version == AGENT_VERSION,
            models.AgentOutput.subject_type == "match",
            models.AgentOutput.subject_id == match_id,
        )
    ).scalar_one_or_none()


def _load_match(session: Session, match_id: int) -> models.Match | None:
    return session.execute(
        select(models.Match).where(
            models.Match.sport == football.SPORT_NAME,
            models.Match.external_id == match_id,
        )
    ).scalar_one_or_none()


def _active_scenario(
    *, my_team_id: int, match: models.Match,
) -> tuple[str, dict[str, int | None]]:
    """Skor + perspektif → leading/level/trailing.

    `my_team_id` ev sahibi ya da deplasman olabilir. None skor → unknown.
    """
    hs = match.home_score
    aws = match.away_score
    score = {"home": hs, "away": aws}
    if hs is None or aws is None:
        return "unknown", score
    if match.home_team_external_id == my_team_id:
        my, opp = hs, aws
    elif match.away_team_external_id == my_team_id:
        my, opp = aws, hs
    else:
        return "unknown", score
    if my > opp:
        return "leading", score
    if my < opp:
        return "trailing", score
    return "level", score


def _estimated_minute(match: models.Match, now: datetime) -> int | None:
    """Kickoff'tan bu yana geçen dakika — basit lineer; HT/uzatma yok."""
    if match.kickoff is None:
        return None
    delta = (now - match.kickoff).total_seconds() / 60.0
    if delta < 0:
        return None
    return int(min(120, delta))


# --------------------------------------------------------------------------- #
# Endpoint: POST /matches/{match_id}/plan
# --------------------------------------------------------------------------- #


@router.post("/{match_id}/plan", response_model=PlanSaved)
def save_match_plan(
    match_id: int,
    payload: PlanPayload,
    session: Session = Depends(get_session),
) -> PlanSaved:
    """Bir maç için game_plan çıktısını sakla (idempotent upsert)."""
    if _load_match(session, match_id) is None:
        raise HTTPException(status_code=404, detail=f"match {match_id} bulunamadı")
    result = AgentResult(
        output_json=payload.output_json,
        summary=payload.summary,
        subject_type="match",
        subject_id=match_id,
    )
    row = save_agent_output(
        session,
        result=result,
        agent_name=AGENT_NAME,
        agent_version=AGENT_VERSION,
    )
    session.commit()
    return PlanSaved(
        match_id=match_id,
        saved=True,
        updated_at=row.updated_at.isoformat(),
    )


# --------------------------------------------------------------------------- #
# Endpoint: GET /matches/{match_id}/plan/vs-live
# --------------------------------------------------------------------------- #


@router.get("/{match_id}/plan/vs-live", response_model=PlanVsLive)
def plan_vs_live(
    match_id: int,
    my_team_id: int,
    session: Session = Depends(get_session),
) -> PlanVsLive:
    """Saklanmış plan'ı canlı maç durumuyla karşılaştır.

    Pre-match planın hangi senaryosu **şimdi aktif**, reçetesi ne, matchup
    önerisi ve set-piece ipucu nelerdir? Köprü pure-data; engine çağırmaz.
    """
    plan = _load_match_plan(session, match_id)
    if plan is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"match {match_id} için plan saklanmamış — "
                f"önce POST /matches/{match_id}/plan"
            ),
        )
    match = _load_match(session, match_id)
    if match is None:
        raise HTTPException(status_code=404, detail=f"match {match_id} bulunamadı")

    try:
        plan_data: dict[str, Any] = json.loads(plan.output_json)
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=500, detail=f"plan JSON çözülemedi: {e}",
        ) from e

    now = datetime.now(UTC)
    age = (now - plan.updated_at).total_seconds() if plan.updated_at else 0.0
    minute = _estimated_minute(match, now)
    active, score = _active_scenario(my_team_id=my_team_id, match=match)

    scenario_plan = plan_data.get("scenario_plan") or {}
    recipe: dict[str, Any] | None = (
        dict(scenario_plan[active])
        if active in scenario_plan and isinstance(scenario_plan[active], dict)
        else None
    )

    matchup_rec: str | None = None
    matchup = plan_data.get("matchup_grid")
    if isinstance(matchup, dict):
        matchup_rec = matchup.get("recommendation")

    set_piece_hint: str | None = None
    sp = plan_data.get("set_piece_plan")
    if isinstance(sp, dict):
        recs = sp.get("top_recommendations") or []
        if recs and isinstance(recs[0], dict):
            r0 = recs[0]
            set_piece_hint = (
                f"{r0.get('zone')} ({r0.get('technique')}) — {r0.get('rationale')}"
            )

    notes: list[str] = []
    if active == "unknown":
        notes.append("Skor veya takım eşleşmesi belirsiz — senaryo seçilemedi")
    if recipe is None and active != "unknown":
        notes.append(f"Planda '{active}' senaryosu için reçete yok")
    if age > 86400:
        notes.append(
            f"Plan {age / 3600:.0f} saat önce kaydedilmiş — güncelliği sorgula",
        )

    return PlanVsLive(
        match_id=match_id,
        plan_age_seconds=round(age, 1),
        score=score,
        minute=minute,
        status=match.status,
        active_scenario=active,
        scenario_recipe=recipe,
        matchup_recommendation=matchup_rec,
        set_piece_hint=set_piece_hint,
        notes=notes,
    )
