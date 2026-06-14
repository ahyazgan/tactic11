"""StatsBomb event parser — Shot dışındaki event tipleri.

`statsbomb_open.py` shot event'lerini parse ediyor; bu modül pass + defansif
aksiyon + carry parser'larını ekler. xT/xA/PPDA/build_up için ana girdiler.

StatsBomb event.type.id referans:
- 16: Shot (statsbomb_open.py'da işleniyor)
- 30: Pass
- 7: Tactical Shift (formation change)
- 9: Clearance
- 10: Interception
- 17: Pressure
- 22: Foul Committed
- 21: Foul Won
- 23: Goal Keeper
- 24: Bad Behaviour
- 43: Carry
- 4: Duel (içinde tackle var: outcome.name=Won)
- 6: Block

Defensive Action grubu (PPDA için):
- tackle (duel won), interception, ball recovery, block, pressure, clearance

Output: PassEvent, DefensiveAction, Carry domain modelleri.
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger
from app.data.sources.statsbomb_open import (
    STATSBOMB_PITCH_LENGTH,
    STATSBOMB_PITCH_WIDTH,
)
from app.domain import Carry, DefensiveAction, FoulEvent, PassEvent
from app.sports import football

log = get_logger(__name__)

# Event type.id constants (StatsBomb event-spec)
PASS_EVENT_TYPE_ID = 30
DUEL_EVENT_TYPE_ID = 4
INTERCEPTION_EVENT_TYPE_ID = 10
PRESSURE_EVENT_TYPE_ID = 17
BLOCK_EVENT_TYPE_ID = 6
CLEARANCE_EVENT_TYPE_ID = 9
BALL_RECOVERY_EVENT_TYPE_ID = 2
CARRY_EVENT_TYPE_ID = 43
FOUL_COMMITTED_EVENT_TYPE_ID = 22
BAD_BEHAVIOUR_EVENT_TYPE_ID = 24

# StatsBomb card.id → bizim CardColor
_CARD_MAP: dict[int, str] = {
    5: "yellow",         # Yellow Card
    6: "second_yellow",  # Second Yellow
    7: "red",            # Red Card
}


# pass.type.id → bizim PassType
_PASS_TYPE_MAP: dict[int, str] = {
    61: "corner",      # Corner
    62: "free_kick",   # Free Kick
    63: "goal_kick",   # Goal Kick
    64: "kick_off",    # Kick Off
    65: "recovery",
    66: "throw_in",
    67: "interception",
}


def _normalize_xy(location: list[float] | None) -> tuple[float, float] | None:
    """[x_120, y_80] → (x_100, y_100). None / boş → None."""
    if not location or len(location) < 2:
        return None
    x_100 = (float(location[0]) / STATSBOMB_PITCH_LENGTH) * 100.0
    y_100 = (float(location[1]) / STATSBOMB_PITCH_WIDTH) * 100.0
    return (
        max(0.0, min(100.0, x_100)),
        max(0.0, min(100.0, y_100)),
    )


def is_pass_event(event: dict[str, Any]) -> bool:
    return int((event.get("type") or {}).get("id", 0)) == PASS_EVENT_TYPE_ID


def is_carry_event(event: dict[str, Any]) -> bool:
    return int((event.get("type") or {}).get("id", 0)) == CARRY_EVENT_TYPE_ID


def is_defensive_action_event(event: dict[str, Any]) -> bool:
    """Defansif sayılan event tipleri (PPDA için)."""
    type_id = int((event.get("type") or {}).get("id", 0))
    if type_id in (
        INTERCEPTION_EVENT_TYPE_ID, PRESSURE_EVENT_TYPE_ID,
        BLOCK_EVENT_TYPE_ID, CLEARANCE_EVENT_TYPE_ID,
        BALL_RECOVERY_EVENT_TYPE_ID,
    ):
        return True
    # Duel — sadece tackle (outcome.name=Won)
    if type_id == DUEL_EVENT_TYPE_ID:
        duel = event.get("duel") or {}
        outcome = (duel.get("outcome") or {}).get("name", "").lower()
        return outcome in ("won", "success")
    return False


def event_to_pass(
    event: dict[str, Any], *, match_id: int,
) -> PassEvent | None:
    """StatsBomb pass event → PassEvent. None döner parse fail'de."""
    if not is_pass_event(event):
        return None
    try:
        start = _normalize_xy(event.get("location"))
        if start is None:
            return None
        pass_block = event.get("pass") or {}
        end = _normalize_xy(pass_block.get("end_location"))
        if end is None:
            return None
        player = event.get("player") or {}
        team = event.get("team") or {}
        # outcome: yoksa completed; varsa "Incomplete"/"Out"/...
        outcome = pass_block.get("outcome") or {}
        completed = not bool(outcome.get("name"))

        pass_type_block = pass_block.get("type") or {}
        pass_type_id = int(pass_type_block.get("id", 0))
        pass_type = _PASS_TYPE_MAP.get(pass_type_id, "regular")

        # Cross/long_ball detection
        if pass_block.get("cross"):
            pass_type = "cross"
        elif pass_block.get("switch"):
            pass_type = "switch"
        elif pass_block.get("through_ball"):
            pass_type = "through_ball"
        elif pass_block.get("long_ball"):
            pass_type = "long_ball"

        # Technique (inswinger/outswinger)
        tech_block = pass_block.get("technique") or {}
        tech_name = str(tech_block.get("name", "")).lower().replace(" ", "")
        if "inswing" in tech_name:
            technique = "inswinger"
        elif "outswing" in tech_name:
            technique = "outswinger"
        elif "straight" in tech_name:
            technique = "straight"
        elif "through" in tech_name:
            technique = "through_ball"
        else:
            technique = "regular"

        period = int(event.get("period", 1))
        return PassEvent(
            sport=football.SPORT_NAME,
            match_external_id=int(match_id),
            player_external_id=int(player.get("id", 0)),
            team_external_id=int(team.get("id", 0)),
            minute=float(event.get("minute", 0)),
            period=period,
            start_x=round(start[0], 2),
            start_y=round(start[1], 2),
            end_x=round(end[0], 2),
            end_y=round(end[1], 2),
            pass_type=pass_type,  # type: ignore[arg-type]
            technique=technique,  # type: ignore[arg-type]
            completed=completed,
            key_pass=bool(pass_block.get("shot_assist")),
            assist=bool(pass_block.get("goal_assist")),
            possession_id=event.get("possession"),
        )
    except (KeyError, ValueError, TypeError) as e:
        log.warning("statsbomb pass parse fail: %s", e)
        return None


