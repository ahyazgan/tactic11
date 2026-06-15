"""In-game Adaptation Detector — rakip stilinin maç içinde değişimi.

Maç boyunca alınan snapshot'lardan (her N dakikada bir) rakibin
8-vektör profili çıkarılır; ardışık iki örnek arasındaki delta belirli
bir eşiği aştığında "adaptation event" kaydedilir.

Örnek olaylar:
  - "Rakip 60'ta gegenpress'i terk etti → mid-block"
  - "Rakip 75'te line'ı yükseltti — riskli savunma"
  - "Rakip 80'de 5-3-2 kilitleme moduna geçti"

Pure compute, snapshot sample listesi input.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from app.audit import AuditRecord, EngineResult

ENGINE_NAME = "engine.adaptation_detector"
ENGINE_VERSION = "1"

# Boyut başına delta eşiği (0..1 birim)
DEFAULT_THRESHOLDS = {
    "ppda_normalized": 0.15,        # PPDA dramatik değişim
    "field_tilt_pct": 0.10,         # field_tilt 10pp
    "press_height": 0.15,
    "direct_play_pct": 0.10,
    "counter_threat": 0.20,
    "high_line_risk": 0.15,
}

DIMENSION_LABELS = {
    "ppda_normalized": "pres baskınlığı",
    "field_tilt_pct": "field tilt",
    "press_height": "pres yüksekliği",
    "direct_play_pct": "direkt oyun",
    "counter_threat": "kontra tehdidi",
    "high_line_risk": "yüksek line riski",
}


@dataclass(frozen=True)
class SnapshotSample:
    """Bir dakika için rakibin profil göstergesi (normalize 0..1)."""
    minute: float
    ppda_normalized: float        # 0=zayıf pres, 1=çok yüksek
    field_tilt_pct: float         # 0..1
    press_height: float
    direct_play_pct: float
    counter_threat: float
    high_line_risk: float

    def values(self) -> dict[str, float]:
        return {
            "ppda_normalized": self.ppda_normalized,
            "field_tilt_pct": self.field_tilt_pct,
            "press_height": self.press_height,
            "direct_play_pct": self.direct_play_pct,
            "counter_threat": self.counter_threat,
            "high_line_risk": self.high_line_risk,
        }


@dataclass(frozen=True)
class AdaptationEvent:
    minute: float
    dimension: str
    label: str                    # TR
    delta: float                  # +/- yön
    direction: str                # "rose" | "fell"
    prev_value: float
    next_value: float
    significance: str             # "high" | "medium" | "low"
    interpretation: str           # 1 cümle TR yorum
    our_counter_advice: str       # öneri


@dataclass(frozen=True)
class AdaptationReport:
    sample_count: int
    events: tuple[AdaptationEvent, ...]
    summary: str
    snapshots_minutes: tuple[float, ...] = field(default_factory=tuple)


def _significance(delta: float, threshold: float) -> str:
    ratio = abs(delta) / threshold if threshold > 0 else 0
    if ratio >= 2.0:
        return "high"
    if ratio >= 1.4:
        return "medium"
    return "low"


def _interpret(dim: str, direction: str, prev: float, nxt: float) -> str:
    label = DIMENSION_LABELS.get(dim, dim)
    if dim == "ppda_normalized":
        if direction == "fell":
            return f"Rakip pres'i bıraktı (PPDA düştü {prev:.2f}→{nxt:.2f}) — mid/low-block'a geçti"
        return f"Rakip pres'i yükseltti (PPDA arttı {prev:.2f}→{nxt:.2f}) — agresif faza geçti"
    if dim == "press_height":
        if direction == "fell":
            return f"Rakip pres yüksekliği düştü {prev:.2f}→{nxt:.2f} — düşük block'a çekildi"
        return f"Rakip pres yüksekliği arttı {prev:.2f}→{nxt:.2f} — yüksek block'a geçti"
    if dim == "field_tilt_pct":
        if direction == "fell":
            return f"Rakip alan kontrolü düştü {prev:.2f}→{nxt:.2f} — bizim hücum payımız arttı"
        return f"Rakip alan kontrolü arttı {prev:.2f}→{nxt:.2f} — daha fazla possession alıyor"
    if dim == "direct_play_pct":
        if direction == "fell":
            return f"Rakip direkt oyunu azalttı {prev:.2f}→{nxt:.2f} — possession denedi"
        return f"Rakip direkt oyunu arttırdı {prev:.2f}→{nxt:.2f} — uzun top patladı"
    if dim == "counter_threat":
        if direction == "fell":
            return f"Rakip kontra tehdidi düştü {prev:.2f}→{nxt:.2f}"
        return f"Rakip kontra tehdidi arttı {prev:.2f}→{nxt:.2f} — hızlı geçişler"
    if dim == "high_line_risk":
        if direction == "fell":
            return f"Rakip line'ı geri çekti {prev:.2f}→{nxt:.2f} — derinlik veriyor"
        return f"Rakip line'ı yükseltti {prev:.2f}→{nxt:.2f} — derinlik riski"
    return f"{label} değişti {prev:.2f}→{nxt:.2f}"


def _our_counter(dim: str, direction: str) -> str:
    if dim == "ppda_normalized":
        if direction == "fell":
            return "Mid-block'a karşı switch of play + half-space inverted FB"
        return "Yüksek pres altında üçüncü oyuncu kombinasyonu + uzun top hedef"
    if dim == "press_height":
        if direction == "fell":
            return "Düşük block — cut-back + ikinci dalga şut"
        return "Yüksek pres — kısa yapı bozar; long ball ya da 3 stoper çıkış"
    if dim == "field_tilt_pct":
        if direction == "fell":
            return "Alan bizdeyken switch + width kullan"
        return "Possession kaybediyoruz — kalabalık orta saha + sabırla mid-block"
    if dim == "direct_play_pct":
        if direction == "fell":
            return "Kısa pas oynayan rakibe pres yüksel"
        return "Uzun top için stoper havada hazır + second-ball avcısı"
    if dim == "counter_threat":
        if direction == "fell":
            return "Tehdit düştü — biraz daha hücum riskine girebiliriz"
        return "Rest-defence 3 oyuncu + sayısal eşitlik üstüne odakla"
    if dim == "high_line_risk":
        if direction == "fell":
            return "Line geri çekildi — uzun şut + ikinci top"
        return "Yüksek line → dik koşu + offside-bait"
    return "Standart oyun planına devam"


def compute_adaptation(
    samples: Iterable[SnapshotSample],
    *,
    thresholds: dict[str, float] | None = None,
) -> EngineResult[AdaptationReport]:
    """Ardışık snapshot'lar arası adaptation event'leri tespit et."""
    thresholds = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    slist = sorted(list(samples), key=lambda s: s.minute)
    events: list[AdaptationEvent] = []
    minutes_seen: list[float] = []

    if len(slist) < 2:
        report = AdaptationReport(
            sample_count=len(slist),
            events=(),
            summary="Adaptation tespiti için en az 2 snapshot gerek",
            snapshots_minutes=tuple(s.minute for s in slist),
        )
        return EngineResult(value=report, audit=AuditRecord(
            engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
            subject_type="match", subject_id=0,
            metric="adaptation",
            value={"sample_count": len(slist), "events": 0},
            inputs={"thresholds": thresholds}, formula="insufficient",
        ))

    for prev, nxt in zip(slist, slist[1:], strict=False):
        minutes_seen.append(nxt.minute)
        prev_vals = prev.values()
        next_vals = nxt.values()
        for dim, th in thresholds.items():
            pv = prev_vals.get(dim, 0)
            nv = next_vals.get(dim, 0)
            delta = nv - pv
            if abs(delta) < th:
                continue
            direction = "rose" if delta > 0 else "fell"
            sig = _significance(delta, th)
            events.append(AdaptationEvent(
                minute=nxt.minute,
                dimension=dim,
                label=DIMENSION_LABELS.get(dim, dim),
                delta=round(delta, 3),
                direction=direction,
                prev_value=round(pv, 3),
                next_value=round(nv, 3),
                significance=sig,
                interpretation=_interpret(dim, direction, pv, nv),
                our_counter_advice=_our_counter(dim, direction),
            ))

    if not events:
        summary = f"{len(slist)} snapshot analiz edildi — anlamlı değişim yok"
    else:
        first = events[0]
        summary = (
            f"{len(events)} adaptation tespit edildi; "
            f"ilk: {first.minute:.0f}. dk {first.label} {first.direction}"
        )

    report = AdaptationReport(
        sample_count=len(slist),
        events=tuple(events),
        summary=summary,
        snapshots_minutes=tuple(s.minute for s in slist),
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="match", subject_id=0,
        metric="adaptation",
        value={
            "sample_count": len(slist),
            "event_count": len(events),
            "dimensions_changed": sorted({e.dimension for e in events}),
            "summary": summary,
        },
        inputs={"thresholds": thresholds},
        formula=(
            "Ardışık snapshot delta her boyut için threshold'u aşarsa event; "
            "significance = |delta|/threshold (high≥2, med≥1.4)"
        ),
    )
    return EngineResult(value=report, audit=audit)
