"""Konuşma orchestrator'ı — kullanıcı mesajı → Claude tool loop → final cevap.

Stateless (Phase 1): konuşma geçmişi caller tarafında tutulur ya da yok.
Phase 3'te `assistant_memory` ile takım-bazlı hafıza gelecek.

Akış:
1. User mesajı + system prompt + tools → Claude
2. Claude tool_use isterse → execute_tool → sonuç back to Claude
3. Claude end_turn dediğinde → final text döner

Stub mode (ANTHROPIC_API_KEY yok): "asistan aktif değil" mesajı + tools listesi.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.ai import AnthropicClient
from app.assistant.memory import memory_list
from app.assistant.tools import (
    MAX_TOOL_ITERATIONS,
    execute_tool,
    get_tool_schemas,
)
from app.core.logging import get_logger
from app.core.usage import consume_quota

log = get_logger(__name__)

_SYSTEM_PROMPT = """Sen futbol takımının teknik ekibine veriyle destek veren \
bir yardımcı manager (co-pilot) asistansın. Türkçe konuş.

Kurallar:
- Sayı uydurma; verilen tool'larla DB'den oku.
- Belirsizlik varsa belirt (örneklem küçükse "düşük güven", ML model yoksa "kalibrasyon yok").
- 3-5 paragraf cevap ver; gerekçe + somut öneri.
- Önce gerekli tool'ları çağır (form, rating, predict, load, schedule); sonra sentezle.
- Birden çok tool gerekiyorsa ardışık çağır.
"""

_ASSISTANT_SOURCE = "anthropic_assistant"
_ASSISTANT_ENDPOINT = "messages/chat"


@dataclass(frozen=True)
class ToolTrace:
    """Bir tool çağrısının izi (audit + UI için)."""
    name: str
    input: dict[str, Any]
    output: str  # JSON string


@dataclass(frozen=True)
class ChatResult:
    """Asistan cevabı + tool trace + token sayım."""
    text: str
    tool_traces: list[ToolTrace]
    iterations: int
    total_tokens: int
    stub: bool


@dataclass
class ChatSession:
    """Çok turlu konuşma için minimal state — caller tutar.

    `messages` Anthropic format'ı (alternating user/assistant). Phase 1'de
    in-memory; Phase 3'te DB'ye persist edilecek.
    """
    messages: list[dict[str, Any]] = field(default_factory=list)

    def add_user(self, text: str) -> None:
        self.messages.append({"role": "user", "content": text})


def chat(
    session: Session,
    *,
    user_message: str,
    history: list[dict[str, Any]] | None = None,
    client: AnthropicClient | None = None,
    max_iterations: int = MAX_TOOL_ITERATIONS,
    team_external_id: int | None = None,
) -> ChatResult:
    """Tek-tur chat: user_message + optional history → asistan cevabı.

    `team_external_id` verilirse o takıma ait hafıza (assistant_memory)
    okunup system prompt'a enjekte edilir — asistanın "kullanıcının takımı,
    geçmiş kararları" bilgisi var.

    `history` boşsa yeni konuşma. Dolu ise önceki turlar (user/assistant)
    Claude'a context olarak verilir.
    """
    client = client or AnthropicClient()
    messages: list[dict[str, Any]] = list(history or [])
    messages.append({"role": "user", "content": user_message})

    # Hafıza enjeksiyonu (Phase 3): team-bazlı saklı kararlar/notlar
    system = _SYSTEM_PROMPT
    if team_external_id is not None:
        mem = memory_list(session, subject_type="team", subject_id=team_external_id)
        if mem:
            system = (
                _SYSTEM_PROMPT
                + f"\n\nKULLANICI BAĞLAMI (takım {team_external_id} için saklı hafıza):\n"
                + "\n".join(f"- {k}: {v}" for k, v in mem.items())
            )

    if client.is_stub():
        tool_names = [t["name"] for t in get_tool_schemas()]
        return ChatResult(
            text=(
                f"[stub:assistant] ANTHROPIC_API_KEY yok. "
                f"Soru: {user_message[:80]}... "
                f"Available tools: {', '.join(tool_names)}."
            ),
            tool_traces=[], iterations=0, total_tokens=0, stub=True,
        )

    tools = get_tool_schemas()
    traces: list[ToolTrace] = []
    total_tokens = 0
    final_text = ""
    iteration_count = 0

    for _ in range(max_iterations):
        iteration_count += 1
        # Kota kontrolü her tur başında — caller'ın session'ını kullan
        # (test-friendly + standart request-scoped UoW)
        consume_quota(
            session, source=_ASSISTANT_SOURCE,
            endpoint=_ASSISTANT_ENDPOINT, tokens=0,
        )

        result = client.message_with_tools(
            system=system,
            messages=messages, tools=tools,
            max_tokens=1500,
        )
        total_tokens += result.total_tokens

        # Token consume — gerçek sayı
        consume_quota(
            session, source=_ASSISTANT_SOURCE,
            endpoint=_ASSISTANT_ENDPOINT, tokens=result.total_tokens,
        )

        if result.stop_reason == "tool_use" and result.tool_calls:
            # Assistant turn'üne tool_use blokları ekle, sonra user turn'üne tool_result
            messages.append({"role": "assistant", "content": result.raw_content})
            tool_results_blocks = []
            for tc in result.tool_calls:
                output = execute_tool(session, tc.name, tc.input)
                traces.append(ToolTrace(name=tc.name, input=tc.input, output=output))
                tool_results_blocks.append({
                    "type": "tool_result",
                    "tool_use_id": tc.id,
                    "content": output,
                })
            messages.append({"role": "user", "content": tool_results_blocks})
            continue

        # end_turn ya da başka stop_reason
        final_text = result.text
        break

    if not final_text:
        log.warning("assistant max_iterations'a ulaştı (%d) — final text yok", max_iterations)
        final_text = (
            f"(Maks tool turuna {max_iterations} ulaştım; sorunu basitleştirip "
            "tekrar dener misin?)"
        )

    return ChatResult(
        text=final_text,
        tool_traces=traces,
        iterations=iteration_count,
        total_tokens=total_tokens,
        stub=False,
    )
