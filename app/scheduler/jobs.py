"""Kayıtlı iş tanımları.

Yeni iş ekleme: handler yaz + dosya sonunda `register(JobSpec(...))` çağır.
Bu modül `app.scheduler.__init__` tarafından otomatik import edilir, böylece
kayıt side effect'i tetiklenir.
"""

from __future__ import annotations

from app.core.logging import get_logger
from app.data.ingest import sync_league
from app.data.predictions import reconcile_pending_predictions
from app.data.sources.api_football import APIFootball
from app.db.session import SessionLocal
from app.scheduler.registry import JobSpec, register
from app.sports import football

log = get_logger(__name__)


def sync_league_handler(*, league_id: int, season: int, last: int = 10) -> None:
    """Bir lig + sezon için adapter'dan çek ve DB'ye yaz (CLI ile aynı yol)."""
    source = APIFootball()
    with SessionLocal() as session:
        report = sync_league(
            session,
            source,
            league_id=league_id,
            season=season,
            matches_per_team=last,
        )
    log.info(
        "job sync_league: leagues=%d teams=%d matches=%d snapshot=%d",
        report.leagues_written,
        report.teams_written,
        report.matches_written,
        report.snapshot_id,
    )


def reconcile_predictions_handler(*, sport: str = football.SPORT_NAME) -> None:
    """Bitmiş maçların actual sonucunu predictions tablosuna yaz."""
    with SessionLocal() as session:
        report = reconcile_pending_predictions(session, sport=sport)
        session.commit()
    log.info(
        "job reconcile_predictions: scanned=%d updated=%d match_not_finished=%d",
        report.scanned, report.updated, report.match_not_finished,
    )


register(
    JobSpec(
        name="sync_league",
        handler=sync_league_handler,
        description="Bir lig + sezon için adapter'dan veri çek, doğrula, DB'ye yaz, snapshot al.",
    )
)

register(
    JobSpec(
        name="reconcile_predictions",
        handler=reconcile_predictions_handler,
        description="Bitmiş maçların actual sonucunu predictions tablosuna yaz (kalibrasyon).",
    )
)
