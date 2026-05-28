"""Field tilt — hangi takım rakibin son üçte topu daha çok kontrol ediyor.

Tanım: rakibin defansif üçünde (x ≥ 66) tamamlanan paslar.
- team_a_passes_in_opp_final_third / total_final_third_passes = a'nın tilt'i

Field tilt > 0.5 = hücum egemenliği. Pep'in Manchester City'si ~0.65-0.75
sezonluk; sıradan takımlar 0.45-0.55.

Saf hesap. PassEvent listesinden iki sayı + oran.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.audit import AuditRecord, EngineResult
from app.domain import PassEvent

ENGINE_NAME = "engine.field_tilt"
ENGINE_VERSION = "1"

# Final third girişi: x ≥ 66 (saha 100×100 normalize'da %33'lük hücum bölgesi).
FINAL_THIRD_X_MIN = 66.0


@dataclass(frozen=True)
class FieldTiltReport:
    team_a_external_id: int
    team_b_external_id: int
    team_a_passes_in_a_final_third: int
    team_b_passes_in_b_final_third: int
    team_a_tilt: float  # 0..1
    team_b_tilt: float


def compute_field_tilt(
    team_a_external_id: int,
    team_b_external_id: int,
    passes: Iterable[PassEvent],
) -> EngineResult[FieldTiltReport]:
    """İki takım arasındaki field tilt.

    Tüm tamamlanmış pasları takım ve hücum üçtebir konumuna göre say,
    oranı çıkar.
    """
    a_passes = 0
    b_passes = 0
    for p in passes:
        if not p.completed:
            continue
        if p.end_x < FINAL_THIRD_X_MIN:
            continue
        # Pas oyuncunun kendi hücum yarısına gidişi sayar
        if p.team_external_id == team_a_external_id:
            a_passes += 1
        elif p.team_external_id == team_b_external_id:
            b_passes += 1
    total = a_passes + b_passes
    a_tilt = a_passes / total if total > 0 else 0.5
    b_tilt = 1.0 - a_tilt if total > 0 else 0.5
    report = FieldTiltReport(
        team_a_external_id=team_a_external_id,
        team_b_external_id=team_b_external_id,
        team_a_passes_in_a_final_third=a_passes,
        team_b_passes_in_b_final_third=b_passes,
        team_a_tilt=round(a_tilt, 4),
        team_b_tilt=round(b_tilt, 4),
    )
    audit = AuditRecord(
        engine=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        subject_type="match",
        subject_id=0,
        metric="field_tilt",
        value={
            "team_a": team_a_external_id, "team_b": team_b_external_id,
            "team_a_passes": a_passes, "team_b_passes": b_passes,
            "team_a_tilt": report.team_a_tilt,
            "team_b_tilt": report.team_b_tilt,
        },
        inputs={"final_third_x_min": FINAL_THIRD_X_MIN},
        formula=(
            f"completed passes ending at x ≥ {FINAL_THIRD_X_MIN}, "
            "team A passes / (A + B passes)"
        ),
    )
    return EngineResult(value=report, audit=audit)
