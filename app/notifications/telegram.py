"""Telegram bot notification (Faz 5 #19).

Pure HTTP (httpx) — Telegram SDK gerektirmez. Env vars:
- TELEGRAM_BOT_TOKEN
- TELEGRAM_CHAT_ID (default hedef; send(recipient=...) ile override)

Token veya chat_id boşsa stub mod (no network call).
"""
from __future__ import annotations

from typing import Any

import httpx

from app.core.logging import get_logger
from app.notifications.base import NotificationChannel, NotificationResult

log = get_logger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org"


class TelegramChannel(NotificationChannel):
    """Telegram Bot sendMessage wrapper."""

    name = "telegram"

    def __init__(
        self,
        *,
        bot_token: str = "",
        default_chat_id: str = "",
        api_base: str = TELEGRAM_API_BASE,
    ) -> None:
        self._token = bot_token
        self._default_chat_id = default_chat_id
        self._api_base = api_base.rstrip("/")

    def is_configured(self) -> bool:
        return bool(self._token and self._default_chat_id)

    def send(
        self,
        text: str,
        *,
        recipient: str | None = None,
        timeout_seconds: float = 10.0,
    ) -> NotificationResult:
        chat_id = recipient or self._default_chat_id

        if not self._token or not chat_id:
            log.info("telegram send STUB — token veya chat_id eksik")
            return NotificationResult(
                channel=self.name,
                success=True,
                stub=True,
                extra={"reason": "missing_credentials"},
            )

        url = f"{self._api_base}/bot{self._token}/sendMessage"
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }
        try:
            r = httpx.post(url, json=payload, timeout=timeout_seconds)
        except httpx.HTTPError as e:
            log.warning("telegram send hata: %s", e)
            return NotificationResult(
                channel=self.name, success=False, error=str(e),
            )
        if r.status_code >= 400:
            return NotificationResult(
                channel=self.name, success=False,
                error=f"HTTP {r.status_code}: {r.text[:200]}",
            )
        try:
            body = r.json()
        except ValueError:
            return NotificationResult(
                channel=self.name, success=False,
                error="JSON parse failed",
            )
        if not body.get("ok"):
            return NotificationResult(
                channel=self.name, success=False,
                error=str(body.get("description") or body),
            )
        msg_id = str((body.get("result") or {}).get("message_id") or "")
        return NotificationResult(
            channel=self.name,
            success=True,
            message_id=msg_id or None,
            extra={"chat_id": chat_id},
        )
