"""EmailChannel — stub mod + konu çıkarımı (stdlib, network'siz)."""
from __future__ import annotations

from app.notifications.email import EmailChannel, _subject_from_text


def test_stub_when_unconfigured() -> None:
    ch = EmailChannel()  # host/from/to boş
    assert ch.is_configured() is False
    res = ch.send("test mesajı")
    assert res.success is True
    assert res.stub is True
    assert res.channel == "email"


def test_stub_when_missing_recipient() -> None:
    ch = EmailChannel(host="smtp.x.com", from_addr="a@x.com")  # to yok
    assert ch.is_configured() is False
    res = ch.send("merhaba")
    assert res.stub is True


def test_is_configured_true_when_complete() -> None:
    ch = EmailChannel(host="smtp.x.com", from_addr="a@x.com", default_to="b@y.com")
    assert ch.is_configured() is True


def test_subject_from_text_strips_markdown() -> None:
    assert _subject_from_text("# Başlık\nikinci satır") == "Başlık"
    assert _subject_from_text("**kalın** uyarı") == "kalın** uyarı".lstrip("*")
    assert _subject_from_text("") == "tactic11 bildirim"
    assert _subject_from_text("   \n  ") == "tactic11 bildirim"


def test_subject_truncated() -> None:
    long = "x" * 300
    assert len(_subject_from_text(long)) == 120
