"""Sprint 3 backend endpoint'leri — kontrat uyarıları + transfer hedef
havuzu + rehab takibi (Faz 5 #34, #35, #43).

Üç ayrı endpoint kümesi tek router'da:

- `GET /players/contract-alerts` — sözleşme bitişi yaklaşan oyuncular
- `GET /players/transfer-targets` — bir oyuncuya benzer transfer adayları
- `POST /players/{id}/rehab` + `GET /players/{id}/rehab/active` — rehab CRUD-lite

Tümü PROTECTED router'a takılır (auth zorunlu).
"""
from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models
from app.db.session import get_session
from app.engine.contract_alerts import compute_contract_alerts
from app.engine.player_similarity import compute_similar_players
from app.sports import football

router = APIRouter(tags=["sprint3"])


# --------------------------------------------------------------------------- #
# #34 — Contract alerts
# --------------------------------------------------------------------------- #


class ContractAlertOut(BaseModel):
    player_external_id: int
    contract_end: date
    days_remaining: int
    level: str
    annual_salary_eur: int | None
    message: str


class ContractAlertsOut(BaseModel):
    team_external_id: int | None
    total_contracts: int
    in_horizon: int
    critical_count: int
    warning_count: int
    notice_count: int
    expired_count: int
    alerts: list[ContractAlertOut]


@router.get("/players/contract-alerts", response_model=ContractAlertsOut)
def list_contract_alerts(
    team_external_id: int | None = None,
    horizon_days: int = 365,
    session: Session = Depends(get_session),
) -> ContractAlertsOut:
    """Sözleşmesi `horizon_days` içinde biten veya geçmiş oyuncular."""
    if horizon_days <= 0:
        raise HTTPException(status_code=400, detail="horizon_days > 0 olmalı")
    q = select(models.PlayerContract).where(
        models.PlayerContract.sport == football.SPORT_NAME,
    )
    if team_external_id is not None:
        q = q.where(models.PlayerContract.team_external_id == team_external_id)
    rows = list(session.execute(q).scalars())
    contracts = [
        {
            "player_external_id": r.player_external_id,
            "contract_end": r.contract_end,
            "annual_salary_eur": r.annual_salary_eur,
        }
        for r in rows
    ]
    result = compute_contract_alerts(
        contracts,
        today=datetime.now(UTC).date(),
        horizon_days=horizon_days,
        team_external_id=team_external_id,
    ).value
    return ContractAlertsOut(
        team_external_id=result.team_external_id,
        total_contracts=result.total_contracts,
        in_horizon=result.in_horizon,
        critical_count=result.critical_count,
        warning_count=result.warning_count,
        notice_count=result.notice_count,
        expired_count=result.expired_count,
        alerts=[
            ContractAlertOut(
                player_external_id=a.player_external_id,
                contract_end=a.contract_end,
                days_remaining=a.days_remaining,
                level=a.level,
                annual_salary_eur=a.annual_salary_eur,
                message=a.message,
            )
            for a in result.alerts
        ],
    )


# --------------------------------------------------------------------------- #
# #35 — Transfer target pool
# --------------------------------------------------------------------------- #


class TransferTargetOut(BaseModel):
    player_external_id: int
    similarity: float
    total_minutes: int
    position: str | None
    age: int | None


class TransferTargetsOut(BaseModel):
    target_player_external_id: int
    candidates_considered: int
    candidates_eligible: int
    pool_size: int
    matches: list[TransferTargetOut]


def _age_from_birth(birth: date | None, today: date) -> int | None:
    if birth is None:
        return None
    return today.year - birth.year - (
        1 if (today.month, today.day) < (birth.month, birth.day) else 0
    )


