"""Threat Pathway — pas/dribbling akışından hangi koridor en tehlikeli.

Saha 5 dikey lane'e bölünür:
  - left_wing (y < 22)
  - left_half_space (22 ≤ y < 36)
  - central (36 ≤ y < 44)
  - right_half_space (44 ≤ y < 58)
  - right_wing (y ≥ 58)

Her event (start_y, end_y) → en çok hangi lane'e değdiğine göre sayım;
threat_weight (xT-benzeri, varsa) ile ağırlıklandırılır. Çıktı:
  - Top lane (en tehlikeli koridor)
  - Lane başına volume, threat_total, threat_per_event
  - Bizim takım için: hangi lane'i tercih etmeli
  - Rakibe karşı: hangi lane'inden tehdit geliyor → counter advice

Pure compute. Tracking yok; event start/end koordinatları input.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from app.audit import AuditRecord, EngineResult

ENGINE_NAME = "engine.threat_pathway"
ENGINE_VERSION = "1"

# StatsBomb-style 80-y axis (0 = sol kenar, 80 = sağ kenar)
LANE_BOUNDS = (
    ("left_wing", 0.0, 22.0),
    ("left_half_space", 22.0, 36.0),
    ("central", 36.0, 44.0),
    ("right_half_space", 44.0, 58.0),
    ("right_wing", 58.0, 80.01),
)

LANE_LABELS = {
    "left_wing": "Sol kanat",
    "left_half_space": "Sol half-space",
    "central": "Merkez (10 koridoru)",
    "right_half_space": "Sağ half-space",
    "right_wing": "Sağ kanat",
}

LANE_COUNTER_ADVICE = {
    "left_wing": "Sağ FB + sağ winger içe geçsin; double-team + sürekli ikinci adam",
    "left_half_space": "Sağ 8 numara yarı sahayı kapatsın; 6 numara screen",
    "central": "Çift 6 numara + LB/RB içeri sıkışsın; orta koridorda kalabalık",
    "right_half_space": "Sol 8 numara yarı sahayı kapatsın; 6 numara screen",
    "right_wing": "Sol FB + sol winger içe geçsin; double-team + sürekli ikinci adam",
}

LANE_OUR_EXPLOIT = {
    "left_wing": "Sol kanat overload; LB underlap + LW içe kesip cut-back",
    "left_half_space": "Sol half-space'te 10 numarayı serbest bırak; inverted LB",
    "central": "Üçüncü adam kombinasyonu; bekir/lacher karşılaşması yarat",
    "right_half_space": "Sağ half-space'te 10 numarayı serbest bırak; inverted RB",
    "right_wing": "Sağ kanat overload; RB underlap + RW içe kesip cut-back",
}


@dataclass(frozen=True)
class PathwayEvent:
    """Bir taktik aksiyon: top hangi noktadan hangi noktaya gitti.

    threat_weight: xT-benzeri delta; yoksa shot=0.3, key_pass=0.2, normal=0.05
    önerisi. Pure consumer; nasıl hesaplandığını umursamaz.
    """
    start_y: float            # 0..80
    end_y: float              # 0..80
    threat_weight: float = 0.05
    is_shot: bool = False
    is_assist: bool = False


@dataclass(frozen=True)
class LaneStats:
    lane: str
    label: str
    event_count: int
    threat_total: float
    threat_per_event: float
    shots_in_lane: int
    assists_in_lane: int


@dataclass(frozen=True)
class ThreatPathwayReport:
    total_events: int
    lanes: tuple[LaneStats, ...]               # threat_total desc
    top_lane: str | None
    top_lane_share: float                      # 0..1
    our_exploit_advice: str
    counter_advice: str
    summary: str
    notes: tuple[str, ...] = field(default_factory=tuple)


def _classify_lane(y: float) -> str:
    y = max(0.0, min(80.0, y))
    for name, lo, hi in LANE_BOUNDS:
        if lo <= y < hi:
            return name
    return "central"


def _event_lane(ev: PathwayEvent) -> str:
    """End konumu öncelikli — paslar/dribbing'in bitiş noktası tehdit yaratır."""
    return _classify_lane(ev.end_y)


