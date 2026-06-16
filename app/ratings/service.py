"""Player match rating persistence — "Maçı Notla" servisi.

Manuel 1-10 oyuncu notlarını kaydeder ve performans motorlarına seri olarak
döndürür. Pure DB katmanı; engine çağrısı yok (onu endpoint/agent yapar).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models
from app.sports import football


@dataclass(frozen=True)
class RatingInput:
    player_external_id: int
    rating: float
    minute_played: float = 90.0
    opp_rating: float | None = None
    fatigue_proxy: float | None = None
    flags: dict[str, bool] | None = None
    note: str | None = None


def save_match_ratings(
    session: Session,
    *,
    match_external_id: int,
    ratings: list[RatingInput],
    kickoff: datetime | None = None,
    by_user_id: str | None = None,
    sport: str = football.SPORT_NAME,
) -> dict[str, int]:
    """Bir maçın oyuncu notlarını idempotent kaydet (upsert).

    Aynı (tenant, sport, match, player) varsa günceller, yoksa ekler.
    Dönüş: {created, updated}.
    """
    now = datetime.now(UTC)
    created = 0
    updated = 0
    for r in ratings:
        existing = session.execute(
            select(models.PlayerMatchRating).where(
                models.PlayerMatchRating.sport == sport,
                models.PlayerMatchRating.match_external_id == match_external_id,
                models.PlayerMatchRating.player_external_id == r.player_external_id,
            )
        ).scalar_one_or_none()
        flags_json = json.dumps(r.flags) if r.flags else None
        if existing is not None:
            existing.rating = r.rating
            existing.minute_played = r.minute_played
            existing.opp_rating = r.opp_rating
            existing.fatigue_proxy = r.fatigue_proxy
            existing.flags_json = flags_json
            existing.note = r.note
            existing.kickoff = kickoff or existing.kickoff
            existing.updated_at = now
            updated += 1
        else:
            session.add(models.PlayerMatchRating(
                sport=sport,
                match_external_id=match_external_id,
                player_external_id=r.player_external_id,
                kickoff=kickoff,
                rating=r.rating,
                minute_played=r.minute_played,
                opp_rating=r.opp_rating,
                fatigue_proxy=r.fatigue_proxy,
                flags_json=flags_json,
                note=r.note,
                by_user_id=by_user_id,
                created_at=now,
                updated_at=now,
            ))
            created += 1
    session.flush()
    return {"created": created, "updated": updated}


def list_player_ratings(
    session: Session,
    *,
    player_external_id: int,
    sport: str = football.SPORT_NAME,
) -> list[models.PlayerMatchRating]:
    """Bir oyuncunun tüm notları — kronolojik (kickoff, sonra match_id)."""
    rows = list(session.execute(
        select(models.PlayerMatchRating).where(
            models.PlayerMatchRating.sport == sport,
            models.PlayerMatchRating.player_external_id == player_external_id,
        )
    ).scalars())
    rows.sort(key=lambda r: (
        r.kickoff or datetime.min.replace(tzinfo=UTC),
        r.match_external_id,
    ))
    return rows


def list_match_ratings(
    session: Session,
    *,
    match_external_id: int,
    sport: str = football.SPORT_NAME,
) -> list[models.PlayerMatchRating]:
    """Bir maçın tüm oyuncu notları."""
    return list(session.execute(
        select(models.PlayerMatchRating).where(
            models.PlayerMatchRating.sport == sport,
            models.PlayerMatchRating.match_external_id == match_external_id,
        ).order_by(models.PlayerMatchRating.player_external_id)
    ).scalars())


def rating_to_dict(r: models.PlayerMatchRating) -> dict[str, Any]:
    return {
        "id": r.id,
        "match_external_id": r.match_external_id,
        "player_external_id": r.player_external_id,
        "kickoff": r.kickoff.isoformat() if r.kickoff else None,
        "rating": r.rating,
        "minute_played": r.minute_played,
        "opp_rating": r.opp_rating,
        "fatigue_proxy": r.fatigue_proxy,
        "flags": json.loads(r.flags_json) if r.flags_json else {},
        "note": r.note,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }
