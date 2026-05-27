"""Engine sonuçları için snapshot-keyed cache.

Engine compute mikrosaniyelik; asıl kazanım:
- **Idempotency:** aynı snapshot + aynı parametreler = aynı bayt yanıt
- **Observability:** hangi engine ne zaman çağrıldı (cache satırları)
- **Tutarlılık:** sync arası iki çağrı arasında veri değişmez sayılır → bayt
  düzeyinde aynı yanıt

Mekanik: `cache_entries.source = 'engine_result'`, key snapshot.id ile
prefix'lenir. Yeni sync = yeni snapshot = yeni key prefix → eski cache
satırları "ölü" kalır (TTL'le temizlenir), yeni hesaplar yeni snapshot
altında biriker. AI cache'ten (Claude yanıtları) bağımsız bir source.

Sözleşme:
- `compute_fn` engine sonucunu serileştirilmiş `dict` (JSON-friendly)
  döndürür — engine_result_to_dict çıktısı tipik kullanım
- Snapshot yoksa cache devre dışı (kararlı bir referans yok) — direkt
  compute_fn çağrılır
- `key_parts` çağıran taraf belirler — endpoint + path params + query params
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.data.cache.store import cache_get, cache_set
from app.db import models

log = get_logger(__name__)

_CACHE_SOURCE = "engine_result"
# Engine sonuçları sync'ler arası kararlı; TTL geniş (7 gün) — yeni snapshot
# zaten yeni key oluşturuyor, eski satırlar TTL'le temizlenir.
_DEFAULT_TTL_SECONDS = 7 * 86_400


def _latest_snapshot_id(session: Session, *, sport: str) -> int | None:
    """Sport için en yeni snapshot.id; sport-içi kayıt yoksa None."""
    return session.execute(
        select(models.Snapshot.id)
        .where(models.Snapshot.sport == sport)
        .order_by(desc(models.Snapshot.created_at))
        .limit(1)
    ).scalar_one_or_none()


def engine_cached(
    session: Session,
    *,
    sport: str,
    key_parts: tuple[str | int, ...],
    compute_fn: Callable[[], dict[str, Any]],
    ttl_seconds: int = _DEFAULT_TTL_SECONDS,
) -> tuple[dict[str, Any], bool]:
    """Snapshot-keyed cache wrapper. Döner: (result, was_cached).

    `key_parts` endpoint + tüm girdileri ifade etmeli (route, path params,
    query params). Snapshot.id otomatik eklenir → sync arası yeni snapshot
    cache'i deterministik biçimde geçersiz kılar.
    """
    snap_id = _latest_snapshot_id(session, sport=sport)
    if snap_id is None:
        # Kararlı referans yok — cache atla, doğrudan hesap
        log.debug("engine_cache: snapshot yok, bypass (parts=%s)", key_parts)
        return compute_fn(), False

    key = "snap=" + str(snap_id) + ":" + ":".join(str(p) for p in key_parts)
    cached = cache_get(session, source=_CACHE_SOURCE, key=key)
    if cached is not None:
        log.info("engine_cache hit: %s", key)
        return cached, True

    log.info("engine_cache miss: %s", key)
    result = compute_fn()
    cache_set(session, source=_CACHE_SOURCE, key=key, value=result, ttl_seconds=ttl_seconds)
    session.commit()
    return result, False
