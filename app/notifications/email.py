"""E-posta (SMTP) notification kanalı — stdlib smtplib (ek bağımlılık yok).

Telegram/WhatsApp ile aynı stub-aware felsefe: SMTP host veya gönderen
adres boşsa kanal stub modda çalışır (no network), `is_configured()` False
döner. Üretimde env vars set'lenince gerçek e-posta atar.

Env vars:
- SMTP_HOST, SMTP_PORT (default 587)
- SMTP_USERNAME, SMTP_PASSWORD (ops — auth gerekmiyorsa boş)
- SMTP_FROM (gönderen adres), SMTP_TO (default hedef)
- SMTP_USE_TLS (default true — STARTTLS)
"""
from __future__ import annotations

import smtplib
from email.message import EmailMessage

from app.core.logging import get_logger
from app.notifications.base import NotificationChannel, NotificationResult

log = get_logger(__name__)

# Mesaj konusu (ilk satır özet olarak kullanılır, yoksa bu sabit).
DEFAULT_SUBJECT = "tactic11 bildirim"


def _subject_from_text(text: str) -> str:
    """İlk satırı konu yap (Markdown başlık işaretlerini sıyır), kısalt."""
    first = (text or "").strip().splitlines()[0] if text.strip() else ""
    first = first.lstrip("#* ").strip()
    if not first:
        return DEFAULT_SUBJECT
    return first[:120]


class EmailChannel(NotificationChannel):
    """SMTP üzerinden düz-metin e-posta gönderir (stdlib)."""

    name = "email"

    def __init__(
        self,
        *,
        host: str = "",
        port: int = 587,
        username: str = "",
        password: str = "",
        from_addr: str = "",
        default_to: str = "",
        use_tls: bool = True,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._from = from_addr
        self._default_to = default_to
        self._use_tls = use_tls

    def is_configured(self) -> bool:
        return bool(self._host and self._from and self._default_to)

    def send(
        self,
        text: str,
        *,
        recipient: str | None = None,
        timeout_seconds: float = 10.0,
    ) -> NotificationResult:
        to_addr = recipient or self._default_to

        if not self._host or not self._from or not to_addr:
            log.info("email send STUB — host/from/to eksik")
            return NotificationResult(
                channel=self.name,
                success=True,
                stub=True,
                extra={"reason": "missing_credentials"},
            )

        msg = EmailMessage()
        msg["From"] = self._from
        msg["To"] = to_addr
        msg["Subject"] = _subject_from_text(text)
        msg.set_content(text)

        try:
            with smtplib.SMTP(self._host, self._port, timeout=timeout_seconds) as smtp:
                if self._use_tls:
                    smtp.starttls()
                if self._username and self._password:
                    smtp.login(self._username, self._password)
                smtp.send_message(msg)
        except (OSError, smtplib.SMTPException) as e:
            log.warning("email send hata: %s", e)
            return NotificationResult(
                channel=self.name, success=False,
                error=f"{type(e).__name__}: {e}",
            )

        return NotificationResult(
            channel=self.name,
            success=True,
            extra={"to": to_addr, "from": self._from},
        )
