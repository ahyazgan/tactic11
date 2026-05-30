"""Notification channels + dispatcher + endpoint testleri (Faz 5 #19)."""
from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from app.notifications import (
    NotificationChannel,
    NotificationResult,
    Notifier,
    TelegramChannel,
    WhatsAppChannel,
    build_default_notifier,
)


# --------------------------------------------------------------------------- #
# Base ABC + NotificationResult
# --------------------------------------------------------------------------- #


def test_notification_result_frozen() -> None:
    r = NotificationResult(channel="x", success=True)
    with pytest.raises(Exception):
        r.success = False  # type: ignore[misc]


def test_notification_result_defaults() -> None:
    r = NotificationResult(channel="x", success=True)
    assert r.stub is False
    assert r.message_id is None
    assert r.error is None
    assert r.extra == {}


def test_notification_channel_is_abstract() -> None:
    """ABC instantiation engellenmiştir."""
    with pytest.raises(TypeError):
        NotificationChannel()  # type: ignore[abstract]


# --------------------------------------------------------------------------- #
# TelegramChannel
# --------------------------------------------------------------------------- #


def test_telegram_stub_when_token_missing() -> None:
    ch = TelegramChannel(bot_token="", default_chat_id="123")
    assert not ch.is_configured()
    r = ch.send("hi")
    assert r.success and r.stub
    assert r.extra["reason"] == "missing_credentials"


def test_telegram_stub_when_chat_id_missing() -> None:
    ch = TelegramChannel(bot_token="abc", default_chat_id="")
    assert not ch.is_configured()
    r = ch.send("hi")
    assert r.success and r.stub


def test_telegram_configured_when_both_set() -> None:
    ch = TelegramChannel(bot_token="abc", default_chat_id="123")
    assert ch.is_configured()


def test_telegram_send_success(monkeypatch: pytest.MonkeyPatch) -> None:
    ch = TelegramChannel(bot_token="t", default_chat_id="c")

    class FakeResp:
        status_code = 200
        text = ""
        def json(self) -> dict:
            return {"ok": True, "result": {"message_id": 42}}

    monkeypatch.setattr(httpx, "post", lambda *a, **kw: FakeResp())
    r = ch.send("hi")
    assert r.success and not r.stub
    assert r.message_id == "42"


def test_telegram_send_recipient_override(monkeypatch: pytest.MonkeyPatch) -> None:
    ch = TelegramChannel(bot_token="t", default_chat_id="default-c")
    captured = {}

    class FakeResp:
        status_code = 200
        text = ""
        def json(self) -> dict:
            return {"ok": True, "result": {"message_id": 1}}

    def fake_post(url, json=None, timeout=None, **kw):
        captured["chat_id"] = json["chat_id"]
        return FakeResp()

    monkeypatch.setattr(httpx, "post", fake_post)
    ch.send("hi", recipient="override-c")
    assert captured["chat_id"] == "override-c"


def test_telegram_send_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    ch = TelegramChannel(bot_token="t", default_chat_id="c")

    def fake_post(*a, **kw):
        raise httpx.ConnectError("dns fail")

    monkeypatch.setattr(httpx, "post", fake_post)
    r = ch.send("hi")
    assert not r.success
    assert "dns fail" in r.error


def test_telegram_send_4xx(monkeypatch: pytest.MonkeyPatch) -> None:
    ch = TelegramChannel(bot_token="t", default_chat_id="c")

    class FakeResp:
        status_code = 400
        text = "Bad Request"
        def json(self) -> dict: return {}

    monkeypatch.setattr(httpx, "post", lambda *a, **kw: FakeResp())
    r = ch.send("hi")
    assert not r.success
    assert "400" in r.error


def test_telegram_send_ok_false_in_body(monkeypatch: pytest.MonkeyPatch) -> None:
    ch = TelegramChannel(bot_token="t", default_chat_id="c")

    class FakeResp:
        status_code = 200
        text = ""
        def json(self) -> dict:
            return {"ok": False, "description": "Forbidden"}

    monkeypatch.setattr(httpx, "post", lambda *a, **kw: FakeResp())
    r = ch.send("hi")
    assert not r.success
    assert "Forbidden" in r.error


# --------------------------------------------------------------------------- #
# WhatsAppChannel (Twilio)
# --------------------------------------------------------------------------- #


def test_whatsapp_stub_when_any_missing() -> None:
    cases = [
        dict(account_sid="", auth_token="t", from_number="f", default_to="d"),
        dict(account_sid="s", auth_token="", from_number="f", default_to="d"),
        dict(account_sid="s", auth_token="t", from_number="", default_to="d"),
        dict(account_sid="s", auth_token="t", from_number="f", default_to=""),
    ]
    for kw in cases:
        ch = WhatsAppChannel(**kw)
        assert not ch.is_configured()
        r = ch.send("hi")
        assert r.success and r.stub


