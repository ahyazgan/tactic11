"""Sub Timing — optimal değişiklik zamanı + etki + paket (Faz 6 #4, #5, #6).

substitution_chess'in canlı, zaman-odaklı genişlemesi:
- Optimal timing: "şimdi mi 70'te mi?" — fatigue eğrisi × kalan dakika ×
  skor senaryosu
- Etki tahmini: sub yaparsan beklenen dominance/fatigue kazancı
- Paket öneri: tek değil, çoklu sub kombinasyonu

Saf hesap. live_sub_recommendation + substitution_chess üstüne kurulu.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.audit import AuditRecord, EngineResult
from app.domain import DefensiveAction, PassEvent
from app.engine.live_sub_recommendation import compute_live_sub_recommendation

ENGINE_NAME = "engine.sub_timing"
ENGINE_VERSION = "1"

# Fatigue dakika başına artış (substitution_chess ile uyumlu)
FATIGUE_PER_MINUTE = 0.007
# "Şimdi sub yap" eşiği: fatigue projeksiyonu bu seviyeyi aşacaksa
URGENT_PROJECTED_FATIGUE = 0.70
# Paket sub: kaç oyuncu birden değişebilir (kural: maç başına 5, tek seferde 3)
MAX_PACKAGE_SIZE = 3


@dataclass(frozen=True)
class SubTimingAdvice:
    player_external_id: int
    current_fatigue: float
    # Şimdi sub yapılırsa vs beklenirse
    timing_verdict: str          # "now" | "wait_10" | "wait_20" | "hold"
    projected_fatigue_full_time: float
    minutes_until_critical: float | None   # kaç dk sonra kritik eşik
    impact_estimate: float        # 0-1 sub'ın beklenen fayda skoru


@dataclass(frozen=True)
class SubTimingReport:
    team_external_id: int
    current_minute: float
    minutes_remaining: float
    advices: tuple[SubTimingAdvice, ...]   # urgency sıralı
    package_recommendation: tuple[int, ...]  # birlikte değiştirilecek oyuncu id
    package_rationale: str


def _minutes_until_critical(
    current_fatigue: float, minutes_remaining: float,
) -> float | None:
    """Kaç dakika sonra URGENT_PROJECTED_FATIGUE aşılır."""
    if current_fatigue >= URGENT_PROJECTED_FATIGUE:
        return 0.0
    gap = URGENT_PROJECTED_FATIGUE - current_fatigue
    minutes = gap / FATIGUE_PER_MINUTE
    if minutes > minutes_remaining:
        return None  # maç bitene kadar kritik olmaz
    return round(minutes, 1)


def _timing_verdict(mins_to_crit: float | None) -> str:
    if mins_to_crit is None:
        return "hold"
    if mins_to_crit <= 2:
        return "now"
    if mins_to_crit <= 12:
        return "wait_10"
    return "wait_20"


def compute_sub_timing(
    team_external_id: int,
    all_passes: Iterable[PassEvent],
    all_def_actions: Iterable[DefensiveAction],
    *,
    current_minute: float,
    match_total_minutes: float = 90.0,
    my_score: int = 0,
    opponent_score: int = 0,
) -> EngineResult[SubTimingReport]:
    """Optimal sub zamanlaması + etki + paket önerisi."""
    passes = list(all_passes)
    defs = list(all_def_actions)
    minutes_remaining = max(0.0, match_total_minutes - current_minute)

    sub_rec = compute_live_sub_recommendation(
        team_external_id, passes, defs,
        current_minute=current_minute,
        my_score=my_score, opponent_score=opponent_score,
    ).value

    advices: list[SubTimingAdvice] = []
    for sub in sub_rec.recommendations:
        fatigue = sub.fatigue_score
        mins_crit = _minutes_until_critical(fatigue, minutes_remaining)
        verdict = _timing_verdict(mins_crit)
        proj = min(1.0, fatigue + FATIGUE_PER_MINUTE * minutes_remaining)
        # Impact: yüksek fatigue + çok kalan dakika = yüksek fayda
        impact = round(min(1.0, fatigue * (minutes_remaining / 45.0)), 3)
        advices.append(SubTimingAdvice(
            player_external_id=sub.player_external_id,
            current_fatigue=round(fatigue, 3),
            timing_verdict=verdict,
            projected_fatigue_full_time=round(proj, 3),
            minutes_until_critical=mins_crit,
            impact_estimate=impact,
        ))

    # Sırala: "now" önce, sonra impact
    verdict_order = {"now": 0, "wait_10": 1, "wait_20": 2, "hold": 3}
    advices.sort(key=lambda a: (verdict_order.get(a.timing_verdict, 9), -a.impact_estimate))

    # Paket: "now" verdict'li + skor geride ise daha agresif
    now_subs = [a.player_external_id for a in advices if a.timing_verdict == "now"]
    package = tuple(now_subs[:MAX_PACKAGE_SIZE])
    if my_score < opponent_score and len(package) < MAX_PACKAGE_SIZE:
        # Geride: wait_10'ları da pakete al (erken müdahale)
        extra = [a.player_external_id for a in advices
                 if a.timing_verdict == "wait_10"
                 and a.player_external_id not in package]
        package = tuple(list(package) + extra)[:MAX_PACKAGE_SIZE]

    if not package:
        pkg_rationale = "Acil değişiklik gerekmiyor"
    elif my_score < opponent_score:
        pkg_rationale = (
            f"Geride — {len(package)} oyuncu paket değişikliği ile "
            f"momentum + tazelik kazan"
        )
    else:
        pkg_rationale = f"{len(package)} oyuncu acil rotasyon (yorgunluk eşiği)"

    report = SubTimingReport(
        team_external_id=team_external_id,
        current_minute=current_minute,
        minutes_remaining=minutes_remaining,
        advices=tuple(advices),
        package_recommendation=package,
        package_rationale=pkg_rationale,
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="team", subject_id=team_external_id,
        metric="sub_timing",
        value={
            "minutes_remaining": minutes_remaining,
            "package": list(package),
            "package_rationale": pkg_rationale,
            "advices": [
                {"player_id": a.player_external_id, "verdict": a.timing_verdict,
                 "impact": a.impact_estimate,
                 "mins_until_critical": a.minutes_until_critical}
                for a in advices
            ],
        },
        inputs={
            "current_minute": current_minute,
            "match_total_minutes": match_total_minutes,
            "urgent_projected_fatigue": URGENT_PROJECTED_FATIGUE,
            "my_score": my_score, "opponent_score": opponent_score,
        },
        formula="minutes_until_critical = (0.70 - fatigue)/0.007; verdict + impact + paket",
    )
    return EngineResult(value=report, audit=audit)
