"""Trained xG mode (Prompt 2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.domain import Shot
from app.engine.xg import (
    compute_shot_xg,
    compute_shot_xg_geometric,
    compute_shot_xg_trained,
    get_active_xg_mode,
)
from app.engine.xg.model_loader import (
    _reset_cache,
    get_model_status,
    is_trained_model_available,
)
from app.engine.xg.train import (
    build_feature_matrix,
    evaluate,
    generate_synthetic_shots,
    save_model,
    train_and_save,
    train_model,
)


def _shot(**kw) -> Shot:
    base = dict(
        sport="football", match_external_id=1, player_external_id=10,
        minute=20.0, x=85.0, y=50.0, body_part="right_foot",
        pattern="open_play", is_goal=False,
    )
    base.update(kw)
    return Shot(**base)  # type: ignore[arg-type]


@pytest.fixture()
def trained_model(tmp_path, monkeypatch):
    """Tek seferlik küçük synthetic model — testler için reproducible."""
    monkeypatch.setenv("XG_MODEL_PATH", str(tmp_path / "test_xg.pkl"))
    from app.core.config import get_settings
    get_settings.cache_clear()  # type: ignore[attr-defined]
    _reset_cache()
    df = generate_synthetic_shots(n=500, seed=42)
    metrics = train_and_save(df, tmp_path / "test_xg.pkl", random_state=42)
    yield tmp_path / "test_xg.pkl", metrics
    _reset_cache()
    get_settings.cache_clear()  # type: ignore[attr-defined]


# --------------------------------------------------------------------------- #
# Training pipeline
# --------------------------------------------------------------------------- #


def test_generate_synthetic_shots_returns_df():
    df = generate_synthetic_shots(n=100, seed=1)
    assert len(df) == 100
    assert {"x", "y", "body_part", "pattern", "is_goal"}.issubset(df.columns)


def test_build_feature_matrix_shape():
    df = generate_synthetic_shots(n=50, seed=1)
    X, y = build_feature_matrix(df)
    assert X.shape == (50, 8)  # 8 feature
    assert y.shape == (50,)
    assert y.dtype.kind == "i"


def test_train_model_returns_fitted_classifier():
    df = generate_synthetic_shots(n=500, seed=1)
    X, y = build_feature_matrix(df)
    model = train_model(X, y)
    assert hasattr(model, "predict_proba")
    proba = model.predict_proba(X[:5])
    assert proba.shape == (5, 2)
    # Probabilities in [0, 1]
    assert (proba >= 0).all() and (proba <= 1).all()


def test_evaluate_returns_expected_metrics():
    df = generate_synthetic_shots(n=500, seed=1)
    X, y = build_feature_matrix(df)
    model = train_model(X, y)
    metrics = evaluate(model, X, y)
    for k in ("brier_score", "log_loss", "roc_auc", "sample_count"):
        assert k in metrics
    # ROC-AUC > 0.5 (better than random for synthetic data)
    assert metrics["roc_auc"] > 0.55


def test_train_and_save_writes_files(tmp_path):
    # 1000 sample yeterli istatistiksel güvenle ROC-AUC > 0.5
    df = generate_synthetic_shots(n=1000, seed=42)
    out = tmp_path / "model.pkl"
    metrics = train_and_save(df, out, version="test_v1")
    assert out.exists()
    assert (tmp_path / "model_metadata.json").exists()
    assert metrics["roc_auc"] > 0.5


# --------------------------------------------------------------------------- #
# Compute trained mode
# --------------------------------------------------------------------------- #


def test_trained_mode_returns_prob_in_unit_interval(trained_model):
    r = compute_shot_xg_trained(_shot(x=88.0, y=50.0))
    assert 0.0 <= r.value.xg <= 1.0


def test_trained_mode_penalty_constant(trained_model):
    """Penalty her durumda 0.76 — trained model'e bile gitse."""
    r = compute_shot_xg_trained(_shot(x=88.0, y=50.0, pattern="penalty"))
    assert r.value.xg == 0.76


def test_trained_audit_includes_model_version(trained_model):
    r = compute_shot_xg_trained(_shot(x=85.0, y=50.0))
    assert "model_version" in r.audit.inputs
    assert "feature_names" in r.audit.inputs
    assert "logistic" in r.audit.formula.lower()


def test_geometric_mode_audit_marks_version():
    r = compute_shot_xg_geometric(_shot(x=85.0, y=50.0))
    assert r.audit.inputs["model_version"] == "xg_geometric_v1"


# --------------------------------------------------------------------------- #
# Mode dispatch
# --------------------------------------------------------------------------- #


def test_auto_falls_back_to_geometric_when_no_model(monkeypatch, tmp_path):
    """Model artifact yoksa auto → geometric."""
    monkeypatch.setenv("XG_MODEL_PATH", str(tmp_path / "nonexistent.pkl"))
    from app.core.config import get_settings
    get_settings.cache_clear()  # type: ignore[attr-defined]
    _reset_cache()
    assert is_trained_model_available() is False
    assert get_active_xg_mode() == "geometric"
    r = compute_shot_xg(_shot(x=85.0, y=50.0), mode="auto")
    assert r.audit.inputs["model_version"] == "xg_geometric_v1"
    get_settings.cache_clear()  # type: ignore[attr-defined]


def test_auto_uses_trained_when_available(trained_model):
    assert is_trained_model_available() is True
    assert get_active_xg_mode() == "trained"
    r = compute_shot_xg(_shot(x=85.0, y=50.0), mode="auto")
    assert "xg_trained" in r.audit.inputs["model_version"]


def test_geometric_mode_forces_old_version(trained_model):
    """mode='geometric' trained varsa bile eski versiyonu kullanır."""
    r = compute_shot_xg(_shot(x=85.0, y=50.0), mode="geometric")
    assert r.audit.inputs["model_version"] == "xg_geometric_v1"


def test_trained_mode_raises_when_no_model(monkeypatch, tmp_path):
    """mode='trained' artifact yoksa RuntimeError."""
    monkeypatch.setenv("XG_MODEL_PATH", str(tmp_path / "nonexistent.pkl"))
    from app.core.config import get_settings
    get_settings.cache_clear()  # type: ignore[attr-defined]
    _reset_cache()
    with pytest.raises(RuntimeError, match="bulunamadı"):
        compute_shot_xg(_shot(x=85.0, y=50.0), mode="trained")
    get_settings.cache_clear()  # type: ignore[attr-defined]


# --------------------------------------------------------------------------- #
# Model status
# --------------------------------------------------------------------------- #


def test_model_status_untrained_when_no_model(monkeypatch, tmp_path):
    monkeypatch.setenv("XG_MODEL_PATH", str(tmp_path / "nonexistent.pkl"))
    from app.core.config import get_settings
    get_settings.cache_clear()  # type: ignore[attr-defined]
    _reset_cache()
    status = get_model_status()
    assert status["status"] == "untrained"
    assert status["mode_in_use"] == "geometric"


def test_model_status_trained(trained_model):
    status = get_model_status()
    assert status["status"] == "trained"
    assert status["mode_in_use"] == "trained"
    assert "metrics" in status  # metadata'dan
    assert "feature_names" in status
