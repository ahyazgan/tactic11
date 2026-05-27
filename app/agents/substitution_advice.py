"""SubstitutionAdviceAgent — maç içi değişiklik önerisi.

Context (canlı maç durumu — caller geçer):
{
  "match_external_id": int,
  "team_external_id": int,
  "minute": float,
  "current_home_score": int,
  "current_away_score": int,
  "on_pitch_player_ids": list[int],
  "bench_player_ids": list[int],
}

Output: önerilen değişiklikler (out → in) + gerekçe.
- Skor + dakika → öncelik (kovalamak / korumak / dengelemek)
- on_pitch oyuncuların yük geçmişi → yüksek yüklüleri çıkar
- AI sentez: 2-3 cümlelik somut öneri (en fazla 3 sub)
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.base import Agent, AgentResult
from app.ai import AnthropicClient, ClaudeCommentator
from app.db import models
from app.engine.load import compute_player_load
from app.sports import football


class SubstitutionAdviceAgent(Agent):
    """Maç içi değişiklik önerisi (en fazla 3 sub)."""

    name = "substitution_advice"
    version = "1"

    def __init__(self, *, commentator: ClaudeCommentator | None = None):
        self._commentator = commentator or ClaudeCommentator(AnthropicClient())

    def run(self, session: Session, *, context: dict[str, Any]) -> AgentResult:
        required = (
            "match_external_id", "team_external_id", "minute",
            "current_home_score", "current_away_score",
            "on_pitch_player_ids", "bench_player_ids",
        )
        for k in required:
            if k not in context:
                raise ValueError(f"context.{k} zorunlu")
        match_id = int(context["match_external_id"])
        team_id = int(context["team_external_id"])
        minute = float(context["minute"])
        ch = int(context["current_home_score"])
        ca = int(context["current_away_score"])
        on_pitch = [int(x) for x in context["on_pitch_player_ids"]]
        bench = [int(x) for x in context["bench_player_ids"]]
        if not on_pitch:
            raise ValueError("on_pitch_player_ids boş olamaz")

        match = session.execute(
            select(models.Match).where(
                models.Match.sport == football.SPORT_NAME,
                models.Match.external_id == match_id,
            )
        ).scalar_one_or_none()
        if match is None:
            raise ValueError(f"match {match_id} yok")
        is_home = team_id == match.home_team_external_id

        # Yük tarama — sadece sahadaki oyuncular için
        sample_app = session.execute(
            select(models.PlayerAppearance).where(
                models.PlayerAppearance.player_external_id.in_(on_pitch),
            ).limit(1)
        ).scalar_one_or_none()
        ref_tz = sample_app.kickoff.tzinfo if sample_app else None
        now = datetime.now(ref_tz) if ref_tz else datetime.utcnow()
        loads_by_player: dict[int, dict[str, Any]] = {}
        for pid in on_pitch:
            apps = list(
                session.execute(
                    select(models.PlayerAppearance).where(
                        models.PlayerAppearance.player_external_id == pid,
                        models.PlayerAppearance.kickoff >= now - timedelta(days=14),
                    )
                ).scalars()
            )
            v = compute_player_load(pid, apps, window_days=14, now=now).value
            loads_by_player[pid] = {
                "minutes_per_week": v.minutes_per_week,
                "high_load": v.high_load,
            }

        # Skor durumu → öncelik
        my_score = ch if is_home else ca
        opp_score = ca if is_home else ch
        gd = my_score - opp_score
        if gd < 0:
            priority = "chase"  # geride, hücum yenile
        elif gd > 0 and minute >= 70:
            priority = "protect"  # önde + son 20 dk, savunma sıkılaştır
        else:
            priority = "balance"

        # Bench impact skoru — son maçlardaki goal involvement proxy:
        # Yedek oyuncunun son 10 maçındaki ortalama dakika > 30 → "regular contributor".
        # Bu primitive bir proxy; gerçek "goal involvement" event-feed gerektirir.
        bench_impact: dict[int, dict[str, Any]] = {}
        for bid in bench:
            apps = list(
                session.execute(
                    select(models.PlayerAppearance).where(
                        models.PlayerAppearance.player_external_id == bid,
                        models.PlayerAppearance.kickoff >= now - timedelta(days=60),
                    ).order_by(models.PlayerAppearance.kickoff.desc()).limit(10)
                ).scalars()
            )
            recent_avg = (sum(a.minutes for a in apps) / len(apps)) if apps else 0.0
            bench_impact[bid] = {
                "recent_appearances": len(apps),
                "avg_minutes_recent": round(recent_avg, 1),
                # impact tier: regular contributor (≥30 dk/maç), squad player (≥10), fringe
                "tier": (
                    "regular" if recent_avg >= 30
                    else "squad" if recent_avg >= 10
                    else "fringe"
                ),
            }

        # Önerilen değişiklik kuralı:
        # 1) En yüksek yüklü 2 oyuncuyu çıkar
        # 2) Bench'ten "regular" → "squad" → "fringe" sırasıyla en iyileri al
        sorted_pitch = sorted(
            on_pitch, key=lambda p: loads_by_player[p]["minutes_per_week"], reverse=True,
        )
        suggested_out = sorted_pitch[:2]
        # Bench'i impact tier'a göre sırala (regular > squad > fringe), tier içinde
        # avg_minutes desc
        _tier_rank = {"regular": 0, "squad": 1, "fringe": 2}
        sorted_bench = sorted(
            bench,
            key=lambda b: (
                _tier_rank.get(bench_impact[b]["tier"], 3),
                -bench_impact[b]["avg_minutes_recent"],
            ),
        )
        suggested_in = sorted_bench[:2]

        # Optimum dakika önerisi — basit heuristic:
        # - chase: 60-70. dk arası ilk sub; 75-80 ikinci
        # - protect: 70+ ilk sub (savunma takviyesi); 85+ ikinci (zaman tüketme)
        # - balance: 55-65 ilk; 70-75 ikinci
        suggested_minutes_map = {
            "chase": [max(int(minute), 60), max(int(minute), 75)],
            "protect": [max(int(minute), 70), max(int(minute), 85)],
            "balance": [max(int(minute), 55), max(int(minute), 70)],
        }
        suggested_minutes = suggested_minutes_map[priority]
        proposed_subs = [
            {
                "out": out, "in": inn,
                "out_load_per_week": loads_by_player[out]["minutes_per_week"],
                "in_tier": bench_impact[inn]["tier"] if inn in bench_impact else "unknown",
                "suggested_minute": suggested_minutes[i] if i < len(suggested_minutes) else None,
            }
            for i, (out, inn) in enumerate(zip(suggested_out, suggested_in, strict=False))
        ]

        ai_brief = _build_sub_brief(
            commentator=self._commentator,
            match_id=match_id, team_id=team_id,
            minute=minute, my_score=my_score, opp_score=opp_score,
            priority=priority, proposed_subs=proposed_subs,
            on_pitch_loads={pid: loads_by_player[pid] for pid in on_pitch},
            bench_size=len(bench),
        )

        output = {
            "match_external_id": match_id,
            "team_external_id": team_id,
            "is_home": is_home,
            "minute": minute,
            "score": {"my": my_score, "opp": opp_score, "diff": gd},
            "priority": priority,
            "proposed_subs": proposed_subs,
            "on_pitch_loads": {str(pid): loads_by_player[pid] for pid in on_pitch},
            "bench_impact": {str(bid): bench_impact[bid] for bid in bench},
            "ai_brief": ai_brief,
        }
        summary = (
            f"Sub öneri match={match_id} team={team_id} dk={minute:.0f}: "
            f"durum={priority}, {len(proposed_subs)} değişiklik önerisi"
        )
        return AgentResult(
            output_json=output, summary=summary,
            subject_type="match", subject_id=match_id,
        )


def _build_sub_brief(
    *, commentator: ClaudeCommentator, match_id: int, team_id: int,
    minute: float, my_score: int, opp_score: int, priority: str,
    proposed_subs: list[dict], on_pitch_loads: dict, bench_size: int,
) -> str:
    if commentator._client.is_stub():
        return (
            f"[stub:sub_advice] match={match_id} dk={minute:.0f} "
            f"({my_score}-{opp_score}) priority={priority}: "
            f"{len(proposed_subs)} değişiklik. ANTHROPIC_API_KEY yok."
        )
    system = (
        "Sen futbol teknik direktörüne maç içi değişiklik önerisi sunan "
        "asistansın. 80-120 kelime. Yapı: (1) durum tespiti (skor+dakika), "
        "(2) önerilen değişiklikler (out → in player_id), "
        "(3) yedek sayısı yeterli mi notu."
    )
    user = (
        f"Maç {match_id}, takım {team_id}, dakika {minute:.0f}\n"
        f"Skor: benim={my_score} rakip={opp_score} (durum: {priority})\n"
        f"Önerilen değişiklikler: {proposed_subs}\n"
        f"Yedek sayısı: {bench_size}"
    )
    return commentator._call(system, user, max_tokens=350)
