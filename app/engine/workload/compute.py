"""Workload — ACWR + monotony + strain (sakatlık riski, saf).

Spor biliminin sakatlık-riski altın standardı: günlük yük (RPE×dakika, GPS
high-speed running vb.) serisinden:
- ACWR (acute:chronic workload ratio): son 7 günün ortalaması / son 28 günün
  ortalaması. "Sweet spot" 0.8-1.3; >1.5 yüksek sakatlık riski; <0.8
  detraining. (Gabbett 2016 literatürü.)
- Monotony (Foster): haftalık yükün ortalaması / standart sapması — tekdüze
  ağır yük riskli.
- Strain: haftalık toplam yük × monotony.

Saf: günlük yük serisi → rapor. Mevcut load/injury_risk motorlarını tamamlar.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field

ENGINE_NAME = "engine.workload"
ENGINE_VERSION = "1"

ACUTE_DAYS = 7
CHRONIC_DAYS = 28
# ACWR risk bölgeleri (Gabbett).
ACWR_UNDER = 0.80     # altı: detraining/yetersiz yük
ACWR_SWEET_HI = 1.30  # 0.80-1.30 sweet spot
ACWR_CAUTION_HI = 1.50  # 1.30-1.50 dikkat; üstü yüksek risk
# Monotony eşiği (üstü tekdüzelik riski).
MONOTONY_HIGH = 2.0


@dataclass(frozen=True)
class ACWRReport:
    acwr: float | None           # acute/chronic; veri yetersizse None
    acute_load: float
    chronic_load: float
    risk_zone: str               # "yetersiz" | "ideal" | "dikkat" | "yüksek_risk" | "bilinmiyor"
    monotony: float | None
    strain: float | None
    flags: tuple[str, ...] = field(default_factory=tuple)
    days_seen: int = 0


def _acwr_zone(acwr: float) -> str:
    if acwr < ACWR_UNDER:
        return "yetersiz"
    if acwr <= ACWR_SWEET_HI:
        return "ideal"
    if acwr <= ACWR_CAUTION_HI:
        return "dikkat"
    return "yüksek_risk"


def compute_workload(
    daily_loads: list[float],
    *,
    acute_days: int = ACUTE_DAYS,
    chronic_days: int = CHRONIC_DAYS,
) -> ACWRReport:
    """daily_loads: kronolojik günlük yük (eski→yeni). Eksik gün = 0 dahil edilir."""
    n = len(daily_loads)
    flags: list[str] = []

    if n < acute_days:
        return ACWRReport(
            acwr=None, acute_load=0.0, chronic_load=0.0,
            risk_zone="bilinmiyor", monotony=None, strain=None,
            flags=("yetersiz veri (< akut pencere)",), days_seen=n,
        )

    acute = statistics.fmean(daily_loads[-acute_days:])
    # Kronik pencere: mevcut veri kadar (en fazla chronic_days).
    chronic_window = daily_loads[-chronic_days:]
    chronic = statistics.fmean(chronic_window)

    acwr: float | None
    if chronic <= 0:
        acwr = None
        zone = "bilinmiyor"
        flags.append("kronik yük 0 — ACWR hesaplanamaz")
    else:
        acwr = round(acute / chronic, 2)
        zone = _acwr_zone(acwr)
        if zone == "yüksek_risk":
            flags.append(f"ACWR {acwr} — yüksek sakatlık riski (yükü düşür)")
        elif zone == "yetersiz":
            flags.append(f"ACWR {acwr} — detraining riski (yük artır)")

    # Monotony + strain (son akut pencere üzerinden günlük dağılım).
    window = daily_loads[-acute_days:]
    sd = statistics.pstdev(window) if len(window) >= 2 else 0.0
    mean = statistics.fmean(window)
    monotony = round(mean / sd, 2) if sd > 0 else None
    strain = round(sum(window) * monotony, 1) if monotony is not None else None
    if monotony is not None and monotony >= MONOTONY_HIGH:
        flags.append(f"monotony {monotony} — tekdüze ağır yük (varyasyon ekle)")

    return ACWRReport(
        acwr=acwr, acute_load=round(acute, 1), chronic_load=round(chronic, 1),
        risk_zone=zone, monotony=monotony, strain=strain,
        flags=tuple(flags), days_seen=n,
    )
