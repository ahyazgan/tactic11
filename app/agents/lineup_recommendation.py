"""LineupRecommendationAgent — başlangıç 11 önerisi.

Girdi: maç + takım (ev ya da dep) + opsiyonel oyuncu havuzu.
Çıktı: önerilen 11 (player_id'ler) + gerekçe (yük + form bağlamı).

Veri gerçekleri:
- Roster proxy: takımın son N maçında en çok dakika alan oyuncular = first XI candidates
- Load filter: high_load oyuncular için "dinlendirme önerisi" notu
- AI sentez: somut 11 listesi + 3-4 cümle gerekçe

Context: {
  "match_external_id": int,
  "team_external_id": int,   # önerilen 11 hangi takım için
  "candidate_player_ids"?: list[int]  # opsiyonel; yoksa roster proxy
}
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.agents.base import Agent, AgentResult
from app.ai import AnthropicClient, ClaudeCommentator
from app.db import models
from app.engine.load import compute_player_load
from app.sports import football


class LineupRecommendationAgent(Agent):
    """Maç + takım için başlangıç 11 önerisi (roster proxy + load + AI)."""

    name = "lineup_recommendation"
    version = "1"

    def __init__(self, *, commentator: ClaudeCommentator | None = None):
        self._commentator = commentator or ClaudeCommentator(AnthropicClient())

    def run(self, session: Session, *, context: dict[str, Any]) -> AgentResult:
        match_id = context.get("match_external_id")
        team_id = context.get("team_external_id")
        if match_id is None or team_id is None:
            raise ValueError("match_external_id + team_external_id zorunlu")
        match_id, team_id = int(match_id), int(team_id)

        match = session.execute(
            select(models.Match).where(
                models.Match.sport == football.SPORT_NAME,
                models.Match.external_id == match_id,
            )
        ).scalar_one_or_none()
        if match is None:
            raise ValueError(f"match {match_id} yok")
        if team_id not in (match.home_team_external_id, match.away_team_external_id):
            raise ValueError(
                f"team {team_id} match {match_id} tarafı değil "
                f"(ev={match.home_team_external_id}, dep={match.away_team_external_id})"
            )

        # Aday havuzu: ya context'ten ya da takımın son maçlarındaki appearance'lardan
        candidate_ids = context.get("candidate_player_ids")
        if not candidate_ids:
            recent_match_ids = [
                m.external_id for m in session.execute(
                    select(models.Match).where(
                        models.Match.sport == football.SPORT_NAME,
                        models.Match.kickoff < match.kickoff,
                        or_(
                            models.Match.home_team_external_id == team_id,
                            models.Match.away_team_external_id == team_id,
                        ),
                    ).order_by(models.Match.kickoff.desc()).limit(10)
                ).scalars()
            ]
            apps = list(
                session.execute(
                    select(models.PlayerAppearance).where(
                        models.PlayerAppearance.sport == football.SPORT_NAME,
                        models.PlayerAppearance.match_external_id.in_(recent_match_ids),
                    )
                ).scalars()
            )
            mins_by_player: dict[int, int] = {}
            for a in apps:
                mins_by_player[a.player_external_id] = (
                    mins_by_player.get(a.player_external_id, 0) + a.minutes
                )
            candidate_ids = [
                pid for pid, _ in sorted(
                    mins_by_player.items(), key=lambda kv: kv[1], reverse=True,
                )[:22]  # 22 = 11 first + 11 alternative
            ]
        if not candidate_ids:
            raise ValueError(
                f"team {team_id}: aday oyuncu bulunamadı (roster proxy boş, "
                "context'e candidate_player_ids ekle)"
            )

        # Her aday için load
        sample_app = session.execute(
            select(models.PlayerAppearance).where(
                models.PlayerAppearance.player_external_id.in_(candidate_ids),
            ).limit(1)
        ).scalar_one_or_none()
        ref_tz = sample_app.kickoff.tzinfo if sample_app else None
        now = datetime.now(ref_tz) if ref_tz else datetime.utcnow()
        loads: dict[int, dict[str, Any]] = {}
        for pid in candidate_ids:
            apps_for_pid = list(
                session.execute(
                    select(models.PlayerAppearance).where(
                        models.PlayerAppearance.player_external_id == pid,
                        models.PlayerAppearance.kickoff >= now - timedelta(days=14),
                    )
                ).scalars()
            )
            v = compute_player_load(pid, apps_for_pid, window_days=14, now=now).value
            loads[pid] = {
                "minutes_per_week": v.minutes_per_week,
                "matches_in_window": v.matches_in_window,
                "high_load": v.high_load,
            }

        # Basit öneri: top 11 (en çok dakika alanlar) - high_load filtrele
        # Aday listesi zaten total mins sıralı; high_load'u en sona alıp ilk 11'i seç
        sortable = [(pid, loads[pid]) for pid in candidate_ids]
        sortable.sort(key=lambda kv: (kv[1]["high_load"], -kv[1]["minutes_per_week"]))
        recommended_starting_xi = [pid for pid, _ in sortable[:11]]
        rest_recommended = [
            pid for pid, ld in sortable if ld["high_load"]
        ][:3]

        ai_brief = _build_lineup_brief(
            commentator=self._commentator,
            match_id=match_id, team_id=team_id,
            starting_xi=recommended_starting_xi, rest_list=rest_recommended,
            loads=loads,
        )

        output = {
            "match_external_id": match_id,
            "team_external_id": team_id,
            "is_home": team_id == match.home_team_external_id,
            "candidate_count": len(candidate_ids),
            "recommended_starting_xi": recommended_starting_xi,
            "suggested_rest": rest_recommended,
            "player_loads": {str(pid): loads[pid] for pid in candidate_ids},
            "ai_brief": ai_brief,
        }
        summary = (
            f"Lineup öneri match={match_id} team={team_id}: "
            f"11 = {recommended_starting_xi[:3]}..., "
            f"dinlendir önerisi {len(rest_recommended)} oyuncu"
        )
        return AgentResult(
            output_json=output, summary=summary,
            subject_type="match", subject_id=match_id,
        )


def _build_lineup_brief(
    *, commentator: ClaudeCommentator, match_id: int, team_id: int,
    starting_xi: list[int], rest_list: list[int], loads: dict[int, dict],
) -> str:
    if commentator._client.is_stub():
        return (
            f"[stub:lineup] match={match_id} team={team_id}: "
            f"11 = {starting_xi}, dinlendir={rest_list}. ANTHROPIC_API_KEY yok."
        )
    system = (
        "Sen futbol teknik direktörüne 11 önerisi sunan bir analiz asistanısın. "
        "100-130 kelime. Yapı: (1) önerilen 11 (sayıyla değil player_id listesiyle), "
        "(2) hangisi yüksek yük → dinlendirme gerekçesi, "
        "(3) somut alternatif öneri (1-2 oyuncu rotasyon)."
    )
    high_load_lines = [
        f"- {pid}: {loads[pid]['minutes_per_week']:.0f} dk/hafta (YÜK)"
        for pid in starting_xi if loads[pid]["high_load"]
    ]
    user = (
        f"Maç {match_id}, takım {team_id}\n"
        f"Önerilen 11 (en çok dakika alan + düşük yüklü): {starting_xi}\n"
        f"Yüksek yüklü oyuncular: {rest_list}\n"
        + ("\nYüksek yüklü first XI üyeleri:\n" + "\n".join(high_load_lines)
           if high_load_lines else "")
    )
    return commentator._call(system, user, max_tokens=400)
