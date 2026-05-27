"""Prediction kayıtlarının kalıcı saklanması.

`/matches/{id}/predict` çağrısı yan etki olarak save_prediction çağırır.
Idempotency: aynı (sport, match, engine, version, params_hash) için yeniden
istek geldiyse yeni satır oluşmaz; mevcut satır predicted_value_json +
updated_at ile tazelenir.

Reconciliation (PR B2) sonradan actual_* alanlarını dolduran scheduler job
ekler. Saklama sırasında actual alanları None bırakılır.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import EngineResult
from app.db import models


def _params_hash(params: dict[str, Any]) -> str:
    """Deterministik 32-char hash — sort_keys ile bayt-stabil."""
    payload = json.dumps(params, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def save_prediction(
    session: Session,
    *,
    sport: str,
    match_external_id: int,
    result: EngineResult,
    params: dict[str, Any],
) -> models.Prediction:
    """Idempotent upsert. Aynı (engine, version, params_hash) bulursa update'ler.

    `result.audit.engine` + `result.audit.engine_version` engine kimliği;
    `result.audit.value` saklanan tahmin payload'ı (asdict çıktısı).
    """
    now = datetime.now(UTC)
    ph = _params_hash(params)
    params_json = json.dumps(params, sort_keys=True, ensure_ascii=False)
    predicted_json = json.dumps(result.audit.value, ensure_ascii=False)

    existing = session.execute(
        select(models.Prediction).where(
            models.Prediction.sport == sport,
            models.Prediction.match_external_id == match_external_id,
            models.Prediction.engine == result.audit.engine,
            models.Prediction.engine_version == result.audit.engine_version,
            models.Prediction.params_hash == ph,
        )
    ).scalar_one_or_none()

    if existing is not None:
        existing.predicted_value_json = predicted_json
        existing.params_json = params_json  # params aynı hash → aynı içerik ama yine de yaz
        existing.updated_at = now
        session.flush()
        return existing

    row = models.Prediction(
        sport=sport,
        match_external_id=match_external_id,
        engine=result.audit.engine,
        engine_version=result.audit.engine_version,
        params_hash=ph,
        params_json=params_json,
        predicted_value_json=predicted_json,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    session.flush()
    return row
