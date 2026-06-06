"""Wellness — subjektif hazırlık (readiness) skoru (saf).

Sabah check-in anketi (Hooper-tipi): uyku, yorgunluk, kas ağrısı, stres, ruh
hali. Objektif GPS yükünü (gps_load) tamamlar — birlikte "antrenmana hazır mı,
yüklensin mi dinlensin mi" kararını besler.

Konvansiyon: her madde 1-7, **yüksek = iyi** (7 mükemmel uyku / dinç / ağrısız /
sakin / iyi ruh hali). readiness = ortalama/7 (0..1). Bireysel baseline
verilirse kişisel düşüş de işaretlenir (lig değil, kendi normuna göre).

Saf: anket değerleri → rapor. DB/HTTP yok.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field

ENGINE_NAME = "engine.wellness"
ENGINE_VERSION = "1"

SCALE_MAX = 7.0
READY_THRESHOLD = 0.70      # ≥ → hazır
MONITOR_THRESHOLD = 0.55    # 0.55-0.70 → izle; altı → dikkat
# Tek-madde düşük eşiği (≤ → o boyut için uyarı).
ITEM_LOW = 3
# Bireysel baseline'dan anlamlı düşüş (oran).
BASELINE_DROP = 0.15


@dataclass(frozen=True)
class WellnessInput:
    sleep_quality: int      # 1-7
    fatigue: int            # 1-7 (7 = dinç)
    muscle_soreness: int    # 1-7 (7 = ağrısız)
    stress: int             # 1-7 (7 = sakin)
    mood: int               # 1-7


@dataclass(frozen=True)
class WellnessReport:
    readiness: float        # 0..1
    zone: str               # "hazır" | "izle" | "dikkat"
    total: int              # 5-35
    below_baseline: bool
    flags: tuple[str, ...] = field(default_factory=tuple)


_ITEM_LABELS = {
    "sleep_quality": "uyku", "fatigue": "yorgunluk",
    "muscle_soreness": "kas ağrısı", "stress": "stres", "mood": "ruh hali",
}


def compute_wellness(
    w: WellnessInput,
    *,
    baseline_totals: list[int] | None = None,
) -> WellnessReport:
    items = {
        "sleep_quality": w.sleep_quality, "fatigue": w.fatigue,
        "muscle_soreness": w.muscle_soreness, "stress": w.stress, "mood": w.mood,
    }
    total = sum(items.values())
    readiness = round(total / (5 * SCALE_MAX), 3)
    zone = ("hazır" if readiness >= READY_THRESHOLD
            else "izle" if readiness >= MONITOR_THRESHOLD else "dikkat")

    flags: list[str] = []
    for key, val in items.items():
        if val <= ITEM_LOW:
            flags.append(f"{_ITEM_LABELS[key]} düşük ({val}/7)")
    # Kas ağrısı özellikle: sakatlık göstergesi
    if w.muscle_soreness <= ITEM_LOW:
        flags.append("kas ağrısı yüksek — yük/sakatlık kontrolü")

    below_baseline = False
    if baseline_totals:
        base_mean = statistics.fmean(baseline_totals)
        if base_mean > 0 and total <= base_mean * (1 - BASELINE_DROP):
            below_baseline = True
            flags.append(
                f"kişisel baseline altında ({total} vs ort. {base_mean:.0f}) — temkinli"
            )

    return WellnessReport(
        readiness=readiness, zone=zone, total=total,
        below_baseline=below_baseline, flags=tuple(flags),
    )
