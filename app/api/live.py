"""Live WebSocket endpoints — canlı maç push.

FastAPI built-in WebSocket; Redis backend gerekmez (tek-process pilot demo).
Production-scale çoklu worker için Redis pub/sub gerekir.

Endpoint: /ws/matches/{match_id}/live?my_team_id=N&interval_seconds=10

Algoritma:
1. Client connect olur
2. Sunucu N saniyede bir tactical-profile + halftime brief snapshot push'lar
3. Client disconnect veya match status FT olduğunda kapanır

Şu an event akışı StatsBomb Open Data static; gerçek canlı feed StatsBomb Pro
veya Opta ile sonradan swap edilir. Bu endpoint protokolü tanımlar.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
from typing import Any

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.serialize import engine_result_to_dict
from app.core.logging import get_logger
from app.data.loaders import load_match_events
from app.db import models
from app.db.session import get_session
from app.engine.field_tilt import compute_field_tilt
from app.engine.live_shape_drift import compute_live_shape_drift
from app.engine.live_sub_recommendation import compute_live_sub_recommendation
from app.engine.match_dominance import compute_match_dominance
from app.engine.ppda import compute_ppda
from app.sports import football

log = get_logger(__name__)

router = APIRouter(prefix="/ws", tags=["live"])

# Tek-process state: aktif WebSocket sayısı (observability)
_ACTIVE_CONNECTIONS: dict[str, int] = {"count": 0}

# Push interval kabul sınırları
MIN_INTERVAL_SECONDS = 5
MAX_INTERVAL_SECONDS = 60

# Maç başlangıcından itibaren simülasyon: "şu an dakika kaç?"
# (gerçek canlı feed varken provider'dan gelecek; şimdi maç süresinden tahmin)
SIMULATION_START_MINUTE = 0.0


def _compute_live_snapshot(
    session, match_id: int, my_team_id: int, current_minute: float,
) -> dict[str, Any]:
    """Tek-snapshot: events şu ana kadar olanlar + canlı engine'ler."""
    match = session.execute(
        select(models.Match).where(
            models.Match.sport == football.SPORT_NAME,
            models.Match.external_id == match_id,
        )
    ).scalar_one_or_none()
    if match is None:
        return {"error": f"match {match_id} bulunamadı"}

    home_id = match.home_team_external_id
    away_id = match.away_team_external_id
    opp_id = away_id if my_team_id == home_id else home_id

    loaded = load_match_events(session, match_id)
    # Sadece şu ana kadar olan event'ler
    passes_so_far = [p for p in loaded.passes if p.minute <= current_minute]
    carries_so_far = [c for c in loaded.carries if c.minute <= current_minute]
    defs_so_far = [d for d in loaded.defensive_actions
                    if d.minute <= current_minute]
    shots_so_far = [s for s in loaded.shots if s.minute <= current_minute]

    if not passes_so_far:
        return {
            "match_id": match_id, "current_minute": current_minute,
            "events_so_far": 0,
            "note": "Henüz event yok",
        }

    snapshot: dict[str, Any] = {
        "match_id": match_id,
        "my_team_id": my_team_id,
        "opponent_id": opp_id,
        "current_minute": current_minute,
        "events_so_far": (len(passes_so_far) + len(carries_so_far)
                          + len(defs_so_far) + len(shots_so_far)),
        "score": f"{match.home_score}-{match.away_score}",
    }
    try:
        ppda = compute_ppda(my_team_id, passes_so_far, defs_so_far)
        snapshot["ppda"] = engine_result_to_dict(ppda)["value"]
        tilt = compute_field_tilt(my_team_id, opp_id, passes_so_far)
        snapshot["field_tilt"] = engine_result_to_dict(tilt)["value"]
        dom = compute_match_dominance(
            team_external_id=my_team_id, opponent_team_external_id=opp_id,
            team_shots=shots_so_far, opponent_shots=shots_so_far,
            all_passes=passes_so_far, team_carries=carries_so_far,
            opponent_carries=carries_so_far,
        )
        snapshot["match_dominance"] = engine_result_to_dict(dom)["value"]
        # Live decisions (gerçek "live" özellikler)
        my_score = match.home_score if my_team_id == home_id else match.away_score
        opp_score = match.away_score if my_team_id == home_id else match.home_score
        sub_rec = compute_live_sub_recommendation(
            my_team_id, passes_so_far, defs_so_far,
            current_minute=current_minute, my_score=my_score,
            opponent_score=opp_score,
        )
        snapshot["live_sub_recommendation"] = engine_result_to_dict(sub_rec)["value"]
        shape = compute_live_shape_drift(
            opp_id, passes_so_far, current_minute=current_minute,
        )
        snapshot["opponent_shape_drift"] = engine_result_to_dict(shape)["value"]
    except (ValueError, ZeroDivisionError, KeyError, TypeError) as e:
        snapshot["error"] = str(e)
    return snapshot


@router.websocket("/matches/{match_id}/live")
async def matches_live(
    websocket: WebSocket,
    match_id: int,
    my_team_id: int = Query(...),
    interval_seconds: int = Query(default=10),
    max_minute: float = Query(default=90.0,
        description="Simülasyon üst sınırı; replay için"),
    tenant_id: str = Query(default="t-default"),
    session: Session = Depends(get_session),
) -> None:
    """WebSocket: her N saniyede tactical snapshot push.

    Replay modu: events tablosundaki match için simulated wall-clock; her
    interval'da "şu dakikadayız" değeri artar.
    """
    interval = max(MIN_INTERVAL_SECONDS, min(MAX_INTERVAL_SECONDS, interval_seconds))
    await websocket.accept()
    _ACTIVE_CONNECTIONS["count"] += 1
    log.info(
        "ws connect match=%d team=%d interval=%ds tenant=%s",
        match_id, my_team_id, interval, tenant_id,
    )
    session.info["tenant_id"] = tenant_id
    start_wall = time.monotonic()
    try:
        while True:
            elapsed_wall = time.monotonic() - start_wall
            # Replay: her interval'da +5 dk simülasyon
            current_minute = min(max_minute, SIMULATION_START_MINUTE
                                 + (elapsed_wall / interval) * 5.0)
            snapshot = _compute_live_snapshot(
                session, match_id, my_team_id, current_minute,
            )
            await websocket.send_text(json.dumps(snapshot, default=str))
            if current_minute >= max_minute:
                await websocket.send_text(json.dumps({
                    "type": "match_ended", "current_minute": current_minute,
                }))
                break
            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.sleep(interval)
    except WebSocketDisconnect:
        log.info("ws disconnect match=%d team=%d", match_id, my_team_id)
    finally:
        _ACTIVE_CONNECTIONS["count"] -= 1


@router.get("/active-connections")
def active_connections() -> dict[str, int]:
    """Şu an kaç WebSocket bağlı (observability)."""
    return _ACTIVE_CONNECTIONS.copy()