def test_whatsapp_configured_when_all_set() -> None:
    ch = WhatsAppChannel(
        account_sid="s", auth_token="t",
        from_number="whatsapp:+1", default_to="whatsapp:+90",
    )
    assert ch.is_configured()


def test_whatsapp_send_success(monkeypatch: pytest.MonkeyPatch) -> None:
    ch = WhatsAppChannel(
        account_sid="s", auth_token="t",
        from_number="whatsapp:+1", default_to="whatsapp:+90",
    )

    class FakeResp:
        status_code = 201
        text = ""
        def json(self) -> dict:
            return {"sid": "SM123abc", "status": "queued"}

    monkeypatch.setattr(httpx, "post", lambda *a, **kw: FakeResp())
    r = ch.send("hi")
    assert r.success and not r.stub
    assert r.message_id == "SM123abc"
    assert r.extra["status"] == "queued"


def test_whatsapp_send_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    ch = WhatsAppChannel(
        account_sid="s", auth_token="t",
        from_number="f", default_to="d",
    )

    def fake_post(*a, **kw):
        raise httpx.ReadTimeout("timeout")

    monkeypatch.setattr(httpx, "post", fake_post)
    r = ch.send("hi")
    assert not r.success
    assert "timeout" in r.error


# --------------------------------------------------------------------------- #
# Notifier (dispatcher)
# --------------------------------------------------------------------------- #


class _DummyChannel(NotificationChannel):
    name = "dummy"

    def __init__(self, *, configured: bool = True, raises: bool = False) -> None:
        self._cfg = configured
        self._raises = raises

    def is_configured(self) -> bool:
        return self._cfg

    def send(
        self, text: str, *, recipient: str | None = None,
        timeout_seconds: float = 10.0,
    ) -> NotificationResult:
        if self._raises:
            raise RuntimeError("kanal patladı")
        return NotificationResult(
            channel=self.name, success=self._cfg, stub=not self._cfg,
        )


def test_notifier_send_all_returns_per_channel_results() -> None:
    n = Notifier([_DummyChannel(), _DummyChannel()])
    results = n.send_all("hi")
    assert len(results) == 1  # 2 kanal aynı isimle — son yazan kazanır
    # Farklı isimlendirme ile tekrar test
    a, b = _DummyChannel(), _DummyChannel()
    a.name, b.name = "a", "b"  # type: ignore[misc]
    n2 = Notifier([a, b])
    r2 = n2.send_all("hi")
    assert set(r2.keys()) == {"a", "b"}


def test_notifier_channel_exception_isolated() -> None:
    good = _DummyChannel(configured=True)
    bad = _DummyChannel(configured=True, raises=True)
    good.name, bad.name = "good", "bad"  # type: ignore[misc]
    n = Notifier([good, bad])
    results = n.send_all("hi")
    assert results["good"].success
    assert not results["bad"].success
    assert "patladı" in results["bad"].error


def test_notifier_active_channel_names() -> None:
    on = _DummyChannel(configured=True)
    off = _DummyChannel(configured=False)
    on.name, off.name = "on", "off"  # type: ignore[misc]
    n = Notifier([on, off])
    assert n.active_channel_names() == ["on"]


def test_notifier_add_channel() -> None:
    n = Notifier()
    assert n.channels == []
    ch = _DummyChannel()
    n.add(ch)
    assert n.channels == [ch]


def test_build_default_notifier_creates_telegram_and_whatsapp() -> None:
    """Settings'ten 2 kanal kurulur — env yokken ikisi de stub."""
    n = build_default_notifier()
    assert len(n.channels) == 2
    names = [c.name for c in n.channels]
    assert "telegram" in names
    assert "whatsapp" in names


# --------------------------------------------------------------------------- #
# Endpoint testleri
# --------------------------------------------------------------------------- #


def test_endpoint_status_returns_channel_list() -> None:
    from app.api.notifications import notifications_status
    out = notifications_status()
    assert out["total_channels"] == 2
    assert "channels" in out
    # Env vars yokken hiç active değil
    assert out["active_channels"] == []


def test_endpoint_test_returns_stub_results_when_no_creds() -> None:
    from app.api.notifications import notifications_test
    out = notifications_test(payload={})
    assert "results" in out
    for r in out["results"].values():
        assert r["success"]
        assert r["stub"]  # env yokken hepsi stub


def test_endpoint_test_uses_custom_text() -> None:
    from app.api.notifications import notifications_test
    out = notifications_test(payload={"text": "özel mesaj"})
    assert out["text"] == "özel mesaj"


def test_endpoint_test_default_text_has_timestamp() -> None:
    from app.api.notifications import notifications_test
    out = notifications_test(payload={})
    assert "manager2" in out["text"]
    assert "UTC" in out["text"]
