"""Redis-destekli cache backend (Faz 9 #9).

`store.py`'nin DB-destekli `cache_get/cache_set/cache_get_stale` arayüzünün
aynısını Redis üzerinde sağlar. Multi-tenant pilotta birden fazla replica
aynı cache'i paylaşsın + DB'ye yük binmesin diye.

Tasarım:
- Değer bir "envelope" olarak saklanır: `{"v": <value>, "exp": <unix_ts>}`.
  Redis anahtar TTL'i = stale retention (uzun); mantıksal son-kullanım `exp`
  envelope içinde. Böylece `cache_get` mantıksal TTL'e bakar, `cache_get_stale`
  süresi geçmiş ama henüz Redis'ten düşmemiş değeri döndürebilir (degraded mod).
- Redis client DIŞARIDAN enjekte edilir (`get_redis_client`); `redis` paketi
  kurulu değilse veya REDIS_URL boşsa backend devre dışı (None) → DB fallback.
- Anahtar namespace: `fi:cache:{source}:{key}`.

Saf değil (I/O); ama `store.py` Redis hatalarında DB'ye düşerek dayanıklılık
sağlar — bu modül yalnız "mutlu yol" + hata yükseltme sunar.
"""

from __future__ import annotations

import json
from typing import Any

from app.core.logging import get_logger

log = get_logger(__name__)

_KEY_PREFIX = "fi:cache"

# Süreç-ömürlü tekil client (lazy). None → henüz kurulmadı / devre dışı.
_client: Any = None
_client_initialized = False


class RedisUnavailable(RuntimeError):
    """Redis paketi yok ya da bağlantı kurulamadı."""


def _redis_key(source: str, key: str) -> str:
    return f"{_KEY_PREFIX}:{source}:{key}"


def get_redis_client() -> Any | None:
    """REDIS_URL set + `redis` kuruluysa tekil client; aksi halde None.

    İlk çağrıda bağlanır; bağlanamazsa None döner (sessizce DB'ye düşülür,
    boot patlamasın). Testler `set_redis_client_for_test` ile fake enjekte eder.
    """
    global _client, _client_initialized
    if _client_initialized:
        return _client
    _client_initialized = True

    from app.core.config import get_settings
    url = get_settings().redis_url
    if not url:
        _client = None
        return None
    try:
        import redis  # type: ignore
    except ImportError:
        log.warning("REDIS_URL set ama `redis` paketi kurulu değil — DB cache kullanılıyor")
        _client = None
        return None
    try:
        client = redis.Redis.from_url(url, decode_responses=True)
        client.ping()
        _client = client
        log.info("Redis cache backend aktif: %s", url.split("@")[-1])
    except Exception as e:  # noqa: BLE001 — bağlantı hatası → DB fallback
        log.warning("Redis bağlantısı başarısız (%s) — DB cache'e düşülüyor", type(e).__name__)
        _client = None
    return _client


def set_redis_client_for_test(client: Any) -> None:
    """Test enjeksiyonu — fake/fakeredis client'ı zorla."""
    global _client, _client_initialized
    _client = client
    _client_initialized = True


def reset_redis_client() -> None:
    """Test temizliği — bir sonraki get_redis_client yeniden kursun."""
    global _client, _client_initialized
    _client = None
    _client_initialized = False


def _now_ts() -> int:
    # datetime.now yerine time.time — store ile tutarlı UTC unix.
    import time
    return int(time.time())


def redis_get(client: Any, *, source: str, key: str) -> dict[str, Any] | None:
    """Mantıksal TTL'e saygı duyarak değer döner (süresi geçti → None)."""
    raw = client.get(_redis_key(source, key))
    if raw is None:
        return None
    try:
        env = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(env, dict) or "v" not in env:
        return None
    if int(env.get("exp", 0)) <= _now_ts():
        return None
    return env["v"]


def redis_get_stale(client: Any, *, source: str, key: str) -> dict[str, Any] | None:
    """TTL'i yok sayarak (henüz evict edilmemiş) değeri döner."""
    raw = client.get(_redis_key(source, key))
    if raw is None:
        return None
    try:
        env = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(env, dict) or "v" not in env:
        return None
    return env["v"]


def redis_set(
    client: Any, *, source: str, key: str, value: dict[str, Any], ttl_seconds: int,
) -> None:
    """Envelope'u stale-retention TTL'iyle yaz (logical exp envelope içinde)."""
    from app.core.config import get_settings
    retention = max(ttl_seconds, get_settings().redis_stale_retention_seconds)
    env = json.dumps({"v": value, "exp": _now_ts() + ttl_seconds})
    client.setex(_redis_key(source, key), retention, env)
