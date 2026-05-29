"""Notification test + status endpoint'leri (Faz 5 #19).

`GET  /admin/notifications/status` — kanalların kurulu olup olmadığı
`POST /admin/notifications/test` — tüm aktif kanallara test mesajı at

Stub kanallarda gerçek HTTP çağrısı yok; sadece success=True + stub=True.
"""
from __future__ import annotations

from fastapi import APIRouter, Body

from app.notifications import build_default_notifier

router = APIRouter(prefix="/admin", tags=["notifications"])


@router.get("/notifications/status")
def notifications_status() -> dict:
    """Hangi kanallar configured (gerçek mod) — env vars hazır mı."""
    n = build_default_notifier()
    return {
        "total_channels": len(n.channels),
        "active_channels": n.active_channel_names(),
        "channels": [
            {"name": ch.name, "configured": ch.is_configured()}
            for ch in n.channels
        ],
    }


@router.post("/notifications/test")
def notifications_test(
    payload: dict = Body(default_factory=dict),
) -> dict:
    """Tüm kanallara test mesajı at — payload: `{"text": "..."}` (opsiyonel).

    Default mesaj 'manager2 test notification — {timestamp}'.
    Yanıt her kanal için NotificationResult dict'i.
    """
    from datetime import UTC, datetime

    text = (payload or {}).get("text") or (
        "manager2 test notification — "
        + datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    )
    n = build_default_notifier()
    results = n.send_all(text)
    return {
        "text": text,
        "results": {
            name: {
                "channel": r.channel,
                "success": r.success,
                "stub": r.stub,
                "message_id": r.message_id,
                "error": r.error,
                "extra": dict(r.extra),
            }
            for name, r in results.items()
        },
    }
