"""Tracking analiz fonksiyonları.

Veri tarafı henüz dolu değil (gerçek `TrackingDataSource` adapter Faz 6'da);
ama engine kuralı şimdiden somut: girdi `Iterable[TrackingFrame]`, çıktı
`EngineResult[T]`. Sentetik frame'lerle test edilebilir, gerçek vendor
geldiğinde sözleşme aynı kalır.

İlk somut metric: **ball-zone distribution** — top sahanın hangi üçte
birinde (defensive / middle / attacking) ne kadar süre kaldı.
Territorial dominance göstergesi; takım-bazlı değil (tek match'in
ball pozisyonu yeterli).

Stub fonksiyonlar (`compute_pressure`, `compute_formation`) Faz 6 için
yer tutuyor — gerçek tracking ingest'i geldiğinde implement edilir.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass

from app.audit import AuditRecord, EngineResult
from app.domain import TrackingFrame

ENGINE_NAME = "engine.tracking"
ENGINE_VERSION = "1"  # 0 → 1: ball_zone_distribution implement edildi

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


def compute_pressure(
    team_external_id: int,
    frames: Iterable[TrackingFrame],
) -> EngineResult:
    """Top sahibi rakip çevresindeki bu takımın pres yoğunluğu.

    Stub — TrackingDataSource adapter geldikten sonra implement edilir
    (top sahibi player_id'sini bilmek gerek + team rosters).
    """
    raise NotImplementedError(
        "compute_pressure Faz 6'da doldurulacak; gerçek tracking ingest + "
        "top sahibi attribution sözleşmesi lazım."
    )


def compute_formation(
    team_external_id: int,
    frames: Iterable[TrackingFrame],
) -> EngineResult:
    """Kümeleme ile yerleşim çıkarımı (örn. '4-3-3', '4-2-3-1').

    Stub — player→team mapping + sample window seçimi gerek (oyun-içi
    yerleşim, set-piece anlarında bozulur).
    """
    raise NotImplementedError(
        "compute_formation Faz 6'da doldurulacak; player roster + zaman "
        "penceresi seçimi sözleşmesi lazım."
    )
