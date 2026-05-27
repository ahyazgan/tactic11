"""MediaBriefAgent — maç sonu medya departmanı için içerik draft'ı.

Çıktı 3 parça:
1. press_release_paragraphs: 3-paragraflık basın bülteni
2. tweet_drafts: 3 alternatif Twitter post (≤240 karakter)
3. instagram_caption: 1 Instagram caption (hashtagler dahil)
4. key_moments: highlight tag önerileri (dakika + kısa açıklama)

Context: {"match_external_id": int, "tone"?: "neutral"|"home"|"away"}
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.base import Agent, AgentResult
from app.ai import AnthropicClient, ClaudeCommentator
from app.db import models
from app.sports import football


class MediaBriefAgent(Agent):
    """Maç sonu medya brief üretici (basın bülteni + sosyal medya draft'ları)."""

    name = "media_brief"
    version = "1"

    def __init__(self, *, commentator: ClaudeCommentator | None = None):
        self._commentator = commentator or ClaudeCommentator(AnthropicClient())

    def run(self, session: Session, *, context: dict[str, Any]) -> AgentResult:
        match_id = context.get("match_external_id")
        if match_id is None:
            raise ValueError("match_external_id zorunlu")
        match_id = int(match_id)
        tone = context.get("tone", "neutral")
        if tone not in ("neutral", "home", "away"):
            raise ValueError(f"tone: neutral|home|away (geldi: {tone!r})")

        match = session.execute(
            select(models.Match).where(
                models.Match.sport == football.SPORT_NAME,
                models.Match.external_id == match_id,
            )
        ).scalar_one_or_none()
        if match is None:
            raise ValueError(f"match {match_id} yok")
        if match.status not in football.FINISHED_STATUSES:
            raise ValueError(
                f"match {match_id} henüz bitmedi (status={match.status}) — "
                "media brief sadece FT maçlar için"
            )
        if match.home_score is None or match.away_score is None:
            raise ValueError(f"match {match_id}: skor yok")

        # Basit key moments — gerçek event feed'i yok; placeholder olarak skoru kullan
        key_moments = [
            {
                "minute": 0,
                "tag": f"Kickoff — {match.home_team_external_id} vs {match.away_team_external_id}",
            },
        ]
        # En az 1 gol varsa key moment ekle (basit placeholder)
        if match.home_score > 0:
            key_moments.append({
                "minute": 30,
                "tag": f"Ev sahibi gol(leri) — {match.home_score}",
            })
        if match.away_score > 0:
            key_moments.append({
                "minute": 60,
                "tag": f"Deplasman gol(leri) — {match.away_score}",
            })

        # AI sentezi
        outcome = (
            "ev_galip" if match.home_score > match.away_score
            else "deplasman_galip" if match.away_score > match.home_score
            else "berabere"
        )
        content = _build_media_content(
            commentator=self._commentator,
            match_id=match_id,
            home_id=match.home_team_external_id,
            away_id=match.away_team_external_id,
            home_score=match.home_score, away_score=match.away_score,
            outcome=outcome, tone=tone,
        )

        output = {
            "match_external_id": match_id,
            "tone": tone,
            "score": f"{match.home_score}-{match.away_score}",
            "outcome": outcome,
            "key_moments": key_moments,
            **content,
        }
        summary = (
            f"Media brief match={match_id} {match.home_score}-{match.away_score} "
            f"tone={tone}"
        )
        return AgentResult(
            output_json=output, summary=summary,
            subject_type="match", subject_id=match_id,
        )


def _build_media_content(
    *, commentator: ClaudeCommentator, match_id: int, home_id: int,
    away_id: int, home_score: int, away_score: int, outcome: str, tone: str,
) -> dict[str, Any]:
    if commentator._client.is_stub():
        return {
            "press_release_paragraphs": [
                f"[stub] Maç {home_id} {home_score}-{away_score} {away_id}.",
                "[stub] Tone=" + tone,
                "[stub] ANTHROPIC_API_KEY yok — gerçek metin yerine placeholder.",
            ],
            "tweet_drafts": [
                f"[stub tweet 1] {home_score}-{away_score}",
                f"[stub tweet 2] sonuç: {outcome}",
                f"[stub tweet 3] #futbol #{home_id}",
            ],
            "instagram_caption": f"[stub IG] {home_id} {home_score}-{away_score} {away_id} #futbol",
        }
    system = (
        "Sen futbol kulübünün medya departmanına maç sonu içerik draft'ı sunan "
        "asistansın. Türkçe, profesyonel ton. Çıktın MUTLAKA bu JSON şemasında "
        "olsun (sade text, code fence olmadan):\n"
        "{\n"
        '  "press_release_paragraphs": ["<para1>", "<para2>", "<para3>"],\n'
        '  "tweet_drafts": ["<240 karakter altı>", "<...>", "<...>"],\n'
        '  "instagram_caption": "<emoji + hashtag dahil tek paragraf>"\n'
        "}\n"
        "Sayıları sadece skor için ver; abartma. Sansasyonel başlık YOK."
    )
    tone_hint = {
        "neutral": "nötr, objektif ton",
        "home": "ev sahibi kulübün resmi hesabı için (galibiyetse coşkulu, mağlubiyetse onurlu)",
        "away": "deplasman kulübünün resmi hesabı için",
    }[tone]
    user = (
        f"Maç: takım {home_id} (ev) {home_score}-{away_score} takım {away_id} (dep)\n"
        f"Sonuç: {outcome}\n"
        f"Tone hedefi: {tone_hint}\n\n"
        "Yukarıdaki JSON şemasıyla draft üret."
    )
    raw = commentator._call(system, user, max_tokens=900)
    # Modeli JSON yapması için yönlendirdik ama parse hata riskine karşı fallback
    import json as _json
    try:
        parsed = _json.loads(raw.strip())
        if isinstance(parsed, dict) and "press_release_paragraphs" in parsed:
            return {
                "press_release_paragraphs": parsed.get("press_release_paragraphs", []),
                "tweet_drafts": parsed.get("tweet_drafts", []),
                "instagram_caption": parsed.get("instagram_caption", ""),
            }
    except (_json.JSONDecodeError, AttributeError):
        pass
    # Parse fail → raw'ı press_release tek paragraf olarak döndür
    return {
        "press_release_paragraphs": [raw],
        "tweet_drafts": [],
        "instagram_caption": "",
    }
