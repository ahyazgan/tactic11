"""Live alert → bildirim köprüsü: seçim/dedup/severity + dispatch (stub)."""
from __future__ import annotations

from app.engine.live_alerts.compute import LiveAlert, LiveAlertsReport
from app.notifications.alert_dispatch import (
    dispatch_live_alerts,
    format_digest,
    select_dispatchable,
)
from app.notifications.dispatcher import Notifier
from app.notifications.email import EmailChannel


def _report(*alerts: LiveAlert) -> LiveAlertsReport:
    sev = [a.severity for a in alerts]
    return LiveAlertsReport(
        current_minute=63.0,
        total=len(alerts),
        critical=sev.count("critical"),
        warning=sev.count("warning"),
        info=sev.count("info"),
        alerts=alerts,
    )


def test_select_filters_below_threshold() -> None:
    rep = _report(
        LiveAlert("fatigue", "critical", "X yorgun", "f:1"),
        LiveAlert("momentum_break", "warning", "Momentum karşı", "m:1"),
        LiveAlert("data_quality", "info", "Veri gecikmesi", "d:1"),
    )
    # warning eşiği → info elenir, critical+warning kalır
    picked = select_dispatchable(rep, min_severity="warning")
    keys = [a.dedup_key for a in picked]
    assert keys == ["f:1", "m:1"]  # critical önce sıralanır


def test_select_critical_only() -> None:
    rep = _report(
        LiveAlert("fatigue", "critical", "X", "f:1"),
        LiveAlert("momentum_break", "warning", "Y", "m:1"),
    )
    picked = select_dispatchable(rep, min_severity="critical")
    assert [a.dedup_key for a in picked] == ["f:1"]


def test_select_skips_already_sent() -> None:
    rep = _report(
        LiveAlert("fatigue", "critical", "X", "f:1"),
        LiveAlert("card_risk", "warning", "Y", "c:1"),
    )
    picked = select_dispatchable(rep, already_sent={"f:1"})
    assert [a.dedup_key for a in picked] == ["c:1"]


def test_format_digest_empty() -> None:
    assert format_digest(()) == ""


def test_format_digest_includes_minute_and_messages() -> None:
    rep = _report(
        LiveAlert("fatigue", "critical", "Oyuncu yorgun", "f:1"),
    )
    text = format_digest(rep.alerts, minute=70)
    assert "70. dk" in text
    assert "Oyuncu yorgun" in text


def test_dispatch_noop_when_no_new_alerts() -> None:
    rep = _report(LiveAlert("data_quality", "info", "x", "d:1"))
    notifier = Notifier([EmailChannel()])  # stub
    out = dispatch_live_alerts(rep, notifier, min_severity="warning")
    assert out.dispatched == 0
    assert out.skipped_reason == "no_new_alerts"


def test_dispatch_sends_and_updates_already_sent() -> None:
    rep = _report(
        LiveAlert("fatigue", "critical", "Oyuncu kritik yorgun", "f:1"),
        LiveAlert("momentum_break", "warning", "Momentum karşı", "m:1"),
    )
    notifier = Notifier([EmailChannel()])  # stub mod — gerçek gönderim yok
    sent: set[str] = set()
    out = dispatch_live_alerts(rep, notifier, already_sent=sent)
    assert out.dispatched == 2
    assert set(out.sent_dedup_keys) == {"f:1", "m:1"}
    assert sent == {"f:1", "m:1"}
    # email kanalı stub → success + stub
    assert out.channel_results["email"].success is True
    assert out.channel_results["email"].stub is True

    # ikinci çağrı: hepsi already_sent → no-op
    out2 = dispatch_live_alerts(rep, notifier, already_sent=sent)
    assert out2.dispatched == 0
