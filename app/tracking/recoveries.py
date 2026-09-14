"""Observed opponent-to-player control changes, conservatively labelled ball recovery.

This cannot distinguish a tackle, interception, loose-ball pickup or a blocked
pass. Never manufacture those subtypes. Missing/interpolated ball, overfull teams,
clock discontinuities and unstable touches break the evidence chain.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from app.domain.tracking import TrackingFrame
from app.tracking.frames import ACTOR_RADIUS_M
from app.tracking.passes import MAX_PASS_SPEED_MPS, MAX_SAMPLE_GAP_SECONDS, _actor, _dist_m

MIN_CONTROL_SECONDS = 0.24
MIN_CONTROL_FRAMES = 3
MAX_RECOVERY_FLIGHT_SECONDS = 2.0


@dataclass(frozen=True)
class DerivedDefensiveAction:
    minute: float
    period: int
    team_external_id: int
    player_external_id: int
    previous_player_external_id: int
    previous_team_external_id: int
    x: float
    y: float
    control_seconds: float
    flight_seconds: float
    action_type: str = "ball_recovery"
    successful: bool = True
    estimated: bool = True


@dataclass(frozen=True)
class RecoveryExtraction:
    actions: tuple[DerivedDefensiveAction, ...] = ()
    rejected: dict[str, int] = field(default_factory=dict)
    note: str = "yalnız gözlenmiş top kazanımları; tackle/interception ayrımı ve tam savunma kapsaması yok"


@dataclass
class _Control:
    player: int
    team: int
    first: TrackingFrame
    last: TrackingFrame
    count: int = 1


def extract_recoveries(frames: list[TrackingFrame]) -> RecoveryExtraction:
    actions = []
    rejected: Counter[str] = Counter()
    confirmed: _Control | None = None
    candidate: _Control | None = None
    previous: TrackingFrame | None = None
    for fr in frames:
        if previous is not None:
            dt = (fr.minute - previous.minute) * 60
            if (fr.match_external_id != previous.match_external_id or fr.period != previous.period
                    or fr.continuity_id != previous.continuity_id
                    or not 0 < dt <= MAX_SAMPLE_GAP_SECONDS):
                confirmed = candidate = None
                rejected["discontinuity"] += 1
        previous = fr
        counts = Counter(p.team_external_id for p in fr.players if p.team_external_id is not None)
        if fr.ball is None or fr.ball_estimated or any(n > 11 for n in counts.values()):
            confirmed = candidate = None
            rejected["ball_unobserved_or_team_invalid"] += 1
            continue
        actor = _actor(fr)
        if (actor is None or actor.team_external_id is None
                or _dist_m(actor.x, actor.y, fr.ball.x, fr.ball.y) > ACTOR_RADIUS_M):
            candidate = None
            continue
        if candidate and (candidate.player, candidate.team) == (actor.player_external_id, actor.team_external_id):
            candidate.last = fr
            candidate.count += 1
        else:
            candidate = _Control(actor.player_external_id, actor.team_external_id, fr, fr)
        held = (fr.minute - candidate.first.minute) * 60
        if candidate.count < MIN_CONTROL_FRAMES or held + 0.001 < MIN_CONTROL_SECONDS:
            continue
        if confirmed is not None and (confirmed.player, confirmed.team) != (candidate.player, candidate.team):
            flight = (candidate.first.minute - confirmed.last.minute) * 60
            old = _actor(confirmed.last)
            new = _actor(candidate.first)
            assert old is not None and new is not None
            if confirmed.player == candidate.player:
                rejected["same_identity_changed_team"] += 1
            elif confirmed.team != candidate.team:
                distance = _dist_m(old.x, old.y, new.x, new.y)
                if 0 < flight <= MAX_RECOVERY_FLIGHT_SECONDS and distance <= MAX_PASS_SPEED_MPS * flight + 2.5:
                    actions.append(DerivedDefensiveAction(
                        minute=candidate.first.minute, period=fr.period,
                        team_external_id=candidate.team, player_external_id=candidate.player,
                        previous_player_external_id=confirmed.player,
                        previous_team_external_id=confirmed.team,
                        x=new.x, y=new.y, control_seconds=round(held, 3),
                        flight_seconds=round(flight, 3),
                    ))
                else:
                    rejected["flight_time_or_distance"] += 1
        # Copy: updating the candidate must not move the previous holder's end.
        confirmed = _Control(candidate.player, candidate.team, candidate.first, fr, candidate.count)
    return RecoveryExtraction(actions=tuple(actions), rejected=dict(rejected))
