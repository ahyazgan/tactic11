"""Veri kaynağı fabrikası — `DATA_SOURCE` config'ine göre adapter seçer.

Appearance ingest/backfill somut sınıf yerine `build_source()` çağırır; böylece
API-Football ↔ Sportmonks geçişi tek env değişkeniyle olur (kod değişmez).
"""

from __future__ import annotations

from app.core.config import get_settings
from app.core.logging import get_logger
from app.data.sources.api_football import APIFootball
from app.data.sources.base import AppearanceSource
from app.data.sources.sportmonks import Sportmonks

log = get_logger(__name__)

_DEFAULT = "api_football"


def build_source(name: str | None = None) -> AppearanceSource:
    """Aktif veri kaynağı adapter'ı. name verilmezse config DATA_SOURCE.

    Bilinmeyen ad → uyarı + API-Football (güvenli varsayılan)."""
    chosen = (name or get_settings().data_source or _DEFAULT).strip().lower()
    if chosen == "sportmonks":
        return Sportmonks()
    if chosen != "api_football":
        log.warning("bilinmeyen DATA_SOURCE '%s' — api_football'a düşülüyor", chosen)
    return APIFootball()
