"""GPS Load — GPS/wearable antrenman yükü normalizasyonu (saf).

Catapult/STATSports gibi cihazların seans çıktısını (mesafe, yüksek-hız koşu,
ivmelenme/yavaşlama, cihaz "player load") tek bir iç-yük (internal load, AU)
değerine indirger. Bu değer doğrudan `engine.workload.compute_workload`
(ACWR) günlük yük serisine beslenir → objektif sakatlık riski.

Ayrıca seans-RPE yükü (RPE × süre) hesaplanır — subjektif yöntem yedek/çapraz
doğrulama. Saf: seans metrikleri → rapor. DataSource adapter'ı cihaz API'sini
bu modele çevirir (mimari hazır).
"""
from __future__ import annotations

from dataclasses import dataclass, field

ENGINE_NAME = "engine.gps_load"
ENGINE_VERSION = "1"

# İç-yük tahmini ağırlıkları (cihaz player_load yoksa). Yüksek-hız koşu ve
# ivme/yavaşlama, düz mesafeden daha yorucu → daha yüksek ağırlık. (AU, kalibre
# edilebilir; kulüp cihaz player_load'u varsa o kullanılır.)
W_DISTANCE = 0.01      # her 100m → 1 AU
W_HSR = 0.05           # yüksek-hız koşu metresi 5×
W_SPRINT = 0.08        # sprint metresi 8×
W_HI_EVENT = 0.5       # her accel/decel → 0.5 AU
# Yüksek-yoğunluk seans bayrağı (distance/min eşiği, m/dk).
HIGH_INTENSITY_M_PER_MIN = 120.0


@dataclass(frozen=True)
class GpsSession:
    duration_min: float
    total_distance_m: float
    hsr_distance_m: float = 0.0       # high-speed running (>~19.8 km/h)
    sprint_distance_m: float = 0.0    # sprint (>~25 km/h)
    accelerations: int = 0            # yüksek ivmelenme sayısı
    decelerations: int = 0            # yüksek yavaşlama sayısı
    player_load: float | None = None  # cihaz "player load" (AU) varsa
    rpe: float | None = None          # session RPE 0-10 (subjektif)


@dataclass(frozen=True)
class GpsLoadReport:
    duration_min: float
    total_distance_m: float
    distance_per_min: float
    hsr_pct: float                    # yüksek-hız koşu / toplam (0..100)
    high_intensity_events: int        # accel + decel
    session_load: float               # iç-yük (AU) — ACWR'ye beslenir
    rpe_load: float | None            # RPE × süre (AU)
    high_intensity_session: bool
    flags: tuple[str, ...] = field(default_factory=tuple)


def compute_gps_load(s: GpsSession) -> GpsLoadReport:
    dur = max(s.duration_min, 1e-9)
    dist_per_min = round(s.total_distance_m / dur, 1)
    hsr_pct = round(100.0 * s.hsr_distance_m / s.total_distance_m, 1) if s.total_distance_m > 0 else 0.0
    hi_events = s.accelerations + s.decelerations

    # İç-yük: cihaz player_load varsa onu kullan; yoksa ağırlıklı tahmin.
    if s.player_load is not None:
        session_load = round(s.player_load, 1)
    else:
        session_load = round(
            s.total_distance_m * W_DISTANCE
            + s.hsr_distance_m * W_HSR
            + s.sprint_distance_m * W_SPRINT
            + hi_events * W_HI_EVENT,
            1,
        )
    rpe_load = round(s.rpe * s.duration_min, 1) if s.rpe is not None else None

    high_intensity = dist_per_min >= HIGH_INTENSITY_M_PER_MIN
    flags: list[str] = []
    if high_intensity:
        flags.append(f"yüksek yoğunluk ({dist_per_min:.0f} m/dk)")
    if hsr_pct >= 15.0:
        flags.append(f"yüksek HSR payı (%{hsr_pct:.0f}) — sakatlık dikkat")

    return GpsLoadReport(
        duration_min=round(s.duration_min, 1),
        total_distance_m=round(s.total_distance_m, 1),
        distance_per_min=dist_per_min,
        hsr_pct=hsr_pct,
        high_intensity_events=hi_events,
        session_load=session_load,
        rpe_load=rpe_load,
        high_intensity_session=high_intensity,
        flags=tuple(flags),
    )
