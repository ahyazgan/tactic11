"""Set-piece Opportunity — standart top fırsatı sinyali (H.1).

Son N dakikada kazanılan duran top sayısı (köşe + faul ofansif bölgede) +
şuta dönüşüm oranı. Yüksek frekans + düşük dönüşüm → "rutini değiştir,
ön basamak hazır olsun".

Pure compute. PassEvent (pass_type='corner'|'free_kick') + Shot
(pattern='corner_kick'|'free_kick') + FoulEvent (ofansif bölgede bizim
lehe) input. Eksik tip → 0 sayılır.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from app.audit import AuditRecord, EngineResult

ENGINE_NAME = "engine.set_piece_opportunity"
ENGINE_VERSION = "1"

DEFAULT_WINDOW_MIN = 20.0
# Ofansif üç eşiği (x ≥ 66 saha %66+)
ATTACKING_THIRD_X = 66.0
# Sıcak fırsat eşikleri
HIGH_FREQUENCY = 3       # window'da 3+ set-piece → "yüksek frekans"
LOW_CONVERSION = 0.15    # şuta dönüşüm < %15 → "rutin değiştir"


@dataclass(frozen=True)
class SetPieceOpportunityReport:
    team_external_id: int
    current_minute: float
    window_min: float
    # Kazanılan set-piece sayıları (window içi)
    corners_won: int
    free_kicks_won_offensive: int
    fouls_drawn_offensive: int       # ofansif bölgede çekilen faul
    total_set_pieces: int
    # Dönüşüm
    set_piece_shots: int             # set-piece sonucu açılan şutlar
    conversion_to_shot_pct: float    # set_piece_shots / total_set_pieces
    # Karar
    high_frequency: bool
    low_conversion: bool
    tactical_advice: str


def _is_offensive(x: float, team_view: bool = True) -> bool:
    """Ofansif üç kontrolü — x ≥ ATTACKING_THIRD_X (saha bizden bakış)."""
    return x >= ATTACKING_THIRD_X


def _build_advice(
    *, total: int, conversion: float, high_freq: bool, low_conv: bool,
) -> str:
    if total == 0:
        return "Set-piece yok — orta sahadan oyunu kur, faul kazandıracak hücum tara"
    parts: list[str] = []
    if high_freq:
        parts.append("Yüksek set-piece frekansı — duran top rutini sıcak tut")
    if low_conv:
        parts.append(
            f"Dönüşüm düşük ({conversion*100:.0f}%) — rutin değiştir "
            "(ön basamak çapraz, kısa-köşe alternatifi dene)"
        )
    if not parts:
        return f"Set-piece akışı normal ({total} fırsat, %{conversion*100:.0f} şut)"
    return " · ".join(parts)


def compute_set_piece_opportunity(
    team_external_id: int,
    *,
    current_minute: float,
    passes: Iterable[Any] = (),       # PassEvent (corner/free_kick)
    shots: Iterable[Any] = (),        # Shot (corner_kick/free_kick pattern)
    fouls: Iterable[Any] = (),        # FoulEvent (rakip yapan, ofansif bölgede)
    opponent_external_id: int | None = None,
    window_min: float = DEFAULT_WINDOW_MIN,
) -> EngineResult[SetPieceOpportunityReport]:
    """Set-piece fırsat sayısı + şuta dönüşüm.

    Köşe: PassEvent.pass_type == 'corner' ve team == bizim
    Ofansif serbest: PassEvent.pass_type == 'free_kick' ve start_x ≥ 66 ve team
    Faul çekme: FoulEvent.team == rakip ve x ≥ 66 (rakip ofansif bölgede faul yaptı = bize karşı faul → biz lehte)
    Set-piece şut: Shot.pattern in (corner_kick, free_kick) ve team == bizim
    """
    window_lo = current_minute - window_min

    corners = 0
    free_kicks_off = 0
    for p in passes:
        if getattr(p, "team_external_id", None) != team_external_id:
            continue
        m = float(getattr(p, "minute", 0.0))
        if not (window_lo <= m <= current_minute):
            continue
        ptype = getattr(p, "pass_type", None)
        if ptype == "corner":
            corners += 1
        elif ptype == "free_kick":
            sx = float(getattr(p, "start_x", 0.0))
            if _is_offensive(sx):
                free_kicks_off += 1

    fouls_drawn = 0
    for f in fouls:
        if opponent_external_id is None:
            # Sadece pozisyon — bizim takım dışında biri ofansif bölgemizde faul yaptı
            if getattr(f, "team_external_id", None) == team_external_id:
                continue
        elif getattr(f, "team_external_id", None) != opponent_external_id:
            continue
        m = float(getattr(f, "minute", 0.0))
        if not (window_lo <= m <= current_minute):
            continue
        if _is_offensive(float(getattr(f, "x", 0.0))):
            fouls_drawn += 1

    sp_shots = 0
    for s in shots:
        if getattr(s, "team_external_id", None) != team_external_id:
            continue
        m = float(getattr(s, "minute", 0.0))
        if not (window_lo <= m <= current_minute):
            continue
        pat = getattr(s, "pattern", None)
        if pat in ("corner_kick", "free_kick", "set_piece"):
            sp_shots += 1

    total = corners + free_kicks_off + fouls_drawn
    conversion = round(sp_shots / total, 3) if total > 0 else 0.0
    high_freq = total >= HIGH_FREQUENCY
    low_conv = high_freq and conversion < LOW_CONVERSION
    advice = _build_advice(
        total=total, conversion=conversion,
        high_freq=high_freq, low_conv=low_conv,
    )

    report = SetPieceOpportunityReport(
        team_external_id=team_external_id,
        current_minute=current_minute, window_min=window_min,
        corners_won=corners,
        free_kicks_won_offensive=free_kicks_off,
        fouls_drawn_offensive=fouls_drawn,
        total_set_pieces=total,
        set_piece_shots=sp_shots,
        conversion_to_shot_pct=conversion,
        high_frequency=high_freq,
        low_conversion=low_conv,
        tactical_advice=advice,
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="team", subject_id=team_external_id,
        metric="set_piece_opportunity",
        value={
            "total_set_pieces": total,
            "corners_won": corners,
            "free_kicks_won_offensive": free_kicks_off,
            "fouls_drawn_offensive": fouls_drawn,
            "set_piece_shots": sp_shots,
            "conversion_to_shot_pct": conversion,
            "high_frequency": high_freq,
            "low_conversion": low_conv,
            "tactical_advice": advice,
        },
        inputs={
            "current_minute": current_minute, "window_min": window_min,
            "thresholds": {
                "attacking_third_x": ATTACKING_THIRD_X,
                "high_frequency": HIGH_FREQUENCY,
                "low_conversion": LOW_CONVERSION,
            },
        },
        formula=(
            "corners + offensive_free_kicks + fouls_drawn = total; "
            "conversion = sp_shots/total; "
            "high_freq AND conversion<15% → 'rutin değiştir'"
        ),
    )
    return EngineResult(value=report, audit=audit)
