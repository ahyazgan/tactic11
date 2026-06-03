"""Anthropic API'sine ince sarmalayıcı.

`ANTHROPIC_API_KEY` boşsa "stub mode": gerçek istek atmaz, `is_stub()` True döner.
Bu pattern api_football adapter'ının `USE_FIXTURES` davranışıyla aynı —
anahtar gelene kadar üst katmanlar yine geliştirilebilir/test edilebilir.

Model `claude-opus-4-7`. Sistem promptu `cache_control: ephemeral` ile
işaretlenir; kısa promptlarda gerçekten cache'lenmez (minimum eşik altında),
ileride büyüdüğünde otomatik kazanım sağlar.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

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


@dataclass(frozen=True)
class ToolCall:
    """Claude'un istek attığı bir tool call."""
    id: str
    name: str
    input: dict[str, Any]


@dataclass(frozen=True)
class ToolUseResult:
    """Tool-use loop'undan dönen ara sonuç.

    `text` final cevap (tool_use bittiğinde dolar); `tool_calls` mevcut turda
    Claude'un istek attığı tool'lar (caller execute eder ve sonuçları geri verir).
    `stop_reason` "tool_use" ise hâlâ devam ediyor; "end_turn" ise bitti.
    """
    text: str
    tool_calls: list[ToolCall]
    stop_reason: str
    raw_content: list[dict[str, Any]] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0

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
        if not text:
            # Model sadece thinking bloğu döndürdüyse veya max_tokens'a takıldıysa
            # text boş olabilir; caller sessizce boş yorum almasın.
            log.warning(
                "anthropic yanıtında text bloğu yok (stop_reason=%s, max_tokens=%d)",
                response.stop_reason,
                max_tokens,
            )
        return MessageResult(
            text=text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )

    def message_with_tools(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int = 1024,
    ) -> ToolUseResult:
        """Tool-use destekli tek tur. Caller loop'u yönetir.

        `messages` standart Anthropic format'ı (user/assistant turn'leri).
        Tool sonuçları dönülürken caller bu listeye assistant tool_use bloğunu
        ve user tool_result bloğunu ekleyip tekrar çağırır.

        Stub mode kontrolü is_stub() ile caller tarafında yapılır.
        """
        if not self._enabled or self._client is None:
            raise RuntimeError("ANTHROPIC_API_KEY boş; önce is_stub() kontrolü yapın.")

        log.info(
            "anthropic messages.create (tool_use) model=%s max_tokens=%d msgs=%d tools=%d",
            MODEL, max_tokens, len(messages), len(tools),
        )
        response = self._client.messages.create(
            model=MODEL,
            max_tokens=max_tokens,
            system=[{
                "type": "text", "text": system,
                "cache_control": {"type": "ephemeral"},
            }],
            tools=tools,  # type: ignore[arg-type]
            messages=messages,  # type: ignore[arg-type]
        )

        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        raw: list[dict[str, Any]] = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
                raw.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                tc = ToolCall(id=block.id, name=block.name, input=dict(block.input))
                tool_calls.append(tc)
                raw.append({
                    "type": "tool_use", "id": block.id,
                    "name": block.name, "input": dict(block.input),
                })
        return ToolUseResult(
            text="".join(text_parts),
            tool_calls=tool_calls,
            stop_reason=response.stop_reason or "",
            raw_content=raw,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
