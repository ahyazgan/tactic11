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
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import models
from app.db.session import get_session
from app.sports import football

router = APIRouter(prefix="/tracking", tags=["tracking"])

MAX_FRAMES = 400
SHAPE_MAX_FRAMES = 600


# --------------------------------------------------------------------------- #
# Kimlik eşlemesi (video: sentetik takip id → gerçek oyuncu)
# --------------------------------------------------------------------------- #


class IdentityIn(BaseModel):
    track_player_external_id: int
    player_name: str = Field(..., min_length=1, max_length=120)
    player_external_id: int | None = None
    jersey_number: int | None = Field(default=None, ge=0, le=99)
    team_external_id: int | None = None
    is_keeper: bool = False


class IdentitiesIn(BaseModel):
    identities: list[IdentityIn]
    replace: bool = False  # True → listede olmayan eşlemeler silinir


def _identity_map(session: Session, match_id: int) -> dict[int, models.TrackingIdentity]:
    rows = session.execute(
        select(models.TrackingIdentity).where(
            models.TrackingIdentity.sport == football.SPORT_NAME,
            models.TrackingIdentity.match_external_id == match_id,
        )
    ).scalars().all()
    return {r.track_player_external_id: r for r in rows}


def _apply_identities(players: list[dict[str, Any]], ids: dict[int, models.TrackingIdentity]) -> list[dict[str, Any]]:
    if not ids:
        return players
    out = []
    for p in players:
        ident = ids.get(int(p.get("player_external_id", -1)))
        if ident is None:
            out.append(p)
            continue
        q = dict(p)
        q["name"] = ident.player_name
        q["track_player_external_id"] = p["player_external_id"]
        if ident.player_external_id is not None:
            q["player_external_id"] = ident.player_external_id
        if ident.jersey_number is not None:
            q["jersey_number"] = ident.jersey_number
        if ident.team_external_id is not None:
            q["team_external_id"] = ident.team_external_id
        if ident.is_keeper:
            q["is_keeper"] = True
        q["identity_estimated"] = False
        out.append(q)
    return out


def _identity_out(r: models.TrackingIdentity) -> dict[str, Any]:
    return {
        "track_player_external_id": r.track_player_external_id,
        "player_name": r.player_name,
        "player_external_id": r.player_external_id,
        "jersey_number": r.jersey_number,
        "team_external_id": r.team_external_id,
        "is_keeper": r.is_keeper,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }


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


