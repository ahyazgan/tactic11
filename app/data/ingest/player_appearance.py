"""Player appearance ingest — lineup + per-player stats → player_appearances.

Akış:
1. `get_fixture_lineups(fixture_id)` → LineupEntry listesi (kadro)
2. `get_fixture_player_stats(fixture_id)` → PlayerMatchStats (oynayanların metrikleri)
3. İki listeyi (lineup'ta ama oynamamış oyuncular için stats yok) player_external_id
   üzerinden birleştir
4. Upsert player_appearances: (sport, player_external_id, match_external_id, tenant_id)
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.data.sources.base import AppearanceSource
from app.db import models
from app.domain import LineupEntry, PlayerMatchStats
from app.sports import football

log = get_logger(__name__)


@dataclass(frozen=True)
class AppearanceIngestReport:
    match_external_id: int
    rows_inserted: int
    rows_updated: int
    players_in_lineup: int
    players_with_stats: int


def ingest_appearances_for_match(
    session: Session,
    source: AppearanceSource,
    *,
    match_external_id: int,
    tenant_id: str,
) -> AppearanceIngestReport:
    """Bir maç için lineup + stats ingest. Idempotent: aynı (match, player, tenant)
    update edilir."""
    match = session.execute(
        select(models.Match).where(
            models.Match.sport == football.SPORT_NAME,
            models.Match.external_id == int(match_external_id),
        )
    ).scalar_one_or_none()
    if match is None:
        raise ValueError(f"match {match_external_id} DB'de yok — önce sync_league")

    lineups = source.get_fixture_lineups(int(match_external_id))
    stats = source.get_fixture_player_stats(int(match_external_id))

    # Index stats by player_external_id
    stats_by_pid: dict[int, PlayerMatchStats] = {s.player_external_id: s for s in stats}
    lineups_by_pid: dict[int, LineupEntry] = {ent.player_external_id: ent for ent in lineups}
    all_pids = set(stats_by_pid) | set(lineups_by_pid)

    # Bir kez DB'den mevcut satırları çek
    existing_rows = session.execute(
        select(models.PlayerAppearance).where(
            models.PlayerAppearance.sport == football.SPORT_NAME,
            models.PlayerAppearance.match_external_id == int(match_external_id),
            models.PlayerAppearance.tenant_id == tenant_id,
        )
    ).scalars().all()
    existing_by_pid = {r.player_external_id: r for r in existing_rows}

    inserted = 0
    updated = 0
    for pid in all_pids:
        lin = lineups_by_pid.get(pid)
        st = stats_by_pid.get(pid)
        # Oynamadı (lineup'ta ama stats yok) → minutes=0; kadroya dahil olarak yine kaydet
        minutes = st.minutes if st else 0
        if st is not None:
            team_id: int | None = st.team_external_id
        elif lin is not None:
            team_id = lin.team_external_id
        else:
            team_id = None
        attrs = dict(
            minutes=minutes,
            kickoff=match.kickoff,
            tenant_id=tenant_id,
            team_external_id=team_id,
            rating_apifootball=st.rating if st else None,
            passes_total=st.passes_total if st else None,
            passes_accuracy=st.passes_accuracy if st else None,
            shots_total=st.shots_total if st else None,
            shots_on=st.shots_on if st else None,
            dribbles_attempts=st.dribbles_attempts if st else None,
            dribbles_success=st.dribbles_success if st else None,
            fouls_committed=st.fouls_committed if st else None,
            fouls_drawn=st.fouls_drawn if st else None,
            yellow_cards=st.yellow_cards if st else None,
            red_cards=st.red_cards if st else None,
            second_yellow=st.second_yellow if st else None,
            substituted_in_minute=st.substituted_in_minute if st else None,
            substituted_out_minute=st.substituted_out_minute if st else None,
            goals=st.goals if st else None,
            assists=st.assists if st else None,
            goals_conceded=st.goals_conceded if st else None,
            saves=st.saves if st else None,
            key_passes=st.key_passes if st else None,
            tackles_total=st.tackles_total if st else None,
            interceptions=st.interceptions if st else None,
            duels_total=st.duels_total if st else None,
            duels_won=st.duels_won if st else None,
            position_played=lin.position_code if lin else None,
            formation_played=lin.formation_played if lin else None,
            captain=lin.captain if lin else None,
        )
        if pid in existing_by_pid:
            row = existing_by_pid[pid]
            for k, v in attrs.items():
                setattr(row, k, v)
            updated += 1
        else:
            row = models.PlayerAppearance(
                sport=football.SPORT_NAME,
                player_external_id=pid,
                match_external_id=int(match_external_id),
                **attrs,
            )
            session.add(row)
            inserted += 1
    session.flush()
    report = AppearanceIngestReport(
        match_external_id=int(match_external_id),
        rows_inserted=inserted,
        rows_updated=updated,
        players_in_lineup=len(lineups_by_pid),
        players_with_stats=len(stats_by_pid),
    )
    log.info(
        "appearance ingest match=%d tenant=%s inserted=%d updated=%d lineup=%d stats=%d",
        report.match_external_id, tenant_id, report.rows_inserted, report.rows_updated,
        report.players_in_lineup, report.players_with_stats,
    )
    return report
