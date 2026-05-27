"""Claude tabanlı `Commentator` somut implementasyonu.

Sözleşme `ai/base.py`'de. Bu sınıf:
1) engine sonucunu prompt'a sarar,
2) quota guard'ı tetikler (anthropic source),
3) Claude'a sorar,
4) token kullanımını `core/usage` üzerinden kaydeder.

`ANTHROPIC_API_KEY` boşsa gerçek istek atmadan deterministik stub yanıtı döner.
"""

from __future__ import annotations

from app.ai.anthropic_client import AnthropicClient
from app.ai.base import Commentator
from app.ai.prompts import SYSTEM_PROMPT, build_user_prompt, stub_response
from app.audit import EngineResult
from app.core.logging import get_logger
from app.core.usage import guard_quota, record_call
from app.db.session import SessionLocal

log = get_logger(__name__)
_SOURCE = "anthropic"
_ENDPOINT = "messages"


class ClaudeCommentator(Commentator):
    def __init__(self, client: AnthropicClient | None = None) -> None:
        self._client = client or AnthropicClient()

    def explain(self, engine_output: EngineResult) -> str:  # type: ignore[override]
        if self._client.is_stub():
            log.info("commentator stub mode (no api key)")
            return stub_response(engine_output)

        user_prompt = build_user_prompt(engine_output)

        with SessionLocal() as session:
            guard_quota(session, _SOURCE)
            session.commit()

        result = self._client.message(system=SYSTEM_PROMPT, user=user_prompt)

        with SessionLocal() as session:
            record_call(
                session,
                source=_SOURCE,
                endpoint=_ENDPOINT,
                tokens=result.total_tokens,
            )
            session.commit()

        return result.text
