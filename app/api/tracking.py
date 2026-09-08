"""Tracking frame endpoint'leri — saha overlay'inin veri kaynağı.

GET /tracking/matches/{match_id}/status          — kaç frame var, dakika aralığı
GET /tracking/matches/{match_id}/frame?minute=   — verilen dakikaya kadar son frame
GET /tracking/matches/{match_id}/frames?from_minute=&to_minute=&limit=
                                                  — aralıktaki frame'ler (scrub)

Koordinatlar 0-100 normalize; provenance her yanıtta (`source`,
`identity_estimated`). Geometri (pas seçeneği, baskı, alan) frontend'de
hesaplanır — bu katman yalnız pozisyon servis eder.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import models
from app.db.session import get_session
from app.sports import football

router = APIRouter(prefix="/tracking", tags=["tracking"])

MAX_FRAMES = 400


def _match_or_404(session: Session, match_id: int) -> models.Match:
    match = session.execute(
        select(models.Match).where(
            models.Match.sport == football.SPORT_NAME,
            models.Match.external_id == match_id,
        )
    ).scalar_one_or_none()
    if match is None:
        raise HTTPException(status_code=404, detail=f"match {match_id} yok")
    return match


def _row_to_frame(row: models.TrackingFrameRow) -> dict[str, Any]:
    players = json.loads(row.players_json)
    meta = json.loads(row.meta_json) if row.meta_json else {}
    return {
        "minute": row.minute,
        "period": row.period,
        "ball": (
            {"x": row.ball_x, "y": row.ball_y}
            if row.ball_x is not None and row.ball_y is not None else None
        ),
        "players": players,
        "source": meta.get("source"),
        "event_uuid": meta.get("event_uuid"),
        "event_type": meta.get("event_type"),
        "possession_team_external_id": meta.get("possession_team_external_id"),
        "visible_area": meta.get("visible_area"),
    }


def _base_query(match_id: int):
    return select(models.TrackingFrameRow).where(
        models.TrackingFrameRow.sport == football.SPORT_NAME,
        models.TrackingFrameRow.match_external_id == match_id,
    )


@router.get("/matches", summary="Tracking karesi olan maçlar (kaynak + aralık)")
def tracking_matches(
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    rows = session.execute(
        select(
            models.TrackingFrameRow.match_external_id,
            func.count(models.TrackingFrameRow.id),
            func.min(models.TrackingFrameRow.minute),
            func.max(models.TrackingFrameRow.minute),
            func.min(models.TrackingFrameRow.meta_json),
        )
        .where(models.TrackingFrameRow.sport == football.SPORT_NAME)
        .group_by(models.TrackingFrameRow.match_external_id)
        .order_by(models.TrackingFrameRow.match_external_id.desc())
    ).all()
    ids = [r[0] for r in rows]
    matches: dict[int, models.Match] = {}
    if ids:
        matches = {
            m.external_id: m
            for m in session.execute(
                select(models.Match).where(
                    models.Match.sport == football.SPORT_NAME,
                    models.Match.external_id.in_(ids),
                )
            ).scalars()
        }
    out = []
    for mid, count, mn, mx, meta in rows:
        m = matches.get(mid)
        source = json.loads(meta).get("source") if meta else None
        out.append({
            "match_id": mid,
            "frames": int(count or 0),
            "first_minute": mn,
            "last_minute": mx,
            "source": source,
            "home_team_external_id": m.home_team_external_id if m else None,
            "away_team_external_id": m.away_team_external_id if m else None,
            "kickoff": m.kickoff.isoformat() if m and m.kickoff else None,
            "score": (
                f"{m.home_score}-{m.away_score}"
                if m and m.home_score is not None and m.away_score is not None else None
            ),
        })
    return {"matches": out, "total": len(out)}


@router.get("/matches/{match_id}/status", summary="Tracking verisi var mı / aralık")
def tracking_status(
    match_id: int,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    match = _match_or_404(session, match_id)
    count, min_minute, max_minute = session.execute(
        select(
            func.count(models.TrackingFrameRow.id),
            func.min(models.TrackingFrameRow.minute),
            func.max(models.TrackingFrameRow.minute),
        ).where(
            models.TrackingFrameRow.sport == football.SPORT_NAME,
            models.TrackingFrameRow.match_external_id == match_id,
        )
    ).one()
    first = session.execute(
        _base_query(match_id).order_by(models.TrackingFrameRow.timestamp).limit(1)
    ).scalar_one_or_none()
    source = None
    if first is not None and first.meta_json:
        source = json.loads(first.meta_json).get("source")
    return {
        "match_id": match_id,
        "home_team_external_id": match.home_team_external_id,
        "away_team_external_id": match.away_team_external_id,
        "frames": int(count or 0),
        "first_minute": min_minute,
        "last_minute": max_minute,
        "source": source,
        "coordinate_system": "normalized_0_100",
    }


@router.get("/matches/{match_id}/frame", summary="Dakikaya kadar son frame")
def tracking_frame_at(
    match_id: int,
    minute: float = Query(..., ge=0, le=130),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    match = _match_or_404(session, match_id)
    row = session.execute(
        _base_query(match_id)
        .where(models.TrackingFrameRow.minute <= minute)
        .order_by(models.TrackingFrameRow.timestamp.desc())
        .limit(1)
    ).scalar_one_or_none()
    return {
        "match_id": match_id,
        "requested_minute": minute,
        "home_team_external_id": match.home_team_external_id,
        "away_team_external_id": match.away_team_external_id,
        "coordinate_system": "normalized_0_100",
        "frame": _row_to_frame(row) if row is not None else None,
    }


@router.get("/matches/{match_id}/frames", summary="Dakika aralığındaki frame'ler")
def tracking_frames_between(
    match_id: int,
    from_minute: float = Query(0, ge=0, le=130),
    to_minute: float = Query(130, ge=0, le=130),
    limit: int = Query(120, ge=1, le=MAX_FRAMES),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    match = _match_or_404(session, match_id)
    if to_minute < from_minute:
        raise HTTPException(status_code=422, detail="to_minute < from_minute")
    # Limit aşılırsa pencerenin SONU (en güncel kareler) korunur — overlay
    # "şu an"ı gösterir, geçmişi değil.
    rows = session.execute(
        _base_query(match_id)
        .where(
            models.TrackingFrameRow.minute >= from_minute,
            models.TrackingFrameRow.minute <= to_minute,
        )
        .order_by(models.TrackingFrameRow.timestamp.desc())
        .limit(limit)
    ).scalars().all()
    rows = list(reversed(rows))
    return {
        "match_id": match_id,
        "home_team_external_id": match.home_team_external_id,
        "away_team_external_id": match.away_team_external_id,
        "coordinate_system": "normalized_0_100",
        "from_minute": from_minute,
        "to_minute": to_minute,
        "count": len(rows),
        "frames": [_row_to_frame(r) for r in rows],
    }
