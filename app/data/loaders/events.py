"""EventRow → domain model loader.

DB'deki ham EventRow satırlarını engine'lerin tükettiği domain modellere
(PassEvent, DefensiveAction, Carry, Shot) çevirir. Tenant filter zaten
session listener üzerinden uygulanıyor; caller `session.info["tenant_id"]`
ya da `set_current_tenant_id` set'lemiş olmalı.

Loader'lar 4 strateji:
- load_match_events(session, match_id) — tek maç
- load_team_events(session, team_id, last_n=10) — son N maç
- load_player_events(session, player_id, last_n=10) — oyuncu son N maç
- _rows_to_domain(rows) — düşük seviye dönüştürücü
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models
from app.domain import Carry, DefensiveAction, FoulEvent, PassEvent, Shot
from app.sports import football


@dataclass(frozen=True)
class LoadedEvents:
    """Engine'lerin ihtiyacı event tipi paketi."""
    passes: list[PassEvent]
    carries: list[Carry]
    defensive_actions: list[DefensiveAction]
    shots: list[Shot]
    match_ids: list[int]      # hangi maçlardan çekildiği (audit için)
    fouls: list[FoulEvent] = field(default_factory=list)  # type: ignore[assignment]

    @property
    def total(self) -> int:
        return (len(self.passes) + len(self.carries)
                + len(self.defensive_actions) + len(self.shots)
                + len(self.fouls))


def _row_to_pass(row: models.EventRow) -> PassEvent | None:
    try:
        return PassEvent(
            sport=row.sport, match_external_id=row.match_external_id,
            player_external_id=row.player_external_id or 0,
            team_external_id=row.team_external_id or 0,
            minute=row.minute, period=row.period,
            start_x=row.start_x or 0.0, start_y=row.start_y or 0.0,
            end_x=row.end_x or 0.0, end_y=row.end_y or 0.0,
            pass_type=row.pattern if row.pattern in {  # type: ignore[arg-type]
                "regular", "long_ball", "through_ball", "cross", "switch",
                "lay_off", "corner", "free_kick", "throw_in", "goal_kick",
            } else "regular",
            completed=(row.outcome == "completed"),
            key_pass=bool(row.key_pass),
            possession_id=row.possession_id,
        )
    except (ValueError, TypeError):
        return None


def _row_to_carry(row: models.EventRow) -> Carry | None:
    try:
        return Carry(
            sport=row.sport, match_external_id=row.match_external_id,
            player_external_id=row.player_external_id or 0,
            team_external_id=row.team_external_id or 0,
            minute=row.minute, period=row.period,
            start_x=row.start_x or 0.0, start_y=row.start_y or 0.0,
            end_x=row.end_x or 0.0, end_y=row.end_y or 0.0,
            possession_id=row.possession_id,
        )
    except (ValueError, TypeError):
        return None


def _row_to_def(row: models.EventRow) -> DefensiveAction | None:
    try:
        action_type = row.pattern if row.pattern in {
            "tackle", "interception", "block", "ball_recovery",
            "clearance", "pressure", "duel_won",
        } else "ball_recovery"
        return DefensiveAction(
            sport=row.sport, match_external_id=row.match_external_id,
            player_external_id=row.player_external_id or 0,
            team_external_id=row.team_external_id or 0,
            minute=row.minute, period=row.period,
            x=row.start_x or 0.0, y=row.start_y or 0.0,
            action_type=action_type,  # type: ignore[arg-type]
            successful=(row.outcome == "successful"),
            possession_id=row.possession_id,
        )
    except (ValueError, TypeError):
        return None


def _row_to_foul(row: models.EventRow) -> FoulEvent | None:
    """EventRow (event_type='foul') → FoulEvent."""
    try:
        card_color = (
            row.outcome
            if row.outcome in ("yellow", "second_yellow", "red")
            else None
        )
        return FoulEvent(
            sport=row.sport, match_external_id=row.match_external_id,
            player_external_id=row.player_external_id or 0,
            team_external_id=row.team_external_id or 0,
            minute=row.minute, period=row.period,
            x=row.start_x or 50.0, y=row.start_y or 50.0,
            card=card_color,  # type: ignore[arg-type]
            advantage_played=(row.pattern == "advantage"),
            possession_id=row.possession_id,
        )
    except (ValueError, TypeError):
        return None


def _row_to_shot(row: models.EventRow) -> Shot | None:
    try:
        body_part = row.body_part if row.body_part in {
            "head", "right_foot", "left_foot", "other",
        } else "right_foot"
        pattern = row.pattern if row.pattern in {
            "open_play", "set_piece", "penalty", "fast_break",
            "corner_kick", "free_kick",
        } else "open_play"
        return Shot(
            sport=row.sport, match_external_id=row.match_external_id,
            player_external_id=row.player_external_id or 0,
            minute=row.minute,
            x=row.start_x or 0.0, y=row.start_y or 0.0,
            body_part=body_part,  # type: ignore[arg-type]
            pattern=pattern,  # type: ignore[arg-type]
            is_goal=bool(row.is_goal),
            team_external_id=row.team_external_id,
        )
    except (ValueError, TypeError):
        return None


