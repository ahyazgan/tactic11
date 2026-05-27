"""Fikstür yoğunluğu analizi — önümüzdeki maçlar.

Saf fonksiyon: girdi `Iterable[MatchLike]` + bir `now` referansı, çıktı
`EngineResult[ScheduleReport]`. Engine kuralı geçerli: DB/HTTP/LLM yok.

Rotasyon/yük kararının ilk somut sinyali: 1-2 hafta içinde 3+ maç var mı,
ilk maça kaç gün var, hangi tarihlerde oynanacak.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta

from app.audit import AuditRecord, EngineResult
from app.engine._protocols import MatchLike
from app.sports import football

ENGINE_NAME = "engine.schedule"
ENGINE_VERSION = "1"

# Yoğun fikstür eşiği — 1 hafta içinde 3+ maç ya da 14 günde 5+ maç.
_DENSE_WEEK_THRESHOLD = 3
_DENSE_FORTNIGHT_THRESHOLD = 5


@dataclass(frozen=True)
class ScheduleReport:
    upcoming_count: int
    matches_next_7d: int
    matches_next_14d: int
    days_until_next_match: float | None  # None = önümüzde maç yok
    next_kickoffs: list[str]  # ISO; en yakın → uzak
    dense_schedule: bool  # True ise yorgunluk riski not edilmeli


def _is_upcoming(m: MatchLike, now: datetime) -> bool:
    """Henüz oynanmamış maç: kickoff geleceğe ait VE durum 'finished' değil."""
    if m.kickoff <= now:
        return False
    return m.status not in football.FINISHED_STATUSES


def compute_schedule(
    team_external_id: int,
    matches: Iterable[MatchLike],
    *,
    now: datetime | None = None,
    horizon_days: int = 30,
) -> EngineResult[ScheduleReport]:
    """Bir takımın önümüzdeki maç yoğunluğu.

    `horizon_days`: bu kadar gün ileriye bak; daha sonrası "ufuk dışı".
    """
    if horizon_days <= 0:
        raise ValueError("horizon_days > 0 olmalı")

    ref_now = now or datetime.now(UTC)
    horizon = ref_now + timedelta(days=horizon_days)

    upcoming = [
        m
        for m in matches
        if _is_upcoming(m, ref_now)
        and m.kickoff <= horizon
        and team_external_id
        in (m.home_team_external_id, m.away_team_external_id)
    ]
    upcoming.sort(key=lambda m: m.kickoff)

    week_cutoff = ref_now + timedelta(days=7)
    fortnight_cutoff = ref_now + timedelta(days=14)
    matches_7d = sum(1 for m in upcoming if m.kickoff <= week_cutoff)
    matches_14d = sum(1 for m in upcoming if m.kickoff <= fortnight_cutoff)

    days_until_next: float | None = None
    if upcoming:
        delta = upcoming[0].kickoff - ref_now
        days_until_next = round(delta.total_seconds() / 86400, 2)

    dense = (
        matches_7d >= _DENSE_WEEK_THRESHOLD
        or matches_14d >= _DENSE_FORTNIGHT_THRESHOLD
    )

    report = ScheduleReport(
        upcoming_count=len(upcoming),
        matches_next_7d=matches_7d,
        matches_next_14d=matches_14d,
        days_until_next_match=days_until_next,
        next_kickoffs=[m.kickoff.isoformat() for m in upcoming],
        dense_schedule=dense,
    )

    audit = AuditRecord(
        engine=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        subject_type="team",
        subject_id=team_external_id,
        metric="schedule_report",
        value=asdict(report),
        inputs={
            "horizon_days": horizon_days,
            "now_iso": ref_now.isoformat(),
            "considered_match_ids": [m.external_id for m in upcoming],
        },
        formula=(
            f"upcoming = future NS matches in next {horizon_days} days; "
            f"dense = >={_DENSE_WEEK_THRESHOLD} maç/7g veya "
            f">={_DENSE_FORTNIGHT_THRESHOLD} maç/14g"
        ),
    )
    return EngineResult(value=report, audit=audit)
