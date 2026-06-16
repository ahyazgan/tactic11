"""Player Comparison — 2-6 oyuncuyu KPI radar ile karşılaştırır.

Her oyuncu için ortak KPI sözlüğü (örn. rating, xt_per_90, xa_per_90,
goals_per_90, defensive_actions_per_90, pass_completion). Çıktı:
  - Per KPI: oyuncular arası sıralama (1 = best) + normalize 0..1
  - Per oyuncu: aggregate_score (KPI ortalaması), strongest_kpi, weakest_kpi
  - Ranked winner + reasoning
  - Composite KPI weight desteği (default = 1)

Pure compute. Tek input dict listesi (PlayerProfile).
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from app.audit import AuditRecord, EngineResult

ENGINE_NAME = "engine.player_comparison"
ENGINE_VERSION = "1"

# Daha yüksek = daha iyi (defaults). Düşük = daha iyi olan KPI'lar buraya.
LOWER_IS_BETTER = frozenset({"ppda", "errors_per_90", "fouls_per_90"})


@dataclass(frozen=True)
class PlayerProfile:
    player_id: int
    name: str
    kpis: dict[str, float] = field(default_factory=dict)
    position_group: str = ""


@dataclass(frozen=True)
class KpiBreakdown:
    kpi: str
    values: dict[int, float]                     # player_id → value
    normalized: dict[int, float]                 # 0..1 (higher=better)
    rank: dict[int, int]                         # player_id → rank (1=best)
    best_player_id: int
    worst_player_id: int


@dataclass(frozen=True)
class PlayerSummary:
    player_id: int
    name: str
    aggregate_score: float                       # 0..1 weighted avg of normalized KPIs
    strongest_kpi: str | None
    weakest_kpi: str | None
    overall_rank: int                            # 1 = best


@dataclass(frozen=True)
class ComparisonReport:
    player_count: int
    kpis_compared: tuple[str, ...]
    per_kpi: tuple[KpiBreakdown, ...]
    per_player: tuple[PlayerSummary, ...]
    winner_id: int | None
    winner_name: str | None
    reasoning: str                                # TR — neden kazandı
    summary: str
    notes: tuple[str, ...] = field(default_factory=tuple)


def _normalize(values: dict[int, float], lower_better: bool) -> dict[int, float]:
    """min-max normalize → 0..1, higher=better unless lower_better."""
    vs = list(values.values())
    if not vs:
        return {}
    lo, hi = min(vs), max(vs)
    if hi == lo:
        return {pid: 0.5 for pid in values}
    out: dict[int, float] = {}
    for pid, v in values.items():
        normalized = (v - lo) / (hi - lo)
        out[pid] = round(1.0 - normalized if lower_better else normalized, 3)
    return out


def _rank(values: dict[int, float], lower_better: bool) -> dict[int, int]:
    """1 = best (lowest if lower_better else highest)."""
    sorted_pids = sorted(
        values.keys(),
        key=lambda pid: (values[pid] if lower_better else -values[pid]),
    )
    return {pid: i + 1 for i, pid in enumerate(sorted_pids)}


def compute_player_comparison(
    players: Iterable[PlayerProfile],
    *,
    kpis: list[str] | None = None,
    weights: dict[str, float] | None = None,
) -> EngineResult[ComparisonReport]:
    plist = list(players)
    notes: list[str] = []

    if len(plist) < 2:
        return _empty(len(plist), "En az 2 oyuncu gerek")

    # KPI listesi: explicit verilmediyse → tüm oyuncuların ortak KPI'ları
    if kpis is None:
        common_kpis: set[str] | None = None
        for p in plist:
            keys = set(p.kpis.keys())
            common_kpis = keys if common_kpis is None else common_kpis & keys
        kpis = sorted(common_kpis or set())
    if not kpis:
        notes.append("Ortak KPI yok — karşılaştırma yapılamadı")
        return _empty(len(plist), "Ortak KPI yok")

    weights = weights or {}

    per_kpi: list[KpiBreakdown] = []
    normalized_by_player: dict[int, dict[str, float]] = {p.player_id: {} for p in plist}

    for kpi in kpis:
        values = {p.player_id: float(p.kpis.get(kpi, 0.0)) for p in plist}
        lower_better = kpi in LOWER_IS_BETTER
        norm = _normalize(values, lower_better)
        rank = _rank(values, lower_better)
        best_pid = min(rank, key=lambda pid: rank[pid])
        worst_pid = max(rank, key=lambda pid: rank[pid])
        per_kpi.append(KpiBreakdown(
            kpi=kpi,
            values={pid: round(v, 3) for pid, v in values.items()},
            normalized=norm,
            rank=rank,
            best_player_id=best_pid,
            worst_player_id=worst_pid,
        ))
        for pid, nv in norm.items():
            normalized_by_player[pid][kpi] = nv

    # Per-player aggregate
    per_player: list[PlayerSummary] = []
    for p in plist:
        nks = normalized_by_player[p.player_id]
        if not nks:
            agg = 0.0
            strongest = weakest = None
        else:
            num = 0.0
            den = 0.0
            for kpi, nv in nks.items():
                w = float(weights.get(kpi, 1.0))
                num += nv * w
                den += w
            agg = round(num / den if den > 0 else 0.0, 3)
            strongest = max(nks, key=lambda k: nks[k])
            weakest = min(nks, key=lambda k: nks[k])
        per_player.append(PlayerSummary(
            player_id=p.player_id,
            name=p.name,
            aggregate_score=agg,
            strongest_kpi=strongest,
            weakest_kpi=weakest,
            overall_rank=0,        # doldurulacak
        ))

    # Overall ranks
    sorted_summaries = sorted(per_player, key=lambda s: -s.aggregate_score)
    rank_map = {s.player_id: i + 1 for i, s in enumerate(sorted_summaries)}
    per_player = [
        PlayerSummary(
            player_id=s.player_id, name=s.name,
            aggregate_score=s.aggregate_score,
            strongest_kpi=s.strongest_kpi,
            weakest_kpi=s.weakest_kpi,
            overall_rank=rank_map[s.player_id],
        )
        for s in per_player
    ]
    per_player.sort(key=lambda s: s.overall_rank)

    winner = per_player[0] if per_player else None
    if winner and len(per_player) >= 2 and winner.aggregate_score == per_player[1].aggregate_score:
        # tie — winner None
        winner_id: int | None = None
        winner_name: str | None = None
        reasoning = "Berabere — aggregate score eşit, KPI bazlı tercih yap"
    elif winner:
        winner_id = winner.player_id
        winner_name = winner.name
        margin = (
            winner.aggregate_score
            - (per_player[1].aggregate_score if len(per_player) > 1 else 0.0)
        )
        reasoning = (
            f"{winner.name} aggregate {winner.aggregate_score:.2f} "
            f"(2.'den +{margin:.2f}); en güçlü {winner.strongest_kpi}"
        )
    else:
        winner_id = None
        winner_name = None
        reasoning = "Karşılaştırma yetersiz"

    summary = (
        f"{len(plist)} oyuncu × {len(kpis)} KPI karşılaştırıldı; "
        f"kazanan: {winner_name or '—'}"
    )

    report = ComparisonReport(
        player_count=len(plist),
        kpis_compared=tuple(kpis),
        per_kpi=tuple(per_kpi),
        per_player=tuple(per_player),
        winner_id=winner_id,
        winner_name=winner_name,
        reasoning=reasoning,
        summary=summary,
        notes=tuple(notes),
    )
    audit = AuditRecord(
        engine=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        subject_type="players",
        subject_id=0,
        metric="player_comparison",
        value={
            "player_count": len(plist),
            "kpis": list(kpis),
            "winner_id": winner_id,
            "rankings": {s.player_id: s.overall_rank for s in per_player},
        },
        inputs={"weights": weights, "lower_is_better": list(LOWER_IS_BETTER & set(kpis))},
        formula=(
            "Per KPI: min-max normalize (1.0 - x if lower_better else x); "
            "rank = sorted by raw value; "
            "aggregate = Σ(weight × normalized) / Σweight"
        ),
    )
    return EngineResult(value=report, audit=audit)


def _empty(n: int, msg: str) -> EngineResult[ComparisonReport]:
    report = ComparisonReport(
        player_count=n,
        kpis_compared=(), per_kpi=(), per_player=(),
        winner_id=None, winner_name=None,
        reasoning=msg, summary=msg,
        notes=(msg,),
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="players", subject_id=0,
        metric="player_comparison",
        value={"player_count": n}, inputs={}, formula="insufficient",
    )
    return EngineResult(value=report, audit=audit)
