"""Kesin-skor dağılımı + market olasılıkları — Poisson/Dixon-Coles üzerine.

`engine.predict` maç sonucu (1X2) olasılığını verir; bu engine aynı
Poisson + Dixon-Coles skor matrisinden medya/bahis-B2B ve teknik ekip için
daha zengin türevler üretir:

- En olası N kesin skor (örn. "en olası: 2-1 %11").
- BTTS (her iki takım da gol atar) olasılığı.
- Over/Under (1.5 / 2.5 / 3.5 gol) olasılıkları.
- Clean sheet (rakip gol atamaz) olasılıkları — ev ve deplasman.
- Beklenen toplam gol.

Matris `engine.predict`'in `_score_matrix`'inden yeniden kullanılır (tek
kaynak): saf Poisson çarpımı × DC τ düzeltmesi. Trunkasyon (max_goals) ve
DC nedeniyle matris toplamı tam 1 olmaz; market olasılıkları matris
toplamına normalize edilir, böylece tümleyici olaylar (over+under) 1'e
toplanır.

Engine kuralı: saf hesap. Girdi iki `FormReport`, çıktı
`EngineResult[ScorePredictionReport]`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from app.audit import AuditRecord, ConfidenceInfo, EngineResult
from app.engine.confidence import score_confidence
from app.engine.form import FormReport
from app.engine.predict.compute import (
    _DEFAULT_RHO,
    _MAX_GOALS,
    _MIN_CONFIDENT_SAMPLE,
    _score_matrix,
)

ENGINE_NAME = "engine.score_prediction"
ENGINE_VERSION = "1"

# Kaç kesin skor döndürülsün (en olasıdan azalan).
_TOP_SCORES = 5


@dataclass(frozen=True)
class ScorePredictionReport:
    home_team_id: int
    away_team_id: int
    expected_home_goals: float
    expected_away_goals: float
    expected_total_goals: float
    # En olası N skor: (home_goals, away_goals, prob) — azalan olasılık.
    top_scores: tuple[tuple[int, int, float], ...]
    prob_btts: float  # her iki takım da en az 1 gol
    prob_over_1_5: float
    prob_over_2_5: float
    prob_over_3_5: float
    prob_under_2_5: float
    prob_home_clean_sheet: float  # deplasman gol atamaz
    prob_away_clean_sheet: float  # ev sahibi gol atamaz
    low_confidence: bool
    sample_size: int
    rho_used: float


def _over_prob(matrix: list[list[float]], line: float) -> float:
    """Toplam gol > `line` olasılığı (örn. line=2.5 → toplam ≥ 3)."""
    return sum(
        matrix[h][a]
        for h in range(_MAX_GOALS + 1)
        for a in range(_MAX_GOALS + 1)
        if h + a > line
    )


def compute_score_prediction(
    home_form: FormReport,
    away_form: FormReport,
    *,
    home_team_id: int,
    away_team_id: int,
    rho: float = _DEFAULT_RHO,
    top_n: int = _TOP_SCORES,
) -> EngineResult[ScorePredictionReport]:
    """İki form raporundan kesin-skor dağılımı + market olasılıkları.

    `engine.predict` ile aynı λ ve skor matrisini kullanır; bu engine
    matristen kesin-skor sıralaması ve market türevleri çıkarır.
    """
    lam_home = home_form.goals_for_per_match
    lam_away = away_form.goals_for_per_match
    matrix = _score_matrix(lam_home, lam_away, rho=rho)

    total_mass = sum(
        matrix[h][a]
        for h in range(_MAX_GOALS + 1)
        for a in range(_MAX_GOALS + 1)
    )
    norm = total_mass if total_mass > 0 else 1.0

    # En olası N skor (normalize edilmiş olasılıkla)
    cells = [
        (h, a, matrix[h][a] / norm)
        for h in range(_MAX_GOALS + 1)
        for a in range(_MAX_GOALS + 1)
    ]
    cells.sort(key=lambda c: c[2], reverse=True)
    top_scores = tuple(
        (h, a, round(p, 4)) for h, a, p in cells[: max(1, top_n)]
    )

    btts = sum(
        matrix[h][a]
        for h in range(1, _MAX_GOALS + 1)
        for a in range(1, _MAX_GOALS + 1)
    ) / norm
    over_1_5 = _over_prob(matrix, 1.5) / norm
    over_2_5 = _over_prob(matrix, 2.5) / norm
    over_3_5 = _over_prob(matrix, 3.5) / norm
    # Clean sheet: rakip 0 gol. Ev sahibinin clean sheet'i = deplasman 0 gol.
    home_clean_sheet = sum(matrix[h][0] for h in range(_MAX_GOALS + 1)) / norm
    away_clean_sheet = sum(matrix[0][a] for a in range(_MAX_GOALS + 1)) / norm

    sample = min(home_form.matches_played, away_form.matches_played)
    low_conf = sample < _MIN_CONFIDENT_SAMPLE

    report = ScorePredictionReport(
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        expected_home_goals=round(lam_home, 3),
        expected_away_goals=round(lam_away, 3),
        expected_total_goals=round(lam_home + lam_away, 3),
        top_scores=top_scores,
        prob_btts=round(btts, 4),
        prob_over_1_5=round(over_1_5, 4),
        prob_over_2_5=round(over_2_5, 4),
        prob_over_3_5=round(over_3_5, 4),
        prob_under_2_5=round(1.0 - over_2_5, 4),
        prob_home_clean_sheet=round(home_clean_sheet, 4),
        prob_away_clean_sheet=round(away_clean_sheet, 4),
        low_confidence=low_conf,
        sample_size=sample,
        rho_used=rho,
    )

    audit = AuditRecord(
        engine=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        subject_type="team_pair",
        subject_id=home_team_id,
        metric="score_distribution_and_markets",
        value=asdict(report),
        inputs={
            "away_team_id": away_team_id,
            "lam_home": lam_home,
            "lam_away": lam_away,
            "rho": rho,
            "home_form_matches": home_form.matches_played,
            "away_form_matches": away_form.matches_played,
            "max_goals_grid": _MAX_GOALS,
            "matrix_mass": round(total_mass, 6),
        },
        formula=(
            "engine.predict skor matrisi M[h][a] = P_home(h)·P_away(a)·τ(h,a); "
            "market olasılıkları matris toplamına normalize edilir; "
            "BTTS=Σ_{h≥1,a≥1}M; over(L)=Σ_{h+a>L}M; "
            "clean_sheet_home=Σ_h M[h][0]; top_scores = en olası N hücre"
        ),
    )
    conf = score_confidence(
        sample_size=sample,
        magnitude=top_scores[0][2] if top_scores else 0.0,
    )
    return EngineResult(
        value=report, audit=audit,
        confidence=ConfidenceInfo(conf.score, conf.label, conf.drivers),
    )
