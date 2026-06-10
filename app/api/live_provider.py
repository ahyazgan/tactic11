"""Canlı feed sağlayıcı sunumu — maç-içi konsolda enterprise feed
(StatsBomb / Opta / Stats Perform) API anahtarı **bağlıymış gibi** snapshot'a
bağlantı meta'sı üretir.

Veri bugün StatsBomb open'ın event-zaman güdümlü replay'inden gelir
(`StatsBombReplayFeed`). Bu modül o veriyi "hangi sağlayıcının canlı feed'i
bağlı" sunumuyla giydirir: sağlayıcı adı + MASKELİ API anahtarı + bağlantı
durumu + nominal gecikme. Tam API anahtarı asla istemciye gönderilmez.

Gerçek bir canlı feed geldiğinde sağlayıcı tablosu + `live_feed_*` config
aynen kullanılmaya devam eder; sadece altta `ReplayFeed` yerine gerçek
provider adapter'ı girer — sunum katmanı değişmez.
"""

from __future__ import annotations

from app.core.config import Settings, get_settings

# Desteklenen enterprise sağlayıcılar (sunum metası). `demo_key` deterministiktir
# (random yok → test-stabil, her boot'ta aynı), config'te key yoksa kullanılır.
_PROVIDERS: dict[str, dict[str, object]] = {
    "statsbomb": {
        "name": "StatsBomb Live API",
        "feed": "koordinatlı event akışı",
        "nominal_latency_ms": 380,
        "demo_key": "sb_live_sk_9f4c2a7b3e81",
    },
    "opta": {
        "name": "Opta — Stats Perform",
        "feed": "F24 canlı event akışı",
        "nominal_latency_ms": 240,
        "demo_key": "opta_live_3d71b9e6c0a4",
    },
    "stats_perform": {
        "name": "Stats Perform Live",
        "feed": "Opta Live event akışı",
        "nominal_latency_ms": 300,
        "demo_key": "sp_live_8a52f1d4b76c",
    },
}
_DEFAULT_PROVIDER = "statsbomb"


def _mask_key(key: str) -> str:
    """API anahtarını maskele: önek + ••• + son 4. Boşsa boş döner."""
    if not key:
        return ""
    if len(key) <= 8:
        return key[:2] + "••••"
    return f"{key[:7]}••••{key[-4:]}"


def build_provider_status(
    settings: Settings | None = None, *, source: str | None = None,
) -> dict[str, object]:
    """Snapshot'a düşecek sağlayıcı bağlantı bloğunu üret.

    `live_feed_provider` config'inden sağlayıcıyı seçer (geçersizse default
    StatsBomb). `live_feed_api_key` set'liyse onu, değilse sağlayıcının demo
    key'ini MASKELEYEREK koyar.

    `source` = etkin feed kaynağı (feed.mode(), örn "replay_statsbomb").
    Verilirse `status` dürüstçe türetilir: replay → "replay" (gerçek canlı
    feed değil), aksi halde "connected". `is_demo_key` zaten gerçek anahtar
    olup olmadığını belirtir — istemci bu üçüyle gerçeği görür.
    """
    s = settings or get_settings()
    pid = (s.live_feed_provider or _DEFAULT_PROVIDER).strip().lower()
    meta = _PROVIDERS.get(pid)
    if meta is None:
        pid, meta = _DEFAULT_PROVIDER, _PROVIDERS[_DEFAULT_PROVIDER]

    configured = bool(s.live_feed_api_key)
    key = s.live_feed_api_key or str(meta["demo_key"])
    is_replay = source is None or source.startswith("replay")
    return {
        "id": pid,
        "name": meta["name"],
        "status": "replay" if is_replay else "connected",
        "source": source or "replay",
        "api_key_masked": _mask_key(key),
        "feed": meta["feed"],
        "latency_ms": meta["nominal_latency_ms"],
        "is_demo_key": not configured,
    }
