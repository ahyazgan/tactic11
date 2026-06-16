"""WhatsApp notification — Twilio (Faz 5 #19).

Twilio SDK gerektirmez (pure httpx + Basic auth). Env vars:
- TWILIO_ACCOUNT_SID
- TWILIO_AUTH_TOKEN
- WHATSAPP_FROM (örn. `whatsapp:+14155238886` Twilio sandbox sender)
- WHATSAPP_TO   (default hedef; send(recipient=...) ile override)

Herhangi biri boşsa stub mod.
"""
from __future__ import annotations

import httpx

from app.core.logging import get_logger
from app.notifications.base import NotificationChannel, NotificationResult

log = get_logger(__name__)

TWILIO_API_BASE = "https://api.twilio.com"


class WhatsAppChannel(NotificationChannel):
    """Twilio WhatsApp Messages.json wrapper."""

    name = "whatsapp"

    def __init__(
        self,
        *,
        account_sid: str = "",
        auth_token: str = "",
        from_number: str = "",
        default_to: str = "",
        api_base: str = TWILIO_API_BASE,
    ) -> None:
        self._sid = account_sid
        self._token = auth_token
        self._from = from_number
        self._default_to = default_to
        self._api_base = api_base.rstrip("/")

    def is_configured(self) -> bool:
        return bool(
            self._sid and self._token and self._from and self._default_to,
        )

    def send(
        self,
        text: str,
        *,
        recipient: str | None = None,
        timeout_seconds: float = 10.0,
    ) -> NotificationResult:
        to = recipient or self._default_to

        if not all((self._sid, self._token, self._from, to)):
            log.info(
                "whatsapp send STUB — Twilio credential veya hedef eksik",
            )
            return NotificationResult(
                channel=self.name,
                success=True,
                stub=True,
                extra={"reason": "missing_credentials"},
            )

        url = (
            f"{self._api_base}/2010-04-01/Accounts/{self._sid}/Messages.json"
        )
        data = {"From": self._from, "To": to, "Body": text}
        try:
            r = httpx.post(
                url,
                data=data,
                auth=(self._sid, self._token),
                timeout=timeout_seconds,
            )
        except httpx.HTTPError as e:
            log.warning("whatsapp send hata: %s", e)
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
        # Twilio sends back sid + status
        msg_id = body.get("sid")
        status = body.get("status")
        if not msg_id:
            return NotificationResult(
                channel=self.name, success=False,
                error=str(body.get("message") or "no sid in response"),
            )
        return NotificationResult(
            channel=self.name,
            success=True,
            message_id=msg_id,
            extra={"to": to, "status": status},
        )
