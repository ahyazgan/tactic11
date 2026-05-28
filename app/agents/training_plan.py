"""TrainingPlanAgent — rakip profilinden bu haftaki antrenman planı önerisi.

Context: {"my_team_external_id": int, "opponent_external_id": int}
Output: {
  opponent profile özet (PPDA, archetype, pres tarzı, kanal tercihi),
  drills: [3-5 öneri — her biri name, focus, rationale],
  ai_brief: "Bu hafta odak: rakip yüksek pres + sol kanat ağır..." 250 kelime
}

Mevcut Faz N + Wave 2/3 engine'lerini agregat eder. Yeni engine yok.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.agents.base import Agent, AgentResult
from app.ai import AnthropicClient, ClaudeCommentator
from app.data.loaders import load_team_events
from app.engine.channel_preference import compute_channel_preference
from app.engine.coaching_identity import compute_coaching_identity
from app.engine.ppda import compute_ppda
from app.engine.pressing_trigger import compute_pressing_trigger
from app.engine.recovery_zone_heat import compute_recovery_zone_heat


class TrainingPlanAgent(Agent):
    """Haftalık antrenman planı — rakip profilinden drill önerileri."""

    name = "training_plan"
    version = "1"

    def __init__(self, *, commentator: ClaudeCommentator | None = None):
        self._commentator = commentator or ClaudeCommentator(AnthropicClient())

    def run(self, session: Session, *, context: dict[str, Any]) -> AgentResult:
        my_team = context.get("my_team_external_id")
        opp_team = context.get("opponent_external_id")
        if my_team is None or opp_team is None:
            raise ValueError(
                "context.my_team_external_id + opponent_external_id zorunlu",
            )
        my_team = int(my_team)
        opp_team = int(opp_team)

        opp_events = load_team_events(session, opp_team, last_n=5)
        if opp_events.total == 0:
            return AgentResult(
                output_json={
                    "my_team_external_id": my_team,
                    "opponent_external_id": opp_team,
                    "events_loaded": 0,
                    "drills": [],
                    "note": "Rakip için event ingest yok",
                    "ai_brief": "[stub:training_plan] rakip events yok.",
                },
                summary=f"training plan: events yok (opp={opp_team})",
                subject_type="team", subject_id=my_team,
            )

        ppda = compute_ppda(
            opp_team, opp_events.passes, opp_events.defensive_actions,
            matches_analyzed=len(opp_events.match_ids),
        ).value
        pres = compute_pressing_trigger(
            opp_team, opp_events.passes, opp_events.defensive_actions,
            matches_analyzed=len(opp_events.match_ids),
        ).value
        rzh = compute_recovery_zone_heat(
            opp_team, opp_events.defensive_actions,
            matches_analyzed=len(opp_events.match_ids),
        ).value
        identity = compute_coaching_identity(
            opp_team, my_team,
            opp_events.passes, opp_events.defensive_actions, opp_events.shots,
            matches_analyzed=len(opp_events.match_ids),
        ).value
        chan = compute_channel_preference(
            opp_team, opp_events.passes,
            matches_analyzed=len(opp_events.match_ids),
        ).value

        drills = _propose_drills(
            ppda_value=ppda.ppda,
            pres_style=pres.style_label,
            recovery_style=rzh.style_label,
            archetype=identity.archetype,
            dominant_channel=chan.dominant_channel,
        )

        ai_brief = _build_training_brief(
            commentator=self._commentator,
            my_team=my_team, opp_team=opp_team,
            ppda=ppda, pres=pres, rzh=rzh,
            identity=identity, chan=chan,
            drills=drills,
        )

        output = {
            "my_team_external_id": my_team,
            "opponent_external_id": opp_team,
            "events_loaded": opp_events.total,
            "matches_analyzed": len(opp_events.match_ids),
            "opponent_profile": {
                "ppda": ppda.ppda,
                "pressing_style": pres.style_label,
                "recovery_style": rzh.style_label,
                "archetype": identity.archetype,
                "dominant_channel": chan.dominant_channel,
            },
            "drills": drills,
            "ai_brief": ai_brief,
        }
        summary = (
            f"training plan vs {opp_team}: arketip {identity.archetype}, "
            f"PPDA {ppda.ppda}, {len(drills)} drill"
        )
        return AgentResult(
            output_json=output, summary=summary,
            subject_type="team", subject_id=my_team,
        )


def _propose_drills(
    *, ppda_value: float, pres_style: str, recovery_style: str,
    archetype: str, dominant_channel: str,
) -> list[dict[str, str]]:
    """Heuristic drill önerileri — rakip profilinin kombinasyonundan."""
    drills: list[dict[str, str]] = []

    # 1. Pres yoğunluğuna göre top çıkış antrenmanı
    if ppda_value < 10:
        drills.append({
            "name": "Pres altında 3-2 build-up",
            "focus": "Yüksek pres'e direnç",
            "rationale": (
                f"Rakip PPDA {ppda_value} (çok yoğun pres). Kaleci+def "
                f"3'lü ile orta sahaya çıkarken 2'ye 1 avantajı oluştur."
            ),
            "duration_min": "20",
        })
    elif ppda_value > 15:
        drills.append({
            "name": "Hızlı dikey atak (mid-block delme)",
            "focus": "Düşük blok'u esnetme",
            "rationale": (
                f"Rakip PPDA {ppda_value} (alçak blok). Geniş tutup "
                f"orta sahadan dikey arkaya çıkış drilli."
            ),
            "duration_min": "25",
        })

    # 2. Pres tarzına göre tepki
    if pres_style == "gegenpress":
        drills.append({
            "name": "Top kayıp sonrası 6sn geri-kazanım",
            "focus": "Counter-press direnç",
            "rationale": (
                "Rakip gegenpress yapıyor. Antrenmanda topu kaybeden "
                "oyuncu hemen yön değiştirip 3 yakın paslaşma."
            ),
            "duration_min": "15",
        })

    # 3. Recovery zone'a göre saldırı
    if recovery_style == "high_press":
        drills.append({
            "name": "Uzun top + ikinci top mücadelesi",
            "focus": "Yüksek savunma hattının arkasına",
            "rationale": (
                "Rakip hücum üçünde top kazanıyor. Kaleci uzun top + "
                "hücum oyuncularıyla ikinci top kazanma."
            ),
            "duration_min": "20",
        })

    # 4. Kanal tercihine göre savunma
    if dominant_channel in ("left", "right"):
        side = "sol" if dominant_channel == "left" else "sağ"
        drills.append({
            "name": f"{side.capitalize()} kanat 2v2 + overlap",
            "focus": f"Rakibin {side} kanat ağırlığına karşı sayısal üstünlük",
            "rationale": (
                f"Rakip atakları {side} kanattan ağırlıklı. "
                f"İlgili bek + kanat orta sahası 2v2 + arkadan overlap drilli."
            ),
            "duration_min": "20",
        })

    # 5. Koç arketipi — strateji
    if archetype == "high_press_possession":
        drills.append({
            "name": "Köşe direkt vuruş + uzun pas çıkışı (Pep-tarz rakibe)",
            "focus": "Possession kaybedince kontra'ya hazırlık",
            "rationale": (
                "Rakip high_press_possession. Top kazanılırsa dikey 1-2 "
                "pas içinde rakip yarısına ulaşma."
            ),
            "duration_min": "15",
        })
    elif archetype == "low_block_counter":
        drills.append({
            "name": "Yan dağılım + cross çeşitliliği",
            "focus": "Derin blok'u kanattan yarmak",
            "rationale": (
                "Rakip low_block_counter. Bek-kanat-orta saha üçlüsünden "
                "in-swinger/out-swinger ve geri pas alternatifleri."
            ),
            "duration_min": "20",
        })

    if not drills:
        drills.append({
            "name": "Standart hafta — top kontrolü + pozisyonel oyun",
            "focus": "Genel",
            "rationale": "Rakip profilinde belirgin pattern yok; standart hafta.",
            "duration_min": "25",
        })
    return drills


def _build_training_brief(
    *, commentator: ClaudeCommentator,
    my_team: int, opp_team: int,
    ppda, pres, rzh, identity, chan,
    drills: list[dict[str, str]],
) -> str:
    if commentator._client.is_stub():
        return (
            f"[stub:training_plan] takım {my_team} vs rakip {opp_team}: "
            f"PPDA {ppda.ppda}, arketip {identity.archetype}, "
            f"{len(drills)} drill önerisi. ANTHROPIC_API_KEY yok."
        )
    system = (
        "Sen futbol teknik direktörünün haftalık antrenman planını öneren "
        "asistansın. 200-250 kelime. Yapı:\n"
        "1) Rakip profil özeti (2 cümle)\n"
        "2) Hafta odağı — 1 cümle (genel hedef)\n"
        "3) Önerilen drill'lerin neden seçildiği (madde madde, kısa)\n"
        "4) Pazar maç öncesi kaçınılması gerekenler (1 cümle)\n"
        "Sayıları tekrar etme; çıkarım yaz."
    )
    drill_lines = "\n".join(
        f"- {d['name']}: {d['focus']} ({d['duration_min']} dk)"
        for d in drills
    )
    user = (
        f"Takım {my_team} vs Rakip {opp_team}\n\n"
        f"Rakip profil:\n"
        f"- PPDA: {ppda.ppda} ({pres.style_label} stilinde)\n"
        f"- Kazanım stili: {rzh.style_label}\n"
        f"- Arketip: {identity.archetype}\n"
        f"- Dominant kanal: {chan.dominant_channel}\n\n"
        f"Önerilen drill'ler:\n{drill_lines}"
    )
    return commentator._call(system, user, max_tokens=700)
