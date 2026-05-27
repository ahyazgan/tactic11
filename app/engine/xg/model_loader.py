"""Trained xG model artifact loader.

Default path: `models/xg_v1.pkl` (project root relative).
Settings'taki `xg_model_path` ile override edilebilir.

Cache: load_trained_model() lru_cached — model dosyası değişmediği sürece
disk'ten tek sefer okunur. Test'te `_reset_cache()` ile temizlenir.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib

from app.core.logging import get_logger

log = get_logger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MODEL_PATH = _PROJECT_ROOT / "models" / "xg_v1.pkl"
DEFAULT_METADATA_PATH = _PROJECT_ROOT / "models" / "xg_v1_metadata.json"


def _resolve_paths() -> tuple[Path, Path]:
    from app.core.config import get_settings
    s = get_settings()
    custom = getattr(s, "xg_model_path", None)
    if custom:
        model = Path(custom)
        # metadata sidecar — aynı dizin, isim _metadata.json
        meta = model.with_name(model.stem + "_metadata.json")
        return model, meta
    return DEFAULT_MODEL_PATH, DEFAULT_METADATA_PATH


def is_trained_model_available() -> bool:
    """Trained model artifact disk'te var mı."""
    model_path, _ = _resolve_paths()
    return model_path.exists()


@lru_cache(maxsize=1)
def load_trained_model() -> dict[str, Any]:
    """Disk'ten model + metadata yükle. lru_cached — tek sefer okur.

    Returns: `{"model": sklearn.Pipeline, "feature_names": list[str],
              "metadata": dict}`
    """
    model_path, meta_path = _resolve_paths()
    if not model_path.exists():
        raise RuntimeError(
            f"trained xG model bulunamadı: {model_path}. "
            "Önce `python scripts/xg_train_initial.py` ile eğit."
        )
    log.info("xg model yükleniyor: %s", model_path)
    bundle = joblib.load(model_path)
    metadata: dict[str, Any] = {}
    if meta_path.exists():
        try:
            metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            log.warning("xg metadata parse fail: %s", e)
    return {
        "model": bundle["model"],
        "feature_names": bundle.get("feature_names", []),
        "metadata": metadata,
    }


def get_model_status() -> dict[str, Any]:
    """`/admin/xg-model-status` endpoint payload'u."""
    model_path, meta_path = _resolve_paths()
    if not model_path.exists():
        return {
            "status": "untrained",
            "model_path": str(model_path),
            "mode_in_use": "geometric",
        }
    metadata: dict[str, Any] = {}
    if meta_path.exists():
        import contextlib
        with contextlib.suppress(json.JSONDecodeError):
            metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    return {
        "status": "trained",
        "model_path": str(model_path),
        "mode_in_use": "trained",
        **metadata,
    }


def _reset_cache() -> None:
    """Test cleanup — model artifact'i değiştikten sonra yeniden yükle."""
    load_trained_model.cache_clear()
