"""Live alert → bildirim kanalı köprüsü (J — gönderim katmanı).

`engine/live_alerts` saf olarak "ne zaman, neyi" kararı verir ama gönderimi
yapmaz. Bu modül o boşluğu kapatır: bir `LiveAlertsReport`'tan eşik üstü +
daha önce gönderilmemiş uyarıları seçer, insan-okur mesaja çevirir ve
`Notifier` üzerinden (Telegram/WhatsApp/e-posta) yollar.

Seçim/format saf ve testlenebilir; gerçek gönderim `Notifier`'a delege edilir
(o da kanal-bazlı stub-aware). `already_sent` (dedup_key kümesi) çağıran
tarafında tutulur — aynı uyarı her snapshot'ta tekrar push edilmesin diye.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.engine.live_alerts.compute import LiveAlert, LiveAlertsReport
from app.notifications.base import NotificationResult
from app.notifications.dispatcher import Notifier

# live_alerts ile aynı önem sıralaması (düşük = daha kritik).
_SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}

# Varsayılan: warning ve üstü (critical) telefona gider; info gitmez.
DEFAULT_MIN_SEVERITY = "warning"

_SEVERITY_LABEL = {
    "critical": "🔴 KRİTİK",
    "warning": "🟠 UYARI",
    "info": "🔵 BİLGİ",
}


def select_dispatchable(
    report: LiveAlertsReport,
    *,
    min_severity: str = DEFAULT_MIN_SEVERITY,
    already_sent: set[str] | None = None,
) -> tuple[LiveAlert, ...]:
    """Eşik (min_severity) üstü + henüz gönderilmemiş uyarıları seç.

    Önem sırasına göre (önce critical) sıralar; bilinmeyen severity göz ardı.
    """
    threshold = _SEVERITY_ORDER.get(min_severity, 1)
    sent = already_sent or set()
    picked = [
        a for a in report.alerts
        if a.dedup_key not in sent
        and _SEVERITY_ORDER.get(a.severity, 99) <= threshold
    ]
    picked.sort(key=lambda a: _SEVERITY_ORDER.get(a.severity, 99))
    return tuple(picked)


def format_alert(alert: LiveAlert, *, minute: float | None = None) -> str:
    """Tek uyarıyı tek satır insan-okur mesaja çevir."""
    label = _SEVERITY_LABEL.get(alert.severity, alert.severity.upper())
    minute_part = f"{int(minute)}' " if minute is not None else ""
    return f"{label} {minute_part}— {alert.message}"


def format_digest(
    alerts: tuple[LiveAlert, ...] | list[LiveAlert],
    *,
    minute: float | None = None,
) -> str:
    """Birden çok uyarıyı tek mesaja topla (kanal başına 1 push)."""
    if not alerts:
        return ""
    header = "⚽ Canlı maç uyarısı"
    if minute is not None:
        header += f" — {int(minute)}. dk"
    lines = [header, ""]
    lines.extend(format_alert(a) for a in alerts)
    return "\n".join(lines)


@dataclass(frozen=True)
class DispatchOutcome:
    """Bir dispatch çağrısının sonucu."""

    dispatched: int                              # gönderilen uyarı sayısı
    sent_dedup_keys: tuple[str, ...] = field(default_factory=tuple)
    channel_results: dict[str, NotificationResult] = field(default_factory=dict)
    skipped_reason: str = ""                     # boşsa gönderildi


def dispatch_live_alerts(
    report: LiveAlertsReport,
    notifier: Notifier,
    *,
    min_severity: str = DEFAULT_MIN_SEVERITY,
    already_sent: set[str] | None = None,
    timeout_seconds: float = 10.0,
) -> DispatchOutcome:
    """Eşik üstü yeni uyarıları seç, tek digest mesajı olarak kanallara gönder.

    `already_sent` verilirse (mutable set) gönderilen dedup_key'ler eklenir —
    çağıran sonraki snapshot'ta tekrar göndermesin. Hiç uygun uyarı yoksa
    no-op (`skipped_reason` dolu) döner.
    """
    picked = select_dispatchable(
        report, min_severity=min_severity, already_sent=already_sent,
    )
    if not picked:
        return DispatchOutcome(dispatched=0, skipped_reason="no_new_alerts")

    text = format_digest(picked, minute=report.current_minute)
    results = notifier.send_all(text, timeout_seconds=timeout_seconds)

    keys = tuple(a.dedup_key for a in picked)
    if already_sent is not None:
        already_sent.update(keys)

    return DispatchOutcome(
        dispatched=len(picked),
        sent_dedup_keys=keys,
        channel_results=results,
    )
