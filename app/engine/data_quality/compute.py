"""Data Quality — event-akışı kalite skoru (saf, runtime).

`app/data/validation/` ingest-anı ŞEMA doğrulaması yapar (lig adı zorunlu vb.).
Bu engine farklı bir katman: bir maçın event akışının ne kadar GÜVENİLİR
olduğunu skorlar — kapsama boşlukları (feed dropout), yoğunluk (seyrek feed),
tazelik (bayat veri), tip dengesi (kritik tip eksik). Çıktı 0..1 skor; bu skor
doğrudan `engine.confidence.score_confidence(data_quality=...)`'a beslenebilir.

Saf: event zaman damgası + tipi listesi → kalite raporu. DB/HTTP yok.
"""
from __future__ import annotations

from dataclasses import dataclass, field

ENGINE_NAME = "engine.data_quality"
ENGINE_VERSION = "1"

# Eşikler (belgeli — gerçek maçta her 1-2 dk'da event olur):
# 8+ dk boşluk → feed kesintisi şüphesi.
MAX_GAP_MIN = 8.0
# Son event 5+ dk önceyse feed bayat.
STALE_MIN = 5.0
# Ortalama 3 event/dk altı seyrek/şüpheli (tipik maç ~10-20 event/dk).
MIN_DENSITY_PER_MIN = 3.0
# Bir maçta beklenen çekirdek event tipleri.
CORE_TYPES = ("pass", "defensive_action", "shot", "carry")

GOOD_THRESHOLD = 0.70
DEGRADED_THRESHOLD = 0.40


@dataclass(frozen=True)
class EventStamp:
    minute: float
    event_type: str


@dataclass(frozen=True)
class DataQualityReport:
    quality_score: float          # 0..1 — confidence.data_quality'ye beslenebilir
    status: str                   # "ok" | "degraded" | "poor"
    events_seen: int
    density_per_min: float
    largest_gap_min: float
    freshness_min: float          # son event'ten current_minute'e geçen dk
    missing_types: tuple[str, ...] = field(default_factory=tuple)
    flags: tuple[str, ...] = field(default_factory=tuple)


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def compute_data_quality(
    events: list[EventStamp],
    *,
    current_minute: float,
    core_types: tuple[str, ...] = CORE_TYPES,
) -> DataQualityReport:
    """Event akışının kalite skoru + tanı bayrakları."""
    minutes = sorted(e.minute for e in events if e.minute <= current_minute)
    seen = len(minutes)
    flags: list[str] = []

    if seen == 0:
        return DataQualityReport(
            quality_score=0.0, status="poor", events_seen=0,
            density_per_min=0.0, largest_gap_min=round(current_minute, 2),
            freshness_min=round(current_minute, 2),
            missing_types=tuple(core_types),
            flags=("event yok",),
        )

    # Yoğunluk
    density = round(seen / max(current_minute, 1.0), 2)

    # En büyük boşluk (ardışık event'ler arası + başlangıç/son)
    bounds = [0.0, *minutes, current_minute]
    largest_gap = round(max(b - a for a, b in zip(bounds, bounds[1:], strict=False)), 2)

    # Tazelik: son event'ten bu yana
    freshness = round(current_minute - minutes[-1], 2)

    # Tip dengesi
    present = {e.event_type for e in events if e.minute <= current_minute}
    missing = tuple(t for t in core_types if t not in present)

    # Skor: 1.0'dan ceza düş
    score = 1.0
    if freshness > STALE_MIN:
        score -= min(0.40, (freshness - STALE_MIN) / 20.0)
        flags.append(f"bayat feed (son event {freshness:.0f} dk önce)")
    if largest_gap > MAX_GAP_MIN:
        score -= min(0.30, (largest_gap - MAX_GAP_MIN) / 20.0)
        flags.append(f"kapsama boşluğu ({largest_gap:.0f} dk)")
    if density < MIN_DENSITY_PER_MIN:
        score -= min(0.30, (MIN_DENSITY_PER_MIN - density) / MIN_DENSITY_PER_MIN * 0.30)
        flags.append(f"seyrek feed ({density:.1f} event/dk)")
    if missing:
        score -= 0.15 * len(missing)
        flags.append(f"eksik tip: {', '.join(missing)}")

    score = round(_clamp01(score), 3)
    status = ("ok" if score >= GOOD_THRESHOLD
              else "degraded" if score >= DEGRADED_THRESHOLD else "poor")

    return DataQualityReport(
        quality_score=score, status=status, events_seen=seen,
        density_per_min=density, largest_gap_min=largest_gap,
        freshness_min=freshness, missing_types=missing, flags=tuple(flags),
    )
