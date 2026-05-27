"""Claude tabanlı `Commentator` somut implementasyonu.

Sözleşme `ai/base.py`'de. Bu sınıf:
1) engine sonucunu prompt'a sarar,
2) cache'e bakar — aynı (engine, value) için aynı yanıt → token tasarrufu,
3) miss'te quota guard'ı tetikler (anthropic source),
4) Claude'a sorar,
5) token kullanımını `core/usage` üzerinden kaydeder,
6) yanıtı cache'e yazar.

`ANTHROPIC_API_KEY` boşsa gerçek istek atmadan deterministik stub yanıtı döner.
Cache TTL: 24 saat — engine sonucu nadiren değişir (yeni maç eklendiğinde
value hash değişir, cache miss); manuel temizlik gerekmez.
"""

from __future__ import annotations

import hashlib
import json

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
from app.data.cache import cache_get, cache_set
from app.db.session import SessionLocal

log = get_logger(__name__)
_SOURCE = "anthropic"
_ENDPOINT = "messages"
_CACHE_SOURCE = "anthropic_explain"
_CACHE_TTL = 86_400  # 24 saat

# Prompt template'i değiştiğinde bump et → tüm cache otomatik invalid.
_PROMPT_VERSION = "1"


def _engine_cache_key(result: EngineResult) -> str:
    """Aynı (engine, version, value) için aynı key."""
    payload = json.dumps(
        {
            "v": _PROMPT_VERSION,
            "engine": result.audit.engine,
            "engine_version": result.audit.engine_version,
            "value": result.audit.value,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]
    return f"explain:{result.audit.engine}:{result.audit.subject_id}:{digest}"


def _preview_cache_key(
    home: EngineResult, away: EngineResult, h2h: EngineResult
) -> str:
    payload = json.dumps(
        {
            "v": _PROMPT_VERSION,
            "home": home.audit.value,
            "away": away.audit.value,
            "h2h": h2h.audit.value,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]
    return f"preview:{home.audit.subject_id}-{away.audit.subject_id}:{digest}"


class ClaudeCommentator(Commentator):
    def __init__(self, client: AnthropicClient | None = None) -> None:
        self._client = client or AnthropicClient()

    def explain(self, engine_output: EngineResult) -> str:  # type: ignore[override]
        if self._client.is_stub():
            log.info("commentator stub mode (no api key)")
            return stub_response(engine_output)

        cache_key = _engine_cache_key(engine_output)
        cached = self._cache_get(cache_key)
        if cached is not None:
            log.info("commentator cache hit: %s", cache_key)
            return cached

        text = self._call(SYSTEM_PROMPT, build_user_prompt(engine_output))
        self._cache_set(cache_key, text)
        return text

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

        cache_key = _preview_cache_key(home_form, away_form, h2h)
        cached = self._cache_get(cache_key)
        if cached is not None:
            log.info("commentator cache hit: %s", cache_key)
            return cached

        user = build_match_preview_prompt(
            home_form,
            away_form,
            h2h,
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            kickoff_iso=kickoff_iso,
        )
        text = self._call(_PREVIEW_SYSTEM_PROMPT, user, max_tokens=400)
        self._cache_set(cache_key, text)
        return text

    # ---- yardımcılar -------------------------------------------------------

    def _cache_get(self, key: str) -> str | None:
        with SessionLocal() as session:
            row = cache_get(session, source=_CACHE_SOURCE, key=key)
        if row is None:
            return None
        # Cache value JSON dict; metni "text" anahtarı altında tutuyoruz.
        return row.get("text") if isinstance(row, dict) else None

    def _cache_set(self, key: str, text: str) -> None:
        with SessionLocal() as session:
            cache_set(
                session,
                source=_CACHE_SOURCE,
                key=key,
                value={"text": text},
                ttl_seconds=_CACHE_TTL,
            )
            session.commit()

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
