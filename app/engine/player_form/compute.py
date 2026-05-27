"""Per-player form raporu — Z-score baseline'la kıyas.

Şu an PlayerAppearance sadece `minutes` taşıyor (tam stat vektörü için lineup
adapter lazım: pas/şut/pres v.b.). Bu engine elimizdeki minimal veri üstünden:

- Son N maçta toplam dakika + maç başına ortalama
- Career baseline ile karşılaştırma (Z-score: (recent_avg - career_avg) / career_std)
- Trend yönü: "yükselen", "sabit", "düşen" — basit linear regression slope sign

Veri akışı zenginleştikçe (key_passes, shot_accuracy v.b.) bu engine'in
sözleşmesi aynı kalır; sadece `PlayerFormSnapshot` alanları eklenir.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from statistics import mean, stdev

from app.audit import AuditRecord, EngineResult
from app.engine._protocols import PlayerAppearanceLike
from app.sports import football

ENGINE_NAME = "engine.player_form"
ENGINE_VERSION = "1"

TREND_THRESHOLD = 5.0  # dk/maç farkı bu eşiği aşarsa "yükselen/düşen"


@dataclass(frozen=True)
class PlayerFormSnapshot:
    player_external_id: int
    recent_matches: int
    recent_minutes_per_match: float
    baseline_matches: int
    baseline_minutes_per_match: float
    baseline_minutes_stdev: float
    z_score: float | None  # None: yetersiz baseline veri
    trend: str  # "rising" | "stable" | "declining" | "unknown"
    last_match_minutes: int | None


def _split_recent_baseline(
    appearances: list[PlayerAppearanceLike],
    *,
    recent_n: int,
) -> tuple[list[PlayerAppearanceLike], list[PlayerAppearanceLike]]:
    """Tarihe göre desc sıralı son recent_n'i 'recent', kalanı 'baseline'."""
    sorted_apps = sorted(appearances, key=lambda a: a.kickoff, reverse=True)
    recent = sorted_apps[:recent_n]
    baseline = sorted_apps[recent_n:]
    return recent, baseline


def _trend_from_minutes(recent_minutes: list[int]) -> str:
    """Simple slope sign: ilk yarı ortalaması vs son yarı ortalaması farkı."""
    if len(recent_minutes) < 3:
        return "unknown"
    # recent_minutes oldest→newest sıralı; ilk yarı vs son yarı kıyas
    half = len(recent_minutes) // 2
    first = mean(recent_minutes[:half]) if recent_minutes[:half] else 0
    second = mean(recent_minutes[half:]) if recent_minutes[half:] else 0
    diff = second - first
    if diff > TREND_THRESHOLD:
        return "rising"
    if diff < -TREND_THRESHOLD:
        return "declining"
    return "stable"


def compute_player_form(
    player_external_id: int,
    appearances: Iterable[PlayerAppearanceLike],
    *,
    recent_n: int = 5,
    baseline_window_days: int = 365,
    now: datetime | None = None,
) -> EngineResult[PlayerFormSnapshot]:
    """Bir oyuncu için form snapshot'ı + Z-score baseline'la karşılaştırma.

    recent_n: son N maç (default 5)
    baseline_window_days: bu kadar geriye gidip baseline çıkar (default 365g)
    """
    ref_now = now or datetime.now(tz=None)
    cutoff = ref_now - timedelta(days=baseline_window_days)
    in_scope = [
        a for a in appearances
        if a.sport == football.SPORT_NAME
        and a.player_external_id == player_external_id
        and a.kickoff >= cutoff
    ]
    if not in_scope:
        snapshot = PlayerFormSnapshot(
            player_external_id=player_external_id,
            recent_matches=0,
            recent_minutes_per_match=0.0,
            baseline_matches=0,
            baseline_minutes_per_match=0.0,
            baseline_minutes_stdev=0.0,
            z_score=None,
            trend="unknown",
            last_match_minutes=None,
        )
    else:
        recent, baseline = _split_recent_baseline(in_scope, recent_n=recent_n)
        recent_avg = mean(a.minutes for a in recent) if recent else 0.0
        baseline_avg = mean(a.minutes for a in baseline) if baseline else 0.0
        baseline_std = stdev(a.minutes for a in baseline) if len(baseline) >= 2 else 0.0
        z = (
            (recent_avg - baseline_avg) / baseline_std
            if baseline_std > 0 else None
        )
        # Oldest→newest minutes for trend
        recent_chrono = sorted(recent, key=lambda a: a.kickoff)
        snapshot = PlayerFormSnapshot(
            player_external_id=player_external_id,
            recent_matches=len(recent),
            recent_minutes_per_match=round(recent_avg, 2),
            baseline_matches=len(baseline),
            baseline_minutes_per_match=round(baseline_avg, 2),
            baseline_minutes_stdev=round(baseline_std, 2),
            z_score=round(z, 3) if z is not None else None,
            trend=_trend_from_minutes([a.minutes for a in recent_chrono]),
            last_match_minutes=recent[0].minutes if recent else None,
        )

    audit = AuditRecord(
        engine=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        subject_type="player",
        subject_id=player_external_id,
        metric="player_form_snapshot",
        value=asdict(snapshot),
        inputs={
            "recent_n": recent_n,
            "baseline_window_days": baseline_window_days,
            "in_scope_count": len(in_scope),
        },
        formula=(
            "recent = son N maç; baseline = kalan (1y içinde); "
            "z_score = (recent_avg - baseline_avg) / baseline_std; "
            "trend = ilk-yarı vs son-yarı dakika ortalaması farkı (eşik=5dk)"
        ),
    )
    return EngineResult(value=snapshot, audit=audit)
