"""Poisson + Dixon-Coles skor tahmini — rakip-göreli güç + ev sahibi avantajı.

Baz model: bir takımın bir maçta atacağı gol sayısı Poisson dağılır, oranı (λ).

**λ nasıl kuruluyor (v3):** Eski sürüm λ'yı yalnız takımın KENDİ gol
ortalamasından alıyordu (`goals_for_per_match`) — kime karşı oynadığını ve
ev/deplasman farkını yok sayıyordu. v3 bunu düzeltir:

1. **Rakip-göreli güç** (Dixon-Coles strength formülasyonu):
       λ_home_adj = home_attack · away_defense / league_avg
       λ_away_adj = away_attack · home_defense / league_avg
   `league_avg` iki formun saldırı+savunma ortalamasından türetilen
   kendi-içinde (self-contained) bir baseline. Sezgi: rakip çok gol
   yiyorsa λ artar, sağlam savunuyorsa düşer.

2. **Shrinkage** (`opponent_weight` w): küçük örneklemde rakip-göreli tahmin
   gürültülü olabilir, bu yüzden kendi-saldırı baseline'ı ile harmanlanır:
       λ = (1-w)·own_attack + w·λ_adj
   w=0 → eski saf "kendi atağı" baseline'ı (geriye uyumlu).

3. **Ev sahibi avantajı** (`home_advantage` hfa): λ_home ↑, λ_away ↓ simetrik:
       λ_home ·= √hfa ;  λ_away /= √hfa
   hfa=1.0 → etkisiz (baseline).

**Dixon-Coles düzeltmesi** (1997): basit Poisson 0-0/1-0/0-1/1-1 frekansını
sistematik altında tahmin eder. DC bu dört hücreyi τ faktörüyle düzeltir:

    τ(0,0) = 1 - λμρ
    τ(0,1) = 1 + λρ
    τ(1,0) = 1 + μρ
    τ(1,1) = 1 - ρ
    τ(x,y) = 1   diğer hücrelerde

ρ tipik -0.18..-0.05; literatür ortası ρ=-0.12 default. ρ=0 saf Poisson'a
indirger (baseline).

Geriye uyumlu baseline: `opponent_weight=0.0, home_advantage=1.0, rho=0.0`
verince eski saf bağımsız-Poisson sonucu çıkar (audit'lenebilir karşılaştırma).

Sınırlamalar:
- Küçük örneklemde (N<5) gürültülü; `low_confidence` flag
- league_avg iki-takım proxy'si; gerçek lig ortalaması beslenince daha keskin
- ρ ve hfa sabit (literatür); veri biriktikçe MLE ile öğrenilebilir

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
ENGINE_VERSION = "3"  # v2 → v3: rakip-göreli güç + ev sahibi avantajı

# Sample size eşiği — bu altında low_confidence flag açılır.
_MIN_CONFIDENT_SAMPLE = 5
# Gol olasılığı hesabında üst sınır — 10 üstü gol pratikte sıfır.
_MAX_GOALS = 10
# Dixon-Coles korelasyon parametresi — literatür tipik -0.18..-0.05;
# ortasını alıp -0.12 default. ρ=0 → saf Poisson (baseline).
_DEFAULT_RHO = -0.12
# Ev sahibi avantajı — λ_home/λ_away oranına uygulanan çarpan. Literatürde
# ev sahibi ~%15 daha üretken; 1.0 → etkisiz baseline.
_DEFAULT_HFA = 1.15
# Rakip-göreli ağırlık (shrinkage): 0 → saf kendi-atağı baseline, 1 → tam
# rakip-göreli. 0.65 → çoğunlukla rakip-göreli ama kendi formu regularize eder.
_DEFAULT_OPP_WEIGHT = 0.65


@dataclass(frozen=True)
class PredictReport:
    home_team_id: int
    away_team_id: int
    expected_home_goals: float  # λ_home (rakip-göreli + hfa uygulanmış)
    expected_away_goals: float  # λ_away
    prob_home_win: float  # 0..1
    prob_draw: float
    prob_away_win: float
    most_likely_score: tuple[int, int]
    most_likely_score_prob: float
    low_confidence: bool  # sample_size < eşik
    sample_size: int  # min(home_form.matches_played, away_form.matches_played)
    rho_used: float  # Dixon-Coles ρ; 0.0 → saf Poisson
    home_advantage_used: float  # hfa; 1.0 → etkisiz
    opponent_weight_used: float  # shrinkage w; 0.0 → saf kendi-atağı baseline
    league_baseline: float  # iki-takım proxy lig ortalaması (gol/maç)


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


def _build_lambdas(
    home_form: FormReport,
    away_form: FormReport,
    *,
    opponent_weight: float,
    home_advantage: float,
) -> tuple[float, float, float]:
    """λ_home, λ_away ve kullanılan league_baseline'ı üretir.

    Rakip-göreli güç + shrinkage + ev sahibi avantajı. Saf fonksiyon.
    """
    home_attack = max(home_form.goals_for_per_match, 0.0)
    away_attack = max(away_form.goals_for_per_match, 0.0)
    home_defense = max(home_form.goals_against_per_match, 0.0)
    away_defense = max(away_form.goals_against_per_match, 0.0)

    # İki-takım proxy lig ortalaması (gol/maç). Tüm veriler 0 ise 0 kalır.
    league_avg = (home_attack + away_attack + home_defense + away_defense) / 4.0

    # Rakip-göreli beklenen gol (Dixon-Coles strength formülasyonu).
    # league_avg=0 → veri yok, kendi-atağı baseline'ına düş.
    if league_avg > 0.0:
        adj_home = home_attack * away_defense / league_avg
        adj_away = away_attack * home_defense / league_avg
    else:
        adj_home, adj_away = home_attack, away_attack

    # Shrinkage: kendi-atağı ile rakip-göreli arasında harmanla.
    w = min(max(opponent_weight, 0.0), 1.0)
    lam_home = (1.0 - w) * home_attack + w * adj_home
    lam_away = (1.0 - w) * away_attack + w * adj_away

    # Ev sahibi avantajı — λ_home/λ_away oranına simetrik çarpan.
    hfa = max(home_advantage, 1e-6)
    factor = math.sqrt(hfa)
    lam_home *= factor
    lam_away /= factor

    return lam_home, lam_away, league_avg


def compute_predict(
    home_form: FormReport,
    away_form: FormReport,
    *,
    home_team_id: int,
    away_team_id: int,
    rho: float = _DEFAULT_RHO,
    home_advantage: float = _DEFAULT_HFA,
    opponent_weight: float = _DEFAULT_OPP_WEIGHT,
) -> EngineResult[PredictReport]:
    """İki form raporundan Poisson + Dixon-Coles skor tahmini.

    λ artık rakibin savunmasına ve ev sahibi avantajına duyarlı (bkz. modül
    docstring). Geriye uyumlu baseline için
    `opponent_weight=0.0, home_advantage=1.0, rho=0.0` ver → eski saf
    bağımsız-Poisson sonucu.

    `rho`: Dixon-Coles korelasyonu (default -0.12).
    `home_advantage`: ev sahibi avantajı çarpanı (default 1.15; 1.0 → etkisiz).
    `opponent_weight`: rakip-göreli shrinkage ağırlığı (default 0.65;
    0.0 → saf kendi-atağı baseline).
    """
    lam_home, lam_away, league_avg = _build_lambdas(
        home_form, away_form,
        opponent_weight=opponent_weight, home_advantage=home_advantage,
    )

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
        home_advantage_used=home_advantage,
        opponent_weight_used=opponent_weight,
        league_baseline=round(league_avg, 4),
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
            "home_advantage": home_advantage,
            "opponent_weight": opponent_weight,
            "league_baseline": round(league_avg, 4),
            "home_attack": home_form.goals_for_per_match,
            "home_defense": home_form.goals_against_per_match,
            "away_attack": away_form.goals_for_per_match,
            "away_defense": away_form.goals_against_per_match,
            "home_form_matches": home_form.matches_played,
            "away_form_matches": away_form.matches_played,
            "min_confident_sample": _MIN_CONFIDENT_SAMPLE,
            "max_goals_grid": _MAX_GOALS,
        },
        formula=(
            "league_avg = mean(home_atk, away_atk, home_def, away_def); "
            "λ_adj_home = home_atk·away_def/league_avg; "
            "λ_home = (1-w)·home_atk + w·λ_adj_home, ·√hfa (away ÷√hfa); "
            "X ~ Poisson(λ); "
            "P(h, a) = P_home(h)·P_away(a)·τ(h, a, λ_h, λ_a, ρ); "
            "Dixon-Coles τ(0,0)=1-λ_h·λ_a·ρ, τ(0,1)=1+λ_h·ρ, "
            "τ(1,0)=1+λ_a·ρ, τ(1,1)=1-ρ, diğer=1; "
            "w=0,hfa=1,ρ=0 → saf bağımsız Poisson baseline; "
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
