"""Multinomial 1X2 classifier (Faz 5 #44).

sklearn LogisticRegression (multinomial) — mevcut Dixon-Coles ρ
optimizasyonuna paralel ML modeli. Reconciled predictions tablosundan
feature matrix + 3-class label (home/draw/away) öğrenir.

Stub-aware: sklearn veya joblib yoksa SKLEARN_AVAILABLE=False, train/predict
ImportError'a temiz hata mesajıyla yer açar (modül import'u patlamaz).

Hafif bir baseline classifier — Dixon-Coles ile karşılaştırılması için.
Production-grade için gradient boosting / xgboost ileride bu API üzerine
swap'lanabilir.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import joblib
    from sklearn.ensemble import GradientBoostingClassifier  # type: ignore
    from sklearn.linear_model import LogisticRegression  # type: ignore
    from sklearn.preprocessing import LabelEncoder  # type: ignore
    SKLEARN_AVAILABLE = True
except ImportError:  # pragma: no cover — opsiyonel paketler
    SKLEARN_AVAILABLE = False
    LogisticRegression = None  # type: ignore[misc, assignment]
    GradientBoostingClassifier = None  # type: ignore[misc, assignment]
    LabelEncoder = None  # type: ignore[misc, assignment]
    joblib = None  # type: ignore[assignment]


MODEL_VERSION = "multinomial_v1"
# Desteklenen model tipleri (Faz 9 #44): logistic (baseline) + gbm (gradient
# boosting — non-lineer etkileşimleri yakalar, küçük-orta veride üstün).
MODEL_TYPES = ("logistic", "gbm")
CLASSES = ("home", "draw", "away")
MIN_SAMPLES = 30
# Feature whitelist — train + predict'in aynı sırayla çağırması için.
DEFAULT_FEATURE_KEYS = (
    "lam_home",
    "lam_away",
    "lam_diff",
    "home_form_ppg",
    "away_form_ppg",
    "h2h_home_rate",
    "h2h_draw_rate",
)


class SklearnNotInstalled(RuntimeError):
    """sklearn / joblib kurulu değil — pip install scikit-learn joblib."""


class NotEnoughMultinomialSamples(RuntimeError):
    """Min sample altında — train'i atla, kaydetme yok."""


@dataclass(frozen=True)
class MultinomialSample:
    """Tek bir train satırı — feature dict + 3-class label."""

    features: dict[str, float]
    label: str  # "home" | "draw" | "away"


@dataclass(frozen=True)
class MultinomialReport:
    """Train sonucu — log loss + per-class isabet sayıları."""

    sample_count: int
    feature_keys: tuple[str, ...]
    train_log_loss: float
    class_counts: dict[str, int]
    model_type: str = "logistic"
    model_version: str = MODEL_VERSION


@dataclass
class MultinomialModel:
    """Eğitilmiş sklearn classifier sarmalayıcısı + meta.

    Pickle/joblib ile diske yazılırken `clf` alanı serileştirilir; runtime'da
    ortak feature_keys sıralaması bilgisini saklar.
    """

    feature_keys: tuple[str, ...]
    clf: Any = field(repr=False)  # sklearn LogisticRegression | GradientBoostingClassifier
    label_encoder: Any = field(repr=False)  # sklearn LabelEncoder
    model_type: str = "logistic"
    model_version: str = MODEL_VERSION


def _require_sklearn() -> None:
    if not SKLEARN_AVAILABLE:
        raise SklearnNotInstalled(
            "sklearn + joblib kurulu değil — pip install scikit-learn joblib",
        )


def _build_classifier(model_type: str, random_state: int):
    """model_type → sklearn classifier (logistic | gbm)."""
    if model_type == "logistic":
        return LogisticRegression(
            max_iter=1000, C=1.0, solver="lbfgs", random_state=random_state,
        )
    if model_type == "gbm":
        # GBM: non-lineer etkileşim (form × h2h × λ) yakalar. Küçük-orta veri
        # için sığ ağaçlar + ılımlı learning rate (overfit'i sınırla).
        return GradientBoostingClassifier(
            n_estimators=150, learning_rate=0.05, max_depth=3,
            subsample=0.9, random_state=random_state,
        )
    raise ValueError(f"bilinmeyen model_type: {model_type!r} (beklenen: {MODEL_TYPES})")


