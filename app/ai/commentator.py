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
from app.ai.prompts import (
    SYSTEM_PROMPT,
    _PREVIEW_SYSTEM_PROMPT,
    build_match_preview_prompt,
    build_user_prompt,
    stub_match_preview,
    stub_response,
)
from app.audit import EngineResult
from app.core.logging import get_logger
from app.core.usage import consume_quota
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
        return self._call(SYSTEM_PROMPT, build_user_prompt(engine_output))

    def explain_match_preview(
        self,
        *,
        home_form: EngineResult,
        away_form: EngineResult,
        h2h: EngineResult,
        home_team_id: int,
        away_team_id: int,
        kickoff_iso: str,
    ) -> str:
        """Maç öncesi brief — üç engine sonucunu sentezler."""
        if self._client.is_stub():
            log.info("commentator stub mode (no api key)")
            return stub_match_preview(home_team_id, away_team_id)
        user = build_match_preview_prompt(
            home_form,
            away_form,
            h2h,
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            kickoff_iso=kickoff_iso,
        )
        return self._call(_PREVIEW_SYSTEM_PROMPT, user, max_tokens=400)

    def _call(self, system: str, user: str, *, max_tokens: int = 256) -> str:
        # Çağrı öncesi 0 tokenli ön rezervasyon: limit zaten doluysa HTTP yapmadan
        # QuotaExceeded fırlat. Gerçek token sayımı için ayrıca aşağıda kayıt eklenir.
        with SessionLocal() as session:
            consume_quota(session, source=_SOURCE, endpoint=_ENDPOINT, tokens=0)
            session.commit()

        result = self._client.message(system=system, user=user, max_tokens=max_tokens)

        with SessionLocal() as session:
            consume_quota(
                session,
                source=_SOURCE,
                endpoint=_ENDPOINT,
                tokens=result.total_tokens,
            )
            session.commit()

        return result.text
