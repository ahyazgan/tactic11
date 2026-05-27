"""Oyuncu yük/rotasyon analizi.

Bir pencere içindeki dakika toplamı + maç sıklığı. Veri girişi
`PlayerAppearance` listesi; ingest henüz doldurmuyor (lineup adapter Faz 6'da
gelecek). Engine yine de bugün saf hâlde çalışıyor ve test ediliyor.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone

from app.audit import AuditRecord, EngineResult
from app.domain import PlayerAppearance
from app.sports import football

ENGINE_NAME = "engine.load"
ENGINE_VERSION = "1"

HIGH_LOAD_MINUTES_PER_WEEK = 270  # ~3 maçlık yük


@dataclass(frozen=True)
class PlayerLoad:
    matches_in_window: int
    minutes_in_window: int
    minutes_per_match: float
    minutes_per_week: float
    high_load: bool


def compute_player_load(
    player_external_id: int,
    appearances: Iterable[PlayerAppearance],
    *,
    window_days: int = 14,
    now: datetime | None = None,
) -> EngineResult[PlayerLoad]:
    if window_days <= 0:
        raise ValueError("window_days > 0 olmalı")

    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=window_days)
    window = [
        a
        for a in appearances
        if a.sport == football.SPORT_NAME
        and a.player_external_id == player_external_id
        and a.kickoff >= cutoff
    ]

    minutes_total = sum(a.minutes for a in window)
    matches = len(window)
    minutes_per_match = round(minutes_total / matches, 2) if matches else 0.0
    minutes_per_week = round(minutes_total / window_days * 7, 2)
    high_load = minutes_per_week >= HIGH_LOAD_MINUTES_PER_WEEK

    load = PlayerLoad(
        matches_in_window=matches,
        minutes_in_window=minutes_total,
        minutes_per_match=minutes_per_match,
        minutes_per_week=minutes_per_week,
        high_load=high_load,
    )

    audit = AuditRecord(
        engine=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        subject_type="player",
        subject_id=player_external_id,
        metric="player_load",
        value=asdict(load),
        inputs={
            "window_days": window_days,
            "considered_match_ids": [a.match_external_id for a in window],
            "high_load_threshold_minutes_per_week": HIGH_LOAD_MINUTES_PER_WEEK,
        },
        formula="sum(minutes in last window_days); per_week = sum/window_days*7",
    )
    return EngineResult(value=load, audit=audit)
