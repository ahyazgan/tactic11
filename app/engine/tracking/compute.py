"""Tracking analiz fonksiyonları — girdi `Iterable[TrackingFrame]`, çıktı `EngineResult[T]`.

Kaynaklar: StatsBomb 360 freeze-frame (`statsbomb_360`) ve video takibi
(`video_tracking`); ikisi de aynı şemaya yazdığı için motorlar kaynağı ayırt etmez.

- `compute_ball_zone_distribution` — top sahanın hangi üçte birinde ne kadar kaldı
- `compute_team_shape` — genişlik / derinlik / kompaktlık / hat yapısı → yerleşim
- `compute_pressure` — rakip topa sahipken top çevresindeki baskı (yakınlık + 5 m içi)
- `compute_formation` — yerleşim tahmini (team_shape kısa yolu)

Not: video kaynağında kimlikler sentetik, kaleci bayrağı yok; izole kenar hattı
tek kişilikse kaleci sayılıp düşülür. Kamera görüş alanı dışındaki oyuncular
sayılmaz — StatsBomb 360'ta kısmi kadro normaldir.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass

from app.audit import AuditRecord, EngineResult
from app.domain import TrackingFrame

ENGINE_NAME = "engine.tracking"
ENGINE_VERSION = "2"  # 1 → 2: team_shape / pressure / formation (pozisyon karelerinden)

# Saha bölgesi sınırları (x ekseni 0-100 normalize)
_DEFENSIVE_THIRD_MAX = 100.0 / 3  # x ≤ 33.33
_MIDDLE_THIRD_MAX = 200.0 / 3     # 33.33 < x ≤ 66.67


@dataclass(frozen=True)
class BallZoneDistribution:
    """Top'un saha üçte birlerinde geçirdiği zaman oranı.

    Toplam frames = defensive + middle + attacking + frames_without_ball.
    Fraksiyonlar 0..1 arası; sum(fractions) = 1 (ball None olan frame'ler
    distribution'a sayılmaz, ayrıca raporda görünür).
    """
    total_frames: int
    frames_with_ball: int
    defensive_third_fraction: float
    middle_third_fraction: float
    attacking_third_fraction: float


def compute_ball_zone_distribution(
    frames: Iterable[TrackingFrame],
) -> EngineResult[BallZoneDistribution]:
    """Top sahanın hangi üçte birinde ne kadar süre kaldı."""
    total = 0
    with_ball = 0
    defensive = middle = attacking = 0

    for f in frames:
        total += 1
        if f.ball is None:
            continue
        with_ball += 1
        x = f.ball.x
        if x <= _DEFENSIVE_THIRD_MAX:
            defensive += 1
        elif x <= _MIDDLE_THIRD_MAX:
            middle += 1
        else:
            attacking += 1

    if with_ball:
        report = BallZoneDistribution(
            total_frames=total,
            frames_with_ball=with_ball,
            defensive_third_fraction=round(defensive / with_ball, 4),
            middle_third_fraction=round(middle / with_ball, 4),
            attacking_third_fraction=round(attacking / with_ball, 4),
        )
    else:
        report = BallZoneDistribution(
            total_frames=total, frames_with_ball=0,
            defensive_third_fraction=0.0,
            middle_third_fraction=0.0,
            attacking_third_fraction=0.0,
        )

    audit = AuditRecord(
        engine=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        subject_type="match",
        subject_id=0,  # frame-level metric, takım yok
        metric="ball_zone_distribution",
        value=asdict(report),
        inputs={
            "total_frames": total,
            "frames_with_ball": with_ball,
            "defensive_third_max_x": _DEFENSIVE_THIRD_MAX,
            "middle_third_max_x": _MIDDLE_THIRD_MAX,
        },
        formula=(
            "defensive = frames where ball.x ≤ 100/3; "
            "middle = 100/3 < ball.x ≤ 200/3; "
            "attacking = ball.x > 200/3; "
            "fractions = count / frames_with_ball"
        ),
    )
    return EngineResult(value=report, audit=audit)


# --------------------------------------------------------------------------- #
# Takım şekli / pres / yerleşim — pozisyon karelerinden (StatsBomb 360 ya da video)
# --------------------------------------------------------------------------- #

PITCH_LENGTH_M = 105.0
PITCH_WIDTH_M = 68.0
PRESS_RADIUS_M = 5.0
LINE_GAP_M = 6.0        # x ekseninde bu kadar boşluk = yeni hat
MIN_LINE_PLAYERS = 7    # daha az görünür oyuncuyla yerleşim tahmini yapılmaz


def _to_m(x: float, y: float) -> tuple[float, float]:
    return x / 100.0 * PITCH_LENGTH_M, y / 100.0 * PITCH_WIDTH_M


def _dist_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def _team_players(frame: TrackingFrame, team_external_id: int) -> list[tuple[float, float]]:
    """Takımın görünür saha oyuncuları (m); kaleci bayrağı varsa dışarıda."""
    return [
        _to_m(p.x, p.y)
        for p in frame.players
        if p.team_external_id == team_external_id and not p.is_keeper
    ]


def _lines_by_x_gap(xs: list[float], gap_m: float) -> list[int]:
    """x'e göre sıralı oyuncuları büyük boşluklardan hatlara böl; hat başına sayı."""
    if not xs:
        return []
    xs = sorted(xs)
    counts = [1]
    for prev, cur in zip(xs, xs[1:], strict=False):
        if cur - prev > gap_m:
            counts.append(1)
        else:
            counts[-1] += 1
    return counts


def _strip_isolated_keeper(counts: list[int], total: int) -> list[int]:
    """Kenar hattı tek kişilikse ve toplam ≥ 10 ise kaleci say, düş."""
    if total >= 10 and len(counts) >= 3:
        if counts[0] == 1:
            return counts[1:]
        if counts[-1] == 1:
            return counts[:-1]
    return counts


@dataclass(frozen=True)
class TeamShapeReport:
    """Takımın pencere boyunca ortalama şekli (metre)."""
    team_external_id: int
    frames_used: int
    players_mean: float
    width_m: float          # enine yayılım (y aralığı)
    depth_m: float          # boyuna yayılım (x aralığı)
    compactness_m: float    # oyuncuların merkeze ortalama uzaklığı (küçük = kompakt)
    centroid_x: float       # 0-100
    centroid_y: float       # 0-100
    rear_line_x: float      # 0-100, en geri oyuncu (küçük x)
    front_line_x: float     # 0-100, en ileri oyuncu (büyük x)
    formation: str | None   # örn. "4-3-3" (x-boşluk hatları; kaleci düşülür)
    formation_support: float  # kareler içinde baskın yerleşimin payı 0..1


def compute_team_shape(
    team_external_id: int,
    frames: Iterable[TrackingFrame],
) -> EngineResult[TeamShapeReport]:
    """Genişlik / derinlik / kompaktlık / hat yapısı — kare ortalaması."""
    from collections import Counter

    used = 0
    n_sum = width_sum = depth_sum = comp_sum = cx_sum = cy_sum = rear_sum = front_sum = 0.0
    formations: Counter[str] = Counter()
    for f in frames:
        pts = _team_players(f, team_external_id)
        if len(pts) < 3:
            continue
        used += 1
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
        n_sum += len(pts)
        width_sum += max(ys) - min(ys)
        depth_sum += max(xs) - min(xs)
        comp_sum += sum(_dist_m(p, (cx, cy)) for p in pts) / len(pts)
        cx_sum += cx / PITCH_LENGTH_M * 100.0
        cy_sum += cy / PITCH_WIDTH_M * 100.0
        rear_sum += min(xs) / PITCH_LENGTH_M * 100.0
        front_sum += max(xs) / PITCH_LENGTH_M * 100.0
        if len(pts) >= MIN_LINE_PLAYERS:
            counts = _strip_isolated_keeper(_lines_by_x_gap(xs, LINE_GAP_M), len(pts))
            if 2 <= len(counts) <= 5:
                formations["-".join(str(c) for c in counts)] += 1

    if used == 0:
        report = TeamShapeReport(
            team_external_id=team_external_id, frames_used=0, players_mean=0.0,
            width_m=0.0, depth_m=0.0, compactness_m=0.0, centroid_x=50.0, centroid_y=50.0,
            rear_line_x=0.0, front_line_x=0.0, formation=None, formation_support=0.0,
        )
    else:
        top = formations.most_common(1)
        report = TeamShapeReport(
            team_external_id=team_external_id,
            frames_used=used,
            players_mean=round(n_sum / used, 1),
            width_m=round(width_sum / used, 1),
            depth_m=round(depth_sum / used, 1),
            compactness_m=round(comp_sum / used, 1),
            centroid_x=round(cx_sum / used, 1),
            centroid_y=round(cy_sum / used, 1),
            rear_line_x=round(rear_sum / used, 1),
            front_line_x=round(front_sum / used, 1),
            formation=top[0][0] if top else None,
            formation_support=round(top[0][1] / sum(formations.values()), 2) if top else 0.0,
        )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="team", subject_id=team_external_id, metric="team_shape",
        value=asdict(report),
        inputs={"frames_used": used, "line_gap_m": LINE_GAP_M, "min_line_players": MIN_LINE_PLAYERS},
        formula=(
            "width = max(y)-min(y); depth = max(x)-min(x); compactness = mean dist to centroid; "
            f"lines = x-sorted players split at gaps > {LINE_GAP_M} m, isolated edge single = GK dropped; "
            "formation = modal line-count string over frames"
        ),
    )
    return EngineResult(value=report, audit=audit)


