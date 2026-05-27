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


def test_build_user_prompt_includes_engine_and_value():
    res = compute_form(611, _matches())
    prompt = build_user_prompt(res)
    assert "engine.form" in prompt
    assert '"subject_id": 611' in prompt
    assert '"metric": "form_report"' in prompt
    assert "Bu çıktıyı kısa" in prompt


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
    n = session.scalar(select(func.count()).select_from(models.UsageEvent))
    assert n == 1
    row = session.execute(select(models.UsageEvent)).scalar_one()
    assert row.source == "anthropic"
    assert row.tokens == 150


def test_system_prompt_is_stable_string():
    # Prompt caching prefix-match olduğu için bayt değişimi olursa farkına varalım.
    assert SYSTEM_PROMPT.startswith("Sen futbol teknik ekibine")
    assert "Türkçe yaz." in SYSTEM_PROMPT
