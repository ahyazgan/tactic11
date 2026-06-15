"""Congestion Risk — fikstür yoğunluğu × seyahat × dinlenme penceresi.

Bir takımın önümüzdeki 14-30 gün fikstür planına bakar; pillar 3:
1. Maç sıklığı (≤3 gün arası kritik)
2. Toplam seyahat (km × gün)
3. Avrupa/lig + kupa kombinasyonu yorgunluğu

Çıktı: 0-100 congestion_score + faz (low|moderate|high|critical) +
risk_areas listesi + takım-bazlı tavsiye (rotation/transfer/tıbbi).

Pure compute. FixtureItem listesi input.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.audit import AuditRecord, EngineResult

ENGINE_NAME = "engine.congestion_risk"
ENGINE_VERSION = "1"

# Dinlenme eşikleri (saat)
CRITICAL_REST_HOURS = 72.0      # 3 gün altı kritik
SHORT_REST_HOURS = 96.0          # 4 gün altı kısa
# Seyahat eşikleri (km/maç ortalaması)
HIGH_TRAVEL_KM_PER_MATCH = 500.0
# Avrupa/kupa kombinasyonu — her ek kompetisyon +risk
EXTRA_COMP_PENALTY = 15.0
# Faz eşikleri (0..100 score)
PHASE_CRITICAL = 75.0
PHASE_HIGH = 55.0
PHASE_MODERATE = 30.0


@dataclass(frozen=True)
class FixtureItem:
    """Bir maç fikstür kalemi (kompozisyon-agnostik)."""
    kickoff: datetime
    is_home: bool
    competition: str                  # "league" | "cup" | "europa" | "champions"
    travel_km: float = 0.0            # toplam yolculuk (rakipten dön+gel)


@dataclass(frozen=True)
class CongestionRiskReport:
    fixtures_count: int
    window_days: int                  # üzerinde analiz yapılan pencere
    avg_rest_hours: float             # maçlar arası ortalama dinlenme
    min_rest_hours: float             # en kısa dinlenme
    short_rest_count: int             # ≤96sa olan boşluk sayısı
    critical_rest_count: int          # ≤72sa
    total_travel_km: float
    avg_travel_km_per_match: float
    competitions: tuple[str, ...] = field(default_factory=tuple)
    congestion_score: float = 0.0     # 0-100
    phase: str = "low"                # low/moderate/high/critical
    risk_areas: tuple[str, ...] = field(default_factory=tuple)
    advice: str = ""


def _rest_gaps(fixtures: list[FixtureItem]) -> list[float]:
    """Maçlar arası saat farkları."""
    if len(fixtures) < 2:
        return []
    ordered = sorted(fixtures, key=lambda f: f.kickoff)
    gaps: list[float] = []
    for prev, nxt in zip(ordered, ordered[1:], strict=False):
        delta = (nxt.kickoff - prev.kickoff).total_seconds() / 3600.0
        gaps.append(delta)
    return gaps


def _phase(score: float) -> str:
    if score >= PHASE_CRITICAL:
        return "critical"
    if score >= PHASE_HIGH:
        return "high"
    if score >= PHASE_MODERATE:
        return "moderate"
    return "low"


def _build_advice(phase: str, risk_areas: list[str]) -> str:
    base = {
        "critical": "Acil rotasyon + kupa kadrosu farklılaştır + tıbbi sayım kontrol",
        "high": "Yoğun rotasyon planla; B kadrosu maç dakikası alsın",
        "moderate": "Seçici rotasyon; kritik mevkilerde yedek hazır",
        "low": "Normal fikstür — standart kadro",
    }[phase]
    if risk_areas:
        base += " · risk: " + ", ".join(risk_areas)
    return base


def compute_congestion_risk(
    fixtures: Iterable[FixtureItem],
    *,
    window_days: int = 28,
    now: datetime | None = None,
) -> EngineResult[CongestionRiskReport]:
    """Fikstür yoğunluğu skor + tavsiye.

    window_days: analiz edilecek gelecek gün penceresi.
    now: 'şimdi' overrideable (test'ler için); default datetime.utcnow.
    """
    ref = now or datetime.utcnow()
    horizon = ref + timedelta(days=window_days)
    flist = sorted(
        [f for f in fixtures if ref <= f.kickoff <= horizon],
        key=lambda f: f.kickoff,
    )

    if not flist:
        plan = CongestionRiskReport(
            fixtures_count=0, window_days=window_days,
            avg_rest_hours=0.0, min_rest_hours=0.0,
            short_rest_count=0, critical_rest_count=0,
            total_travel_km=0.0, avg_travel_km_per_match=0.0,
            competitions=(), congestion_score=0.0, phase="low",
            risk_areas=(), advice="Pencere içinde fikstür yok",
        )
        return EngineResult(value=plan, audit=AuditRecord(
            engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
            subject_type="team", subject_id=0, metric="congestion_risk",
            value={"fixtures_count": 0, "phase": "low"},
            inputs={"window_days": window_days}, formula="empty",
        ))

    gaps = _rest_gaps(flist)
    avg_rest = (sum(gaps) / len(gaps)) if gaps else 0.0
    min_rest = min(gaps) if gaps else 0.0
    short = sum(1 for g in gaps if g <= SHORT_REST_HOURS)
    critical_g = sum(1 for g in gaps if g <= CRITICAL_REST_HOURS)
    total_km = sum(f.travel_km for f in flist)
    avg_km = total_km / len(flist) if flist else 0.0
    comps = tuple(sorted({f.competition for f in flist}))

    # Skor (0-100)
    rest_term = min(50.0, critical_g * 18.0 + short * 7.0)
    travel_term = min(20.0, (avg_km / HIGH_TRAVEL_KM_PER_MATCH) * 20.0)
    extra_comps = max(0, len(comps) - 1)
    comp_term = min(30.0, extra_comps * EXTRA_COMP_PENALTY)
    score = round(rest_term + travel_term + comp_term, 1)
    phase = _phase(score)

    risk_areas: list[str] = []
    if critical_g > 0:
        risk_areas.append(f"{critical_g} kritik kısa dinlenme (≤72sa)")
    if avg_km >= HIGH_TRAVEL_KM_PER_MATCH:
        risk_areas.append(f"yüksek seyahat ({avg_km:.0f}km/maç)")
    if extra_comps >= 2:
        risk_areas.append(f"{len(comps)} farklı kompetisyon")

    advice = _build_advice(phase, risk_areas)

    report = CongestionRiskReport(
        fixtures_count=len(flist), window_days=window_days,
        avg_rest_hours=round(avg_rest, 1),
        min_rest_hours=round(min_rest, 1),
        short_rest_count=short, critical_rest_count=critical_g,
        total_travel_km=round(total_km, 1),
        avg_travel_km_per_match=round(avg_km, 1),
        competitions=comps,
        congestion_score=score, phase=phase,
        risk_areas=tuple(risk_areas),
        advice=advice,
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="team", subject_id=0, metric="congestion_risk",
        value={
            "fixtures_count": len(flist),
            "congestion_score": score, "phase": phase,
            "min_rest_hours": round(min_rest, 1),
            "critical_rest_count": critical_g,
            "avg_travel_km": round(avg_km, 1),
            "competitions": list(comps),
            "advice": advice,
        },
        inputs={
            "window_days": window_days,
            "thresholds": {
                "critical_rest_h": CRITICAL_REST_HOURS,
                "short_rest_h": SHORT_REST_HOURS,
                "high_travel_km": HIGH_TRAVEL_KM_PER_MATCH,
                "extra_comp_penalty": EXTRA_COMP_PENALTY,
            },
        },
        formula=(
            "score = rest_term(critical*18+short*7, cap 50) + "
            "travel_term(avg_km/500*20, cap 20) + "
            "comp_term(extras*15, cap 30)"
        ),
    )
    return EngineResult(value=report, audit=audit)