def compute_threat_pathway(
    events: Iterable[PathwayEvent],
    *,
    perspective: str = "ours",   # "ours" → exploit advice, "opponent" → counter advice
) -> EngineResult[ThreatPathwayReport]:
    """Event listesinden lane bazlı threat dağılımı."""
    evlist = list(events)
    counts: dict[str, int] = {n: 0 for n, _, _ in LANE_BOUNDS}
    threats: dict[str, float] = {n: 0.0 for n, _, _ in LANE_BOUNDS}
    shots: dict[str, int] = {n: 0 for n, _, _ in LANE_BOUNDS}
    assists: dict[str, int] = {n: 0 for n, _, _ in LANE_BOUNDS}

    for ev in evlist:
        lane = _event_lane(ev)
        counts[lane] += 1
        threats[lane] += max(0.0, float(ev.threat_weight))
        if ev.is_shot:
            shots[lane] += 1
        if ev.is_assist:
            assists[lane] += 1

    total_threat = sum(threats.values())
    lane_stats = [
        LaneStats(
            lane=name,
            label=LANE_LABELS[name],
            event_count=counts[name],
            threat_total=round(threats[name], 3),
            threat_per_event=(
                round(threats[name] / counts[name], 4) if counts[name] else 0.0
            ),
            shots_in_lane=shots[name],
            assists_in_lane=assists[name],
        )
        for name, _, _ in LANE_BOUNDS
    ]
    lane_stats.sort(key=lambda s: s.threat_total, reverse=True)

    top_lane: str | None = None
    top_share = 0.0
    if lane_stats and lane_stats[0].threat_total > 0:
        top_lane = lane_stats[0].lane
        top_share = lane_stats[0].threat_total / total_threat if total_threat > 0 else 0.0

    notes: list[str] = []
    if not evlist:
        notes.append("Event yok — threat pathway hesaplanamadı")
    elif total_threat <= 0:
        notes.append("Threat ağırlığı sıfır — sadece volume bazlı ranking")

    if top_lane:
        our_advice = LANE_OUR_EXPLOIT[top_lane]
        opp_advice = LANE_COUNTER_ADVICE[top_lane]
    else:
        our_advice = "Tüm koridorları dengeli kullan"
        opp_advice = "Dengeli baskı kur"

    if top_lane:
        summary = (
            f"{LANE_LABELS[top_lane]} en tehlikeli koridor "
            f"(toplam threat {threats[top_lane]:.2f}, pay %{top_share*100:.0f})"
        )
    else:
        summary = f"{len(evlist)} event analiz edildi — belirgin lane tercihi yok"

    report = ThreatPathwayReport(
        total_events=len(evlist),
        lanes=tuple(lane_stats),
        top_lane=top_lane,
        top_lane_share=round(top_share, 3),
        our_exploit_advice=our_advice,
        counter_advice=opp_advice,
        summary=summary,
        notes=tuple(notes),
    )
    audit = AuditRecord(
        engine=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        subject_type="team",
        subject_id=0,
        metric="threat_pathway",
        value={
            "total_events": len(evlist),
            "top_lane": top_lane,
            "top_lane_share": round(top_share, 3),
            "lane_threats": {s.lane: s.threat_total for s in lane_stats},
            "perspective": perspective,
        },
        inputs={
            "lane_bounds": {n: [lo, hi] for n, lo, hi in LANE_BOUNDS},
            "perspective": perspective,
        },
        formula=(
            "Her event end_y → lane sınıflama; lane.threat = Σ threat_weight; "
            "top_lane = max(threat); share = top/total"
        ),
    )
    return EngineResult(value=report, audit=audit)
