from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.ai import AnthropicClient, ClaudeCommentator
from app.ai.anthropic_client import MessageResult
from app.ai.prompts import SYSTEM_PROMPT, build_user_prompt, stub_response
from app.domain import Match
from app.engine.form import compute_form
from app.sports import football


def _matches():
    base = datetime.now(timezone.utc)
    return [
        Match(
            sport=football.SPORT_NAME,
            external_id=1,
            league_external_id=203,
            season=2024,
            kickoff=base - timedelta(days=10),
            status="FT",
            home_team_external_id=611,
            away_team_external_id=607,
            home_score=2,
            away_score=1,
        ),
        Match(
            sport=football.SPORT_NAME,
            external_id=2,
            league_external_id=203,
            season=2024,
            kickoff=base - timedelta(days=3),
            status="FT",
            home_team_external_id=614,
            away_team_external_id=611,
            home_score=1,
            away_score=3,
        ),
    ]


def test_form_prompt_uses_turkish_prose_not_json():
    res = compute_form(611, _matches())
    prompt = build_user_prompt(res)
    # Per-engine builder: Türkçe prose, JSON dump değil
    assert "Takım 611" in prompt
    assert "galibiyet" in prompt
    assert "beraberlik" in prompt
    assert "Maç başı puan" in prompt
    # form ve rating sayıları
    assert "averaj" in prompt
    # eski JSON şekli olmasın
    assert '"subject_id"' not in prompt


def test_unknown_engine_falls_back_to_json(monkeypatch):
    # Sözleşme: bilinmeyen engine sistemi patlatmamalı.
    from app.audit import AuditRecord, EngineResult

    audit = AuditRecord(
        engine="engine.future_xyz",
        engine_version="0",
        subject_type="team",
        subject_id=42,
        metric="something",
        value={"x": 1},
        inputs={},
        formula="?",
    )
    fake_result = EngineResult(value={"x": 1}, audit=audit)
    prompt = build_user_prompt(fake_result)
    assert "bilinmeyen engine" in prompt.lower()
    assert "engine.future_xyz" in prompt


def test_stub_response_includes_metadata():
    res = compute_form(611, _matches())
    text = stub_response(res)
    assert "stub:engine.form" in text
    assert "611" in text
    assert "form_report" in text


def test_commentator_stub_mode_does_not_call_api(monkeypatch):
    # API anahtarı yok → is_stub=True, gerçek istek atılmamalı
    client = AnthropicClient(api_key="")
    assert client.is_stub() is True

    def _fail(*a, **kw):
        raise AssertionError("stub mode'da message() çağrılmamalı")

    monkeypatch.setattr(client, "message", _fail)
    com = ClaudeCommentator(client=client)
    text = com.explain(compute_form(611, _matches()))
    assert "stub" in text.lower()


def test_commentator_records_usage_and_returns_text(monkeypatch, session):
    # Gerçek API yerine yamayla yanıtı taklit ediyoruz; record_call'un tetiklendiğini
    # ve text'in geri döndüğünü doğrula.
    client = AnthropicClient(api_key="dummy")
    assert client.is_stub() is False

    fake = MessageResult(text="Galatasaray son maçlarda 2G 1M.", input_tokens=120, output_tokens=30)
    monkeypatch.setattr(client, "message", lambda **kw: fake)

    # SessionLocal'i test fixture'ı session ile değiştir (tek session)
    from app.ai import commentator as commentator_module

    class _Ctx:
        def __init__(self, s):
            self.s = s

        def __enter__(self):
            return self.s

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(commentator_module, "SessionLocal", lambda: _Ctx(session))

    com = ClaudeCommentator(client=client)
    text = com.explain(compute_form(611, _matches()))
    assert text == fake.text

    from sqlalchemy import select, func
    from app.db import models
    # consume_quota iki kez çağrılır: HTTP öncesi rezervasyon (tokens=0) +
    # HTTP sonrası gerçek tüketim. Toplam tokens doğrudur, satır sayısı 2'dir.
    n = session.scalar(select(func.count()).select_from(models.UsageEvent))
    assert n == 2
    rows = session.execute(
        select(models.UsageEvent).order_by(models.UsageEvent.id)
    ).scalars().all()
    assert all(r.source == "anthropic" for r in rows)
    assert sum(r.tokens for r in rows) == 150


def test_system_prompt_is_stable_string():
    # Prompt caching prefix-match olduğu için bayt değişimi olursa farkına varalım.
    assert SYSTEM_PROMPT.startswith("Sen futbol teknik ekibine")
    assert "Türkçe yaz." in SYSTEM_PROMPT


def test_match_preview_prompt_synthesizes_three_inputs():
    from app.ai.prompts import build_match_preview_prompt
    from app.engine.form import compute_form
    from app.engine.opponent import compute_head_to_head

    matches = _matches()
    home_form = compute_form(611, matches, last_n=5)
    away_form = compute_form(607, matches, last_n=5)
    h2h = compute_head_to_head(611, 607, matches)

    prompt = build_match_preview_prompt(
        home_form, away_form, h2h,
        home_team_id=611, away_team_id=607,
        kickoff_iso="2024-09-01T18:00:00+00:00",
    )
    assert "EV SAHİBİ (takım 611)" in prompt
    assert "DEPLASMAN (takım 607)" in prompt
    assert "kickoff 2024-09-01" in prompt
    assert "Geçmiş" in prompt
    assert "3-5 cümlelik" in prompt


def test_explain_match_preview_stub_mode():
    from app.engine.form import compute_form
    from app.engine.opponent import compute_head_to_head

    client = AnthropicClient(api_key="")
    com = ClaudeCommentator(client=client)
    matches = _matches()
    text = com.explain_match_preview(
        home_form=compute_form(611, matches),
        away_form=compute_form(607, matches),
        h2h=compute_head_to_head(611, 607, matches),
        home_team_id=611,
        away_team_id=607,
        kickoff_iso="2024-09-01T18:00:00+00:00",
    )
    assert "stub:match_preview" in text
    assert "611" in text and "607" in text
