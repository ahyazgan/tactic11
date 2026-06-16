"""Poisson + Dixon-Coles skor tahmini — klasik futbol istatistiği.

Baz model: bir takımın bir maçta atacağı gol sayısı Poisson dağılır, oranı
(λ) o takımın geçmiş maçlarındaki ortalama gol oranıdır.

P(k gol) = (λ^k · e^-λ) / k!

**Dixon-Coles düzeltmesi** (1997): basit Poisson, futbol verisinde
0-0/1-0/0-1/1-1 frekansını sistematik biçimde altında tahmin eder
(düşük skorlu maçlarda hafif negatif korelasyon var). DC bu dört hücreyi
bir τ faktörüyle düzeltir:

    τ(0,0) = 1 - λμρ
    τ(0,1) = 1 + λρ
    τ(1,0) = 1 + μρ
    τ(1,1) = 1 - ρ
    τ(x,y) = 1   diğer hücrelerde

ρ tipik olarak -0.18 ile -0.05 arasında; biz literatür ortasında
ρ=-0.12 default'u tutuyoruz. ρ=0 saf Poisson'a indirger
(geriye uyumlu baseline; karşılaştırma için audit'lenebilir).

τ değişimleri sıfır toplamlı: P(0,0)/P(1,1) artar, P(0,1)/P(1,0) eşit
miktarda azalır — toplam olasılık 1 kalır.

Sınırlamalar:
- Küçük örneklemde (N<5) gürültülü; `low_confidence` flag
- Ev sahibi avantajı modele dahil değil (form zaten home/away ayrımı taşıyor)
- ρ sabit; literatür değeri. Veri biriktiğinde ρ'yu MLE ile öğrenmek
  mümkün — bu modül baseline olarak kalır
- ML değil — gerçek veri biriktiğinde elastic-net / XGBoost'la rakip-
  spesifik kalibre edilebilir

Engine kuralı: saf hesap. Girdi `FormReport` (engine.form'dan), çıktı
`EngineResult[PredictReport]`.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from app.audit import AuditRecord, ConfidenceInfo, EngineResult
from app.engine.confidence import score_confidence
from app.engine.form import FormReport

ENGINE_NAME = "engine.predict"
ENGINE_VERSION = "2"  # v1 → v2: Dixon-Coles düşük skor düzeltmesi default

# Sample size eşiği — bu altında low_confidence flag açılır.
_MIN_CONFIDENT_SAMPLE = 5
# Gol olasılığı hesabında üst sınır — 10 üstü gol pratikte sıfır.
_MAX_GOALS = 10
# Dixon-Coles korelasyon parametresi — literatür tipik -0.18..-0.05;
# ortasını alıp -0.12 default. ρ=0 → saf Poisson (baseline).
_DEFAULT_RHO = -0.12


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
    rho_used: float  # Dixon-Coles ρ; 0.0 → saf Poisson


def _poisson_pmf(lam: float, k: int) -> float:
    """P(X=k) for X ~ Poisson(lam)."""
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return (lam**k) * math.exp(-lam) / math.factorial(k)


def _dixon_coles_tau(home_goals: int, away_goals: int, lam_home: float, lam_away: float, rho: float) -> float:
    """DC τ düzeltmesi — yalnız (0,0), (0,1), (1,0), (1,1) hücrelerinde 1'den sapar."""
    if home_goals == 0 and away_goals == 0:
        return 1.0 - lam_home * lam_away * rho
    if home_goals == 0 and away_goals == 1:
        return 1.0 + lam_home * rho
    if home_goals == 1 and away_goals == 0:
        return 1.0 + lam_away * rho
    if home_goals == 1 and away_goals == 1:
        return 1.0 - rho
    return 1.0


def _score_matrix(
    lam_home: float, lam_away: float, *, rho: float, max_goals: int = _MAX_GOALS
) -> list[list[float]]:
    """`max_goals+1` × `max_goals+1` olasılık matrisi: M[h][a] = P(home=h ∧ away=a).

    Saf Poisson × DC τ. ρ=0 ise τ ≡ 1 ve sonuç bağımsız Poisson çarpımı.
    """
    home_probs = [_poisson_pmf(lam_home, k) for k in range(max_goals + 1)]
    away_probs = [_poisson_pmf(lam_away, k) for k in range(max_goals + 1)]
    return [
        [
            home_probs[h] * away_probs[a]
            * _dixon_coles_tau(h, a, lam_home, lam_away, rho)
            for a in range(max_goals + 1)
        ]
        for h in range(max_goals + 1)
    ]


def compute_predict(
    home_form: FormReport,
    away_form: FormReport,
    *,
    home_team_id: int,
    away_team_id: int,
    rho: float = _DEFAULT_RHO,
) -> EngineResult[PredictReport]:
    """İki form raporundan Poisson + Dixon-Coles skor tahmini.

    λ_home = home_form.goals_for_per_match (kendi geçmişindeki ortalama)
    λ_away = away_form.goals_for_per_match

    `rho`: Dixon-Coles korelasyon parametresi. Default -0.12 (literatür
    ortası). ρ=0 saf Poisson baseline'a indirger — karşılaştırma için
    kasıtlı kullanılır.
    """
    lam_home = home_form.goals_for_per_match
    lam_away = away_form.goals_for_per_match

    matrix = _score_matrix(lam_home, lam_away, rho=rho)

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
        rho_used=rho,
    )

    audit = AuditRecord(
        engine=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        subject_type="team_pair",
        subject_id=home_team_id,
        metric="poisson_dixon_coles_predict",
        value=asdict(report),
        inputs={
            "away_team_id": away_team_id,
            "lam_home": lam_home,
            "lam_away": lam_away,
            "rho": rho,
            "home_form_matches": home_form.matches_played,
            "away_form_matches": away_form.matches_played,
            "min_confident_sample": _MIN_CONFIDENT_SAMPLE,
            "max_goals_grid": _MAX_GOALS,
        },
        formula=(
            "X ~ Poisson(λ); λ_home = home_form.goals_for_per_match; "
            "λ_away = away_form.goals_for_per_match; "
            "P(h, a) = P_home(h)·P_away(a)·τ(h, a, λ_h, λ_a, ρ); "
            "Dixon-Coles τ(0,0)=1-λ_h·λ_a·ρ, τ(0,1)=1+λ_h·ρ, "
            "τ(1,0)=1+λ_a·ρ, τ(1,1)=1-ρ, diğer=1; "
            "ρ=0 saf Poisson; "
            f"sample_size < {_MIN_CONFIDENT_SAMPLE} → low_confidence"
        ),
    )
    # Güven: sample_size = iki formun min maç sayısı; magnitude = en olası
    # sonucun olasılığı (tahminin keskinliği).
    conf = score_confidence(
        sample_size=min(home_form.matches_played, away_form.matches_played),
        magnitude=max(p_home_win, p_draw, p_away_win),
    )
    return EngineResult(
        value=report, audit=audit,
        confidence=ConfidenceInfo(conf.score, conf.label, conf.drivers),
    )
