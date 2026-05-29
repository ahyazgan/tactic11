"""Set Piece Timing — standart/duran top zamanlaması (Faz 7 H: #7, #8).

İki sinyal (payload-reçete; canlı tracking gelince zon analizi otomatikleşir):
7. Köşe/faul fırsat sinyali: kazandığımız duran topta rakibin boş bıraktığı
   zona göre rutin öner.
8. Penaltı alıcısı durumu: belirlenen penaltı atıcısının o anki yorgunluk +
   isabet durumuna göre "uygun" / "alternatif düşün".

Pure: payload + skor-zaman bağlamı.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.audit import AuditRecord, EngineResult

ENGINE_NAME = "engine.set_piece_timing"
ENGINE_VERSION = "1"

# Penaltı atıcı uygunluk eşikleri
PEN_FATIGUE_MAX = 0.80   # üstü → yorgun
PEN_ACCURACY_MIN = 0.65  # altı → isabet düşük

# Bilinen zayıf zon → rutin eşlemesi
ZONE_ROUTINE = {
    "near_post": "near-post flick-on rutini",
    "far_post": "far-post overload — uzun direğe yüklen",
    "penalty_spot": "penaltı noktası blok + arkaya kesme",
    "second_ball": "kısa korner → ikinci top için kenara dağıl",
    "zone_14": "kısa serbest vuruş — zone-14'e indirip şut",
}


@dataclass(frozen=True)
class SetPieceOpportunity:
    set_piece_type: str          # "corner" | "free_kick"
    target_zone: str
    routine: str


@dataclass(frozen=True)
class PenaltyStatus:
    player_external_id: int
    fatigue: float
    recent_accuracy: float
    fit_to_take: bool
    verdict: str


@dataclass(frozen=True)
class SetPieceTimingReport:
    team_external_id: int
    current_minute: float
    opportunity: SetPieceOpportunity | None
    penalty_status: PenaltyStatus | None
    alerts: tuple[str, ...] = field(default_factory=tuple)


def compute_set_piece_timing(
    team_external_id: int,
    *,
    current_minute: float,
    set_piece_won: str | None = None,         # "corner" | "free_kick"
    opponent_weak_zones: list[str] | None = None,
    penalty_taker: dict[str, Any] | None = None,
) -> EngineResult[SetPieceTimingReport]:
    alerts: list[str] = []

    # #7 köşe/faul fırsat
    opportunity: SetPieceOpportunity | None = None
    if set_piece_won in ("corner", "free_kick"):
        zones = opponent_weak_zones or []
        target = zones[0] if zones else (
            "far_post" if set_piece_won == "corner" else "zone_14"
        )
        routine = ZONE_ROUTINE.get(target, f"{target} bölgesine yüklen")
        opportunity = SetPieceOpportunity(set_piece_won, target, routine)
        sp = "Korner" if set_piece_won == "corner" else "Serbest vuruş"
        alerts.append(f"FIRSAT: {sp} kazanıldı — rakip {target} boş, {routine}")

    # #8 penaltı atıcısı durumu
    penalty_status: PenaltyStatus | None = None
    if penalty_taker:
        pid = int(penalty_taker.get("player_id", 0))
        fatigue = float(penalty_taker.get("fatigue", 0.0))
        acc = float(penalty_taker.get("recent_accuracy", 1.0))
        fit = fatigue <= PEN_FATIGUE_MAX and acc >= PEN_ACCURACY_MIN
        if fit:
            verdict = "uygun — belirlenen atıcı kalsın"
        elif fatigue > PEN_FATIGUE_MAX and acc < PEN_ACCURACY_MIN:
            verdict = "yorgun + isabet düşük — alternatif atıcı düşün"
        elif fatigue > PEN_FATIGUE_MAX:
            verdict = "yorgun — alternatif atıcı hazırla"
        else:
            verdict = "isabet düşük — alternatif atıcı düşün"
        penalty_status = PenaltyStatus(pid, round(fatigue, 3), round(acc, 3),
                                       fit, verdict)
        if not fit:
            alerts.append(f"PENALTI: #{pid} {verdict}")

    report = SetPieceTimingReport(
        team_external_id=team_external_id,
        current_minute=current_minute,
        opportunity=opportunity,
        penalty_status=penalty_status,
        alerts=tuple(alerts),
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="match", subject_id=team_external_id,
        metric="set_piece_timing",
        value={
            "opportunity": opportunity.target_zone if opportunity else None,
            "penalty_fit": penalty_status.fit_to_take if penalty_status else None,
            "alerts": list(alerts),
        },
        inputs={
            "current_minute": current_minute, "set_piece_won": set_piece_won,
            "opponent_weak_zones": opponent_weak_zones,
        },
        formula="zayıf zon → rutin eşleme; penaltı fatigue/accuracy eşiği → atıcı uygunluğu",
    )
    return EngineResult(value=report, audit=audit)
