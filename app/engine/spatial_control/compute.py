"""Spatial Control — mekânsal/alan kontrolü (Faz 7 F: #1, #2, #3).

Üç canlı sinyal (event-window proxy):
1. Boşluk haritası: rakip iki hat arasını açtı mı — zone-14/half-space'te
   bizim tamamlanan paslarımız çok, rakibin defansif aksiyonu az →
   "10 numaranın arkası boş".
2. Sayısal üstünlük: bir kanatta bizim katılım vs rakip def aksiyon farkı
   → "sol kanatta 3'e 2 üstünlük, oraya çevir".
3. Genişlik/darlık: bizim pas konumlarının y-dağılımı çok dar/geniş mi →
   kompaktlık bozuldu uyarısı.

Saf hesap. Pas + def listesi + current_minute + window → mekânsal rapor.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from app.audit import AuditRecord, EngineResult
from app.domain import DefensiveAction, PassEvent

ENGINE_NAME = "engine.spatial_control"
ENGINE_VERSION = "1"

WINDOW_MIN = 10.0
# Zone-14 / half-space kutusu (x ileri üçte bir, y merkez bandı)
Z14_X_LO, Z14_X_HI = 66.0, 83.0
Z14_Y_LO, Z14_Y_HI = 25.0, 75.0
# Boşluk: bizim z14 tamamlanan pas >= bu + rakip def <= bu
GAP_OUR_MIN = 3
GAP_OPP_MAX = 1
# Sayısal üstünlük: kanatta fark >= bu
SUPERIORITY_DIFF = 2
# Genişlik: y std bandı
NARROW_STD = 12.0
WIDE_STD = 28.0


@dataclass(frozen=True)
class FlankBalance:
    flank: str          # "left" | "center" | "right"
    our_count: int
    opp_count: int
    diff: int


@dataclass(frozen=True)
class SpatialControlReport:
    team_external_id: int
    opponent_external_id: int
    current_minute: float
    window_min: float
    # #1 boşluk
    gap_between_lines: bool
    our_zone14_passes: int
    opp_zone14_defs: int
    # #2 sayısal üstünlük
    superiority_flank: str | None
    flank_balance: tuple[FlankBalance, ...] = field(default_factory=tuple)
    # #3 genişlik/darlık
    shape_state: str = "balanced"   # "narrow" | "wide" | "balanced"
    width_y_std: float = 0.0
    alerts: tuple[str, ...] = field(default_factory=tuple)


def _flank(y: float) -> str:
    if y < 33.0:
        return "left"
    if y > 66.0:
        return "right"
    return "center"


def compute_spatial_control(
    team_external_id: int,
    opponent_external_id: int,
    passes: list[PassEvent],
    defs: list[DefensiveAction],
    *,
    current_minute: float,
    window_min: float = WINDOW_MIN,
) -> EngineResult[SpatialControlReport]:
    win_start = current_minute - window_min
    in_win = lambda m: win_start <= m <= current_minute  # noqa: E731

    our_p = [p for p in passes if p.team_external_id == team_external_id
             and in_win(p.minute)]
    opp_d = [d for d in defs if d.team_external_id == opponent_external_id
             and in_win(d.minute)]

    # #1 boşluk haritası — zone-14
    our_z14 = sum(
        1 for p in our_p if p.completed
        and Z14_X_LO <= p.end_x <= Z14_X_HI
        and Z14_Y_LO <= p.end_y <= Z14_Y_HI
    )
    opp_z14_def = sum(
        1 for d in opp_d
        if Z14_X_LO <= (100.0 - d.x) <= Z14_X_HI
        and Z14_Y_LO <= d.y <= Z14_Y_HI
    )
    gap = our_z14 >= GAP_OUR_MIN and opp_z14_def <= GAP_OPP_MAX

    # #2 sayısal üstünlük — kanat bazlı katılım
    balances: list[FlankBalance] = []
    for fl in ("left", "center", "right"):
        our_c = sum(1 for p in our_p if _flank(p.end_y) == fl)
        # rakip def aksiyonu: y aynı, x ayna (100 - x bizim hücum yönümüz)
        opp_c = sum(1 for d in opp_d if _flank(d.y) == fl)
        balances.append(FlankBalance(fl, our_c, opp_c, our_c - opp_c))
    sup = max(balances, key=lambda b: b.diff)
    sup_flank = sup.flank if sup.diff >= SUPERIORITY_DIFF and sup.our_count > 0 else None

    # #3 genişlik/darlık — pas konum y dağılımı
    ys = [p.end_y for p in our_p]
    y_std = statistics.pstdev(ys) if len(ys) >= 2 else 0.0
    if len(ys) < 3:
        shape = "balanced"
    elif y_std < NARROW_STD:
        shape = "narrow"
    elif y_std > WIDE_STD:
        shape = "wide"
    else:
        shape = "balanced"

    # Alert metinleri
    alerts: list[str] = []
    if gap:
        alerts.append(
            f"BOŞLUK: hatlar arası açık ({our_z14} pas, rakip {opp_z14_def} def) "
            "— 10 numaranın arkasını kullan"
        )
    if sup_flank:
        side = {"left": "sol", "center": "merkez", "right": "sağ"}[sup_flank]
        alerts.append(
            f"SAYISAL ÜSTÜNLÜK: {side} kanatta {sup.our_count}'e {sup.opp_count} "
            "— oyunu oraya çevir"
        )
    if shape == "narrow":
        alerts.append(f"DARLIK: takım daraldı (y std {y_std:.0f}) — kanatları kullan")
    elif shape == "wide":
        alerts.append(f"GENİŞLİK: takım fazla yayıldı (y std {y_std:.0f}) — kompakt ol")

    report = SpatialControlReport(
        team_external_id=team_external_id,
        opponent_external_id=opponent_external_id,
        current_minute=current_minute,
        window_min=window_min,
        gap_between_lines=gap,
        our_zone14_passes=our_z14,
        opp_zone14_defs=opp_z14_def,
        superiority_flank=sup_flank,
        flank_balance=tuple(balances),
        shape_state=shape,
        width_y_std=round(y_std, 2),
        alerts=tuple(alerts),
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="match", subject_id=team_external_id,
        metric="spatial_control",
        value={
            "gap_between_lines": gap, "superiority_flank": sup_flank,
            "shape_state": shape, "alerts": list(alerts),
        },
        inputs={
            "current_minute": current_minute, "window_min": window_min,
            "opponent_external_id": opponent_external_id,
        },
        formula="zone14 pas/def → boşluk; kanat katılım farkı → üstünlük; y-std → genişlik",
    )
    return EngineResult(value=report, audit=audit)