def rows_to_domain(rows: Iterable[models.EventRow]) -> LoadedEvents:
    """EventRow listesini domain listelere böl."""
    passes: list[PassEvent] = []
    carries: list[Carry] = []
    defs: list[DefensiveAction] = []
    shots: list[Shot] = []
    fouls: list[FoulEvent] = []
    match_ids: set[int] = set()

    for r in rows:
        match_ids.add(r.match_external_id)
        if r.event_type == "pass":
            p = _row_to_pass(r)
            if p:
                passes.append(p)
        elif r.event_type == "carry":
            c = _row_to_carry(r)
            if c:
                carries.append(c)
        elif r.event_type == "defensive_action":
            d = _row_to_def(r)
            if d:
                defs.append(d)
        elif r.event_type == "shot":
            s = _row_to_shot(r)
            if s:
                shots.append(s)
        elif r.event_type == "foul":
            f = _row_to_foul(r)
            if f:
                fouls.append(f)
    return LoadedEvents(
        passes=passes, carries=carries,
        defensive_actions=defs, shots=shots,
        match_ids=sorted(match_ids), fouls=fouls,
    )


def load_match_events(session: Session, match_external_id: int) -> LoadedEvents:
    """Bir maçın tüm event'lerini engine-hazır domain modellere yükle."""
    rows = session.execute(
        select(models.EventRow).where(
            models.EventRow.sport == football.SPORT_NAME,
            models.EventRow.match_external_id == match_external_id,
        )
    ).scalars().all()
    return rows_to_domain(rows)


def load_team_events(
    session: Session, team_external_id: int, *, last_n: int = 10,
) -> LoadedEvents:
    """Bir takımın son N maçındaki event'leri yükle.

    Son N: matches tablosundan en yeni N maçı al; sonra events join.
    """
    match_rows = session.execute(
        select(models.Match.external_id).where(
            models.Match.sport == football.SPORT_NAME,
            (models.Match.home_team_external_id == team_external_id)
            | (models.Match.away_team_external_id == team_external_id),
            models.Match.status.in_(football.FINISHED_STATUSES),
        ).order_by(models.Match.kickoff.desc()).limit(last_n)
    ).scalars().all()
    if not match_rows:
        return LoadedEvents([], [], [], [], [], [])

    event_rows = session.execute(
        select(models.EventRow).where(
            models.EventRow.sport == football.SPORT_NAME,
            models.EventRow.match_external_id.in_(match_rows),
        )
    ).scalars().all()
    return rows_to_domain(event_rows)


def load_player_events(
    session: Session, player_external_id: int, *, last_n: int = 10,
) -> tuple[LoadedEvents, dict[str, Any]]:
    """Oyuncunun son N maçındaki event'leri + meta (team_id, minutes_played).

    Meta'da: takım, oyunduğu dakika (PlayerAppearance'tan).
    """
    # En son maçları PlayerAppearance üstünden bul
    appearances = session.execute(
        select(models.PlayerAppearance).where(
            models.PlayerAppearance.sport == football.SPORT_NAME,
            models.PlayerAppearance.player_external_id == player_external_id,
        ).order_by(models.PlayerAppearance.match_external_id.desc()).limit(last_n)
    ).scalars().all()

    match_ids = [a.match_external_id for a in appearances]
    total_minutes = float(sum(a.minutes or 0 for a in appearances))
    team_id = appearances[0].team_external_id if appearances else None

    if not match_ids:
        return LoadedEvents([], [], [], [], [], []), {
            "team_external_id": team_id, "minutes_played": 0.0,
            "matches_analyzed": 0,
        }

    event_rows = session.execute(
        select(models.EventRow).where(
            models.EventRow.sport == football.SPORT_NAME,
            models.EventRow.match_external_id.in_(match_ids),
        )
    ).scalars().all()
    return rows_to_domain(event_rows), {
        "team_external_id": team_id,
        "minutes_played": total_minutes,
        "matches_analyzed": len(match_ids),
    }


def shots_by_team(shots, team_external_id: int) -> list:
    """Şutları team_external_id'ye göre filtrele.

    Eski ingest'lenen veya Shot domain'de team_id None ise: o şutu DAHİL et
    (backward compat — eski test'ler kırılmasın). Yeni ingest sonrası tüm
    şutlarda team_id var; filter doğru çalışır.

    Bu fix `engine.match_dominance` ve `engine.transition`'ın
    NO_SIGNAL bug'ını kapatır (full_season_audit findings).
    """
    return [
        s for s in shots
        if s.team_external_id is None or s.team_external_id == team_external_id
    ]