@dataclass(frozen=True)
class PressureReport:
    """Rakip topa sahipken bu takımın top çevresindeki baskısı."""
    team_external_id: int
    frames_used: int            # rakip possession + top görünür
    nearest_mean_m: float       # topa en yakın oyuncunun ortalama uzaklığı
    within_5m_mean: float       # 5 m içindeki ortalama oyuncu
    press_index: float          # 0..1 — within_5m/3 ve yakınlık birleşik


def compute_pressure(
    team_external_id: int,
    frames: Iterable[TrackingFrame],
) -> EngineResult[PressureReport]:
    """Top sahibi rakip çevresindeki bu takımın pres yoğunluğu.

    Yalnız `possession_team_external_id` bu takım değilken ve top görünürken
    sayılır (video kaynağında topa en yakın oyuncunun takımı possession sayılır).
    """
    used = 0
    nearest_sum = within_sum = 0.0
    for f in frames:
        if f.ball is None or f.possession_team_external_id in (None, team_external_id):
            continue
        pts = _team_players(f, team_external_id)
        if not pts:
            continue
        ball = _to_m(f.ball.x, f.ball.y)
        d = sorted(_dist_m(p, ball) for p in pts)
        used += 1
        nearest_sum += d[0]
        within_sum += sum(1 for v in d if v <= PRESS_RADIUS_M)
    if used:
        nearest = nearest_sum / used
        within = within_sum / used
        proximity = max(0.0, min(1.0, 1.0 - nearest / (2 * PRESS_RADIUS_M)))
        index = round(0.5 * min(1.0, within / 3.0) + 0.5 * proximity, 2)
        report = PressureReport(team_external_id, used, round(nearest, 1), round(within, 2), index)
    else:
        report = PressureReport(team_external_id, 0, 0.0, 0.0, 0.0)
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="team", subject_id=team_external_id, metric="pressure",
        value=asdict(report),
        inputs={"frames_used": used, "press_radius_m": PRESS_RADIUS_M},
        formula=(
            "frames: opponent possession & ball visible; nearest = min dist(team player, ball); "
            f"within = count dist ≤ {PRESS_RADIUS_M} m; index = 0.5·min(1, within/3) + 0.5·(1 − nearest/{2 * PRESS_RADIUS_M})"
        ),
    )
    return EngineResult(value=report, audit=audit)


@dataclass(frozen=True)
class FormationEstimate:
    team_external_id: int
    formation: str | None
    support: float
    frames_used: int


def compute_formation(
    team_external_id: int,
    frames: Iterable[TrackingFrame],
) -> EngineResult[FormationEstimate]:
    """Yerleşim tahmini — `compute_team_shape`'in hat sayımı (kısa yol)."""
    shape = compute_team_shape(team_external_id, frames)
    v = shape.value
    est = FormationEstimate(team_external_id, v.formation, v.formation_support, v.frames_used)
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="team", subject_id=team_external_id, metric="formation",
        value=asdict(est), inputs=shape.audit.inputs, formula=shape.audit.formula,
    )
    return EngineResult(value=est, audit=audit)
