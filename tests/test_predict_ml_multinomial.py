"""Multinomial classifier testleri (Faz 5 #44).

sklearn opsiyonel — yoksa pytest module-level skip.
"""
from __future__ import annotations

import random

import pytest

from app.engine.predict_ml.multinomial import SKLEARN_AVAILABLE

if not SKLEARN_AVAILABLE:
    pytest.skip(
        "sklearn + joblib kurulu değil",
        allow_module_level=True,
    )

from app.engine.predict_ml.multinomial import (  # noqa: E402
    CLASSES,
    DEFAULT_FEATURE_KEYS,
    MIN_SAMPLES,
    MODEL_VERSION,
    MultinomialModel,
    MultinomialSample,
    NotEnoughMultinomialSamples,
    load_model,
    predict_multinomial,
    save_model,
    train_multinomial,
)

# --------------------------------------------------------------------------- #
# Sample generator — deterministic synthetic data
# --------------------------------------------------------------------------- #


def _make_samples(n: int = 60, seed: int = 7) -> list[MultinomialSample]:
    """Sentetik 3-class samples: features ile label korele.

    Yüksek lam_diff + yüksek home_form_ppg → home; düşük → away; ortada → draw.
    Modelin öğrenip öğrenmediğini bu desenle test ederiz.
    """
    rng = random.Random(seed)
    samples: list[MultinomialSample] = []
    for _ in range(n):
        lam_home = rng.uniform(0.5, 3.0)
        lam_away = rng.uniform(0.5, 3.0)
        lam_diff = lam_home - lam_away
        home_form = rng.uniform(0.5, 2.5)
        away_form = rng.uniform(0.5, 2.5)
        h2h_home = rng.uniform(0.0, 1.0)
        h2h_draw = rng.uniform(0.0, 1.0 - h2h_home)
        score = lam_diff + 0.5 * (home_form - away_form) + 0.3 * h2h_home
        if score > 0.5:
            label = "home"
        elif score < -0.5:
            label = "away"
        else:
            label = "draw"
        samples.append(MultinomialSample(
            features={
                "lam_home": lam_home,
                "lam_away": lam_away,
                "lam_diff": lam_diff,
                "home_form_ppg": home_form,
                "away_form_ppg": away_form,
                "h2h_home_rate": h2h_home,
                "h2h_draw_rate": h2h_draw,
            },
            label=label,
        ))
    return samples


# --------------------------------------------------------------------------- #
# Saf train + predict
# --------------------------------------------------------------------------- #


def test_train_below_min_samples_raises() -> None:
    samples = _make_samples(n=MIN_SAMPLES - 1)
    with pytest.raises(NotEnoughMultinomialSamples):
        train_multinomial(samples)


def test_train_returns_model_and_report() -> None:
    samples = _make_samples(n=80)
    model, report = train_multinomial(samples)
    assert isinstance(model, MultinomialModel)
    assert report.sample_count == 80
    assert report.feature_keys == DEFAULT_FEATURE_KEYS
    assert report.model_version == MODEL_VERSION
    assert 0.0 <= report.train_log_loss < 5.0
    assert sum(report.class_counts.values()) == 80


def test_predict_returns_probabilities_summing_to_one() -> None:
    samples = _make_samples(n=80)
    model, _ = train_multinomial(samples)
    probs = predict_multinomial(model, samples[0].features)
    assert set(probs.keys()) >= set(CLASSES)
    total = sum(probs[c] for c in CLASSES)
    assert abs(total - 1.0) < 0.01


def test_predict_extreme_home_features_picks_home_class() -> None:
    samples = _make_samples(n=120)
    model, _ = train_multinomial(samples)
    extreme_home = {
        "lam_home": 3.5, "lam_away": 0.5, "lam_diff": 3.0,
        "home_form_ppg": 2.8, "away_form_ppg": 0.5,
        "h2h_home_rate": 0.9, "h2h_draw_rate": 0.05,
    }
    probs = predict_multinomial(model, extreme_home)
    assert probs["home"] > probs["away"]
    assert probs["home"] > probs["draw"]


def test_predict_extreme_away_features_picks_away_class() -> None:
    samples = _make_samples(n=120)
    model, _ = train_multinomial(samples)
    extreme_away = {
        "lam_home": 0.5, "lam_away": 3.5, "lam_diff": -3.0,
        "home_form_ppg": 0.5, "away_form_ppg": 2.8,
        "h2h_home_rate": 0.05, "h2h_draw_rate": 0.10,
    }
    probs = predict_multinomial(model, extreme_away)
    assert probs["away"] > probs["home"]


def test_predict_missing_features_default_to_zero() -> None:
    samples = _make_samples(n=80)
    model, _ = train_multinomial(samples)
    sparse = {"lam_home": 1.5, "lam_away": 1.5}  # diğerleri eksik
    probs = predict_multinomial(model, sparse)
    # Tüm 3 anahtarın olduğundan emin ol
    for c in CLASSES:
        assert c in probs


# --------------------------------------------------------------------------- #
# save_model / load_model round-trip
# --------------------------------------------------------------------------- #


def test_save_and_load_round_trip(tmp_path) -> None:
    samples = _make_samples(n=80)
    model, _ = train_multinomial(samples)
    model_path = tmp_path / "multinomial_v1.pkl"
    save_model(model, model_path)
    assert model_path.exists()
    meta_path = model_path.with_suffix(".pkl.meta.json")
    assert meta_path.exists()

    loaded = load_model(model_path)
    assert loaded.feature_keys == model.feature_keys
    assert loaded.model_version == model.model_version

    # Predict aynı sonucu vermeli
    test_features = samples[0].features
    p1 = predict_multinomial(model, test_features)
    p2 = predict_multinomial(loaded, test_features)
    for c in CLASSES:
        assert abs(p1[c] - p2[c]) < 1e-9


def test_load_missing_artifact_raises(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        load_model(tmp_path / "yok.pkl")


def test_load_missing_meta_raises(tmp_path) -> None:
    samples = _make_samples(n=80)
    model, _ = train_multinomial(samples)
    p = tmp_path / "model.pkl"
    save_model(model, p)
    meta_path = p.with_suffix(".pkl.meta.json")
    meta_path.unlink()
    with pytest.raises(FileNotFoundError):
        load_model(p)
