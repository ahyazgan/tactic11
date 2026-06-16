"""Canlı feed fabrikası — WS handler'ı somut feed sınıfından ayırır.

Bugüne kadar WS handler `StatsBombReplayFeed`'i doğrudan kuruyordu; bu
fabrika o bağı koparır: snapshot/engine/WS-döngüsü değişmeden, veri kaynağı
config'ten seçilir. Yeni bir gerçek sağlayıcı (Opta / StatsBomb Pro) `ReplayFeed`
Protocol'ünü implement edip buradaki REGISTRY'ye eklenir — başka hiçbir yer
değişmez.

VERİ GERÇEĞİ (önemli): tactical motorlar (xT, VAEP, alan-üstünlüğü) KOORDİNATLI
event akışı ister (pas/şut x-y + dakika). API-Football canlı uçları yalnız
gol/kart/değişiklik verir — koordinat YOK; bu yüzden tek başına bu motorları
besleyemez. Koordinatlı canlı akış Opta/StatsBomb Pro (ücretli) gerektirir.
`LIVE_FEED_MODE=live_api` seçilse bile, kayıtlı bir koordinatlı adapter yoksa
fabrika sessizce ve güvenle "replay"e düşer (demoyu/asla bozmaz).
"""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

from app.api.replay_feed import ReplayFeed, StatsBombReplayFeed
from app.core.config import Settings, get_settings
from app.core.logging import get_logger

log = get_logger(__name__)

# mode → feed kurucu. Gerçek koordinatlı sağlayıcı adapter'ı geldiğinde
# buraya "live_api": <AdapterClass> eklenir; WS handler dokunulmaz.
_REGISTRY: dict[str, Callable[[Session, int], ReplayFeed]] = {
    "replay": StatsBombReplayFeed,
}
_DEFAULT_MODE = "replay"


def resolve_feed_mode(settings: Settings | None = None) -> str:
    """Etkin feed modunu çöz. Kayıtlı kurucusu olmayan mod → replay'e düşer.

    Böylece config'te LIVE_FEED_MODE=live_api olsa bile (koordinatlı adapter
    henüz yoksa) sistem demoyu/replay'i bozmadan çalışır.
    """
    s = settings or get_settings()
    requested = (s.live_feed_mode or _DEFAULT_MODE).strip().lower()
    if requested not in _REGISTRY:
        log.info(
            "live feed mode '%s' için kayıtlı adapter yok — replay'e düşülüyor "
            "(koordinatlı canlı akış Opta/StatsBomb Pro gerektirir).",
            requested,
        )
        return _DEFAULT_MODE
    return requested


def build_live_feed(
    session: Session, match_id: int, *, settings: Settings | None = None,
) -> ReplayFeed:
    """Etkin moda göre canlı feed kur. ValueError → maç DB'de yok (WS handler
    bunu istemciye 'error' olarak iletir; mevcut davranış korunur)."""
    mode = resolve_feed_mode(settings)
    factory = _REGISTRY[mode]
    return factory(session, match_id)
