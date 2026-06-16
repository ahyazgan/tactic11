"""Canlı VAEP REST endpoint (Faz 5 #47).

WebSocket snapshot zaten VAEP feed'i taşır; bu endpoint UI/agent için
tek-shot REST erişimi sağlar (subscribe etmeden anlık kesit alma).

`GET /matches/{id}/live-vaep?my_team_id=N&current_minute=M&top_n=K`
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.live import _compute_live_vaep
from app.data.loaders import load_match_events
from app.db import models
from app.db.session import get_session
from app.sports import football

router = APIRouter(tags=["live"])


@router.get("/matches/{match_id}/live-vaep")
def live_vaep_snapshot(
    match_id: int,
    my_team_id: int,
    current_minute: float = 90.0,
    top_n: int = 5,
    session: Session = Depends(get_session),
) -> dict:
    """Bir maç için takım + top-N oyuncu canlı VAEP kesiti.

    `current_minute` filtresi event'leri o ana kadar kısıtlar (sızıntı yok).
    """
    if current_minute < 0 or current_minute > 130:
        raise HTTPException(
            status_code=400,
            detail="current_minute 0..130 aralığında olmalı",
        )
    if top_n < 1 or top_n > 25:
        raise HTTPException(
            status_code=400, detail="top_n 1..25 aralığında olmalı",
        )

    match = session.execute(
        select(models.Match).where(
            models.Match.sport == football.SPORT_NAME,
            models.Match.external_id == match_id,
        )
    ).scalar_one_or_none()
    if match is None:
        raise HTTPException(
            status_code=404, detail=f"match {match_id} bulunamadı",
        )

    if my_team_id not in (
        match.home_team_external_id, match.away_team_external_id,
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                f"my_team_id {my_team_id} bu maçta oynamıyor "
                f"({match.home_team_external_id} vs "
                f"{match.away_team_external_id})"
            ),
        )

    opp_team_id = (
        match.away_team_external_id
        if my_team_id == match.home_team_external_id
        else match.home_team_external_id
    )

    loaded = load_match_events(session, match_id)
    passes = [p for p in loaded.passes if p.minute <= current_minute]
    carries = [c for c in loaded.carries if c.minute <= current_minute]
    shots = [s for s in loaded.shots if s.minute <= current_minute]

    if not passes and not carries and not shots:
        return {
            "match_id": match_id,
            "my_team_id": my_team_id,
            "opponent_id": opp_team_id,
            "current_minute": current_minute,
            "info": "Henüz event yok",
        }

    vaep = _compute_live_vaep(
        my_team_id=my_team_id,
        opp_team_id=opp_team_id,
        passes=passes, carries=carries, shots=shots,
        current_minute=current_minute,
        top_n=top_n,
    )
    return {
        "match_id": match_id,
        "my_team_id": my_team_id,
        "opponent_id": opp_team_id,
        "events_so_far": len(passes) + len(carries) + len(shots),
        "vaep": vaep,
    }
