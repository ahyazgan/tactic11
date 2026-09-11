"""Haftalık rapor: PDF dizimi + e-posta (ek dosya) + zamanlanmış iş.

Rapor backend backlog #5. İlke: SMTP yoksa "gönderildi" DENMEZ — kanal stub
döner, uç `sent=false, stub=true` verir, iş `sent=False` loglar.
"""
from __future__ import annotations

import email
import smtplib

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.notifications.email import EmailChannel
from app.reports.pdf import REPORTLAB_AVAILABLE
from app.reports.weekly_pdf import build_weekly_report_pdf

pytestmark = pytest.mark.skipif(not REPORTLAB_AVAILABLE, reason="reportlab yok")

REPORT = {
    "club": "Beşiktaş", "week_no": 34, "week_range": "02–08 Haziran",
    "opponent": "Antalyaspor (E)", "score": [2, 1], "xg_for": 1.84, "xg_against": 0.92,
    "kpis": [{"label": "Hazır", "value": "17/24", "delta": "+2"},
             {"label": "Riskli", "value": "3"},
             {"label": "Ort. ACWR", "value": "1.12", "delta": "−0.05"}],
    "sections": [{"title": "Maç", "lines": ["Beşiktaş 2–1 Antalyaspor — galibiyet.", "xG 1.84–0.92"]},
                 {"title": "Sağlık & Yük", "lines": ["3 oyuncu kırmızı: Ndidi (RTP %91)"]},
                 {"title": "Boş bölüm", "lines": []}],
    "note": "Salı toparlanma, Çarşamba yüklenme.\nPerşembe taktik.",
}


def test_builder_returns_pdf() -> None:
    pdf = build_weekly_report_pdf(REPORT)
    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 1500


def test_builder_tolerates_minimal_and_garbage_input() -> None:
    assert build_weekly_report_pdf({})[:4] == b"%PDF"
    junk = {"kpis": ["x", None], "sections": [1, {"title": "a", "lines": [None, " "]}], "score": "2-1"}
    assert build_weekly_report_pdf(junk)[:4] == b"%PDF"


# --- e-posta kanalı: ek dosya ------------------------------------------------ #

class _FakeSMTP:
    sent: list = []

    def __init__(self, host, port, timeout=None):
        self.host = host

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self):
        pass

    def login(self, u, p):
        pass

    def send_message(self, msg):
        _FakeSMTP.sent.append(msg)


def test_email_attaches_pdf_and_uses_subject(monkeypatch) -> None:
    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)
    _FakeSMTP.sent.clear()
    ch = EmailChannel(host="smtp.x", from_addr="a@x", default_to="b@y")
    res = ch.send("gövde", subject="Konu X", attachments=[("r.pdf", b"%PDF-1.4 x", "application/pdf")])
    assert res.success and not res.stub and res.extra["attachments"] == ["r.pdf"]
    msg = _FakeSMTP.sent[0]
    assert msg["Subject"] == "Konu X"
    parsed = email.message_from_bytes(bytes(msg))
    atts = [p for p in parsed.walk() if p.get_filename()]
    assert atts and atts[0].get_filename() == "r.pdf"
    assert atts[0].get_content_type() == "application/pdf"
    assert atts[0].get_payload(decode=True) == b"%PDF-1.4 x"


def test_email_stub_still_lists_attachments() -> None:
    res = EmailChannel().send("x", attachments=[("r.pdf", b"%PDF", "application/pdf")])
    assert res.stub and res.extra["attachments"] == ["r.pdf"]


# --- uçlar ------------------------------------------------------------------ #

@pytest.fixture()
def client():
    return TestClient(app)


def test_weekly_pdf_endpoint(client) -> None:
    r = client.post("/reports/weekly/pdf", json=REPORT)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/pdf")
    assert "haftalik_rapor_hafta34.pdf" in r.headers["content-disposition"]
    assert r.content[:4] == b"%PDF"


def test_weekly_pdf_validates_sizes(client) -> None:
    bad = {**REPORT, "sections": [{"title": "a", "lines": ["x"] * 13}]}
    assert client.post("/reports/weekly/pdf", json=bad).status_code == 422


def test_weekly_send_is_honest_without_smtp(client) -> None:
    """SMTP yok → gönderildi DEĞİL: sent=false, stub=true, açıklama var."""
    r = client.post("/reports/weekly/send", json=REPORT)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["sent"] is False and body["stub"] is True and body["configured"] is False
    assert "GÖNDERİLMEDİ" in body["note"]
    assert body["attachment"] == "haftalik_rapor_hafta34.pdf"


def test_weekly_send_with_configured_channel(client, monkeypatch) -> None:
    from app.api import reports as reports_mod

    captured = {}

    class _Chan(EmailChannel):
        def send(self, text, *, recipient=None, timeout_seconds=10.0, subject=None, attachments=None):
            captured.update(text=text, recipient=recipient, subject=subject, attachments=attachments)
            from app.notifications.base import NotificationResult
            return NotificationResult(channel="email", success=True, extra={"to": recipient})

    monkeypatch.setattr(reports_mod, "build_email_channel",
                        lambda: _Chan(host="h", from_addr="a@x", default_to="b@y"))
    r = client.post("/reports/weekly/send", json={**REPORT, "to": "td@club.tr"})
    body = r.json()
    assert body["sent"] is True and body["stub"] is False and body["to"] == "td@club.tr"
    assert captured["subject"] == "Beşiktaş — 34. Hafta raporu"
    assert captured["attachments"][0][0] == "haftalik_rapor_hafta34.pdf"
    assert captured["attachments"][0][1][:4] == b"%PDF"
    assert "Hazır: 17/24 (+2)" in captured["text"] and "TD notu" in captured["text"]


# --- zamanlanmış iş --------------------------------------------------------- #

def test_send_weekly_report_job_registered() -> None:
    from app.scheduler.registry import get

    spec = get("send_weekly_report")
    assert callable(spec.handler) and "stub" in spec.description


def test_send_weekly_report_job_reports_stub(monkeypatch) -> None:
    """Özet üretilir + kaydedilir; SMTP yoksa sent=False (başarı sayılmaz)."""
    from datetime import UTC, datetime
    from types import SimpleNamespace

    from app.scheduler import jobs as jobs_mod

    calls = {}

    class _Agent:
        name, version = "weekly_digest", "test"

        def run(self, session, context):
            calls["context"] = context
            return SimpleNamespace(summary="3 maç, 2 galibiyet", output_json={"a": 1},
                                   subject_type="league", subject_id=context["league_external_id"])

    def _save(session, *, result, agent_name, agent_version):
        return SimpleNamespace(id=7, subject_type="league", subject_id=203, summary=result.summary,
                               output_json='{"a": 1}', updated_at=datetime.now(UTC))

    class _Session:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def commit(self):
            pass

    monkeypatch.setattr(jobs_mod, "WeeklyDigestAgent", _Agent)
    monkeypatch.setattr(jobs_mod, "save_agent_output", _save)
    monkeypatch.setattr(jobs_mod, "SessionLocal", _Session)
    out = jobs_mod.send_weekly_report_handler(league_external_id=203, lookback_days=7)
    assert calls["context"]["league_external_id"] == 203
    assert out["sent"] is False and out["stub"] is True and out["agent_output_id"] == 7
