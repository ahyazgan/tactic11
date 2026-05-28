"""ScoutWatchlistDigestAgent — izlenen oyuncuların haftalık özet.

Bir scout şefi için: watchlist'teki oyuncuların son form snapshot'larını
toplayıp "bu hafta neler oldu" briefi üretir. AI sentez: "Aksiyon önerisi:
oyuncu X 3 hafta üst üste yüksek dakika → scout gönder" tarzı.

v2: engine.player_similarity entegre — yüksek Z-score oyuncular için
benzer profilde "alternatif" listesi (transfer hedefi öneri).

Context: {
  "user_id": str = "default",
  "recent_n": int = 5,
  "include_similarity": bool = True,
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
from app.engine.player_form import compute_player_form
from app.engine.player_similarity import compute_similar_players
from app.scout import list_watchlist
from app.sports import football


class ScoutWatchlistDigestAgent(Agent):
    """Haftalık scout watchlist özet."""

    name = "scout_watchlist_digest"
    version = "2"  # v1 → v2: engine.player_similarity entegre (similar suggestions)

    def __init__(self, *, commentator: ClaudeCommentator | None = None):
        self._commentator = commentator or ClaudeCommentator(AnthropicClient())

    def run(self, session: Session, *, context: dict[str, Any]) -> AgentResult:
        user_id = context.get("user_id", "default")
        recent_n = int(context.get("recent_n", 5))
        watch = list_watchlist(session, user_id=user_id)
        if not watch:
            return AgentResult(
                output_json={
                    "user_id": user_id, "player_count": 0,
                    "snapshots": [], "alerts": [], "ai_brief": "Watchlist boş.",
                },
                summary=f"watchlist boş (user={user_id})",
                subject_type="team", subject_id=0,
            )

        now = datetime.now(UTC)
        cutoff = now - timedelta(days=365)
        snapshots: list[dict[str, Any]] = []
        alerts: list[str] = []
        for entry in watch:
            apps = list(
                session.execute(
                    select(models.PlayerAppearance).where(
                        models.PlayerAppearance.sport == football.SPORT_NAME,
                        models.PlayerAppearance.player_external_id == entry.player_external_id,
                        models.PlayerAppearance.kickoff >= cutoff,
                    )
                ).scalars()
            )
            r = compute_player_form(
                entry.player_external_id, apps,
                recent_n=recent_n, now=now,
            ).value
            snapshots.append({
                "player_id": entry.player_external_id,
                "notes": entry.notes,
                "recent_matches": r.recent_matches,
                "recent_minutes_per_match": r.recent_minutes_per_match,
                "z_score": r.z_score,
                "trend": r.trend,
            })
            # Alert kuralları:
            if r.z_score is not None and r.z_score >= 1.0:
                alerts.append(
                    f"Player {entry.player_external_id}: Z={r.z_score:.2f} "
                    f"(baseline'dan belirgin yüksek dakika) — scout gönder"
                )
            if r.trend == "rising" and r.recent_matches >= 3:
                alerts.append(
                    f"Player {entry.player_external_id}: yükselen trend "
                    f"({r.recent_minutes_per_match:.0f} dk/maç)"
                )

        # v2: player_similarity — high-z player için benzer alternatif öner
        # (örnek: "izlediğin oyuncu pahalı, ama X/Y benzer profilde + ucuz")
        similar_suggestions: list[dict[str, Any]] = []
        if context.get("include_similarity", True):
            similar_suggestions = _compute_similarity_suggestions(
                session, snapshots, top_n=3,
            )

        ai_brief = _build_digest_brief(
            commentator=self._commentator,
            user_id=user_id, snapshots=snapshots, alerts=alerts,
            similar_suggestions=similar_suggestions,
        )

        output = {
            "user_id": user_id,
            "player_count": len(watch),
            "snapshots": snapshots,
            "alerts": alerts,
            "similar_suggestions": similar_suggestions,
            "ai_brief": ai_brief,
        }
        summary = (
            f"Scout digest (user={user_id}): {len(watch)} oyuncu, "
            f"{len(alerts)} alert"
        )
        return AgentResult(
            output_json=output, summary=summary,
            subject_type="team", subject_id=0,
        )


def _build_digest_brief(
    *, commentator: ClaudeCommentator, user_id: str,
    snapshots: list[dict], alerts: list[str],
    similar_suggestions: list[dict[str, Any]] | None = None,
) -> str:
    if commentator._client.is_stub():
        sim_n = sum(len(s.get("similar", [])) for s in (similar_suggestions or []))
        return (
            f"[stub:scout_digest] user={user_id} {len(snapshots)} oyuncu, "
            f"{len(alerts)} alert, {sim_n} benzer öneri. ANTHROPIC_API_KEY yok."
        )
    if not alerts and not snapshots:
        return "Watchlist'te aksiyon gerektiren oyuncu yok."
    system = (
        "Sen kulüp scout şefine haftalık watchlist raporu sunan asistansın. "
        "100-150 kelime. Yapı: (1) öne çıkan 2-3 oyuncu (Z-score + trend), "
        "(2) somut aksiyon önerileri (canlı izleme, scout maça gönder vs.)."
    )
    user = (
        f"Scout watchlist ({len(snapshots)} oyuncu).\n"
        f"Alert'ler ({len(alerts)}):\n" + "\n".join(f"- {a}" for a in alerts[:5])
        + "\n\nTop 3 form (Z-score):\n" + "\n".join(
            f"- player {s['player_id']}: Z={s['z_score']}, trend={s['trend']}, "
            f"{s['recent_minutes_per_match']} dk/maç"
            for s in sorted(
                snapshots,
                key=lambda x: x["z_score"] if x["z_score"] is not None else -99,
                reverse=True,
            )[:3]
        )
    )
    return commentator._call(system, user, max_tokens=400)


def _compute_similarity_suggestions(
    session: Session,
    snapshots: list[dict[str, Any]],
    *,
    top_n: int = 3,
) -> list[dict[str, Any]]:
    """High-Z watchlist oyuncuları için player_similarity ile benzer
    profilde N oyuncu öner.

    Aday havuzu: appearance'ı olan tüm oyuncular (current tenant — loader
    criteria aktif). High-Z (z_score >= 1.0) oyunculara öncelik.
    """
    # High-Z watchlist player'larını sırala
    targets = [
        s for s in snapshots
        if s.get("z_score") is not None and s["z_score"] >= 1.0
    ]
    if not targets:
        # high-Z yoksa en yüksek z'leri al
        targets = sorted(
            [s for s in snapshots if s.get("z_score") is not None],
            key=lambda x: x["z_score"], reverse=True,
        )[:2]
    if not targets:
        return []

    # Aday havuzu: appearance'ı olan tüm oyuncular
    all_apps = list(
        session.execute(
            select(models.PlayerAppearance).where(
                models.PlayerAppearance.sport == football.SPORT_NAME,
            )
        ).scalars()
    )
    if not all_apps:
        return []
    by_pid: dict[int, list] = {}
    for a in all_apps:
        by_pid.setdefault(a.player_external_id, []).append(a)

    suggestions: list[dict[str, Any]] = []
    for target in targets[:3]:  # max 3 target × top_n öneri
        pid = target["player_id"]
        target_apps = by_pid.get(pid, [])
        if not target_apps:
            continue
        candidates = {p: apps for p, apps in by_pid.items() if p != pid}
        result = compute_similar_players(
            pid, target_apps, candidates, top_n=top_n, min_minutes=180,
        )
        if not result.value.top_matches:
            continue
        suggestions.append({
            "target_player_id": pid,
            "target_z_score": target["z_score"],
            "similar": [
                {
                    "player_id": m.player_external_id,
                    "similarity": m.similarity,
                    "minutes": m.total_minutes,
                }
                for m in result.value.top_matches
            ],
        })
    return suggestions
