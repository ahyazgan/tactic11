"""LLM vendor-agnostic abstraction.

Claude (Anthropic) bugün ana sağlayıcı; OpenAI/Gemini'a swap edebilmek için
ABC + adapter pattern. Mevcut `AnthropicClient` zaten `is_stub()`+`message()`
arayüzünü taşıyor; bu modül `LLMClient` Protocol'ünü tanımlıyor ve
`get_llm_client()` factory'sini settings'tan provider seçiyor.

Şu an:
- "anthropic" → AnthropicClient (gerçek)
- "openai" → OpenAIClient (stub iskelet; OpenAI SDK yüklü değilse RuntimeError)
- "gemini" → GeminiClient (aynı pattern)

Tool use için `message_with_tools` zorunlu; Anthropic format standart kabul
edilmiş, openai/gemini provider'ları aynı semantiği kendi formatlarına
çevirecek (vendor-specific glue).
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from app.ai.anthropic_client import AnthropicClient, MessageResult, ToolUseResult
from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)


@runtime_checkable
class LLMClient(Protocol):
    """Tüm LLM provider'larının uyması gereken minimal arayüz."""

    def is_stub(self) -> bool: ...

    def message(
        self, *, system: str, user: str, max_tokens: int = ...,
    ) -> MessageResult: ...

    def message_with_tools(
        self, *, system: str, messages: list[dict[str, Any]],
        tools: list[dict[str, Any]], max_tokens: int = ...,
    ) -> ToolUseResult: ...


class _UnsupportedProviderClient:
    """Stub for providers not yet implemented; is_stub=True döner."""

    def __init__(self, provider: str, reason: str):
        self._provider = provider
        self._reason = reason

    def is_stub(self) -> bool:
        return True

    def message(self, **kwargs):
        raise RuntimeError(
            f"{self._provider} provider implement edilmedi: {self._reason}. "
            "anthropic ile devam edin (LLM_PROVIDER=anthropic) ya da provider "
            "adapter'ını ekleyin."
        )

    def message_with_tools(self, **kwargs):
        raise RuntimeError(
            f"{self._provider} provider tool_use henüz desteklemiyor: {self._reason}."
        )


def get_llm_client() -> LLMClient:
    """Settings'taki `llm_provider`'a göre uygun client'ı döner.

    Default: anthropic (mevcut tüm kullanım yolu). 'openai'/'gemini' istenirse
    SDK yüklü mü kontrol edip uygun client'ı veya is_stub=True iskeletini döner.
    """
    s = get_settings()
    provider = (getattr(s, "llm_provider", None) or "anthropic").lower()

    if provider == "anthropic":
        return AnthropicClient()

    if provider == "openai":
        try:
            import openai  # noqa: F401
        except ImportError:
            return _UnsupportedProviderClient(
                "openai", "openai SDK yüklü değil (pip install openai)",
            )
        return _UnsupportedProviderClient(
            "openai",
            "tool_use adapter henüz yazılmadı — Anthropic'in tools format'ından "
            "OpenAI function-calling format'ına çevirici eklenecek",
        )

    if provider == "gemini":
        try:
            import google.generativeai  # noqa: F401
        except ImportError:
            return _UnsupportedProviderClient(
                "gemini", "google-generativeai SDK yüklü değil",
            )
        return _UnsupportedProviderClient(
            "gemini",
            "Gemini function-declarations adapter henüz yazılmadı",
        )

    log.warning("bilinmeyen LLM provider: %s — anthropic'e fallback", provider)
    return AnthropicClient()
