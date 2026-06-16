"""Team Form Health — kadronun toplu O+P aggregate.

Her oyuncunun maç-maç rating serisinden hem consistency hem trajectory
hesaplanır → takım seviyesinde özetlenir:
  - team_avg_rating, % improving, % declining, % stable
  - % high / medium / volatile consistency
  - top_performers (top 3 aggregate)
  - concern_list (declining + low reliability)
  - team_health_score 0..100 = mean(reliability) × (1 + slope_avg/0.30)
    aritmetik dengeli
  - 1-cümle özet (TR)

Pure compute, alt motor olarak engine.performance_consistency ve
engine.performance_trajectory'yi çağırır.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from app.audit import AuditRecord, EngineResult
from app.engine.performance_consistency import (
    PerformanceSample,
    compute_performance_consistency,
)
from app.engine.performance_trajectory import (
    TrajectoryPoint,
    compute_performance_trajectory,
)

ENGINE_NAME = "engine.team_form_health"
ENGINE_VERSION = "1"

CONCERN_RELIABILITY_THRESHOLD = 50.0


@dataclass(frozen=True)
class PlayerSeries:
    player_id: int
    name: str
    ratings: tuple[float, ...]      # kronolojik
    position_group: str = ""


@dataclass(frozen=True)
class PlayerSnapshot:
    player_id: int
    name: str
    mean_rating: float
    consistency_label: str
    direction: str
    reliability: float
    z_recent_5: float


@dataclass(frozen=True)
class TeamFormHealthReport:
    player_count: int
    team_avg_rating: float
    team_health_score: float                     # 0..100
    pct_improving: float
    pct_declining: float
    pct_stable: float
    pct_high_consistency: float
    pct_volatile: float
    snapshots: tuple[PlayerSnapshot, ...]
    top_performers: tuple[PlayerSnapshot, ...]   # top 3 reliability
    concerns: tuple[PlayerSnapshot, ...]         # declining + low reliability
    summary: str                                 # TR 1-cümle
    notes: tuple[str, ...] = field(default_factory=tuple)


def _pct(numerator: int, denominator: int) -> float:
    return round(100.0 * numerator / denominator, 1) if denominator else 0.0


def compute_team_form_health(
    players: Iterable[PlayerSeries],
) -> EngineResult[TeamFormHealthReport]:
    plist = list(players)
    notes: list[str] = []

    if not plist:
        return _empty(0, "Oyuncu yok")

    snapshots: list[PlayerSnapshot] = []
    direction_counts = {"improving": 0, "declining": 0, "stable": 0, "insufficient": 0}
    consistency_counts = {"high": 0, "medium": 0, "volatile": 0, "insufficient": 0}

    for p in plist:
        if not p.ratings:
            notes.append(f"{p.name}: rating serisi boş, atlanıyor")
            continue
        samples = [
            PerformanceSample(match_id=i + 1, value=v)
            for i, v in enumerate(p.ratings)
        ]
        points = [
            TrajectoryPoint(match_id=i + 1, value=v, game_index=i)
            for i, v in enumerate(p.ratings)
        ]
        c = compute_performance_consistency(samples).value
        t = compute_performance_trajectory(points).value
        snapshots.append(PlayerSnapshot(
            player_id=p.player_id,
            name=p.name,
            mean_rating=c.mean,
            consistency_label=c.consistency_label,
            direction=t.direction,
            reliability=c.reliability_score,
            z_recent_5=c.z_recent_5,
        ))
        direction_counts[t.direction] = direction_counts.get(t.direction, 0) + 1
        consistency_counts[c.consistency_label] = (
            consistency_counts.get(c.consistency_label, 0) + 1
        )

    if not snapshots:
        return _empty(len(plist), "Geçerli oyuncu serisi yok")

    n = len(snapshots)
    team_avg = sum(s.mean_rating for s in snapshots) / n

    avg_reliability = sum(s.reliability for s in snapshots) / n
    slope_indicator = (direction_counts["improving"] - direction_counts["declining"]) / n
    team_health = max(
        0.0,
        min(100.0, avg_reliability * (1.0 + 0.30 * slope_indicator)),
    )

    pct_improving = _pct(direction_counts["improving"], n)
    pct_declining = _pct(direction_counts["declining"], n)
    pct_stable = _pct(direction_counts["stable"], n)
    pct_high = _pct(consistency_counts["high"], n)
    pct_volatile = _pct(consistency_counts["volatile"], n)

    sorted_by_rel = sorted(snapshots, key=lambda s: -s.reliability)
    top_performers = tuple(sorted_by_rel[:3])
    concerns = tuple(
        s for s in snapshots
        if s.direction == "declining" and s.reliability < CONCERN_RELIABILITY_THRESHOLD
    )

    if team_health >= 70:
        verdict = "Kadronun formu sağlıklı"
    elif team_health >= 50:
        verdict = "Kadronun formu orta — kritik bir iki oyuncu izlenmeli"
    else:
        verdict = "Kadronun formu zayıf — derinlikte sorun var"
    summary = (
        f"{n} oyuncu, ortalama rating {team_avg:.2f}, health {team_health:.0f}/100 — "
        f"{verdict}; %{pct_improving:.0f} yükselişte / %{pct_declining:.0f} düşüşte"
    )

    report = TeamFormHealthReport(
        player_count=n,
        team_avg_rating=round(team_avg, 3),
        team_health_score=round(team_health, 1),
        pct_improving=pct_improving,
        pct_declining=pct_declining,
        pct_stable=pct_stable,
        pct_high_consistency=pct_high,
        pct_volatile=pct_volatile,
        snapshots=tuple(snapshots),
        top_performers=top_performers,
        concerns=concerns,
        summary=summary,
        notes=tuple(notes),
    )
    audit = AuditRecord(
        engine=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        subject_type="team",
        subject_id=0,
        metric="team_form_health",
        value={
            "player_count": n,
            "team_avg_rating": round(team_avg, 3),
            "team_health_score": round(team_health, 1),
            "directions": direction_counts,
            "consistencies": consistency_counts,
            "concern_count": len(concerns),
            "top_names": [s.name for s in top_performers],
        },
        inputs={"concern_reliability_threshold": CONCERN_RELIABILITY_THRESHOLD},
        formula=(
            "Per oyuncu → consistency + trajectory; "
            "team_health = avg_reliability × (1 + 0.30 × (improving-declining)/n); "
            "concerns = declining + reliability<50"
        ),
    )
    return EngineResult(value=report, audit=audit)


def _empty(n: int, msg: str) -> EngineResult[TeamFormHealthReport]:
    report = TeamFormHealthReport(
        player_count=n,
        team_avg_rating=0.0,
        team_health_score=0.0,
        pct_improving=0.0, pct_declining=0.0, pct_stable=0.0,
        pct_high_consistency=0.0, pct_volatile=0.0,
        snapshots=(), top_performers=(), concerns=(),
        summary=msg,
        notes=(msg,),
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="team", subject_id=0,
        metric="team_form_health",
        value={"player_count": n}, inputs={}, formula="insufficient",
    )
    return EngineResult(value=report, audit=audit)
