"""Karar sinyali ortak tipleri — Faz 8 bağlam katmanının ortak dili.

8 maç-içi engine (momentum/sub_timing/tactical/risk/spatial/matchup/
score_time/opponent) ham sinyallerini bu normalize forma çevirir. Bağlam
katmanı (signal_quality → confidence → context_engine) hep bu tip üzerinden
çalışır; böylece her engine'i tek tek tanımak zorunda kalmaz.

Saf veri taşıyıcı; davranış yok.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Sinyal kategorileri — context_engine bunlara göre çakışmaları birleştirir
SignalType = str  # "substitution" | "tactical" | "risk" | "spatial" |
#                   "matchup" | "closing" | "opponent" | "set_piece"


@dataclass(frozen=True)
class CandidateSignal:
    """Bir engine'in ürettiği tek ham sinyal (kalite/güven öncesi)."""

    key: str                 # kaynak engine anahtarı, örn. "momentum"
    signal_type: SignalType
    headline: str            # kısa Türkçe öneri metni
    urgency: float           # 0..1 — kaynak engine'in aciliyet tahmini
    fired: bool              # engine bunu aktif sinyal saydı mı
    minute: float
    # kalite + güven kanıtı
    sample_size: int = 0     # destekleyen event/şut/düello sayısı
    magnitude: float = 0.0   # 0..1 — altta yatan metriğin gücü
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ScoredSignal:
    """signal_quality + confidence geçmiş, context_engine'e hazır sinyal."""

    candidate: CandidateSignal
    quality: float           # 0..1 — sinyal kalite filtresi skoru
    quality_verdict: str     # "ok" | "degraded" | "suppressed"
    quality_reason: str
    confidence: float        # 0..1 — güven skoru
    confidence_label: str    # "yüksek" | "orta" | "düşük"
    confidence_drivers: tuple[str, ...] = field(default_factory=tuple)

    @property
    def priority(self) -> float:
        """Sıralama skoru: aciliyet × güven × kalite."""
        return round(
            self.candidate.urgency * self.confidence * self.quality, 4
        )
