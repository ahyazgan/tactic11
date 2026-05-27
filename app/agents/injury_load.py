"""InjuryLoadAgent — verilen oyuncu listesi için yük raporu + rotasyon önerisi.

engine.load üstüne çıktısı human-readable. PlayerAppearance tablosunda
team_id alanı olmadığı için bu agent context'e oyuncu listesi alır;
caller (scheduler job ya da API) hangi oyuncuları taradığına karar verir.

Context: {
  "player_external_ids": list[int],  # zorunlu (min 1)
  "subject_id": int,                  # rapor "kime ait" (team_id genelde)
  "window_days": int (default 14)
}
Output: {
  subject_id, window_days,
  player_loads: [{player_id, minutes_in_window, minutes_per_week, high_load}, ...],
  high_load_count: int,
  ai_brief: str
}
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.base import Agent, AgentResult
from app.ai import AnthropicClient, ClaudeCommentator
from app.db import models
from app.engine.load import compute_player_load
from app.sports import football


class InjuryLoadAgent(Agent):
    """Oyuncu yük raporu + rotasyon önerisi."""

    name = "injury_load"
    version = "1"

    def __init__(self, *, commentator: ClaudeCommentator | None = None):
        self._commentator = commentator or ClaudeCommentator(AnthropicClient())

    def run(self, session: Session, *, context: dict[str, Any]) -> AgentResult:
        player_ids = context.get("player_external_ids")
        if not player_ids:
            raise ValueError("context.player_external_ids zorunlu (min 1)")
        subject_id = int(context.get("subject_id", 0))
        window_days = int(context.get("window_days", 14))

        # SQLite tz-strip workaround: appearances'tan ref_tz çıkar,
        # `now` parametresini compute_player_load'a aynı tz ile geç
        sample_app = session.execute(
            select(models.PlayerAppearance).where(
                models.PlayerAppearance.sport == football.SPORT_NAME,
                models.PlayerAppearance.player_external_id.in_(player_ids),
            ).limit(1)
        ).scalar_one_or_none()
        ref_tz = sample_app.kickoff.tzinfo if sample_app is not None else UTC
        now = datetime.now(ref_tz)
        cutoff = now - timedelta(days=window_days)

        rows = list(
            session.execute(
                select(models.PlayerAppearance).where(
                    models.PlayerAppearance.sport == football.SPORT_NAME,
                    models.PlayerAppearance.player_external_id.in_(player_ids),
                    models.PlayerAppearance.kickoff >= cutoff,
                )
            ).scalars()
        )
        by_player: dict[int, list[models.PlayerAppearance]] = {pid: [] for pid in player_ids}
        for row in rows:
            by_player.setdefault(row.player_external_id, []).append(row)

        player_loads: list[dict[str, Any]] = []
        high_load_players: list[int] = []
        for pid in player_ids:
            result = compute_player_load(
                pid, by_player.get(pid, []),
                window_days=window_days, now=now,
            )
            v = result.value
            player_loads.append({
                "player_id": pid,
                "matches_in_window": v.matches_in_window,
                "minutes_in_window": v.minutes_in_window,
                "minutes_per_match": v.minutes_per_match,
                "minutes_per_week": v.minutes_per_week,
                "high_load": v.high_load,
            })
            if v.high_load:
                high_load_players.append(pid)

        ai_brief = _build_load_brief(
            commentator=self._commentator,
            subject_id=subject_id, window_days=window_days,
            high_load_players=high_load_players, player_loads=player_loads,
        )

        output = {
            "subject_id": subject_id,
            "window_days": window_days,
            "player_loads": player_loads,
            "high_load_count": len(high_load_players),
            "high_load_players": high_load_players,
            "ai_brief": ai_brief,
        }
        summary = (
            f"Subject {subject_id} yük raporu (window={window_days}g): "
            f"{len(high_load_players)}/{len(player_ids)} yüksek yük"
        )
        return AgentResult(
            output_json=output, summary=summary,
            subject_type="team", subject_id=subject_id,
        )


def _build_load_brief(
    *, commentator: ClaudeCommentator, subject_id: int, window_days: int,
    high_load_players: list[int], player_loads: list[dict],
) -> str:
    if commentator._client.is_stub():
        return (
            f"[stub:injury_load] subject={subject_id} window={window_days}g: "
            f"{len(high_load_players)} yüksek-yük oyuncu. ANTHROPIC_API_KEY yok."
        )
    if not high_load_players:
        # Tek satırlık not — AI çağrısı israf
        return (
            f"Son {window_days} gün içinde yüksek yük göstereni yok. "
            "Rotasyon baskısı düşük; standart kadro önerilir."
        )
    sorted_loads = sorted(player_loads, key=lambda p: p["minutes_per_week"], reverse=True)
    top = sorted_loads[:5]
    system = (
        "Sen futbol kondisyon koçuna oyuncu yük raporunu yorumlayan asistanısın. "
        "100-130 kelime. Yapı: (1) en yüksek yüklü 2-3 oyuncu listesi + dakika, "
        "(2) hangi pozisyonlarda rotasyon riski yüksek, "
        "(3) somut rotasyon önerisi (önümüzdeki maçta hangi oyuncu dinlensin)."
    )
    user = (
        f"Subject (takım) {subject_id}, pencere {window_days} gün.\n"
        f"Yüksek yüklü oyuncu sayısı: {len(high_load_players)}\n"
        f"Top 5 yüklü oyuncu (player_id, mins/week):\n" +
        "\n".join(f"- {p['player_id']}: {p['minutes_per_week']:.0f} dk/hafta "
                  f"({p['matches_in_window']} maç)" for p in top)
    )
    return commentator._call(system, user, max_tokens=350)
