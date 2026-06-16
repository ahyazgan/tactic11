"""Notifier — birden çok kanala paralel olmayan ardışık mesaj dağıtımı (Faz 5 #19).

`build_default_notifier()` settings'ten kanal listesini kurar
(`TelegramChannel` + `WhatsAppChannel`). Kanal env'i eksikse stub mod —
hâlâ kayda alınır, success=True + stub=True döner.

Pre-match brief / live alert gibi orchestrator'lar `notifier.send_all(text)`
çağırır; per-kanal NotificationResult dict'i alır, log'lar / DB'ye
yazabilir.
"""
from __future__ import annotations

from app.core.logging import get_logger
from app.notifications.base import NotificationChannel, NotificationResult

log = get_logger(__name__)


class Notifier:
    """Birden çok kanala mesaj dağıtım orchestrator'ı."""

    def __init__(self, channels: list[NotificationChannel] | None = None) -> None:
        self._channels: list[NotificationChannel] = list(channels or [])

    @property
    def channels(self) -> list[NotificationChannel]:
        return list(self._channels)

    def add(self, channel: NotificationChannel) -> None:
        self._channels.append(channel)

    def active_channel_names(self) -> list[str]:
        """Configured (gerçek mod) olan kanal adları."""
        return [c.name for c in self._channels if c.is_configured()]

    def send_all(
        self,
        text: str,
        *,
        timeout_seconds: float = 10.0,
    ) -> dict[str, NotificationResult]:
        """Tüm kayıtlı kanallara aynı mesajı sırayla gönder.

        Bir kanalın hatası diğerlerini bloklamaz — her kanal bağımsız
        NotificationResult döner; dict key = channel name.
        """
        out: dict[str, NotificationResult] = {}
        for ch in self._channels:
            try:
                result = ch.send(text, timeout_seconds=timeout_seconds)
            except Exception as e:  # noqa: BLE001 — kanal-bazlı izolasyon
                log.warning("notifier channel=%s exception: %s", ch.name, e)
                result = NotificationResult(
                    channel=ch.name, success=False,
                    error=f"unhandled: {type(e).__name__}: {e}",
                )
            out[ch.name] = result
            if result.success and not result.stub:
                log.info(
                    "notifier sent channel=%s msg_id=%s",
                    ch.name, result.message_id,
                )
            elif result.stub:
                log.debug("notifier stub channel=%s", ch.name)
            else:
                log.warning(
                    "notifier fail channel=%s error=%s",
                    ch.name, result.error,
                )
        return out


def build_default_notifier() -> Notifier:
    """Settings'ten kanal config'lerini okuyup Notifier kur.

    Settings'te alan yoksa boş string → kanal stub modda çalışır.
    """
    from app.core.config import get_settings
    from app.notifications.email import EmailChannel
    from app.notifications.telegram import TelegramChannel
    from app.notifications.whatsapp import WhatsAppChannel

    s = get_settings()
    return Notifier([
        TelegramChannel(
            bot_token=getattr(s, "telegram_bot_token", ""),
            default_chat_id=getattr(s, "telegram_chat_id", ""),
        ),
        WhatsAppChannel(
            account_sid=getattr(s, "twilio_account_sid", ""),
            auth_token=getattr(s, "twilio_auth_token", ""),
            from_number=getattr(s, "whatsapp_from", ""),
            default_to=getattr(s, "whatsapp_to", ""),
        ),
        EmailChannel(
            host=getattr(s, "smtp_host", ""),
            port=getattr(s, "smtp_port", 587),
            username=getattr(s, "smtp_username", ""),
            password=getattr(s, "smtp_password", ""),
            from_addr=getattr(s, "smtp_from", ""),
            default_to=getattr(s, "smtp_to", ""),
            use_tls=getattr(s, "smtp_use_tls", True),
        ),
    ])
