"""NotificationChannel arayüzü (Faz 5 #19).

Stub-aware tasarım — credential yoksa kanal `is_configured()` False döner,
`send()` çağrısı `NotificationResult(success=True, stub=True)` ile sessizce
geçer. Üretim ortamında env vars set'lendiğinde aynı API gerçek mesajı atar.

Anthropic stub mod ile aynı felsefe: kütüphane/secret eksik = sistem
çalışmaya devam, "STUB" bayrağı log'da görünür.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class NotificationResult:
    """Bir kanal send sonucu — orchestrator response dict'i için JSON-uyumlu."""

    channel: str
    success: bool
    stub: bool = False
    message_id: str | None = None
    error: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class NotificationChannel(ABC):
    """Tek kanal sözleşmesi (Telegram, WhatsApp, ileride email, vb).

    `is_configured()` → channel env vars hazır mı?
    `send(text, recipient=None)` → mesaj gönder veya stub kabul et.
    """

    name: str = ""

    @abstractmethod
    def is_configured(self) -> bool:
        """Credential ve hedef bilgisi var mı (env vars hazırsa True)."""

    @abstractmethod
    def send(
        self,
        text: str,
        *,
        recipient: str | None = None,
        timeout_seconds: float = 10.0,
    ) -> NotificationResult:
        """Mesajı kanala gönder. Stub mod aktifse stub=True ile success=True dön.

        `recipient` opsiyonel — default kanal env'deki hedef
        (TELEGRAM_CHAT_ID / WHATSAPP_TO). Override edilirse onu kullanır.
        Network hatası → success=False + error.
        """