def train_multinomial(
    samples: list[MultinomialSample],
    *,
    feature_keys: tuple[str, ...] = DEFAULT_FEATURE_KEYS,
    min_samples: int = MIN_SAMPLES,
    random_state: int = 42,
    model_type: str = "logistic",
) -> tuple[MultinomialModel, MultinomialReport]:
    """sklearn 1X2 classifier eğit. `model_type`: "logistic" (baseline) | "gbm".

    GBM aynı feature matrix'i kullanır; non-lineer etkileşimleri yakaladığı
    için yeterli veri biriktiğinde log loss'u düşürmesi beklenir. Az veride
    (MIN_SAMPLES civarı) logistic daha güvenli olabilir — ikisi de A/B
    karşılaştırması için saklanabilir.
    """
    _require_sklearn()
    if model_type not in MODEL_TYPES:
        raise ValueError(f"bilinmeyen model_type: {model_type!r} (beklenen: {MODEL_TYPES})")
    if len(samples) < min_samples:
        raise NotEnoughMultinomialSamples(
            f"{len(samples)} < {min_samples} sample — train atlandı",
        )

    X = [[s.features.get(k, 0.0) for k in feature_keys] for s in samples]
    y = [s.label for s in samples]

    le = LabelEncoder()
    y_enc = le.fit_transform(y)

    clf = _build_classifier(model_type, random_state)
    clf.fit(X, y_enc)

    # Train-set log loss (üstün uyum/underfit bir bakışta görünsün)
    probs = clf.predict_proba(X)
    eps = 1e-12
    total_ll = 0.0
    for row, true_idx in zip(probs, y_enc, strict=True):
        p = max(eps, min(1.0 - eps, row[true_idx]))
        total_ll += -math.log(p)
    train_ll = total_ll / len(samples)

    class_counts = {c: y.count(c) for c in CLASSES}
    # Geriye uyumluluk: logistic → "multinomial_v1" (mevcut artifact'ler);
    # gbm → "gbm_v1".
    model_version = MODEL_VERSION if model_type == "logistic" else f"{model_type}_v1"
    report = MultinomialReport(
        sample_count=len(samples),
        feature_keys=feature_keys,
        train_log_loss=round(train_ll, 6),
        class_counts=class_counts,
        model_type=model_type,
        model_version=model_version,
    )
    model = MultinomialModel(
        feature_keys=feature_keys, clf=clf, label_encoder=le,
        model_type=model_type, model_version=model_version,
    )
    return model, report


def predict_multinomial(
    model: MultinomialModel,
    features: dict[str, float],
) -> dict[str, float]:
    """Bir maç için {home, draw, away} olasılıkları."""
    _require_sklearn()
    x = [[features.get(k, 0.0) for k in model.feature_keys]]
    probs = model.clf.predict_proba(x)[0]
    # le.classes_ → encoded class labels in same order as probs columns
    labels = list(model.label_encoder.inverse_transform(
        range(len(model.label_encoder.classes_)),
    ))
    out: dict[str, float] = {}
    for label, p in zip(labels, probs, strict=True):
        out[label] = float(p)
    # 3 anahtar da var olsun (sample'da hiç draw görmemişse 0)
    for c in CLASSES:
        out.setdefault(c, 0.0)
    return out


def save_model(model: MultinomialModel, path: str | Path) -> None:
    """Joblib + JSON meta side-car — model.pkl + model.json."""
    _require_sklearn()
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"clf": model.clf, "le": model.label_encoder}, p)
    meta_path = p.with_suffix(p.suffix + ".meta.json")
    meta_path.write_text(
        json.dumps({
            "feature_keys": list(model.feature_keys),
            "model_version": model.model_version,
            "model_type": model.model_type,
        }, indent=2),
        encoding="utf-8",
    )


def load_model(path: str | Path) -> MultinomialModel:
    """Eğitilmiş artifact'i geri yükle."""
    _require_sklearn()
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"model artifact yok: {p}")
    payload = joblib.load(p)
    meta_path = p.with_suffix(p.suffix + ".meta.json")
    if not meta_path.exists():
        raise FileNotFoundError(f"model meta yok: {meta_path}")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    return MultinomialModel(
        feature_keys=tuple(meta["feature_keys"]),
        clf=payload["clf"],
        label_encoder=payload["le"],
        model_type=meta.get("model_type", "logistic"),
        model_version=meta.get("model_version", MODEL_VERSION),
    )
