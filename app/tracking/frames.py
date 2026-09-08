"""Gözlem → TrackingFrame.

Video hattının çıktısı, StatsBomb 360 ile aynı domain şemasına yazılır;
/tracking API'si ve saha overlay'i kaynağı ayırt etmeden çalışır.

- player_external_id: VIDEO_PLAYER_BASE_ID + track_id (sentetik, identity_estimated)
- team_external_id: kümeleme 0 → ev sahibi id, 1 → deplasman id, None → yok (hakem/GK)
- is_actor: topa en yakın (ACTOR_RADIUS_M içinde) oyuncu
- possession_team_external_id: aktörün takımı
- visible_area: kamera görüş alanının saha izdüşümü
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from app.domain.tracking import PlayerPosition, TrackingFrame
from app.tracking.calibration import PitchCalibration

VIDEO_PLAYER_BASE_ID = 30000
ACTOR_RADIUS_M = 2.5
SOURCE_NAME = "video_tracking"
# StatsBomb 360 adapter ile aynı sentetik zaman ekseni ((match, timestamp) tekilliği)
FRAME_EPOCH = datetime(2000, 1, 1, tzinfo=UTC)


@dataclass(frozen=True)
class TrackObservation:
    track_id: int
    u: float  # piksel — ayak noktası (bbox alt-orta)
    v: float
    team: int | None
    conf: float = 1.0
    velocity_mps: float | None = None


@dataclass(frozen=True)
class BallObservation:
    u: float
    v: float
    conf: float = 1.0
    velocity_mps: float | None = None


def _dist_m(a: tuple[float, float], b: tuple[float, float], calib: PitchCalibration) -> float:
    dx = (a[0] - b[0]) / 100.0 * calib.pitch_length_m
    dy = (a[1] - b[1]) / 100.0 * calib.pitch_width_m
    return (dx * dx + dy * dy) ** 0.5


def build_frame(
    *,
    match_id: int,
    seconds: float,
    order: int,
    calib: PitchCalibration,
    players: list[TrackObservation],
    ball: BallObservation | None,
    home_team_id: int,
    away_team_id: int,
    period: int = 1,
    clip_offset_minutes: float = 0.0,
    sport: str = "football",
    ball_estimated: bool = False,
) -> TrackingFrame | None:
    """Bir örnekleme anının gözlemlerini TrackingFrame'e çevir; saha dışı/boş → None."""
    positions: list[tuple[TrackObservation, tuple[float, float]]] = []
    for obs in players:
        if not calib.is_on_pitch(obs.u, obs.v):
            continue
        positions.append((obs, calib.image_to_normalized(obs.u, obs.v)))
    if not positions:
        return None

    ball_pos: PlayerPosition | None = None
    ball_xy: tuple[float, float] | None = None
    if ball is not None and calib.is_on_pitch(ball.u, ball.v, margin_m=5.0):
        ball_xy = calib.image_to_normalized(ball.u, ball.v)
        ball_pos = PlayerPosition(player_external_id=0, x=ball_xy[0], y=ball_xy[1], velocity_mps=ball.velocity_mps)

    actor_idx: int | None = None
    if ball_xy is not None:
        best = ACTOR_RADIUS_M
        for i, (obs, xy) in enumerate(positions):
            if obs.team is None:
                continue
            d = _dist_m(xy, ball_xy, calib)
            if d < best:
                best, actor_idx = d, i

    def team_id(t: int | None) -> int | None:
        if t == 0:
            return home_team_id
        if t == 1:
            return away_team_id
        return None

    out_players = tuple(
        PlayerPosition(
            player_external_id=VIDEO_PLAYER_BASE_ID + obs.track_id,
            x=xy[0], y=xy[1],
            velocity_mps=obs.velocity_mps,
            team_external_id=team_id(obs.team),
            is_actor=(i == actor_idx),
            is_keeper=False,
            identity_estimated=True,
        )
        for i, (obs, xy) in enumerate(positions)
    )
    minute = clip_offset_minutes + seconds / 60.0
    possession = team_id(positions[actor_idx][0].team) if actor_idx is not None else None
    return TrackingFrame(
        sport=sport,
        match_external_id=match_id,
        timestamp=FRAME_EPOCH + timedelta(seconds=minute * 60.0, microseconds=order),
        period=period,
        minute=round(minute, 4),
        ball=ball_pos,
        ball_estimated=ball_estimated and ball_pos is not None,
        players=out_players,
        source=SOURCE_NAME,
        event_uuid=None,
        event_type="video_sample",
        possession_team_external_id=possession,
        visible_area=calib.visible_area_normalized(),
    )


def frames_to_json(frames: list[TrackingFrame], *, match_id: int, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "match_external_id": match_id,
        "source": SOURCE_NAME,
        "frames": [f.model_dump(mode="json") for f in frames],
        **(extra or {}),
    }


def frames_from_json(payload: dict[str, Any], *, match_id: int | None = None) -> list[TrackingFrame]:
    out: list[TrackingFrame] = []
    for d in payload.get("frames", []):
        if match_id is not None:
            d = {**d, "match_external_id": match_id}
        out.append(TrackingFrame.model_validate(d))
    return out
