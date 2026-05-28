"""Injury Risk — yük + sıklık + yaş → sakatlık risk skoru (Faz 5 #42).

Gabbett (2016) acute:chronic workload ratio + yaş + back-to-back sıklığı
heuristic'i. Gerçek ML 2+ sezon sakatlık geçmişi ister; bu skor literatür
tabanlı kompozit.

Girdi: oyuncunun load raporu (minutes_per_week, back_to_back) + yaş +
(opsiyonel) son 28 gün vs son 7 gün dakika (acute:chronic).

Çıktı: 0-100 risk skoru + seviye (low/moderate/high/severe) + faktör kırılımı.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.audit import AuditRecord, EngineResult

ENGINE_NAME = "engine.injury_risk"
ENGINE_VERSION = "1"

# Acute:Chronic Workload Ratio (ACWR) — Gabbett 2016 "sweet spot" 0.8-1.3
# >1.5 = yüksek risk ("danger zone")
ACWR_SAFE_LOW = 0.8
ACWR_SAFE_HIGH = 1.3
ACWR_DANGER = 1.5

# Yaş risk eşikleri
AGE_RISK_THRESHOLD = 30
AGE_HIGH_RISK = 33


@dataclass(frozen=True)
class InjuryRiskReport:
    player_external_id: int
    risk_score: float           # 0-100 kompozit
    risk_level: str             # "low" | "moderate" | "high" | "severe"
    acwr: float | None          # acute:chronic ratio (verilirse)
    acwr_flag: str              # "safe" | "undertrained" | "danger" | "unknown"
    load_factor: float          # 0-40 (yük katkısı)
    age_factor: float           # 0-30 (yaş katkısı)
    frequency_factor: float     # 0-30 (sıklık katkısı)
    recommendation: str


def _acwr_flag(acwr: float | None) -> str:
    if acwr is None:
        return "unknown"
    if acwr >= ACWR_DANGER:
        return "danger"
    if acwr < ACWR_SAFE_LOW:
        return "undertrained"
    return "safe"


def _level(score: float) -> str:
    if score >= 70:
        return "severe"
    if score >= 50:
        return "high"
    if score >= 30:
        return "moderate"
    return "low"


def compute_injury_risk(
    player_external_id: int,
    *,
    minutes_per_week: float,
    back_to_back_count: int,
    age: int | None = None,
    acute_minutes_7d: float | None = None,
    chronic_minutes_28d_avg: float | None = None,
) -> EngineResult[InjuryRiskReport]:
    """Sakatlık risk skoru.

    `acute_minutes_7d` + `chronic_minutes_28d_avg` verilirse ACWR hesaplanır
    (en güçlü sinyal). Yoksa load + age + frequency heuristic.
    """
    # 1. Yük faktörü (0-40): minutes_per_week 270+ riskli
    load_factor = min(40.0, max(0.0, (minutes_per_week - 180) / 180 * 40))

    # 2. Yaş faktörü (0-30)
    if age is None:
        age_factor = 10.0  # bilinmiyor → nötr-orta
    elif age >= AGE_HIGH_RISK:
        age_factor = 30.0
    elif age >= AGE_RISK_THRESHOLD:
        age_factor = 15.0 + (age - AGE_RISK_THRESHOLD) / (AGE_HIGH_RISK - AGE_RISK_THRESHOLD) * 15.0
    else:
        age_factor = max(0.0, (age - 18) / (AGE_RISK_THRESHOLD - 18) * 15.0)

    # 3. Sıklık faktörü (0-30): back_to_back
    frequency_factor = min(30.0, back_to_back_count / 4 * 30)

    # ACWR — varsa load_factor'u override edecek güçte
    acwr: float | None = None
    if (acute_minutes_7d is not None and chronic_minutes_28d_avg
            and chronic_minutes_28d_avg > 0):
        # acute haftalık, chronic 28-gün haftalık ortalama
        acwr = round(acute_minutes_7d / chronic_minutes_28d_avg, 3)
        if acwr >= ACWR_DANGER:
            load_factor = 40.0  # danger zone
        elif acwr >= ACWR_SAFE_HIGH:
            load_factor = max(load_factor, 28.0)

    raw_score = load_factor + age_factor + frequency_factor
    score = round(min(100.0, raw_score), 1)
    level = _level(score)
    flag = _acwr_flag(acwr)

    if level == "severe":
        rec = "Acil dinlendirme — antrenman yükü düşür, maç dışı düşün"
    elif level == "high":
        rec = "Yük yönetimi — rotasyon + ek toparlanma"
    elif level == "moderate":
        rec = "İzlemede tut — antrenman yoğunluğunu dengele"
    else:
        rec = "Risk düşük — normal program"

    report = InjuryRiskReport(
        player_external_id=player_external_id,
        risk_score=score,
        risk_level=level,
        acwr=acwr,
        acwr_flag=flag,
        load_factor=round(load_factor, 1),
        age_factor=round(age_factor, 1),
        frequency_factor=round(frequency_factor, 1),
        recommendation=rec,
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="player", subject_id=player_external_id,
        metric="injury_risk",
        value={
            "risk_score": score, "risk_level": level,
            "acwr": acwr, "acwr_flag": flag,
            "load_factor": report.load_factor,
            "age_factor": report.age_factor,
            "frequency_factor": report.frequency_factor,
        },
        inputs={
            "minutes_per_week": minutes_per_week,
            "back_to_back_count": back_to_back_count,
            "age": age,
            "acwr_safe_range": [ACWR_SAFE_LOW, ACWR_SAFE_HIGH],
            "acwr_danger": ACWR_DANGER,
        },
        formula=(
            "risk = load_factor(0-40) + age_factor(0-30) + frequency_factor(0-30); "
            "ACWR varsa Gabbett danger zone load'u 40'a çeker"
        ),
    )
    return EngineResult(value=report, audit=audit)
