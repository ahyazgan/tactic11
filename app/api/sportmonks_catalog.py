"""Sportmonks zengin veri uçları + medya proxy.

Frontend'in puan durumu / kadro / fikstür sayfalarını CANLI Sportmonks verisine
bağlar. DATA_SOURCE=sportmonks + SPORTMONKS_API_KEY gerekir; yoksa 503 döner
(frontend demo moduna düşer). Tüm uçlar dataclass'ları düz JSON'a serialize eder.

Medya proxy (/media/sportmonks/...) cdn.sportmonks.com görsellerini SUNUCU
tarafında çeker → tarayıcı engelli CDN'e hiç gitmez (self-host kuralı). Bytes
process-içi küçük LRU'da tutulur; uzun Cache-Control ile tarayıcı da cache'ler.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import asdict
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from app.core.config import get_settings
from app.core.logging import get_logger
from app.data.sources.sportmonks import Sportmonks

log = get_logger(__name__)

# Protected (X-API-Key) router — veri uçları
sportmonks_router = APIRouter(prefix="/sm", tags=["sportmonks"])

# Medya proxy ayrı router — AUTH YOK (<img src> header gönderemez). app'e mount.
media_router = APIRouter(prefix="/media", tags=["media"])

_CDN_HOST = "cdn.sportmonks.com"
_CDN_BASE = f"https://{_CDN_HOST}"


def _client() -> Sportmonks:
    """Anahtar varsa Sportmonks; yoksa 503 (frontend demo'ya düşer)."""
    s = get_settings()
    if s.data_source.strip().lower() != "sportmonks" or not s.sportmonks_api_key:
        raise HTTPException(
            status_code=503,
            detail="Sportmonks etkin değil (DATA_SOURCE=sportmonks + SPORTMONKS_API_KEY).",
        )
    return Sportmonks()


def _proxy_photo(url: str | None) -> str | None:
    """cdn.sportmonks.com URL'sini kendi medya proxy yolumuza çevir."""
    if not url:
        return None
    if _CDN_HOST in url:
        path = url.split(_CDN_HOST, 1)[1].lstrip("/")
        return f"/media/sportmonks/{path}"
    return url


def _safe(fn, *args, **kwargs):
    """Sportmonks çağrısını sar: erişim/ağ hatasını 502'ye çevir (UI degrade)."""
    try:
        return fn(*args, **kwargs)
    except httpx.HTTPStatusError as e:  # 403 abonelik kapsamı vb.
        code = e.response.status_code
        msg = ""
        try:
            msg = e.response.json().get("message", "")[:160]
        except Exception:  # noqa: BLE001
            pass
        raise HTTPException(status_code=502, detail=f"Sportmonks {code}: {msg}") from e
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Sportmonks ağ hatası: {e}") from e


@sportmonks_router.get("/leagues", summary="Abone olunan ligler (Sportmonks)")
def sm_leagues() -> list[dict[str, Any]]:
    sm = _client()
    return [lg.model_dump() for lg in _safe(sm.get_leagues)]


@sportmonks_router.get("/standings", summary="Lig puan durumu (Sportmonks, canlı)")
def sm_standings(
    league_id: int = Query(..., description="Sportmonks lig id (ör. 600 Süper Lig)"),
    season: int = Query(..., description="Sezon başlangıç yılı (ör. 2025)"),
) -> dict[str, Any]:
    sm = _client()
    season_id = _safe(sm._resolve_season_id, league_id, season)
    if season_id is None:
        raise HTTPException(
            status_code=404,
            detail=f"Lig {league_id} / sezon {season} bulunamadı (abonelik kapsamı?).",
        )
    rows = _safe(sm.get_standings, season_id)
    return {"season_id": season_id, "rows": [asdict(r) for r in rows]}


@sportmonks_router.get("/squad", summary="Takım sezon kadrosu + sezon-stat + foto")
def sm_squad(
    team_id: int = Query(..., description="Sportmonks takım id"),
    season: int = Query(..., description="Sezon başlangıç yılı"),
) -> list[dict[str, Any]]:
    sm = _client()
    members = _safe(sm.get_squad_season, team_id, season)
    out: list[dict[str, Any]] = []
    for m in members:
        d = asdict(m)
        d["photo_url"] = _proxy_photo(m.photo_url)
        out.append(d)
    return out


@sportmonks_router.get("/schedule", summary="Takım programı (bitenler + yaklaşanlar)")
def sm_schedule(
    team_id: int = Query(..., description="Sportmonks takım id"),
    last_n: int = Query(10, ge=1, le=50),
) -> dict[str, Any]:
    sm = _client()
    sched = _safe(sm.get_team_schedule, team_id, last_n)
    return {
        "finished": [m.model_dump(mode="json") for m in sched["finished"]],
        "upcoming": [m.model_dump(mode="json") for m in sched["upcoming"]],
        "team_names": {str(k): v for k, v in sched["team_names"].items()},
    }


# ── Medya proxy ───────────────────────────────────────────────────────────────
_MEDIA_CACHE: "OrderedDict[str, tuple[bytes, str]]" = OrderedDict()
_MEDIA_CACHE_MAX = 256  # process-içi küçük LRU


@media_router.get("/sportmonks/{path:path}", summary="Sportmonks görsel proxy (self-host)")
def media_sportmonks(path: str) -> Response:
    """cdn.sportmonks.com görselini sunucu tarafından çekip döndür.

    Yalnız bu CDN'e izinli (SSRF güvenliği). Bytes LRU'da + tarayıcıda cache'lenir.
    """
    # Path temizliği — yalnız cdn.sportmonks.com altındaki göreli yol.
    safe_path = path.lstrip("/")
    if ".." in safe_path or safe_path.startswith("http"):
        raise HTTPException(status_code=400, detail="Geçersiz medya yolu.")

    if safe_path in _MEDIA_CACHE:
        body, ctype = _MEDIA_CACHE.pop(safe_path)
        _MEDIA_CACHE[safe_path] = (body, ctype)  # LRU: en sona taşı
        return Response(content=body, media_type=ctype,
                        headers={"Cache-Control": "public, max-age=604800"})

    url = f"{_CDN_BASE}/{safe_path}"
    s = get_settings()
    try:
        with httpx.Client(timeout=s.http_timeout_seconds) as c:
            r = c.get(url)
            r.raise_for_status()
            body = r.content
            ctype = r.headers.get("content-type", "image/png")
    except httpx.HTTPError as e:
        raise HTTPException(status_code=404, detail=f"Görsel alınamadı: {e}") from e

    _MEDIA_CACHE[safe_path] = (body, ctype)
    if len(_MEDIA_CACHE) > _MEDIA_CACHE_MAX:
        _MEDIA_CACHE.popitem(last=False)  # en eskiyi at
    return Response(content=body, media_type=ctype,
                    headers={"Cache-Control": "public, max-age=604800"})
