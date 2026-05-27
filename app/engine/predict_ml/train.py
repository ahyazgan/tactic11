"""ML training — predictions tablosundan reconciled samples → best ρ.

Multi-class log loss minimization over a ρ grid. Pure-Python (no numpy/
sklearn dep) — saf hesap, küçük model.

Akış:
1. Predictions tablosundan actual_outcome NOT NULL satırları
2. Her satırın orijinal (home_form, away_form) snapshot'ından feature çıkar
   → ama biz form'ları yeniden hesaplamak yerine "predicted_value_json"'daki
   λ_home + λ_away'i kullanırız (PR #17 audit'te kayıtlı)
3. ρ grid: [-0.20, -0.18, ..., 0.0]  (12 değer, 0.02 adım)
4. Her ρ için: Poisson+DC ile tahmin → multi-class log loss
5. En düşük log loss veren ρ → learned_rho
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models
from app.engine.predict.compute import _score_matrix  # internal re-use

# Grid: -0.20 ile 0.0 arası, 0.02 adım (11 değer; 0.0 saf Poisson baseline'ı dahil).
RHO_GRID: tuple[float, ...] = tuple(round(-0.20 + 0.02 * i, 2) for i in range(11))

# Log loss clipping (PR B3 engine.calibration ile aynı)
_PROB_EPS = 1e-6


@dataclass(frozen=True)
class TrainingReport:
    sample_count: int
    rho_grid: list[float]
    log_loss_per_rho: dict[str, float]  # rho str-key → log_loss
    best_rho: float | None
    best_log_loss: float | None


class NotEnoughTrainingData(RuntimeError):
    """Predictions reconciled değil veya çok az — train fail-fast."""


def _log_loss_for_rho(samples: list[tuple[float, float, str]], rho: float) -> float:
    """Multi-class log loss; her sample: (lam_home, lam_away, actual_outcome).

    Outcome → 1X2 probabilities via Poisson+DC ile compute_predict mantığı,
    sonra -ln(P(actual)) ortalaması.
    """
    total = 0.0
    for lam_home, lam_away, actual in samples:
        matrix = _score_matrix(lam_home, lam_away, rho=rho)
        max_g = len(matrix) - 1
        p_home = sum(matrix[h][a] for h in range(max_g + 1) for a in range(max_g + 1) if h > a)
        p_draw = sum(matrix[k][k] for k in range(max_g + 1))
        p_away = sum(matrix[h][a] for h in range(max_g + 1) for a in range(max_g + 1) if h < a)
        if actual == "home":
            p = p_home
        elif actual == "draw":
            p = p_draw
        else:
            p = p_away
        p = max(_PROB_EPS, min(1.0 - _PROB_EPS, p))
        total += -math.log(p)
    return total / len(samples) if samples else 0.0


def _extract_samples(session: Session, *, min_samples: int) -> list[tuple[float, float, str]]:
    """Reconciled predictions'tan training samples çıkar.

    Her sample: (lam_home, lam_away, actual_outcome). predicted_value_json'dan
    `expected_home_goals` ve `expected_away_goals` okunur (PR #17 audit'te
    expected_home_goals = λ_home).
    """
    rows = list(
        session.execute(
            select(models.Prediction).where(
                models.Prediction.engine == "engine.predict",
                models.Prediction.actual_outcome.is_not(None),
            )
        ).scalars()
    )
    samples: list[tuple[float, float, str]] = []
    for r in rows:
        try:
            v = json.loads(r.predicted_value_json)
        except json.JSONDecodeError:
            continue
        lam_h = v.get("expected_home_goals")
        lam_a = v.get("expected_away_goals")
        outcome = r.actual_outcome
        if lam_h is None or lam_a is None or outcome not in ("home", "draw", "away"):
            continue
        samples.append((float(lam_h), float(lam_a), outcome))
    if len(samples) < min_samples:
        raise NotEnoughTrainingData(
            f"sadece {len(samples)} sample var, min {min_samples} gerek"
        )
    return samples


def train_best_rho(session: Session, *, min_samples: int = 20) -> TrainingReport:
    """Ana training entry point.

    `min_samples=20` default — küçük veri setinde overfit'ten kaçınmak için
    eşik. Az veri varsa NotEnoughTrainingData fırlat (caller skip eder).
    """
    samples = _extract_samples(session, min_samples=min_samples)

    log_losses: dict[str, float] = {}
    for rho in RHO_GRID:
        log_losses[str(rho)] = round(_log_loss_for_rho(samples, rho), 4)

    best_rho = min(log_losses.keys(), key=lambda k: log_losses[k])
    return TrainingReport(
        sample_count=len(samples),
        rho_grid=list(RHO_GRID),
        log_loss_per_rho=log_losses,
        best_rho=float(best_rho),
        best_log_loss=log_losses[best_rho],
    )
