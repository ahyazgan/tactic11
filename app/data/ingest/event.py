"""Event ingest pipeline — StatsBomb event'lerini DB'ye yaz.

Akış:
1. StatsBomb adapter'dan bir maçın tüm event'lerini çek (raw JSON)
2. Her event için tipe göre dispatch → Shot/Pass/Carry/DefensiveAction parse
3. EventRow oluştur + session.add
4. Idempotent: (tenant_id, sport, source, source_event_id) unique key

Kullanım:
    with SessionLocal() as s:
        s.info["tenant_id"] = "t-konya"
        report = ingest_events_for_match(
            s, source=StatsBombOpen(), match_external_id=3754066,
            tenant_id="t-konya",
        )
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.data.sources.statsbomb_event_parser import (
    event_to_carry,
    event_to_defensive_action,
    event_to_pass,
    is_carry_event,
    is_defensive_action_event,
    is_pass_event,
)
from app.data.sources.statsbomb_open import (
    StatsBombOpen,
    _event_to_shot,
    _is_shot_event,
)
from app.db import models
from app.sports import football

log = get_logger(__name__)


@dataclass(frozen=True)
class EventIngestReport:
    match_external_id: int
    tenant_id: str
    rows_inserted: int
    rows_skipped: int  # idempotent skip (zaten varsa)
    shots: int
    passes: int
    carries: int
    defensive_actions: int


def _shot_to_row(shot, tenant_id: str, source_event_id: str | None,
                 now: datetime) -> models.EventRow:
    return models.EventRow(
        sport=football.SPORT_NAME, tenant_id=tenant_id,
        source="statsbomb_open", source_event_id=source_event_id,
        match_external_id=shot.match_external_id,
        team_external_id=getattr(shot, "team_external_id", None),
        player_external_id=shot.player_external_id,
        event_type="shot",
        minute=shot.minute, period=1,
        start_x=shot.x, start_y=shot.y,
        end_x=None, end_y=None,
        outcome="goal" if shot.is_goal else None,
        body_part=shot.body_part, pattern=shot.pattern,
        possession_id=None,
        is_goal=shot.is_goal, key_pass=None,
        raw_json=None,
        created_at=now,
    )


def _pass_to_row(p, tenant_id: str, source_event_id: str | None,
                 now: datetime) -> models.EventRow:
    return models.EventRow(
        sport=football.SPORT_NAME, tenant_id=tenant_id,
        source="statsbomb_open", source_event_id=source_event_id,
        match_external_id=p.match_external_id,
        team_external_id=p.team_external_id,
        player_external_id=p.player_external_id,
        event_type="pass",
        minute=p.minute, period=p.period,
        start_x=p.start_x, start_y=p.start_y,
        end_x=p.end_x, end_y=p.end_y,
        outcome="completed" if p.completed else "incomplete",
        body_part=None, pattern=p.pass_type,
        possession_id=p.possession_id,
        is_goal=None, key_pass=p.key_pass,
        raw_json=None,
        created_at=now,
    )


def _carry_to_row(c, tenant_id: str, source_event_id: str | None,
                  now: datetime) -> models.EventRow:
    return models.EventRow(
        sport=football.SPORT_NAME, tenant_id=tenant_id,
        source="statsbomb_open", source_event_id=source_event_id,
        match_external_id=c.match_external_id,
        team_external_id=c.team_external_id,
        player_external_id=c.player_external_id,
        event_type="carry",
        minute=c.minute, period=c.period,
        start_x=c.start_x, start_y=c.start_y,
        end_x=c.end_x, end_y=c.end_y,
        outcome=None, body_part=None, pattern=None,
        possession_id=c.possession_id,
        is_goal=None, key_pass=None,
        raw_json=None,
        created_at=now,
    )


def _def_to_row(d, tenant_id: str, source_event_id: str | None,
                now: datetime) -> models.EventRow:
    return models.EventRow(
        sport=football.SPORT_NAME, tenant_id=tenant_id,
        source="statsbomb_open", source_event_id=source_event_id,
        match_external_id=d.match_external_id,
        team_external_id=d.team_external_id,
        player_external_id=d.player_external_id,
        event_type="defensive_action",
        minute=d.minute, period=d.period,
        start_x=d.x, start_y=d.y,
        end_x=None, end_y=None,
        outcome="successful" if d.successful else "unsuccessful",
        body_part=None, pattern=d.action_type,
        possession_id=d.possession_id,
        is_goal=None, key_pass=None,
        raw_json=None,
        created_at=now,
    )


def _dispatch(
    ev: dict[str, Any], match_external_id: int, tenant_id: str,
    source_event_id: str | None, now: datetime,
) -> tuple[str, models.EventRow] | None:
    """Tek event'i tipine göre parse + EventRow'a çevir. None → relevant değil."""
    if _is_shot_event(ev):
        shot = _event_to_shot(ev, match_id=match_external_id)
        if shot is None:
            return None
        return "shot", _shot_to_row(shot, tenant_id, source_event_id, now)
    if is_pass_event(ev):
        p = event_to_pass(ev, match_id=match_external_id)
        if p is None:
            return None
        return "pass", _pass_to_row(p, tenant_id, source_event_id, now)
    if is_carry_event(ev):
        c = event_to_carry(ev, match_id=match_external_id)
        if c is None:
            return None
        return "carry", _carry_to_row(c, tenant_id, source_event_id, now)
    if is_defensive_action_event(ev):
        d = event_to_defensive_action(ev, match_id=match_external_id)
        if d is None:
            return None
        return "defensive_action", _def_to_row(d, tenant_id, source_event_id, now)
    return None


def ingest_events_for_match(
    session: Session,
    source: StatsBombOpen,
    *,
    match_external_id: int,
    tenant_id: str,
) -> EventIngestReport:
    """Bir maç için StatsBomb event'lerini çek + parse + DB'ye yaz.

    Idempotent: aynı (tenant_id, sport, source, source_event_id) varsa skip.
    """
    events_json = source.get_events(match_external_id)

    # Pre-check: mevcut source_event_id'leri tek query'de çek
    existing_ids = set(
        session.execute(
            select(models.EventRow.source_event_id).where(
                models.EventRow.sport == football.SPORT_NAME,
                models.EventRow.tenant_id == tenant_id,
                models.EventRow.match_external_id == match_external_id,
                models.EventRow.source == "statsbomb_open",
            )
        ).scalars()
    )

    counts = {"shot": 0, "pass": 0, "carry": 0, "defensive_action": 0}
    inserted = 0
    skipped = 0
    now = datetime.now(UTC)

    for ev in events_json:
        evid = str(ev.get("id", "")) or None
        result = _dispatch(ev, match_external_id, tenant_id, evid, now)
        if result is None:
            continue
        ev_type, row = result
        counts[ev_type] += 1
        if evid and evid in existing_ids:
            skipped += 1
            continue
        session.add(row)
        if evid:
            existing_ids.add(evid)  # aynı batch'te tekrar gelirse skip
        inserted += 1

    session.flush()
    report = EventIngestReport(
        match_external_id=match_external_id,
        tenant_id=tenant_id,
        rows_inserted=inserted,
        rows_skipped=skipped,
        shots=counts["shot"],
        passes=counts["pass"],
        carries=counts["carry"],
        defensive_actions=counts["defensive_action"],
    )
    log.info(
        "event ingest match=%d tenant=%s inserted=%d skipped=%d "
        "(shots=%d passes=%d carries=%d def=%d)",
        match_external_id, tenant_id, inserted, skipped,
        report.shots, report.passes, report.carries, report.defensive_actions,
    )
    return report
