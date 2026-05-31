"""Sezon projeksiyonu — kalan maçlardan final puan dağılımı + hedef olasılığı.

Direktör sorusu: "Bu gidişle kaç puan toplarız, hedefe (Avrupa / şampiyonluk /
küme düşme hattı) ulaşır mıyız?"

Yöntem (saf, deterministik): her kalan maç bağımsız bir sonuç dağılımı taşır
(kazanır=+3, berabere=+1, kaybeder=0; olasılıklar `engine.predict`'ten gelir).
Mevcut puandan başlayıp her maçı dinamik programlama (DP) ile konvolüsyon
yaparak final puanın TAM dağılımını üretiriz — Monte Carlo gürültüsü yok.

    dist_0 = {current_points: 1.0}
    dist_i+1[p+3] += dist_i[p]·P(win)
    dist_i+1[p+1] += dist_i[p]·P(draw)
    dist_i+1[p+0] += dist_i[p]·P(loss)

Çıktıdan beklenen puan, yüzdelik aralık (p10..p90) ve istenen puan hedefine
ulaşma olasılığı türetilir.

Sınırlamalar:
- Final lig SIRASI için diğer takımların projeksiyonu gerekir; bu engine tek
  takımın puan dağılımını verir (sıralama üst katmanda birleştirilir).
- Maç sonuçları bağımsız varsayılır (form sürüklenmesi modellenmez).
- Kalan maç yoksa dağılım mevcut puanda tek nokta.

Engine kuralı: saf hesap. Girdi mevcut puan + kalan maç olasılıkları, çıktı
`EngineResult[SeasonProjectionReport]`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from app.audit import AuditRecord, ConfidenceInfo, EngineResult
from app.engine.confidence import score_confidence

ENGINE_NAME = "engine.season_projection"
ENGINE_VERSION = "1"

# Bu sayının altında kalan maç varsa projeksiyon gürültülü → low_confidence.
_MIN_CONFIDENT_REMAINING = 3


@dataclass(frozen=True)
class MatchOutcomeProb:
    """Bir kalan maç için kazan/berabere/kaybet olasılıkları (takım perspektifi)."""
    prob_win: float
    prob_draw: float
    prob_loss: float


@dataclass(frozen=True)
class SeasonProjectionReport:
    team_external_id: int
    current_points: int
    matches_played: int
    remaining_matches: int
    expected_final_points: float
    # Final puanın yüzdelik aralığı (belirsizlik bandı)
    points_p10: int
    points_p50: int  # medyan
    points_p90: int
    min_possible_points: int  # hepsini kaybet
    max_possible_points: int  # hepsini kazan
    low_confidence: bool


def _outcome_distribution(
    current_points: int, remaining: list[MatchOutcomeProb],
) -> dict[int, float]:
    """DP konvolüsyonu ile final puanın tam olasılık dağılımı."""
    dist: dict[int, float] = {current_points: 1.0}
    for m in remaining:
        nxt: dict[int, float] = {}
        for pts, prob in dist.items():
            if prob <= 0.0:
                continue
            nxt[pts + 3] = nxt.get(pts + 3, 0.0) + prob * m.prob_win
            nxt[pts + 1] = nxt.get(pts + 1, 0.0) + prob * m.prob_draw
            nxt[pts] = nxt.get(pts, 0.0) + prob * m.prob_loss
        dist = nxt
    return dist


def _percentile(sorted_points: list[int], cdf: list[float], q: float) -> int:
    """CDF üzerinde q-yüzdelik puan (q ∈ 0..1)."""
    for pts, cum in zip(sorted_points, cdf, strict=True):
        if cum >= q:
            return pts
    return sorted_points[-1]


def compute_season_projection(
    team_external_id: int,
    *,
    current_points: int,
    matches_played: int,
    remaining: list[MatchOutcomeProb],
) -> EngineResult[SeasonProjectionReport]:
    """Mevcut puan + kalan maç olasılıklarından final puan projeksiyonu."""
    if current_points < 0:
        raise ValueError("current_points negatif olamaz")

    dist = _outcome_distribution(current_points, remaining)
    sorted_points = sorted(dist)
    # Kümülatif dağılım fonksiyonu
    cdf: list[float] = []
    running = 0.0
    for pts in sorted_points:
        running += dist[pts]
        cdf.append(running)

    expected = sum(pts * prob for pts, prob in dist.items())
    n_remaining = len(remaining)

    report = SeasonProjectionReport(
        team_external_id=team_external_id,
        current_points=current_points,
        matches_played=matches_played,
        remaining_matches=n_remaining,
        expected_final_points=round(expected, 2),
        points_p10=_percentile(sorted_points, cdf, 0.10),
        points_p50=_percentile(sorted_points, cdf, 0.50),
        points_p90=_percentile(sorted_points, cdf, 0.90),
        min_possible_points=current_points,
        max_possible_points=current_points + 3 * n_remaining,
        low_confidence=n_remaining < _MIN_CONFIDENT_REMAINING,
    )

    audit = AuditRecord(
        engine=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        subject_type="team",
        subject_id=team_external_id,
        metric="final_points_projection",
        value=asdict(report),
        inputs={
            "current_points": current_points,
            "matches_played": matches_played,
            "remaining_matches": n_remaining,
            "min_confident_remaining": _MIN_CONFIDENT_REMAINING,
        },
        formula=(
            "DP konvolüsyon: dist_0={cp:1}; her maç p+3·P(W), p+1·P(D), p·P(L); "
            "E[final]=Σ p·P(p); p10/p50/p90 CDF yüzdelikleri"
        ),
    )
    conf = score_confidence(
        sample_size=matches_played,
        magnitude=cdf[-1] if cdf else 1.0,  # toplam kütle (≈1)
    )
    return EngineResult(
        value=report, audit=audit,
        confidence=ConfidenceInfo(conf.score, conf.label, conf.drivers),
    )


# --------------------------------------------------------------------------- #
# Puan hedefi sorgusu — projeksiyon dağılımından P(final ≥ hedef)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class PointsTargetReport:
    team_external_id: int
    current_points: int
    target_points: int
    remaining_matches: int
    expected_final_points: float
    prob_reach_target: float  # P(final ≥ target)
    points_needed: int  # max(0, target - current)
    wins_needed_if_only_wins: int  # kaba: ceil(points_needed / 3)
    achievable: bool  # max_possible ≥ target mı


def compute_points_target(
    team_external_id: int,
    *,
    current_points: int,
    matches_played: int,
    remaining: list[MatchOutcomeProb],
    target_points: int,
) -> EngineResult[PointsTargetReport]:
    """Belirli bir puan hedefine ulaşma olasılığı (projeksiyon dağılımından)."""
    if target_points < 0:
        raise ValueError("target_points negatif olamaz")

    dist = _outcome_distribution(current_points, remaining)
    expected = sum(pts * prob for pts, prob in dist.items())
    prob_reach = sum(prob for pts, prob in dist.items() if pts >= target_points)
    n_remaining = len(remaining)
    points_needed = max(0, target_points - current_points)
    max_possible = current_points + 3 * n_remaining

    report = PointsTargetReport(
        team_external_id=team_external_id,
        current_points=current_points,
        target_points=target_points,
        remaining_matches=n_remaining,
        expected_final_points=round(expected, 2),
        prob_reach_target=round(prob_reach, 4),
        points_needed=points_needed,
        wins_needed_if_only_wins=-(-points_needed // 3),  # ceil bölme
        achievable=max_possible >= target_points,
    )

    audit = AuditRecord(
        engine=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        subject_type="team",
        subject_id=team_external_id,
        metric="points_target_probability",
        value=asdict(report),
        inputs={
            "current_points": current_points,
            "target_points": target_points,
            "remaining_matches": n_remaining,
        },
        formula="P(final ≥ target) = Σ_{p≥target} P(p); projeksiyon DP dağılımından",
    )
    conf = score_confidence(sample_size=matches_played, magnitude=prob_reach)
    return EngineResult(
        value=report, audit=audit,
        confidence=ConfidenceInfo(conf.score, conf.label, conf.drivers),
    )
