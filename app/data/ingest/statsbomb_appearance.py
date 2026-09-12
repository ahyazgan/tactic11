"""StatsBomb events JSON → player_appearances (ilk 11 + değişiklikler + mevki).

## Neden bu modül var

Canlı karar paneli değişiklik adaylarını event aktörlerinden türetiyordu; kimin
SAHADA olduğunu bilmiyordu. Koç zekâ karnesinde ölçüldü (294 gerçek
değişiklik): motorun aday listesindeki oyuncuların %26'sı hamle anında
sahada bile değildi. `player_appearances` tablosu (API-Football ingest'i
doldurur) StatsBomb maçları için boştu; bu modül aynı tabloyu açık veriden
doldurur ki panel her iki kaynakta da kadro-farkında çalışsın.

Yazılan alanlar: takım, giriş/çıkış dakikası, oynanan dakika, mevki kodu
(`position_played`: API-Football sözlüğüyle uyumlu GK/DC/MC/FC vb.). Sakatlık
ile çıkan da "çıktı"dır; sebep burada tutulmaz (`CoachMove.tactical` ayrı).

Idempotent: aynı (maç, oyuncu, tenant) satırı güncellenir.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data.sources.statsbomb_open import (
    appearances_from_events_json,
    lineup_positions_from_events_json,
    position_group,
)
from app.db import models
from app.sports import football

# Mevki grubu → position_played kodu (API-Football sözlüğü: ilk harf G/D/M/F).
_GROUP_CODE = {"GK": "GK", "DEF": "DC", "MID": "MC", "FWD": "FC"}
DEFAULT_MATCH_END = 90.0


@dataclass(frozen=True)
class StatsBombAppearanceReport:
    match_external_id: int
    rows_inserted: int
    rows_updated: int


def position_code_for(events_json: list[dict[str, Any]]) -> dict[int, str]:
    """Oyuncu → mevki kodu. Değişiklikle giren, çıkanın mevkisini devralır."""
    from app.data.sources.statsbomb_open import coach_moves_from_events_json

    pos = dict(lineup_positions_from_events_json(events_json))
    for mv in sorted(coach_moves_from_events_json(events_json), key=lambda m: m.minute):
        if (mv.kind == "substitution" and mv.player_on is not None
                and mv.player_off is not None and mv.player_on not in pos
                and mv.player_off in pos):
            pos[mv.player_on] = pos[mv.player_off]
    return {pid: _GROUP_CODE.get(position_group(p), "MC") for pid, p in pos.items()}


def ingest_statsbomb_appearances(
    session: Session, *, match_external_id: int, tenant_id: str,
    events_json: list[dict[str, Any]], match_end_minute: float | None = None,
) -> StatsBombAppearanceReport:
    match = session.execute(
        select(models.Match).where(
            models.Match.sport == football.SPORT_NAME,
            models.Match.external_id == int(match_external_id),
        )
    ).scalar_one_or_none()
    if match is None:
        raise ValueError(f"match {match_external_id} DB'de yok")

    end = match_end_minute if match_end_minute is not None else max(
        [DEFAULT_MATCH_END] + [float(ev.get("minute", 0)) for ev in events_json]
    )
    codes = position_code_for(events_json)
    existing = {
        r.player_external_id: r for r in session.execute(
            select(models.PlayerAppearance).where(
                models.PlayerAppearance.sport == football.SPORT_NAME,
                models.PlayerAppearance.match_external_id == int(match_external_id),
                models.PlayerAppearance.tenant_id == tenant_id,
            )
        ).scalars()
    }
    inserted = updated = 0
    for a in appearances_from_events_json(events_json):
        pid = int(a["player_external_id"])
        start = float(a["start_minute"])
        stop = a["end_minute"]
        attrs = dict(
            minutes=int(round(max(0.0, (end if stop is None else float(stop)) - start))),
            kickoff=match.kickoff,
            tenant_id=tenant_id,
            team_external_id=int(a["team_external_id"]),
            substituted_in_minute=None if start == 0.0 else int(round(start)),
            substituted_out_minute=None if stop is None else int(round(float(stop))),
            position_played=codes.get(pid),
        )
        row = existing.get(pid)
        if row is not None:
            for k, v in attrs.items():
                setattr(row, k, v)
            updated += 1
        else:
            session.add(models.PlayerAppearance(
                sport=football.SPORT_NAME, player_external_id=pid,
                match_external_id=int(match_external_id), **attrs,
            ))
            inserted += 1
    session.flush()
    return StatsBombAppearanceReport(int(match_external_id), inserted, updated)
