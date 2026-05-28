"""Opponent Reaction — rakip okuma (Faz 6 #13, #14).

İki canlı sinyal:
1. Rakip sub tepkisi: rakip oyuncu değiştirdiğinde "bu X'e geçiş demek,
   sen Y yap" — pozisyon-bazlı yorumlama
2. Rakip momentum kırma: rakip baskısında "molayı kullan / oyunu yavaşlat"

Saf hesap. Rakip sub event'leri + mevcut momentum input.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from app.audit import AuditRecord, EngineResult

ENGINE_NAME = "engine.opponent_reaction"
ENGINE_VERSION = "1"

# Pozisyon → rakip ne yapmaya çalışıyor + bizim karşı hamle
SUB_INTENT = {
    "F": {
        "intent": "hücum gücü artırıyor (forvet girdi)",
        "counter": "ekstra defansif orta saha / bek desteği düşün",
    },
    "M": {
        "intent": "orta saha kontrolü / tazelik",
        "counter": "orta saha presini koru, top kaybetme",
    },
    "D": {
        "intent": "savunmayı sağlamlaştırıyor (sonucu koruyor olabilir)",
        "counter": "kanat genişliği + duran top ile zorla",
    },
    "G": {
        "intent": "kaleci değişikliği (sakatlık/penaltı)",
        "counter": "yeni kalecinin ilk dakikalarını test et — şut dene",
    },
}


@dataclass(frozen=True)
class OpponentReactionReport:
    team_external_id: int
    opponent_external_id: int
    current_minute: float
    opp_subs_detected: int
    sub_interpretation: tuple[dict[str, Any], ...]  # her sub için intent+counter
    momentum_break_advice: str | None    # rakip baskıdaysa
    overall_advice: str


def compute_opponent_reaction(
    team_external_id: int,
    opponent_external_id: int,
    opponent_subs: Iterable[dict[str, Any]],
    *,
    current_minute: float,
    momentum_score: float = 0.0,
) -> EngineResult[OpponentReactionReport]:
    """Rakip sub'larını yorumla + momentum kırma önerisi.

    opponent_subs: [{position_in, minute}] — rakibin giren oyuncularının
    pozisyonu (F/M/D/G)
    momentum_score: -1 (rakip baskın) .. +1 (biz baskın)
    """
    subs = list(opponent_subs)
    interpretations: list[dict[str, Any]] = []
    for sub in subs:
        pos = sub.get("position_in", "M")
        info = SUB_INTENT.get(pos, SUB_INTENT["M"])
        interpretations.append({
            "minute": sub.get("minute"),
            "position_in": pos,
            "opponent_intent": info["intent"],
            "our_counter": info["counter"],
        })

    # Momentum kırma: rakip baskınsa (momentum < -0.3)
    momentum_break: str | None = None
    if momentum_score < -0.3:
        momentum_break = (
            "Rakip baskı kuruyor → oyunu yavaşlat (kaleci topu beklet, "
            "taç/korner uzat), ritmi boz; gerekirse zorunlu mola/sakatlık "
            "duraklamasını kullan"
        )

    # Overall
    if subs and momentum_break:
        overall = (
            f"Rakip {len(subs)} değişiklik + baskı kuruyor — hem karşı "
            f"hamleyi hem ritim kırmayı uygula"
        )
    elif subs:
        overall = f"Rakip {len(subs)} değişiklik yaptı — niyeti oku, karşı pozisyon al"
    elif momentum_break:
        overall = "Rakip baskıda ama henüz değişiklik yok — ritmi kır, sabırlı ol"
    else:
        overall = "Rakip statik — kendi planını sürdür"

    report = OpponentReactionReport(
        team_external_id=team_external_id,
        opponent_external_id=opponent_external_id,
        current_minute=current_minute,
        opp_subs_detected=len(subs),
        sub_interpretation=tuple(interpretations),
        momentum_break_advice=momentum_break,
        overall_advice=overall,
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="match", subject_id=team_external_id,
        metric="opponent_reaction",
        value={
            "opp_subs_detected": len(subs),
            "sub_interpretation": interpretations,
            "momentum_break_advice": momentum_break,
            "overall_advice": overall,
        },
        inputs={
            "current_minute": current_minute,
            "momentum_score": momentum_score,
            "opponent_external_id": opponent_external_id,
        },
        formula="rakip sub pozisyonu → intent+counter map; momentum<-0.3 → ritim kırma",
    )
    return EngineResult(value=report, audit=audit)
