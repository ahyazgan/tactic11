"""Bitmiş maçların gerçek sonuçlarını predictions tablosuna yazma.

Pre-game predictions saklanmıştı (`save_prediction`); maç bitince actual_*
alanları doldurulmalı ki PR B3 accuracy report bunları okuyabilsin.

Idempotent: zaten reconciled satırlara dokunulmaz (reconciled_at != NULL
filter). Bilinmeyen / hâlâ NS olan match'ler atlanır, raporda sayılır.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db import models
from app.sports import football

log = get_logger(__name__)


@dataclass(frozen=True)
class ReconcileReport:
    scanned: int  # actual_outcome NULL satır sayısı
    updated: int  # bu çağrıda doldurulan satır
    match_not_found: int  # tahmin var ama match satırı yok (defansif)
    match_not_finished: int  # match var ama henüz FT değil


def _outcome(home_score: int, away_score: int) -> str:
    if home_score > away_score:
        return "home"
    if home_score < away_score:
        return "away"
    return "draw"


def reconcile_pending_predictions(
    session: Session, *, sport: str = football.SPORT_NAME
) -> ReconcileReport:
    """`actual_outcome IS NULL` olan tahminleri tara, FT olanları doldur."""
    pending = list(
        session.execute(
            select(models.Prediction).where(
                models.Prediction.sport == sport,
                models.Prediction.actual_outcome.is_(None),
            )
        ).scalars()
    )

    updated = 0
    not_found = 0
    not_finished = 0
    now = datetime.now(UTC)

    for pred in pending:
        match = session.execute(
            select(models.Match).where(
                models.Match.sport == sport,
                models.Match.external_id == pred.match_external_id,
            )
        ).scalar_one_or_none()
        if match is None:
            not_found += 1
            continue
        if match.status not in football.FINISHED_STATUSES:
            not_finished += 1
            continue
        if match.home_score is None or match.away_score is None:
            # FT statüsünde ama skor None — veri tutarsızlığı; defansif log
            log.warning(
                "match %d FT statüde ama skor None; reconcile atlandı",
                match.external_id,
            )
            not_finished += 1
            continue

        pred.actual_home_score = match.home_score
        pred.actual_away_score = match.away_score
        pred.actual_outcome = _outcome(match.home_score, match.away_score)
        pred.reconciled_at = now
        updated += 1

    session.flush()
    return ReconcileReport(
        scanned=len(pending),
        updated=updated,
        match_not_found=not_found,
        match_not_finished=not_finished,
    )
