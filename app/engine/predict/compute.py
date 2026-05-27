"""Poisson skor tahmini — klasik futbol istatistiği.

Varsayım: bir takımın bir maçta atacağı gol sayısı Poisson dağılır, oranı
(λ) o takımın geçmiş maçlarındaki ortalama gol oranıdır. İki takımın
skorları bağımsız varsayılır.

P(k gol) = (λ^k · e^-λ) / k!

Bu, üzerinden 100 yıllık literatür bulunan **en açıklanabilir** futbol
tahmin modeli. ML değil; "sayılara göre şu beklenti var" diyebilirsin.
Audit'e formül net yazılır.

Sınırlamalar:
- Küçük örneklemde (N<5) gürültülü; `low_confidence` flag ile döner
- Ev sahibi avantajı modele dahil değil (form zaten home/away ayrımı taşıyor
  ama bu engine'de toplu kullanılıyor — gelecekte refine edilebilir)
- Karşılıklı korelasyon (defansif maç → ikisi de az gol) yok; bağımsız
  varsayım
- ML modeli değil — gerçek veri biriktiğinde elastic-net veya XGBoost ile
  rakip-spesifik kalibre edilebilir; bu modül baseline olarak kalır

Engine kuralı: saf hesap. Girdi `FormReport` (engine.form'dan), çıktı
`EngineResult[PredictReport]`.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from app.audit import AuditRecord, EngineResult
from app.engine.form import FormReport

ENGINE_NAME = "engine.predict"
ENGINE_VERSION = "1"

# Sample size eşiği — bu altında low_confidence flag açılır.
_MIN_CONFIDENT_SAMPLE = 5
# Gol olasılığı hesabında üst sınır — 10 üstü gol pratikte sıfır.
_MAX_GOALS = 10


@dataclass(frozen=True)
class PredictReport:
    home_team_id: int
    away_team_id: int
    expected_home_goals: float  # λ_home
    expected_away_goals: float  # λ_away
    prob_home_win: float  # 0..1
    prob_draw: float
    prob_away_win: float
    most_likely_score: tuple[int, int]
    most_likely_score_prob: float
    low_confidence: bool  # sample_size < eşik
    sample_size: int  # min(home_form.matches_played, away_form.matches_played)


def _poisson_pmf(lam: float, k: int) -> float:
    """P(X=k) for X ~ Poisson(lam)."""
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return (lam**k) * math.exp(-lam) / math.factorial(k)


def _score_matrix(
    lam_home: float, lam_away: float, max_goals: int = _MAX_GOALS
) -> list[list[float]]:
    """`max_goals+1` × `max_goals+1` olasılık matrisi: M[h][a] = P(home=h ∧ away=a)."""
    home_probs = [_poisson_pmf(lam_home, k) for k in range(max_goals + 1)]
    away_probs = [_poisson_pmf(lam_away, k) for k in range(max_goals + 1)]
    return [[home_probs[h] * away_probs[a] for a in range(max_goals + 1)] for h in range(max_goals + 1)]


def compute_predict(
    home_form: FormReport,
    away_form: FormReport,
    *,
    home_team_id: int,
    away_team_id: int,
) -> EngineResult[PredictReport]:
    """İki form raporundan Poisson skor tahmini.

    λ_home = home_form.goals_for_per_match (kendi geçmişindeki ortalama)
    λ_away = away_form.goals_for_per_match
    """
    lam_home = home_form.goals_for_per_match
    lam_away = away_form.goals_for_per_match

    matrix = _score_matrix(lam_home, lam_away)

    p_home_win = sum(
        matrix[h][a]
        for h in range(_MAX_GOALS + 1)
        for a in range(_MAX_GOALS + 1)
        if h > a
    )
    p_draw = sum(matrix[k][k] for k in range(_MAX_GOALS + 1))
    p_away_win = sum(
        matrix[h][a]
        for h in range(_MAX_GOALS + 1)
        for a in range(_MAX_GOALS + 1)
        if h < a
    )

    # En olası skor — matrix maksimumu
    best_h, best_a, best_p = 0, 0, 0.0
    for h in range(_MAX_GOALS + 1):
        for a in range(_MAX_GOALS + 1):
            if matrix[h][a] > best_p:
                best_h, best_a, best_p = h, a, matrix[h][a]

    sample = min(home_form.matches_played, away_form.matches_played)
    low_conf = sample < _MIN_CONFIDENT_SAMPLE

    report = PredictReport(
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        expected_home_goals=round(lam_home, 3),
        expected_away_goals=round(lam_away, 3),
        prob_home_win=round(p_home_win, 4),
        prob_draw=round(p_draw, 4),
        prob_away_win=round(p_away_win, 4),
        most_likely_score=(best_h, best_a),
        most_likely_score_prob=round(best_p, 4),
        low_confidence=low_conf,
        sample_size=sample,
    )

    audit = AuditRecord(
        engine=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        subject_type="team_pair",
        subject_id=home_team_id,
        metric="poisson_predict",
        value=asdict(report),
        inputs={
            "away_team_id": away_team_id,
            "lam_home": lam_home,
            "lam_away": lam_away,
            "home_form_matches": home_form.matches_played,
            "away_form_matches": away_form.matches_played,
            "min_confident_sample": _MIN_CONFIDENT_SAMPLE,
            "max_goals_grid": _MAX_GOALS,
        },
        formula=(
            "X ~ Poisson(λ); λ_home = home_form.goals_for_per_match; "
            "λ_away = away_form.goals_for_per_match; P(home=h, away=a) = "
            "P_home(h)·P_away(a) (bağımsız); sample_size < "
            f"{_MIN_CONFIDENT_SAMPLE} → low_confidence"
        ),
    )
    return EngineResult(value=report, audit=audit)
