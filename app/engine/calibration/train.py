"""Kalibrasyon training — predictions tablosundan en iyi sıcaklık T öğren.

ρ pipeline'ının (predict_ml) kalibrasyon ikizi. Reconciled engine.predict
satırlarının HAM 1X2 olasılıklarını okur, log-loss'u minimize eden tek
sıcaklık T'yi öğrenir (temperature scaling) ve cache'e yazar.

ÖNEMLİ: training HAM (ham=kalibre edilmemiş) olasılıklar üzerinden yapılır;
serving anında T uygulanır ama saklanan tahmin HAM kalır → bir sonraki
training yine ham veriyi görür (feedback loop yok, T peşinde koşmaz).

Akış:
1. Predictions: engine.predict, actual_outcome NOT NULL → (ph, pd, pa, actual)
2. fit_temperature → best T + log_loss before/after
3. Persistence: cache_entries(source='calibration_model', key='best_temperature_v1')
4. Inference (api): cache'ten T oku, response'a kalibre olasılık bloğu ekle
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models
from app.engine.calibration.recalibrate import fit_temperature

# Cache key — öğrenilmiş sıcaklığın saklandığı yer (predict_ml ile aynı desen).
CACHE_SOURCE = "calibration_model"
CACHE_KEY = "best_temperature_v1"


@dataclass(frozen=True)
class CalibrationTrainingReport:
    sample_count: int
    best_temperature: float | None
    log_loss_before: float | None
    log_loss_after: float | None
    improved: bool


class NotEnoughTrainingData(RuntimeError):
    """Predictions reconciled değil veya çok az — train fail-fast."""


def _extract_samples(
    session: Session, *, min_samples: int
) -> list[tuple[float, float, float, str]]:
    """Reconciled engine.predict satırlarından (ph, pd, pa, actual) çıkar."""
    rows = list(
        session.execute(
            select(models.Prediction).where(
                models.Prediction.engine == "engine.predict",
                models.Prediction.actual_outcome.is_not(None),
            )
        ).scalars()
    )
    samples: list[tuple[float, float, float, str]] = []
    for r in rows:
        try:
            v = json.loads(r.predicted_value_json)
        except json.JSONDecodeError:
            continue
        ph = v.get("prob_home_win")
        pd = v.get("prob_draw")
        pa = v.get("prob_away_win")
        outcome = r.actual_outcome
        if ph is None or pd is None or pa is None or outcome not in ("home", "draw", "away"):
            continue
        samples.append((float(ph), float(pd), float(pa), outcome))
    if len(samples) < min_samples:
        raise NotEnoughTrainingData(
            f"sadece {len(samples)} sample var, min {min_samples} gerek"
        )
    return samples


def train_best_temperature(
    session: Session, *, min_samples: int = 20
) -> CalibrationTrainingReport:
    """Ana training entry point — reconciled tahminlerden en iyi T'yi öğrenir.

    `min_samples=20` default; az veride overfit'ten kaçınmak için eşik.
    Yetersiz veri → NotEnoughTrainingData (caller skip eder).
    """
    samples = _extract_samples(session, min_samples=min_samples)
    calib = fit_temperature(samples)
    return CalibrationTrainingReport(
        sample_count=calib.n_train,
        best_temperature=calib.temperature,
        log_loss_before=calib.log_loss_before,
        log_loss_after=calib.log_loss_after,
        improved=calib.improved,
    )
