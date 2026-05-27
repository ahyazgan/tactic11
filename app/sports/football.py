"""Futbol-spesifik sabitler.

Diğer modüller `"football"` literal'i ya da sahaya özgü kodları gömmek yerine
buradan okur. Ufuk 4'te `basketball.py`/`volleyball.py` aynı şablonu izleyecek.
"""

from __future__ import annotations

SPORT_NAME: str = "football"

# Pozisyon kodları (API-Football şemasına yakın: Goalkeeper/Defender/Midfielder/Attacker)
POSITION_GOALKEEPER = "G"
POSITION_DEFENDER = "D"
POSITION_MIDFIELDER = "M"
POSITION_FORWARD = "F"

POSITIONS: tuple[str, ...] = (
    POSITION_GOALKEEPER,
    POSITION_DEFENDER,
    POSITION_MIDFIELDER,
    POSITION_FORWARD,
)

# API-Football "status short" kodlarına göre maç tamamlandı sayılan durumlar:
# FT = Match Finished, AET = After Extra Time, PEN = Penalty Shoot-out
FINISHED_STATUSES: frozenset[str] = frozenset({"FT", "AET", "PEN"})

# Normal süre (dakika)
REGULAR_DURATION_MIN: int = 90
