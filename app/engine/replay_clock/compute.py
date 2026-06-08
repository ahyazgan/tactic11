"""Replay clock — event-zaman güdümlü maç saati (saf).

Mevcut canlı pipeline saati sahte-lineerdi: her interval'da sabit +5 dk,
gerçek event-zamanıyla ilgisiz; ve maç düz 90'da biterdi. Bu modül saati
gerçek son-event dakikasına bağlar ve `speed` çarpanıyla wall-time→match-time
eşler.

Saf: `elapsed_wall`'ın fonksiyonu; içeride wall-clock OKUMAZ (test'lerde
sentetik elapsed enjekte edilir → determinist). DB/HTTP bilmez.
"""

from __future__ import annotations

from dataclasses import dataclass

# Kapanış penceresi — score_time_matrix ile aynı konvansiyon (tek kaynak orası
# ama import döngüsü yaratmamak için sabiti burada tekrar tanımlıyoruz).
CLOSING_MINUTE = 75.0
HALFTIME_MINUTE = 45.0


@dataclass(frozen=True)
class ClockConfig:
    """Replay saat ayarları."""

    speed: float = 5.0              # her interval'da ilerleyen match-dakikası
    start_minute: float = 0.0
    halftime_pause_ticks: int = 0   # 45'te N tick beklet (0 = kapalı)


def advance_minute(
    *,
    elapsed_wall: float,
    interval: float,
    last_event_minute: float,
    config: ClockConfig | None = None,
) -> tuple[float, bool]:
    """(current_minute, ended) — geçen wall-süreden replay dakikası.

    Temel eşleme: raw = start + (elapsed_wall / interval) * speed.
    Bitiş gerçek son-event dakikasında (`raw >= last_event_minute`), düz 90'da
    değil. Halftime pause açıksa 45'i geçerken N tick 45'te tutulur.
    """
    cfg = config or ClockConfig()
    interval = interval if interval > 0 else 1.0
    ticks = elapsed_wall / interval
    raw = cfg.start_minute + ticks * cfg.speed

    if cfg.halftime_pause_ticks > 0 and raw > HALFTIME_MINUTE:
        # 45'i aşan ham dakikayı, pause süresince 45'te tut; pause sonrası kaydır.
        pause_minutes = cfg.halftime_pause_ticks * cfg.speed
        if raw <= HALFTIME_MINUTE + pause_minutes:
            raw = HALFTIME_MINUTE
        else:
            raw -= pause_minutes

    current = min(raw, last_event_minute)
    ended = raw >= last_event_minute
    return current, ended


def current_phase(minute: float) -> str:
    """Dakikadan maç fazı: 1H | 2H | closing (>=75) | FT (>=90).

    HT (devre arası) ayrı bir saat-durumu; burada dakika-tabanlı türetmede
    45-90 arası 2H sayılır (pause varsa caller 45'te takılı kalır).
    """
    if minute >= 90.0:
        return "FT"
    if minute >= CLOSING_MINUTE:
        return "closing"
    if minute > HALFTIME_MINUTE:
        return "2H"
    return "1H"
