"""Takip kareleri → WS snapshot'ında savunma şekli bekçisi (`engine.shape_watch`).

Yalnız sürekli takipte (sabit kamera videosu ya da ekran yakalama) çalışır;
StatsBomb 360 gibi olay çapalı kareler topun çevresini gösterdiği için şekil
"normali" anlamsızdır (tracking_signals ile aynı kural). Kare yoksa blok eklenmez.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from sqlalchemy.orm import Session

from app.api.tracking import frames_in_window
from app.engine.shape_watch import compute_shape_watch
from app.engine.shape_watch.compute import BASELINE_MIN, RECENT_MIN

CONTINUOUS_SOURCES = frozenset({"video_tracking", "screen_capture"})
MAX_FRAMES = 1500


def shape_watch_for(
    session: Session, match_id: int, *, home_team_id: int, away_team_id: int, my_team_id: int,
    minute: float, home_attack: int = 0,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """(snapshot bloğu, pano uyarıları); sürekli takip karesi yoksa (None, [])."""
    frames = frames_in_window(session, match_id, minute - RECENT_MIN - BASELINE_MIN, minute,
                              limit=MAX_FRAMES, spread=True)
    if not frames or not all(f.source in CONTINUOUS_SOURCES for f in frames if f.source):
        return None, []
    report = compute_shape_watch(
        frames, home_team_external_id=home_team_id, away_team_external_id=away_team_id,
        my_team_external_id=my_team_id, minute=minute, home_attack=home_attack).value
    alerts = [{
        "type": f"shape_{f.metric}", "severity": f.severity, "message": f.message,
        "dedup_key": f"shape:{f.team_external_id}:{f.metric}:{'+' if f.delta_m > 0 else '-'}",
        "player_id": None,
    } for f in report.findings] if report.data_quality > 0 else []
    return asdict(report), alerts
