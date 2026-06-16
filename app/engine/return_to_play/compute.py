"""Return-to-Play Plan — sakatlıktan dönüş çoklu-test sentezi.

`engine.performance_test.return_to_play_readiness` tekil test bazlı (10m
sprint, CMJ vb.) hızlı kontrol verir. Bu engine TÜM mikro-test sonuçlarını
birleştirir; readiness yüzdesi + phase (1-5 protokol) + öneri dakika
sahasında kalma süresini üretir. Çıktı medikal merkez + saha-içi karar
panelinde tek-bakışta gösterilir.

Pure compute. TestResultInput listesi + opsiyonel oyuncu meta input.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from app.audit import AuditRecord, EngineResult

ENGINE_NAME = "engine.return_to_play"
ENGINE_VERSION = "1"

# Tek test için yeşil ışık eşiği (performance_test ile uyumlu)
TEST_GREEN_PCT = 95.0
TEST_AMBER_PCT = 85.0

# RTP fazı belirleyici toplam readiness
PHASE_THRESHOLDS = [
    (95.0, 5),   # 5: full match — ≥%95
    (88.0, 4),   # 4: tam antrenman + maç dakikaları
    (78.0, 3),   # 3: takım antrenmanı (sınırlı temas)
    (60.0, 2),   # 2: bireysel + grup top çalışması
    (0.0, 1),    # 1: temel kondisyon
]

# Faza göre güvenli maç dakikası (tahmini ceiling)
PHASE_MAX_MINUTES = {1: 0, 2: 0, 3: 15, 4: 45, 5: 90}


@dataclass(frozen=True)
class TestResultInput:
    """Bir mikro test'in (sprint/cmj/jump vb.) güncel ve sakatlık-öncesi değerleri."""
    test_name: str
    current: float
    pre_injury_baseline: float
    higher_is_better: bool = True
    weight: float = 1.0          # toplam readiness'a katkı ağırlığı


@dataclass(frozen=True)
class TestResultScore:
    test_name: str
    pct_of_baseline: float       # 0-100+; baseline'a göre yüzde
    light: str                   # "yeşil" | "sarı" | "kırmızı"
    weight: float


@dataclass(frozen=True)
class ReturnToPlayPlan:
    player_external_id: int
    test_count: int
    overall_readiness_pct: float        # ağırlıklı ortalama
    phase: int                          # 1..5
    light: str                          # genel — yeşil/sarı/kırmızı
    recommended_max_minutes: int        # bu fazda güvenli ceiling
    weakest_test: TestResultScore | None
    strongest_test: TestResultScore | None
    test_scores: tuple[TestResultScore, ...] = field(default_factory=tuple)
    advice: str = ""


def _test_pct(t: TestResultInput) -> float:
    if t.pre_injury_baseline <= 0 or t.current <= 0:
        return 0.0
    ratio = (t.current / t.pre_injury_baseline if t.higher_is_better
             else t.pre_injury_baseline / t.current)
    return round(ratio * 100.0, 1)


def _test_light(pct: float) -> str:
    if pct >= TEST_GREEN_PCT:
        return "yeşil"
    if pct >= TEST_AMBER_PCT:
        return "sarı"
    return "kırmızı"


def _phase_for(readiness: float) -> int:
    for threshold, phase in PHASE_THRESHOLDS:
        if readiness >= threshold:
            return phase
    return 1


def _build_advice(phase: int, weakest: TestResultScore | None,
                   light: str) -> str:
    base = {
        5: "Tam maç oynayabilir; izlemeye devam (yüklenmeyi takip et).",
        4: "Tam antrenmana dön; ilk maçta kısıtlı dakika (≤45 dk) ile başla.",
        3: "Takım antrenmanına gir; temaslı drilleri sınırla, son üçte oyna.",
        2: "Bireysel + grup top çalışması; takım antrenmanına henüz hazır değil.",
        1: "Temel kondisyon + tedavi devam etsin; saha çalışması erken.",
    }.get(phase, "Plan belirsiz")
    if weakest and weakest.light == "kırmızı":
        base += f" Zayıf nokta: {weakest.test_name} (%{weakest.pct_of_baseline:.0f})"
    if light == "kırmızı":
        base += " — kırmızı ışık, klinik karar zorunlu."
    return base


def compute_return_to_play_plan(
    player_external_id: int,
    tests: Iterable[TestResultInput],
) -> EngineResult[ReturnToPlayPlan]:
    """Çoklu-test sonuçlarından RTP plan."""
    scored: list[TestResultScore] = []
    weighted_sum = 0.0
    weight_total = 0.0
    for t in tests:
        pct = _test_pct(t)
        score = TestResultScore(
            test_name=t.test_name, pct_of_baseline=pct,
            light=_test_light(pct), weight=t.weight,
        )
        scored.append(score)
        weighted_sum += pct * t.weight
        weight_total += t.weight

    overall = round(weighted_sum / weight_total, 1) if weight_total > 0 else 0.0
    phase = _phase_for(overall)
    light = "yeşil" if overall >= TEST_GREEN_PCT else (
        "sarı" if overall >= TEST_AMBER_PCT else "kırmızı"
    )
    max_minutes = PHASE_MAX_MINUTES.get(phase, 0)

    weakest = min(scored, key=lambda s: s.pct_of_baseline) if scored else None
    strongest = max(scored, key=lambda s: s.pct_of_baseline) if scored else None

    advice = _build_advice(phase, weakest, light)

    plan = ReturnToPlayPlan(
        player_external_id=player_external_id,
        test_count=len(scored),
        overall_readiness_pct=overall,
        phase=phase, light=light,
        recommended_max_minutes=max_minutes,
        weakest_test=weakest, strongest_test=strongest,
        test_scores=tuple(scored),
        advice=advice,
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="player", subject_id=player_external_id,
        metric="return_to_play_plan",
        value={
            "overall_readiness_pct": overall,
            "phase": phase,
            "light": light,
            "recommended_max_minutes": max_minutes,
            "weakest_test": weakest.test_name if weakest else None,
            "strongest_test": strongest.test_name if strongest else None,
            "test_count": len(scored),
            "advice": advice,
        },
        inputs={
            "test_count": len(scored),
            "thresholds": {
                "test_green_pct": TEST_GREEN_PCT,
                "test_amber_pct": TEST_AMBER_PCT,
                "phase_thresholds": dict((str(p), t) for t, p in PHASE_THRESHOLDS),
            },
        },
        formula=(
            "pct = (current/baseline | baseline/current) × 100; "
            "overall = Σ(pct·w) / Σw; "
            "phase = 5(≥95) | 4(≥88) | 3(≥78) | 2(≥60) | 1"
        ),
    )
    return EngineResult(value=plan, audit=audit)