def _row_to_frame(row: models.TrackingFrameRow, ids: dict[int, models.TrackingIdentity] | None = None) -> dict[str, Any]:
    players = _apply_identities(json.loads(row.players_json), ids or {})
    meta = json.loads(row.meta_json) if row.meta_json else {}
    return {
        "minute": row.minute,
        "period": row.period,
        "ball": (
            {"x": row.ball_x, "y": row.ball_y, "velocity_mps": meta.get("ball_velocity_mps")}
            if row.ball_x is not None and row.ball_y is not None else None
        ),
        "players": players,
        "source": meta.get("source"),
        "event_uuid": meta.get("event_uuid"),
        "event_type": meta.get("event_type"),
        "possession_team_external_id": meta.get("possession_team_external_id"),
        "ball_estimated": bool(meta.get("ball_estimated", False)),
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
    ids = _identity_map(session, match_id)
    return {
        "match_id": match_id,
        "requested_minute": minute,
        "home_team_external_id": match.home_team_external_id,
        "away_team_external_id": match.away_team_external_id,
        "coordinate_system": "normalized_0_100",
        "frame": _row_to_frame(row, ids) if row is not None else None,
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
    ids = _identity_map(session, match_id)
    return {
        "match_id": match_id,
        "home_team_external_id": match.home_team_external_id,
        "away_team_external_id": match.away_team_external_id,
        "coordinate_system": "normalized_0_100",
        "from_minute": from_minute,
        "to_minute": to_minute,
        "count": len(rows),
        "frames": [_row_to_frame(r, ids) for r in rows],
    }


# --------------------------------------------------------------------------- #
# Takip özeti + kimlik eşlemesi uçları
# --------------------------------------------------------------------------- #


@router.get("/matches/{match_id}/tracks", summary="Maçtaki takipler (sentetik id) — kimlik eşleme için")
def tracking_tracks(
    match_id: int,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    match = _match_or_404(session, match_id)
    rows = session.execute(_base_query(match_id).order_by(models.TrackingFrameRow.timestamp)).scalars().all()
    agg: dict[int, dict[str, Any]] = {}
    for r in rows:
        for p in json.loads(r.players_json):
            pid = int(p["player_external_id"])
            a = agg.setdefault(pid, {
                "player_external_id": pid, "team_external_id": p.get("team_external_id"),
                "frames": 0, "first_minute": r.minute, "last_minute": r.minute,
                "actor_frames": 0, "speed_sum": 0.0, "speed_n": 0, "x_sum": 0.0, "y_sum": 0.0,
                "identity_estimated": bool(p.get("identity_estimated", False)),
            })
            a["frames"] += 1
            a["last_minute"] = r.minute
            a["actor_frames"] += 1 if p.get("is_actor") else 0
            a["x_sum"] += float(p["x"])
            a["y_sum"] += float(p["y"])
            v = p.get("velocity_mps")
            if v is not None:
                a["speed_sum"] += float(v)
                a["speed_n"] += 1
    ids = _identity_map(session, match_id)
    tracks = []
    for pid, a in sorted(agg.items(), key=lambda kv: -kv[1]["frames"]):
        ident = ids.get(pid)
        tracks.append({
            "player_external_id": pid,
            "team_external_id": a["team_external_id"],
            "frames": a["frames"],
            "first_minute": round(a["first_minute"], 2),
            "last_minute": round(a["last_minute"], 2),
            "actor_frames": a["actor_frames"],
            "mean_speed_mps": round(a["speed_sum"] / a["speed_n"], 2) if a["speed_n"] else None,
            "mean_x": round(a["x_sum"] / a["frames"], 1),
            "mean_y": round(a["y_sum"] / a["frames"], 1),
            "identity_estimated": a["identity_estimated"],
            "identity": _identity_out(ident) if ident else None,
        })
    return {
        "match_id": match_id,
        "home_team_external_id": match.home_team_external_id,
        "away_team_external_id": match.away_team_external_id,
        "frames": len(rows),
        "tracks": tracks,
        "total": len(tracks),
    }


@router.get("/matches/{match_id}/identities", summary="Kimlik eşlemeleri")
def get_identities(match_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    _match_or_404(session, match_id)
    ids = _identity_map(session, match_id)
    return {"match_id": match_id, "identities": [_identity_out(r) for r in ids.values()], "total": len(ids)}


@router.put("/matches/{match_id}/identities", summary="Kimlik eşlemelerini kaydet (upsert)")
def put_identities(
    match_id: int,
    body: IdentitiesIn,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    _match_or_404(session, match_id)
    existing = _identity_map(session, match_id)
    now = datetime.now(UTC)
    tenant_id = session.info.get("tenant_id")
    seen: set[int] = set()
    for item in body.identities:
        seen.add(item.track_player_external_id)
        row = existing.get(item.track_player_external_id)
        if row is None:
            row = models.TrackingIdentity(
                tenant_id=tenant_id, sport=football.SPORT_NAME,
                match_external_id=match_id,
                track_player_external_id=item.track_player_external_id,
                player_name=item.player_name, updated_at=now,
            )
            session.add(row)
        row.player_name = item.player_name.strip()
        row.player_external_id = item.player_external_id
        row.jersey_number = item.jersey_number
        row.team_external_id = item.team_external_id
        row.is_keeper = item.is_keeper
        row.updated_at = now
    removed = 0
    if body.replace:
        for pid, row in existing.items():
            if pid not in seen:
                session.delete(row)
                removed += 1
    session.commit()
    ids = _identity_map(session, match_id)
    return {"match_id": match_id, "identities": [_identity_out(r) for r in ids.values()], "total": len(ids), "removed": removed}


@router.delete("/matches/{match_id}/identities/{track_id}", summary="Tek eşlemeyi sil")
def delete_identity(match_id: int, track_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    _match_or_404(session, match_id)
    row = _identity_map(session, match_id).get(track_id)
    if row is None:
        raise HTTPException(status_code=404, detail="eşleme yok")
    session.delete(row)
    session.commit()
    return {"deleted": track_id}


# --------------------------------------------------------------------------- #
# Takım şekli / pres — engine.tracking köprüsü
# --------------------------------------------------------------------------- #


@router.get("/matches/{match_id}/shape", summary="Pencere içinde takım şekli + pres (engine.tracking)")
def tracking_shape(
    match_id: int,
    minute: float = Query(..., ge=0, le=130),
    window: float = Query(1.0, gt=0, le=15),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    from app.api.serialize import engine_result_to_dict
    from app.domain.tracking import TrackingFrame
    from app.engine.tracking.compute import compute_pressure, compute_team_shape

    match = _match_or_404(session, match_id)
    rows = session.execute(
        _base_query(match_id)
        .where(
            models.TrackingFrameRow.minute >= max(0.0, minute - window),
            models.TrackingFrameRow.minute <= minute,
        )
        .order_by(models.TrackingFrameRow.timestamp.desc())
        .limit(SHAPE_MAX_FRAMES)
    ).scalars().all()
    rows = list(reversed(rows))
    ids = _identity_map(session, match_id)
    frames: list[TrackingFrame] = []
    for r in rows:
        d = _row_to_frame(r, ids)
        frames.append(TrackingFrame(
            sport=football.SPORT_NAME, match_external_id=match_id,
            timestamp=r.timestamp, period=r.period, minute=r.minute,
            ball=({"player_external_id": 0, **d["ball"]} if d["ball"] else None),
            players=tuple(
                {k: v for k, v in p.items() if k in {
                    "player_external_id", "x", "y", "velocity_mps", "team_external_id",
                    "is_actor", "is_keeper", "identity_estimated",
                }} for p in d["players"]
            ),
            source=d["source"], event_type=d["event_type"],
            possession_team_external_id=d["possession_team_external_id"],
        ))
    out: dict[str, Any] = {
        "match_id": match_id, "minute": minute, "window": window, "frames": len(frames),
        "home_team_external_id": match.home_team_external_id,
        "away_team_external_id": match.away_team_external_id,
        "teams": {},
    }
    for side, tid in (("home", match.home_team_external_id), ("away", match.away_team_external_id)):
        shape = engine_result_to_dict(compute_team_shape(tid, frames))
        press = engine_result_to_dict(compute_pressure(tid, frames))
        out["teams"][side] = {"team_external_id": tid, "shape": shape["value"], "pressure": press["value"],
                              "formula": {"shape": shape.get("audit", {}).get("formula"), "pressure": press.get("audit", {}).get("formula")}}
    return out