def event_to_carry(
    event: dict[str, Any], *, match_id: int,
) -> Carry | None:
    if not is_carry_event(event):
        return None
    try:
        start = _normalize_xy(event.get("location"))
        carry_block = event.get("carry") or {}
        end = _normalize_xy(carry_block.get("end_location"))
        if start is None or end is None:
            return None
        player = event.get("player") or {}
        team = event.get("team") or {}
        return Carry(
            sport=football.SPORT_NAME,
            match_external_id=int(match_id),
            player_external_id=int(player.get("id", 0)),
            team_external_id=int(team.get("id", 0)),
            minute=float(event.get("minute", 0)),
            period=int(event.get("period", 1)),
            start_x=round(start[0], 2),
            start_y=round(start[1], 2),
            end_x=round(end[0], 2),
            end_y=round(end[1], 2),
            possession_id=event.get("possession"),
        )
    except (KeyError, ValueError, TypeError) as e:
        log.warning("statsbomb carry parse fail: %s", e)
        return None


def event_to_defensive_action(
    event: dict[str, Any], *, match_id: int,
) -> DefensiveAction | None:
    if not is_defensive_action_event(event):
        return None
    try:
        loc = _normalize_xy(event.get("location"))
        if loc is None:
            return None
        player = event.get("player") or {}
        team = event.get("team") or {}
        type_id = int((event.get("type") or {}).get("id", 0))
        if type_id == INTERCEPTION_EVENT_TYPE_ID:
            action_type = "interception"
        elif type_id == PRESSURE_EVENT_TYPE_ID:
            action_type = "pressure"
        elif type_id == BLOCK_EVENT_TYPE_ID:
            action_type = "block"
        elif type_id == CLEARANCE_EVENT_TYPE_ID:
            action_type = "clearance"
        elif type_id == BALL_RECOVERY_EVENT_TYPE_ID:
            action_type = "ball_recovery"
        elif type_id == DUEL_EVENT_TYPE_ID:
            action_type = "tackle"
        else:
            return None
        # Successful: ball_recovery/tackle için outcome var, diğerleri default True
        successful = True
        return DefensiveAction(
            sport=football.SPORT_NAME,
            match_external_id=int(match_id),
            player_external_id=int(player.get("id", 0)),
            team_external_id=int(team.get("id", 0)),
            minute=float(event.get("minute", 0)),
            period=int(event.get("period", 1)),
            x=round(loc[0], 2),
            y=round(loc[1], 2),
            action_type=action_type,  # type: ignore[arg-type]
            successful=successful,
            possession_id=event.get("possession"),
        )
    except (KeyError, ValueError, TypeError) as e:
        log.warning("statsbomb defensive parse fail: %s", e)
        return None


