"""Anthropic API'sine ince sarmalayıcı.

`ANTHROPIC_API_KEY` boşsa "stub mode": gerçek istek atmaz, `is_stub()` True döner.
Bu pattern api_football adapter'ının `USE_FIXTURES` davranışıyla aynı —
anahtar gelene kadar üst katmanlar yine geliştirilebilir/test edilebilir.

Model `claude-opus-4-7`. Sistem promptu `cache_control: ephemeral` ile
işaretlenir; kısa promptlarda gerçekten cache'lenmez (minimum eşik altında),
ileride büyüdüğünde otomatik kazanım sağlar.
"""

from __future__ import annotations

from dataclasses import dataclass

import anthropic

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)

MODEL = "claude-opus-4-7"
MAX_TOKENS_DEFAULT = 256


@dataclass(frozen=True)
class MessageResult:
    text: str
    input_tokens: int
    output_tokens: int

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class AnthropicClient:
    def __init__(self, api_key: str | None = None) -> None:
        if api_key is None:
            api_key = get_settings().anthropic_api_key
        self._enabled = bool(api_key)
        self._client = anthropic.Anthropic(api_key=api_key) if self._enabled else None

    def is_stub(self) -> bool:
        return not self._enabled

    def message(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = MAX_TOKENS_DEFAULT,
    ) -> MessageResult:
        if not self._enabled or self._client is None:
            raise RuntimeError("ANTHROPIC_API_KEY boş; önce is_stub() kontrolü yapın.")

        log.info("anthropic messages.create model=%s max_tokens=%d", MODEL, max_tokens)
        response = self._client.messages.create(
            model=MODEL,
            max_tokens=max_tokens,
            system=[
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user}],
        )
        text = next((b.text for b in response.content if b.type == "text"), "")
        return MessageResult(
            text=text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
