"""LLMClient abstraction — multi-provider scaffold."""

from __future__ import annotations

import pytest

from app.ai.llm_client import LLMClient, _UnsupportedProviderClient, get_llm_client
from app.core.config import get_settings


@pytest.fixture(autouse=True)
def _restore_settings(monkeypatch):
    """Her test sonrası provider default'a dönsün."""
    yield
    get_settings.cache_clear()  # type: ignore[attr-defined]


def test_anthropic_is_default():
    client = get_llm_client()
    # AnthropicClient'ın is_stub'ı var → Protocol uyumlu
    assert hasattr(client, "is_stub")
    assert hasattr(client, "message")
    assert hasattr(client, "message_with_tools")
    assert isinstance(client, LLMClient)


def test_openai_returns_unsupported_stub(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    client = get_llm_client()
    assert client.is_stub() is True
    assert isinstance(client, _UnsupportedProviderClient)


def test_unsupported_provider_raises_on_message(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    client = get_llm_client()
    with pytest.raises(RuntimeError, match="implement"):
        client.message(system="x", user="y")


def test_unknown_provider_falls_back_to_anthropic(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama_something")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    client = get_llm_client()
    # Anthropic'e fallback → AnthropicClient
    from app.ai import AnthropicClient
    assert isinstance(client, AnthropicClient)


def test_gemini_returns_unsupported_stub(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    client = get_llm_client()
    assert client.is_stub() is True
