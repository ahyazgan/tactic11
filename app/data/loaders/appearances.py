"""player_appearances → engine `live_lineup.PlayerAppearance` (kadro farkındalığı).

Replay akışı (Faz B) ve canlı karar paneli aynı yükleyiciyi kullanır: kimin
sahada olduğu tek yerden gelsin. Yalnız gerçekten oynamış satırlar alınır
(minutes>0 ya da sonradan girmiş); kadroda olup oynamayan hariç.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models
from app.engine.live_lineup import PlayerAppearance
from app.sports import football


def load_match_appearances(session: Session, match_external_id: int) -> list[PlayerAppearance]:
    rows = session.execute(
        select(models.PlayerAppearance).where(
            models.PlayerAppearance.sport == football.SPORT_NAME,
            models.PlayerAppearance.match_external_id == match_external_id,
        )
    ).scalars().all()
    out: list[PlayerAppearance] = []
    for r in rows:
        played = bool(r.minutes and r.minutes > 0)
        came_on = r.substituted_in_minute is not None
        if not (played or came_on) or r.team_external_id is None:
            continue
        out.append(PlayerAppearance(
            player_external_id=r.player_external_id,
            team_external_id=r.team_external_id,
            start_minute=float(r.substituted_in_minute or 0),
            end_minute=(
                float(r.substituted_out_minute)
                if r.substituted_out_minute is not None else None
            ),
            position=r.position_played,
        ))
    return out