def is_foul_event(event: dict[str, Any]) -> bool:
    """Foul Committed (type 22) veya Bad Behaviour (type 24, kart yiyen).

    Bad Behaviour pozisyon dışında kart (örn. yan hakem itirazına kırmızı);
    foul_pressure açısından kart sayımına dahil ama lokasyon yok.
    """
    type_id = int((event.get("type") or {}).get("id", 0))
    return type_id in (FOUL_COMMITTED_EVENT_TYPE_ID, BAD_BEHAVIOUR_EVENT_TYPE_ID)


def event_to_foul(
    event: dict[str, Any], *, match_id: int,
) -> FoulEvent | None:
    """Foul/Bad Behaviour event → FoulEvent. Lokasyon yoksa default (50,50)."""
    if not is_foul_event(event):
        return None
    try:
        type_id = int((event.get("type") or {}).get("id", 0))
        loc = _normalize_xy(event.get("location"))
        # Bad Behaviour'da location yok; default pitch ortası
        x, y = (loc if loc is not None else (50.0, 50.0))

        # Kart: foul_committed.card veya bad_behaviour.card
        card_color: str | None = None
        advantage = False
        if type_id == FOUL_COMMITTED_EVENT_TYPE_ID:
            fc = event.get("foul_committed") or {}
            card_block = fc.get("card") or {}
            card_id = int(card_block.get("id", 0))
            card_color = _CARD_MAP.get(card_id)
            advantage = bool(fc.get("advantage"))
        elif type_id == BAD_BEHAVIOUR_EVENT_TYPE_ID:
            bb = event.get("bad_behaviour") or {}
            card_block = bb.get("card") or {}
            card_id = int(card_block.get("id", 0))
            card_color = _CARD_MAP.get(card_id)

        player = event.get("player") or {}
        team = event.get("team") or {}
        pid = int(player.get("id", 0))
        tid = int(team.get("id", 0))
        # Bad Behaviour'da player/team eksik olabilir (taktik faul vb.)
        if pid == 0 or tid == 0:
            return None

        return FoulEvent(
            sport=football.SPORT_NAME,
            match_external_id=int(match_id),
            player_external_id=pid,
            team_external_id=tid,
            minute=float(event.get("minute", 0)),
            period=int(event.get("period", 1)),
            x=round(x, 2), y=round(y, 2),
            card=card_color,  # type: ignore[arg-type]
            advantage_played=advantage,
            possession_id=event.get("possession"),
        )
    except (KeyError, ValueError, TypeError) as e:
        log.warning("statsbomb foul parse fail: %s", e)
        return None


def parse_all_events(
    events_json: list[dict[str, Any]], *, match_id: int,
) -> dict[str, list]:
    """Bir maç'ın tüm event'lerini parse et — pass/carry/defansif/shot/foul ayrıştır.

    Caller (ingest pipeline) bu sözlüğü tüketir. Shot için
    `statsbomb_open.shots_from_events_json` zaten var.
    """
    from app.data.sources.statsbomb_open import shots_from_events_json

    passes: list[PassEvent] = []
    carries: list[Carry] = []
    defensive: list[DefensiveAction] = []
    fouls: list[FoulEvent] = []
    for ev in events_json:
        if is_pass_event(ev):
            p = event_to_pass(ev, match_id=match_id)
            if p is not None:
                passes.append(p)
        elif is_carry_event(ev):
            c = event_to_carry(ev, match_id=match_id)
            if c is not None:
                carries.append(c)
        elif is_defensive_action_event(ev):
            d = event_to_defensive_action(ev, match_id=match_id)
            if d is not None:
                defensive.append(d)
        elif is_foul_event(ev):
            f = event_to_foul(ev, match_id=match_id)
            if f is not None:
                fouls.append(f)
    shots = shots_from_events_json(events_json, match_id=match_id)
    return {
        "shots": shots,
        "passes": passes,
        "carries": carries,
        "defensive_actions": defensive,
        "fouls": fouls,
    }
