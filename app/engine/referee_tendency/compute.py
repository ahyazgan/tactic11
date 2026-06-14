"""Referee Tendency — hakem eğilim profili (J.1).

Bir hakemin geçmiş maçlarındaki kart/faul oranlarından eğilim çıkarır:
- yellows_per_match, reds_per_match
- cards_per_foul_ratio (kart/faul)
- severity: "lenient" | "average" | "strict"
- penalty_rate_per_match
- home_bias_pct (ev sahibine vs deplasmana çıkan sarı dağılımı)

Pure compute. PriorMatch listesi (her biri summary dict) + current match
context (opsiyonel) input. Maç-içi panele "rakip + bizim taraf temaslı
tackle azalt" tavsiyesi döner.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from app.audit import AuditRecord, EngineResult

ENGINE_NAME = "engine.referee_tendency"
ENGINE_VERSION = "1"

# Liga ortalaması referans (Süper Lig / La Liga ~ 4-5 sarı / maç)
LEAGUE_AVG_YELLOWS = 4.5
LEAGUE_AVG_REDS = 0.18
LEAGUE_AVG_CARDS_PER_FOUL = 0.12

# Severity eşikleri (vs liga avg)
STRICT_THRESHOLD = 1.20    # ≥ avg × 1.2 → strict
LENIENT_THRESHOLD = 0.80   # ≤ avg × 0.8 → lenient

# Min örnek (altı veri yetersiz → "unknown")
MIN_MATCHES_FOR_TENDENCY = 5


@dataclass(frozen=True)
class RefereeTendencyReport:
    referee_id: str | None
    referee_name: str | None
    matches_analyzed: int
    # Ham metrik
    yellows_per_match: float
    reds_per_match: float
    cards_per_foul_ratio: float
    penalty_rate_per_match: float
    home_yellow_share_pct: float       # bizim ev'deysek lehimize/aleyhimize
    # Karar
    severity: str                       # "lenient" | "average" | "strict" | "unknown"
    severity_score: float              # vs liga avg ratio (1.0 = ortalama)
    tactical_advice: str


def _avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _classify_severity(yellows_ratio: float, matches: int) -> str:
    if matches < MIN_MATCHES_FOR_TENDENCY:
        return "unknown"
    if yellows_ratio >= STRICT_THRESHOLD:
        return "strict"
    if yellows_ratio <= LENIENT_THRESHOLD:
        return "lenient"
    return "average"


def _build_advice(*, severity: str, penalty_rate: float, home_bias: float) -> str:
    if severity == "unknown":
        return "Hakem geçmişi yetersiz — standart disiplin uygula"
    parts: list[str] = []
    if severity == "strict":
        parts.append(
            "Hakem strict — temaslı tackle azalt, sarı eşiğine erken yaklaşıyoruz"
        )
    elif severity == "lenient":
        parts.append(
            "Hakem lenient — fiziksel oyun çalışır, taktik faul cezasız kalabilir"
        )
    else:
        parts.append("Hakem ortalama — standart disiplin")
    if penalty_rate >= 0.5:
        parts.append("penaltı verme oranı yüksek — ceza alanında temas dikkat")
    if abs(home_bias - 50) >= 15:
        side = "ev sahibine" if home_bias > 50 else "deplasmana"
        parts.append(
            f"sarı dağılımı {side} eğilimli (%{home_bias:.0f}) — bizim sahaya göre değerlendir"
        )
    return " · ".join(parts)


def compute_referee_tendency(
    prior_matches: Iterable[dict[str, Any]],
    *,
    referee_id: str | None = None,
    referee_name: str | None = None,
) -> EngineResult[RefereeTendencyReport]:
    """Hakem eğilim çıkar.

    prior_matches: [{
        yellows_total: int, reds_total: int,
        fouls_total: int (opsiyonel),
        penalties: int (opsiyonel, 0/1),
        yellows_home: int (opsiyonel, ev sahibi tarafı sarı sayısı),
    }]
    """
    matches = list(prior_matches)
    yellows = [float(m.get("yellows_total", 0)) for m in matches]
    reds = [float(m.get("reds_total", 0)) for m in matches]
    fouls = [float(m.get("fouls_total", 0)) for m in matches if m.get("fouls_total")]
    penalties = [float(m.get("penalties", 0)) for m in matches]
    yellow_home_shares: list[float] = []
    for m in matches:
        yh = m.get("yellows_home")
        yt = m.get("yellows_total", 0)
        if yh is not None and yt:
            yellow_home_shares.append(100.0 * float(yh) / float(yt))

    ypm = round(_avg(yellows), 2)
    rpm = round(_avg(reds), 3)
    cards_per_foul = (
        round((sum(yellows) + sum(reds)) / sum(fouls), 3)
        if fouls and sum(fouls) > 0 else LEAGUE_AVG_CARDS_PER_FOUL
    )
    penalty_rate = round(_avg(penalties), 3)
    home_yellow_share = round(_avg(yellow_home_shares), 1) if yellow_home_shares else 50.0

    severity_score = round(ypm / LEAGUE_AVG_YELLOWS, 2) if LEAGUE_AVG_YELLOWS else 1.0
    severity = _classify_severity(severity_score, len(matches))
    advice = _build_advice(
        severity=severity, penalty_rate=penalty_rate, home_bias=home_yellow_share,
    )

    report = RefereeTendencyReport(
        referee_id=referee_id, referee_name=referee_name,
        matches_analyzed=len(matches),
        yellows_per_match=ypm, reds_per_match=rpm,
        cards_per_foul_ratio=cards_per_foul,
        penalty_rate_per_match=penalty_rate,
        home_yellow_share_pct=home_yellow_share,
        severity=severity,
        severity_score=severity_score,
        tactical_advice=advice,
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="referee", subject_id=hash(referee_id or "") & 0xFFFF,
        metric="referee_tendency",
        value={
            "severity": severity,
            "severity_score": severity_score,
            "yellows_per_match": ypm,
            "reds_per_match": rpm,
            "cards_per_foul_ratio": cards_per_foul,
            "penalty_rate_per_match": penalty_rate,
            "home_yellow_share_pct": home_yellow_share,
            "matches_analyzed": len(matches),
            "tactical_advice": advice,
        },
        inputs={
            "referee_id": referee_id,
            "league_avg_yellows": LEAGUE_AVG_YELLOWS,
            "thresholds": {
                "strict": STRICT_THRESHOLD, "lenient": LENIENT_THRESHOLD,
                "min_matches": MIN_MATCHES_FOR_TENDENCY,
            },
        },
        formula=(
            "yellows_per_match / league_avg → severity_score; "
            "≥1.2 strict, ≤0.8 lenient, arası average"
        ),
    )
    return EngineResult(value=report, audit=audit)
