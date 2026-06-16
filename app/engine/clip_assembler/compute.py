"""Clip Assembler — bir kararın etrafındaki kısa video kesit metası.

Gerçek video kaynağı henüz yok (broadcast/CMS entegrasyonu pilot kulüpte
gelir). Bu engine pure-compute olarak "şu dakikada şu pencere için clip"
URL'i + thumbnail + güven seviyesini üretir. Frontend PrimaryBanner
"▶ İzle" butonu bu URL'i açar (mevcut değilse "yakında" placeholder).

Tasarım:
- Karar verilen dakikanın ±N saniyesi (default: -30/+5)
- URL template env'den (`CLIP_BASE_URL`) veya fallback stub
- available: video kaynağı configured mı (gerçek pilot'ta True olur)
- decision_type'a göre confidence ipucu (substitution yüksek, tactical
  daha düşük — çünkü sub için 1 net oyuncu/dakika var; taktik için
  pencere geniş)

Multi-tenant: tenant_id URL'e gömülür → her kulüp kendi video bucket'ına
yönlendirilir.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from app.audit import AuditRecord, EngineResult

ENGINE_NAME = "engine.clip_assembler"
ENGINE_VERSION = "1"

DEFAULT_BACK_SECONDS = 30
DEFAULT_FORWARD_SECONDS = 5
# decision_type → öneri pencere uzunluğu farkı (saniye)
_TYPE_BACK_SECONDS: dict[str, int] = {
    "substitution": 20,         # değişiklik karar anı net
    "formation_change": 45,     # tactical shift pencere geniş
    "tactical_instruction": 35,
    "set_piece": 15,            # standart top kısa
    "other": DEFAULT_BACK_SECONDS,
}


@dataclass(frozen=True)
class ClipReport:
    match_external_id: int
    minute: float
    decision_type: str
    # Pencere
    start_second: int
    end_second: int
    duration_seconds: int
    # Video kaynağı
    clip_id: str               # deterministic ID — frontend cache + idempotent
    video_url: str | None      # base url + path; None → "yakında"
    thumbnail_url: str | None
    poster_minute_label: str   # "67' 30''" gibi insan-okur etiket
    available: bool            # video kaynağı configured mi
    source: str                # "stub" | "broadcast" | "cdn"


def _clip_id(match_id: int, minute: float, decision_type: str) -> str:
    """Deterministic ID — aynı (match, minute, type) için aynı clip."""
    # Minute'u 0.1 sn doğruluğunda yuvarla
    m_int = int(round(minute * 60))  # saniye
    return f"clip-{match_id}-{m_int}-{decision_type[:3]}"


def _minute_label(minute: float) -> str:
    """45.5 → "45' 30''" formatı."""
    whole = int(minute)
    sec = int(round((minute - whole) * 60))
    return f"{whole}' {sec:02d}\""


def compute_clip_for_decision(
    *,
    match_external_id: int,
    minute: float,
    decision_type: str = "other",
    tenant_id: str = "default",
    back_seconds: int | None = None,
    forward_seconds: int = DEFAULT_FORWARD_SECONDS,
) -> EngineResult[ClipReport]:
    """Bir karar için clip metası.

    URL template `CLIP_BASE_URL` env'den okunur. Set'liyse `available=True`,
    değilse `available=False` (frontend "yakında" rozetiyle gösterir).
    """
    back = back_seconds if back_seconds is not None else _TYPE_BACK_SECONDS.get(
        decision_type, DEFAULT_BACK_SECONDS,
    )
    minute_seconds = int(round(minute * 60))
    start_s = max(0, minute_seconds - back)
    end_s = minute_seconds + forward_seconds
    duration = end_s - start_s

    cid = _clip_id(match_external_id, minute, decision_type)
    base = os.environ.get("CLIP_BASE_URL", "").rstrip("/")
    available = bool(base)
    if available:
        video_url: str | None = (
            f"{base}/{tenant_id}/{match_external_id}/{start_s}-{end_s}.mp4"
        )
        thumbnail_url: str | None = (
            f"{base}/{tenant_id}/{match_external_id}/{start_s}-{end_s}.jpg"
        )
        source = "broadcast"
    else:
        video_url = None
        thumbnail_url = None
        source = "stub"

    report = ClipReport(
        match_external_id=match_external_id,
        minute=minute, decision_type=decision_type,
        start_second=start_s, end_second=end_s, duration_seconds=duration,
        clip_id=cid,
        video_url=video_url, thumbnail_url=thumbnail_url,
        poster_minute_label=_minute_label(minute),
        available=available, source=source,
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="match", subject_id=match_external_id,
        metric="clip_assembler",
        value={
            "clip_id": cid, "video_url": video_url,
            "duration_seconds": duration, "available": available,
            "source": source, "label": _minute_label(minute),
        },
        inputs={
            "minute": minute, "decision_type": decision_type,
            "tenant_id": tenant_id, "back_seconds": back,
            "forward_seconds": forward_seconds,
            "clip_base_url_set": available,
        },
        formula=(
            "start = minute*60 - back; end = minute*60 + forward; "
            "url = CLIP_BASE_URL/tenant/match/start-end.mp4"
        ),
    )
    return EngineResult(value=report, audit=audit)
