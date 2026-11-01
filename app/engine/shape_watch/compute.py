"""Savunma şekli bekçisi — "takım kendi normalinden saptı mı?" (pozisyon karelerinden).

`engine.tracking_signals` ardışık iki 1 dakikalık pencereyi karşılaştırır: hızlı ama
titrek, ve topa sahip olunan anla savunulan anı karıştırır. Bu motor koçun maç
sırasında sorduğu soruyu sorar: **savunurken** bloğumuz, genişliğimiz ve hat
aralığımız son birkaç dakikada bu maçtaki normalimizden kalıcı olarak saptı mı?

Ölçümler (yalnız SAVUNAN takımın kareleri; sahiplik karenin
`possession_team_external_id` alanından, yoksa kare sayılmaz):

- **Blok derinliği** — en geri hattın kendi kalesine uzaklığı (m)
- **Genişlik** — kaleci düşülmüş oyuncuların enine yayılımı (m)
- **Hat aralığı** — en geri iki hat arasındaki mesafe (m)
- **Takım boyu** — en geri hattan en ileri hatta (m)

Normal = son `RECENT_MIN` dakikadan ÖNCEKİ `BASELINE_MIN` dakikanın medyanı;
şimdi = son `RECENT_MIN` dakikanın medyanı. Fark eşiği aşar ve iki pencerede de
yeterli kare varsa bulgu üretilir. Medyan, tek tük hayalet tespitine dayanıklıdır.

Hücum yönü devre başına kaleci/en derin oyuncudan çıkarılır (space_map kuralı);
belirsizse o devrenin kareleri sayılmaz. Eşikler (blok 6 m, genişlik 6 m, hat
aralığı 4 m, boy 6 m) antrenörlük sezgisinden alınmıştır, etiketli maçla
ayarlanmadı; ölçümü ve kalibrasyonu doğruluk karnesinin işidir.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from statistics import median
from typing import Any

from app.audit import AuditRecord, EngineResult
from app.domain import TrackingFrame
from app.engine.space_map.compute import (
    LINE_CLUSTER_GAP_M,
    MIN_LINE_PLAYERS,
    infer_attack_direction,
)
from app.engine.tracking.coverage import coverage_quality

ENGINE_NAME = "engine.shape_watch"
ENGINE_VERSION = "1"

PITCH_LENGTH_M = 105.0
PITCH_WIDTH_M = 68.0
RECENT_MIN = 5.0
BASELINE_MIN = 25.0
MIN_TEAM_PLAYERS = 6          # savunan takımdan görünür oyuncu (kaleci hariç)
MIN_SAMPLES = 20              # pencere başına savunma karesi
THRESHOLDS_M = {"block_depth": 6.0, "width": 6.0, "line_gap": 4.0, "length": 6.0}
METRICS = ("block_depth", "width", "line_gap", "length")


@dataclass(frozen=True)
class ShapeSample:
    """Bir karede savunan takımın şekli (m). `line_gap` tek hat görünüyorsa None."""

    minute: float
    team: int
    block_depth: float
    width: float
    line_gap: float | None
    length: float
    players: int


@dataclass(frozen=True)
class MetricState:
    baseline: float | None
    recent: float | None
    delta: float | None


@dataclass(frozen=True)
class TeamShapeWatch:
    team_external_id: int
    baseline_samples: int
    recent_samples: int
    metrics: dict[str, MetricState]


@dataclass(frozen=True)
class ShapeFinding:
    team_external_id: int
    ours: bool
    metric: str
    baseline_m: float
    recent_m: float
    delta_m: float
    severity: str                # warning | info
    message: str


@dataclass(frozen=True)
class ShapeWatchReport:
    minute: float
    recent_window: tuple[float, float]
    baseline_window: tuple[float, float]
    teams: list[TeamShapeWatch]
    findings: list[ShapeFinding] = field(default_factory=list)
    coverage: float = 0.0
    data_quality: float = 0.0


def _lines(depths: list[float]) -> list[list[float]]:
    """Kendi kalesine uzaklıkları büyük boşluklardan hatlara böl (space_map kuralı);
    izole en derin tek oyuncu kaleci sayılıp düşülür."""
    groups: list[list[float]] = []
    for d in sorted(depths):
        if groups and d - groups[-1][-1] <= LINE_CLUSTER_GAP_M:
            groups[-1].append(d)
        else:
            groups.append([d])
    if len(groups) > 1 and len(groups[0]) == 1:
        groups = groups[1:]
    return groups


def sample_frame(frame: TrackingFrame, team: int, direction: int) -> ShapeSample | None:
    """`team` savunurken karedeki şekli; yetersiz oyuncu/hat varsa None."""
    pts = [(p.x / 100.0 * PITCH_LENGTH_M, p.y / 100.0 * PITCH_WIDTH_M)
           for p in frame.players if p.team_external_id == team and not p.is_keeper]
    if direction == 0 or len(pts) < MIN_TEAM_PLAYERS:
        return None
    depth = {i: (x if direction > 0 else PITCH_LENGTH_M - x) for i, (x, _y) in enumerate(pts)}
    groups = _lines(list(depth.values()))
    kept = [d for g in groups for d in g]
    if len(kept) < MIN_TEAM_PLAYERS:
        return None
    lines = [g for g in groups if len(g) >= MIN_LINE_PLAYERS]
    if not lines:
        return None
    keeper_cut = min(kept)
    ys = [pts[i][1] for i, d in depth.items() if d >= keeper_cut]
    centers = [sum(g) / len(g) for g in lines]
    return ShapeSample(
        minute=frame.minute, team=team, block_depth=round(centers[0], 2),
        width=round(max(ys) - min(ys), 2),
        line_gap=round(centers[1] - centers[0], 2) if len(centers) >= 2 else None,
        length=round(max(kept) - centers[0], 2), players=len(kept))


def _directions(frames: list[TrackingFrame], home: int, away: int) -> dict[tuple[int, int], int]:
    """(devre, takım) → hücum yönü; devre başına bir kez çıkarılır."""
    out: dict[tuple[int, int], int] = {}
    for period in sorted({f.period for f in frames}):
        part = [f for f in frames if f.period == period]
        d_home, _ = infer_attack_direction(part, home, away)
        out[(period, home)] = d_home
        out[(period, away)] = -d_home
    return out


def _median(values: list[float]) -> float | None:
    return round(median(values), 1) if values else None


_PHRASES = {
    ("block_depth", True, -1): ("warning", "Savunma bloğumuz {d:.0f} m geriledi ({b:.0f} → {r:.0f} m) — rakip orta sahada rahat"),
    ("block_depth", True, 1): ("info", "Savunma bloğumuz {d:.0f} m yükseldi ({b:.0f} → {r:.0f} m) — arkaya atılan topa dikkat"),
    ("width", True, 1): ("warning", "Savunurken {d:.0f} m genişledik ({b:.0f} → {r:.0f} m) — oyuncular arası boşluk açıldı"),
    ("width", True, -1): ("info", "Savunurken {d:.0f} m daraldık ({b:.0f} → {r:.0f} m) — zayıf kanat açık kalabilir"),
    ("line_gap", True, 1): ("warning", "Hatlarımız arası {d:.0f} m açıldı ({b:.0f} → {r:.0f} m) — rakip araya oynayabilir"),
    ("line_gap", True, -1): ("info", "Hatlarımız {d:.0f} m sıkılaştı ({b:.0f} → {r:.0f} m)"),
    ("length", True, 1): ("warning", "Takımımız boyuna {d:.0f} m uzadı ({b:.0f} → {r:.0f} m) — kompaktlık kayboldu"),
    ("length", True, -1): ("info", "Takımımız boyuna {d:.0f} m kısaldı ({b:.0f} → {r:.0f} m)"),
    ("block_depth", False, -1): ("info", "Rakip bloğu {d:.0f} m geri çekildi ({b:.0f} → {r:.0f} m) — topu rahat çevir, ceza sahası çevresine yüklen"),
    ("block_depth", False, 1): ("info", "Rakip bloğu {d:.0f} m yükseldi ({b:.0f} → {r:.0f} m) — savunma arkasına koşu fırsatı"),
    ("width", False, -1): ("info", "Rakip savunurken {d:.0f} m daraldı ({b:.0f} → {r:.0f} m) — kanat değiştir"),
    ("width", False, 1): ("info", "Rakip savunurken {d:.0f} m genişledi ({b:.0f} → {r:.0f} m) — içeriden kombinasyon"),
    ("line_gap", False, 1): ("info", "Rakip hatları arası {d:.0f} m açıldı ({b:.0f} → {r:.0f} m) — araya pas fırsatı"),
    ("line_gap", False, -1): ("info", "Rakip hatları {d:.0f} m sıkılaştı ({b:.0f} → {r:.0f} m)"),
    ("length", False, 1): ("info", "Rakip boyuna {d:.0f} m uzadı ({b:.0f} → {r:.0f} m) — hatlar arasına oyna"),
    ("length", False, -1): ("info", "Rakip boyuna {d:.0f} m kısaldı ({b:.0f} → {r:.0f} m)"),
}


def compute_shape_watch(
    frames: Iterable[TrackingFrame], *, home_team_external_id: int, away_team_external_id: int,
    my_team_external_id: int | None, minute: float,
    recent_min: float = RECENT_MIN, baseline_min: float = BASELINE_MIN,
    thresholds_m: dict[str, float] | None = None, min_samples: int = MIN_SAMPLES,
) -> EngineResult[ShapeWatchReport]:
    """Savunma şeklinin normalden sapması. `frames` en az baseline+recent penceresini kapsamalı."""
    thr = {**THRESHOLDS_M, **(thresholds_m or {})}
    recent = (max(0.0, minute - recent_min), minute)
    base = (max(0.0, minute - recent_min - baseline_min), recent[0])
    frames = [f for f in frames if base[0] <= f.minute <= minute]
    home, away = home_team_external_id, away_team_external_id
    dirs = _directions(frames, home, away) if frames else {}
    samples: list[ShapeSample] = []
    visible: list[int] = []
    for f in frames:
        owner = f.possession_team_external_id
        visible.append(len(f.players))
        if owner not in (home, away):
            continue
        team = away if owner == home else home
        s = sample_frame(f, team, dirs.get((f.period, team), 0))
        if s is not None:
            samples.append(s)

    teams: list[TeamShapeWatch] = []
    findings: list[ShapeFinding] = []
    for team in (home, away):
        mine = [s for s in samples if s.team == team]
        b = [s for s in mine if s.minute < recent[0]]
        r = [s for s in mine if s.minute >= recent[0]]
        states: dict[str, MetricState] = {}
        for m in METRICS:
            bv = _median([v for s in b if (v := getattr(s, m)) is not None])
            rv = _median([v for s in r if (v := getattr(s, m)) is not None])
            delta = round(rv - bv, 1) if bv is not None and rv is not None else None
            states[m] = MetricState(bv, rv, delta)
            enough = len(b) >= min_samples and len(r) >= min_samples
            if enough and delta is not None and bv is not None and rv is not None and abs(delta) >= thr[m]:
                ours = team == my_team_external_id
                sign = 1 if delta > 0 else -1
                sev, tmpl = _PHRASES[(m, ours, sign)]
                findings.append(ShapeFinding(
                    team_external_id=team, ours=ours, metric=m, baseline_m=bv, recent_m=rv, delta_m=delta,
                    severity=sev, message=tmpl.format(d=abs(delta), b=bv, r=rv)))
        teams.append(TeamShapeWatch(team, len(b), len(r), states))
    findings.sort(key=lambda f: (f.severity != "warning", -abs(f.delta_m)))
    cov, quality = coverage_quality(sum(visible) / len(visible) if visible else 0.0)
    report = ShapeWatchReport(minute=minute, recent_window=recent, baseline_window=base, teams=teams,
                              findings=findings, coverage=cov, data_quality=quality)
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION, subject_type="match",
        subject_id=frames[0].match_external_id if frames else 0, metric="shape_watch",
        value=_jsonable(report),
        inputs={"frames": len(frames), "defending_samples": len(samples), "recent_min": recent_min,
                "baseline_min": baseline_min, "min_samples": min_samples, "thresholds_m": thr},
        formula=("defending frames only (possession from frame); per-period attack direction; "
                 "block_depth = deepest line mean distance to own goal; width = y-range without keeper; "
                 "line_gap = 2nd − 1st line; length = front − back line; median recent vs median baseline"),
    )
    return EngineResult(value=report, audit=audit)


def _jsonable(report: ShapeWatchReport) -> dict[str, Any]:
    return asdict(report)
