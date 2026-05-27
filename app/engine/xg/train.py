"""xG modeli eğitim pipeline'ı (sklearn LogisticRegression).

CLI: `python -m app.engine.xg.train --output models/xg_v1.pkl`
StatsBomb Open data desteği: `--source statsbomb_open --competition 43,11`
Synthetic data (test/dev): `--source synthetic --n 5000`

Feature engineering — Caley 2014 yaklaşımı:
- distance_to_goal (öklid)
- angle_to_goal (radyan, görünür kale)
- is_header (bool)
- is_open_play / is_set_piece / is_fast_break (bool)
- x, y (saha koordinatı)

Penalty şutları train'e dahil edilmez (xG=0.76 sabit).

Çıktı:
- models/xg_v1.pkl: joblib bundle {"model", "feature_names"}
- models/xg_v1_metadata.json: train tarihi, metrikler, feature list
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.model_selection import train_test_split

from app.core.logging import get_logger
from app.engine.xg.compute import _distance, _shot_angle

log = get_logger(__name__)

FEATURE_NAMES: tuple[str, ...] = (
    "distance", "angle",
    "is_header", "is_open_play", "is_set_piece", "is_fast_break",
    "x", "y",
)


def _shot_to_features(shot: dict[str, Any]) -> dict[str, float]:
    """Tek bir shot dict'inden feature dict üret.

    Şutun format'ı StatsBomb Open data ya da synthetic'ten gelir;
    field mapping: x, y (0-100), body_part, pattern, is_goal.
    """
    return {
        "distance": _distance(float(shot["x"]), float(shot["y"])),
        "angle": _shot_angle(float(shot["x"]), float(shot["y"])),
        "is_header": 1.0 if shot.get("body_part") == "head" else 0.0,
        "is_open_play": 1.0 if shot.get("pattern") == "open_play" else 0.0,
        "is_set_piece": 1.0 if shot.get("pattern") in ("set_piece", "free_kick", "corner_kick") else 0.0,
        "is_fast_break": 1.0 if shot.get("pattern") == "fast_break" else 0.0,
        "x": float(shot["x"]),
        "y": float(shot["y"]),
    }


def generate_synthetic_shots(n: int = 5000, seed: int = 42) -> pd.DataFrame:
    """Train pipeline'ı için sentetik şut veri — geometric baseline'ı yumuşatarak
    gerçek-benzeri dağılım üretir. StatsBomb Open yok ise scaffolding için."""
    rng = np.random.default_rng(seed)
    shots = []
    for _ in range(n):
        # Şut konumu — hücum yarısı yoğun
        x = float(rng.uniform(50, 99))
        y = float(rng.uniform(0, 100))
        body = rng.choice(["right_foot", "left_foot", "head", "other"], p=[0.55, 0.28, 0.15, 0.02])
        pattern = rng.choice(
            ["open_play", "set_piece", "fast_break", "corner_kick", "free_kick"],
            p=[0.65, 0.10, 0.12, 0.08, 0.05],
        )
        # Penalty'leri synthetic'de atlıyoruz (sabit 0.76)
        # Goal olasılığı geometric baseline + gürültü
        dist = _distance(x, y)
        angle = _shot_angle(x, y)
        log_odds = (
            -0.5
            - 0.08 * dist
            + 1.8 * angle
            + (-0.5 if body == "head" else 0.0)
            + (0.4 if pattern == "fast_break" else -0.3 if pattern in ("set_piece", "free_kick", "corner_kick") else 0.0)
        )
        p = 1.0 / (1.0 + np.exp(-log_odds))
        # Gerçek goal — gürültü ile sample
        is_goal = bool(rng.random() < p * 0.9 + rng.normal(0, 0.02))
        shots.append({
            "x": x, "y": y, "body_part": body, "pattern": pattern,
            "is_goal": is_goal,
        })
    return pd.DataFrame(shots)


def build_feature_matrix(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """DataFrame → (X, y)."""
    feature_rows = [_shot_to_features(row.to_dict()) for _, row in df.iterrows()]
    X = pd.DataFrame(feature_rows)[list(FEATURE_NAMES)].values
    y = df["is_goal"].astype(int).values
    return X, y


def train_model(
    X: np.ndarray, y: np.ndarray, *, C: float = 1.0,
) -> LogisticRegression:
    model = LogisticRegression(
        C=C, max_iter=1000, class_weight="balanced", solver="lbfgs",
    )
    model.fit(X, y)
    return model


def evaluate(
    model: LogisticRegression, X_test: np.ndarray, y_test: np.ndarray,
) -> dict[str, float]:
    proba = model.predict_proba(X_test)[:, 1]
    return {
        "brier_score": float(brier_score_loss(y_test, proba)),
        "log_loss": float(log_loss(y_test, proba)),
        "roc_auc": float(roc_auc_score(y_test, proba)),
        "sample_count": int(len(y_test)),
    }


def save_model(
    model: LogisticRegression, output: Path,
    metrics: dict[str, Any], version: str = "xg_trained_v1",
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({
        "model": model, "feature_names": list(FEATURE_NAMES),
    }, output)
    metadata = {
        "version": version,
        "trained_at": datetime.now(UTC).isoformat(),
        "feature_names": list(FEATURE_NAMES),
        "metrics": metrics,
    }
    meta_path = output.with_name(output.stem + "_metadata.json")
    meta_path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8",
    )
    log.info("xg model saved: %s + %s", output, meta_path)


def _load_statsbomb_shots(
    *, competitions: list[tuple[int, int]] | None = None,
    max_matches: int | None = None,
) -> pd.DataFrame:
    """StatsBomb Open Data'dan shot event'lerini çek + DataFrame.

    `competitions`: (competition_id, season_id) tuple listesi. Default: La Liga
    (11, 90) + FIFA WC 2022 (43, 106) — popüler ve açık.

    Penalty şutları DAHIL EDILMEZ (sabit 0.76 zaten).
    """
    from app.data.sources.statsbomb_open import StatsBombOpen

    if competitions is None:
        # Default: küçük + popüler — La Liga 2020-21 + WC 2022
        competitions = [(11, 90), (43, 106)]

    adapter = StatsBombOpen()
    all_rows: list[dict] = []
    for comp_id, season_id in competitions:
        try:
            matches = adapter.get_matches(
                competition_id=comp_id, season_id=season_id,
            )
        except RuntimeError as e:
            log.warning("statsbomb skip %d/%d: %s", comp_id, season_id, e)
            continue
        if max_matches:
            matches = matches[:max_matches]
        for m in matches:
            mid = m.get("match_id")
            if mid is None:
                continue
            try:
                shots = adapter.get_shots_for_match(int(mid))
            except RuntimeError as e:
                log.warning("statsbomb skip match %s: %s", mid, e)
                continue
            for s in shots:
                if s.pattern == "penalty":
                    continue  # penalty xG=0.76 sabit
                all_rows.append({
                    "x": s.x, "y": s.y,
                    "body_part": s.body_part,
                    "pattern": s.pattern,
                    "is_goal": s.is_goal,
                })
    if not all_rows:
        raise RuntimeError(
            "StatsBomb data toplanamadı — ağ erişimi var mı? "
            "Synthetic fallback için --source synthetic kullan."
        )
    return pd.DataFrame(all_rows)


def train_and_save(
    df: pd.DataFrame, output: Path,
    *, test_size: float = 0.2, random_state: int = 42,
    version: str = "xg_trained_v1",
) -> dict[str, Any]:
    X, y = build_feature_matrix(df)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=random_state, stratify=y,
    )
    model = train_model(X_train, y_train)
    metrics = evaluate(model, X_test, y_test)
    save_model(model, output, metrics, version=version)
    return metrics


def main() -> int:
    parser = argparse.ArgumentParser(description="xG model train pipeline")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--source", choices=["synthetic", "statsbomb_open"], default="synthetic",
    )
    parser.add_argument("--n", type=int, default=5000, help="synthetic sample count")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--version", default="xg_trained_v1")
    args = parser.parse_args()

    if args.source == "synthetic":
        df = generate_synthetic_shots(n=args.n, seed=args.seed)
    else:
        df = _load_statsbomb_shots()
    metrics = train_and_save(
        df, args.output, version=args.version,
    )
    print(f"Trained. Metrics: {json.dumps(metrics, indent=2)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