@router.get("/players/transfer-targets", response_model=TransferTargetsOut)
def transfer_targets(
    target_player_id: int,
    position: str | None = None,
    max_age: int | None = None,
    min_minutes: int = 270,
    top_n: int = 10,
    session: Session = Depends(get_session),
) -> TransferTargetsOut:
    """Hedef oyuncuya benzer transfer havuzu — pozisyon + yaş ön-filtresi.

    `target_player_id` mevcut kadrodakilerden biri olabilir; havuz dışındaki
    tüm aktif oyunculardan position + max_age ön-filtre uygulanır, sonra
    player_similarity ile cosine sıralama.
    """
    today = datetime.now(UTC).date()

    # Hedef oyuncunun appearance'larını al
    target_apps = list(session.execute(
        select(models.PlayerAppearance).where(
            models.PlayerAppearance.sport == football.SPORT_NAME,
            models.PlayerAppearance.player_external_id == target_player_id,
        )
    ).scalars())
    if not target_apps:
        raise HTTPException(
            status_code=404,
            detail=f"target player {target_player_id} appearance yok",
        )

    # Aday havuzu: Player tablosundan filtre uygula
    pool_q = select(models.Player).where(
        models.Player.sport == football.SPORT_NAME,
        models.Player.external_id != target_player_id,
    )
    if position is not None:
        pool_q = pool_q.where(models.Player.position == position)
    pool = list(session.execute(pool_q).scalars())
    pool_filtered: list[models.Player] = []
    for p in pool:
        if max_age is not None:
            a = _age_from_birth(p.birth_date, today)
            if a is None or a > max_age:
                continue
        pool_filtered.append(p)
    pool_ids = {p.external_id for p in pool_filtered}
    if not pool_ids:
        return TransferTargetsOut(
            target_player_external_id=target_player_id,
            candidates_considered=0, candidates_eligible=0,
            pool_size=0, matches=[],
        )

    # Aday appearance'larını batch çek + by pid grupla
    cand_apps = list(session.execute(
        select(models.PlayerAppearance).where(
            models.PlayerAppearance.sport == football.SPORT_NAME,
            models.PlayerAppearance.player_external_id.in_(pool_ids),
        )
    ).scalars())
    by_pid: dict[int, list[Any]] = {}
    for a in cand_apps:
        by_pid.setdefault(a.player_external_id, []).append(a)

    sim = compute_similar_players(
        target_player_id, target_apps, by_pid,
        top_n=top_n, min_minutes=min_minutes,
    ).value

    # Player meta'sını sonuç dict'ine ekle
    meta = {p.external_id: p for p in pool_filtered}
    out_matches: list[TransferTargetOut] = []
    for m in sim.top_matches:
        p = meta.get(m.player_external_id)
        out_matches.append(TransferTargetOut(
            player_external_id=m.player_external_id,
            similarity=m.similarity,
            total_minutes=m.total_minutes,
            position=p.position if p else None,
            age=_age_from_birth(p.birth_date, today) if p else None,
        ))

    return TransferTargetsOut(
        target_player_external_id=target_player_id,
        candidates_considered=sim.candidates_considered,
        candidates_eligible=sim.candidates_eligible,
        pool_size=len(pool_filtered),
        matches=out_matches,
    )


# --------------------------------------------------------------------------- #
# #43 — Rehabilitation tracking
# --------------------------------------------------------------------------- #


VALID_REHAB_STATUSES = ("active", "recovering", "cleared")


class RehabPayload(BaseModel):
    injury_type: str = Field(..., min_length=1, max_length=128)
    injury_start: date
    expected_return: date | None = None
    actual_return: date | None = None
    status: str = Field(..., description="active | recovering | cleared")
    notes: str | None = Field(None, max_length=1024)


class RehabOut(BaseModel):
    id: int
    player_external_id: int
    injury_type: str
    injury_start: date
    expected_return: date | None
    actual_return: date | None
    status: str
    notes: str | None
    created_at: datetime
    updated_at: datetime


@router.post("/players/{player_id}/rehab", response_model=RehabOut)
def create_rehab(
    player_id: int,
    payload: RehabPayload,
    session: Session = Depends(get_session),
) -> RehabOut:
    """Yeni rehab kaydı oluştur (geçmiş kayıtların yanına eklenir)."""
    if payload.status not in VALID_REHAB_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"status {payload.status} geçersiz — {VALID_REHAB_STATUSES}",
        )
    now = datetime.now(UTC)
    row = models.PlayerRehabilitation(
        sport=football.SPORT_NAME,
        player_external_id=player_id,
        injury_type=payload.injury_type,
        injury_start=payload.injury_start,
        expected_return=payload.expected_return,
        actual_return=payload.actual_return,
        status=payload.status,
        notes=payload.notes,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    session.flush()
    session.commit()
    return _rehab_to_out(row)


@router.get("/players/{player_id}/rehab/active", response_model=list[RehabOut])
def list_active_rehab(
    player_id: int,
    session: Session = Depends(get_session),
) -> list[RehabOut]:
    """Oyuncu için aktif (henüz cleared olmamış) rehab kayıtları."""
    rows = list(session.execute(
        select(models.PlayerRehabilitation)
        .where(
            models.PlayerRehabilitation.sport == football.SPORT_NAME,
            models.PlayerRehabilitation.player_external_id == player_id,
            models.PlayerRehabilitation.status != "cleared",
        )
        .order_by(models.PlayerRehabilitation.injury_start.desc())
    ).scalars())
    return [_rehab_to_out(r) for r in rows]


def _rehab_to_out(r: models.PlayerRehabilitation) -> RehabOut:
    return RehabOut(
        id=r.id,
        player_external_id=r.player_external_id,
        injury_type=r.injury_type,
        injury_start=r.injury_start,
        expected_return=r.expected_return,
        actual_return=r.actual_return,
        status=r.status,
        notes=r.notes,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )
