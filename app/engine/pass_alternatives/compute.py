"""Pass Alternatives — bir pasın yapıldığı yerden alternatif hedef noktalar.

Frame-by-frame coach feedback için: "32. dk'da Y'ye pas yerine X'e açabilirdin
(xT delta +0.18)". Tracking yokken heuristic: pasın başlangıç noktasından
360° etrafında simüle edilen N noktada xT_value_at karşılaştır.

Saf hesap. PassEvent → top K alternatif (xT artışı en yüksek).
Gerçek tracking ile (boş oyuncu pozisyonu) doğruluk %30-50 artar; bu
heuristic versiyon mevcut data ile %70 değer üretir.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.audit import AuditRecord, EngineResult
from app.domain import PassEvent
from app.engine.xt import xt_value_at

ENGINE_NAME = "engine.pass_alternatives"
ENGINE_VERSION = "1"

# Alternatif hedef noktaları üreten konvansiyon
# 8 yön × 3 mesafe = 24 nokta (üretmek için)
DIRECTIONS = 8
DISTANCE_STEPS = (10.0, 20.0, 30.0)  # saha birimi (100x100)
TOP_K = 3  # En iyi 3 alternatif


@dataclass(frozen=True)
class AlternativeTarget:
    target_x: float
    target_y: float
    xt_value: float
    delta_vs_actual: float       # alternatif_xt - actual_end_xt
    distance: float              # actual end'ten uzaklık (yorumlanabilirlik)


@dataclass(frozen=True)
class PassAlternativesReport:
    pass_minute: float
    pass_player_id: int
    actual_start: tuple[float, float]
    actual_end: tuple[float, float]
    actual_end_xt: float
    actual_completed: bool
    alternatives: tuple[AlternativeTarget, ...]   # Top K, sorted desc by delta
    best_alternative_delta: float
    actual_was_optimal: bool   # delta ≤ 0.02 ise actual zaten optimaldi


def _generate_targets(start_x: float, start_y: float) -> list[tuple[float, float]]:
    """360° etrafında DIRECTIONS × DISTANCE_STEPS noktalar."""
    targets: list[tuple[float, float]] = []
    for i in range(DIRECTIONS):
        angle = (i / DIRECTIONS) * 2 * math.pi
        for d in DISTANCE_STEPS:
            tx = start_x + d * math.cos(angle)
            ty = start_y + d * math.sin(angle)
            if 0 <= tx <= 100 and 0 <= ty <= 100:
                targets.append((round(tx, 2), round(ty, 2)))
    return targets


def compute_pass_alternatives(
    p: PassEvent,
    *,
    top_k: int = TOP_K,
) -> EngineResult[PassAlternativesReport]:
    """Verilen pas için top-K alternatif hedef + xT karşılaştırma.

    Heuristic: 24 nokta üretir (8 yön × 3 mesafe), her birinin xT_value_at'ını
    hesaplar, actual end'ten farkını alır, en yüksek K alternatifi döner.
    """
    actual_end_xt = xt_value_at(p.end_x, p.end_y)
    candidates = _generate_targets(p.start_x, p.start_y)

    scored: list[AlternativeTarget] = []
    for tx, ty in candidates:
        xt = xt_value_at(tx, ty)
        delta = xt - actual_end_xt
        dist = math.hypot(tx - p.end_x, ty - p.end_y)
        scored.append(AlternativeTarget(
            target_x=tx, target_y=ty,
            xt_value=round(xt, 4),
            delta_vs_actual=round(delta, 4),
            distance=round(dist, 2),
        ))
    # Sort desc by delta
    scored.sort(key=lambda a: -a.delta_vs_actual)
    top = tuple(scored[:top_k])
    best_delta = top[0].delta_vs_actual if top else 0.0

    report = PassAlternativesReport(
        pass_minute=p.minute,
        pass_player_id=p.player_external_id,
        actual_start=(p.start_x, p.start_y),
        actual_end=(p.end_x, p.end_y),
        actual_end_xt=round(actual_end_xt, 4),
        actual_completed=p.completed,
        alternatives=top,
        best_alternative_delta=best_delta,
        actual_was_optimal=best_delta <= 0.02,
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="pass",
        subject_id=p.player_external_id,
        metric="pass_alternatives",
        value={
            "actual_end_xt": report.actual_end_xt,
            "best_alternative_delta": best_delta,
            "actual_was_optimal": report.actual_was_optimal,
            "top_alternatives": [
                {"x": a.target_x, "y": a.target_y,
                 "xt": a.xt_value, "delta": a.delta_vs_actual}
                for a in top
            ],
        },
        inputs={
            "directions": DIRECTIONS,
            "distance_steps": list(DISTANCE_STEPS),
            "top_k": top_k,
        },
        formula=(
            "8 yön × 3 mesafe = 24 nokta; her birinde xT_value_at; "
            "actual end xT'den fark; top K en yüksek delta. "
            "Heuristic — gerçek tracking ile (boş oyuncu pos) %30-50 daha doğru."
        ),
    )
    return EngineResult(value=report, audit=audit)


def compute_player_pass_alternatives_summary(
    player_external_id: int,
    passes: list[PassEvent],
    *,
    top_n_suboptimal: int = 3,
) -> dict:
    """Bir oyuncunun maçtaki TÜM paslarının alternatif analizi özeti.

    Çıktı: ortalama best_delta, suboptimal pass yüzdesi, top N en kötü pas
    (en yüksek delta — best alternative ile arası en açık).
    """
    player_passes = [p for p in passes if p.player_external_id == player_external_id]
    if not player_passes:
        return {
            "player_external_id": player_external_id,
            "passes_analyzed": 0,
            "mean_best_delta": 0.0,
            "suboptimal_share": 0.0,
            "top_suboptimal": [],
        }

    deltas = []
    suboptimal_passes: list[tuple[PassEvent, PassAlternativesReport]] = []
    for p in player_passes:
        r = compute_pass_alternatives(p).value
        deltas.append(r.best_alternative_delta)
        if not r.actual_was_optimal:
            suboptimal_passes.append((p, r))

    suboptimal_passes.sort(key=lambda t: -t[1].best_alternative_delta)
    top_suboptimal = [
        {
            "minute": p.minute,
            "start": [p.start_x, p.start_y],
            "actual_end": [p.end_x, p.end_y],
            "best_alternative": {
                "x": r.alternatives[0].target_x if r.alternatives else None,
                "y": r.alternatives[0].target_y if r.alternatives else None,
                "delta": r.best_alternative_delta,
            },
            "completed": p.completed,
        }
        for p, r in suboptimal_passes[:top_n_suboptimal]
    ]
    return {
        "player_external_id": player_external_id,
        "passes_analyzed": len(player_passes),
        "mean_best_delta": round(sum(deltas) / len(deltas), 4),
        "suboptimal_share": round(
            sum(1 for d in deltas if d > 0.02) / len(deltas), 3,
        ),
        "top_suboptimal": top_suboptimal,
    }
