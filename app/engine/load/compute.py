"""Oyuncu yük/rotasyon analizi.

Bir pencere içindeki dakika toplamı + maç sıklığı. Veri girişi
`PlayerAppearance` listesi (api_football lineup adapter besler).

Eşik (`HIGH_LOAD_MINUTES_PER_WEEK`) artık caller tarafından override
edilebilir; default `DEFAULT_HIGH_LOAD_MINUTES_PER_WEEK` sabiti
`app/sports/football.py`'da yaşar. Lig/pozisyon/yaş bazlı override
üst katmana (endpoint/agent) bırakılmıştır.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta

from app.audit import AuditRecord, EngineResult
from app.engine._protocols import PlayerAppearanceLike
from app.sports import football

# Backward-compatible re-export: `from app.engine.load.compute import
# HIGH_LOAD_MINUTES_PER_WEEK` çağrılarının kırılmaması için. Yeni kod
# `football.DEFAULT_HIGH_LOAD_MINUTES_PER_WEEK` ya da `compute_player_load`
# `threshold_minutes_per_week` keyword arg'ını kullanmalı.
from app.sports.football import (
    DEFAULT_HIGH_LOAD_MINUTES_PER_WEEK as HIGH_LOAD_MINUTES_PER_WEEK,
)

ENGINE_NAME = "engine.load"
# v2 davranışı korunur (pure-additive opt-in keyword arg; default
# threshold_minutes_per_week=None ile bit-için-bit eski sonuç). Version
# bump gerekmez.
ENGINE_VERSION = "2"

# Sakatlık risk eşikleri — heuristic (ML yerine):
# Gerçek ML 2+ sezon load data ister; bu eşikler literatür (Gabbett 2016
# acute:chronic workload) ve futbol kondisyon ekiplerinin standart pratiği:
#   - low:    <180 dk/hafta
#   - medium: 180-270 dk/hafta
#   - high:   ≥270 dk/hafta (HIGH_LOAD_MINUTES_PER_WEEK)
#   - extreme: ≥360 dk/hafta VEYA 5 günde 3+ maç back-to-back
RISK_THRESHOLDS_MIN_PER_WEEK = {"medium": 180, "high": 270, "extreme": 360}
BACK_TO_BACK_DAYS = 5  # 5 günde ≥3 maç → extreme bayrağı


@dataclass(frozen=True)
class PlayerLoad:
    matches_in_window: int
    minutes_in_window: int
    minutes_per_match: float
    minutes_per_week: float
    high_load: bool
    risk_level: str  # "low" | "medium" | "high" | "extreme"
    back_to_back_count: int  # 5-günlük en yoğun pencerede maç sayısı


def _max_window_match_count(kickoffs: list[datetime], window_days: int) -> int:
    """Sliding window: bir oyuncunun ardışık `window_days` günde max maç sayısı."""
    if len(kickoffs) <= 1:
        return len(kickoffs)
    sorted_ks = sorted(kickoffs)
    window_seconds = window_days * 86400
    max_count = 1
    left = 0
    for right in range(len(sorted_ks)):
        while (sorted_ks[right] - sorted_ks[left]).total_seconds() > window_seconds:
            left += 1
        max_count = max(max_count, right - left + 1)
    return max_count


def _classify_risk(minutes_per_week: float, back_to_back: int) -> str:
    if back_to_back >= 3:
        return "extreme"
    if minutes_per_week >= RISK_THRESHOLDS_MIN_PER_WEEK["extreme"]:
        return "extreme"
    if minutes_per_week >= RISK_THRESHOLDS_MIN_PER_WEEK["high"]:
        return "high"
    if minutes_per_week >= RISK_THRESHOLDS_MIN_PER_WEEK["medium"]:
        return "medium"
    return "low"


def compute_player_load(
    player_external_id: int,
    appearances: Iterable[PlayerAppearanceLike],
    *,
    window_days: int = 14,
    now: datetime | None = None,
    threshold_minutes_per_week: int | None = None,
) -> EngineResult[PlayerLoad]:
    """Oyuncunun pencere içi yük raporu.

    `threshold_minutes_per_week` verilmezse `football.DEFAULT_HIGH_LOAD_
    MINUTES_PER_WEEK` (270) kullanılır. Caller (endpoint/agent) lig veya
    pozisyon bazlı override yapabilir.
    """
    if window_days <= 0:
        raise ValueError("window_days > 0 olmalı")

    effective_threshold = (
        threshold_minutes_per_week
        if threshold_minutes_per_week is not None
        else HIGH_LOAD_MINUTES_PER_WEEK
    )

    cutoff = (now or datetime.now(UTC)) - timedelta(days=window_days)
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
    high_load = minutes_per_week >= effective_threshold
    back_to_back = _max_window_match_count(
        [a.kickoff for a in window], BACK_TO_BACK_DAYS,
    )
    risk_level = _classify_risk(minutes_per_week, back_to_back)

    load = PlayerLoad(
        matches_in_window=matches,
        minutes_in_window=minutes_total,
        minutes_per_match=minutes_per_match,
        minutes_per_week=minutes_per_week,
        high_load=high_load,
        risk_level=risk_level,
        back_to_back_count=back_to_back,
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
            "high_load_threshold_minutes_per_week": effective_threshold,
            "default_threshold_minutes_per_week": HIGH_LOAD_MINUTES_PER_WEEK,
            "threshold_overridden": threshold_minutes_per_week is not None,
            "risk_thresholds_min_per_week": RISK_THRESHOLDS_MIN_PER_WEEK,
            "back_to_back_window_days": BACK_TO_BACK_DAYS,
        },
        formula=(
            "minutes/week + 5-günde sliding window maç sayısı; risk_level: "
            "extreme(>=360 ya da ≥3 maç/5g) > high(>=270) > medium(>=180) > low"
        ),
    )
    return EngineResult(value=load, audit=audit)
