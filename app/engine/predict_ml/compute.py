"""ML-tabanlı kalibre edilmiş skor tahmini.

PR #17 engine.predict v2 Poisson + Dixon-Coles getirdi; ρ literatür değeri
(-0.12) sabit. Bu modül **veriden öğrenilmiş ρ** ile aynı pipeline'ı çalıştırır.

Şu an: tek-parametre ML — `ρ` değeri grid search ile log loss minimize edilir.
Gerçek ML (xgboost, multinomial logistic) ileride; ama altyapı (training,
persistence, inference) aynı kalır.

Akış:
1. Training (train.py): predictions tablosundan reconciled satırlar →
   ρ grid'inde log loss → en iyi ρ
2. Persistence: cache_entries source='ml_predict_model'
3. Inference (compute.py): cache'ten ρ oku, compute_predict(rho=learned_rho)

Engine kuralı: girdi `FormReport`, çıktı `EngineResult[PredictReport]`.
DB'ye dokunmaz; cache'ten ρ okuma sorumluluğu üst katmanın.
"""

from __future__ import annotations

from app.audit import EngineResult
from app.engine.form import FormReport
from app.engine.predict import compute_predict
from app.engine.predict.compute import PredictReport

ENGINE_NAME = "engine.predict_ml"
ENGINE_VERSION = "1"

# Cache key — model parametrelerinin saklandığı yer (PR B1 cache pattern)
CACHE_SOURCE = "ml_predict_model"
CACHE_KEY = "best_rho_v1"


def compute_ml_predict(
    home_form: FormReport,
    away_form: FormReport,
    *,
    home_team_id: int,
    away_team_id: int,
    learned_rho: float,
) -> EngineResult[PredictReport]:
    """`learned_rho` ile compute_predict çağırır.

    Üst katman cache'ten son trained ρ değerini okuyup geçer. Eğer ML model
    henüz train edilmediyse caller default Poisson+DC ρ'sunu (-0.12)
    geçirebilir (engine.predict default'u). Engine kendi başına cache'e
    dokunmaz.
    """
    return compute_predict(
        home_form, away_form,
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        rho=learned_rho,
    )
