"""Asistan hafıza — (subject_type, subject_id, key) → value_json upsert.

Kullanım:
    memory_set(session, subject_type="team", subject_id=611,
               key="preferred_formation", value="4-3-3")
    memory_get(session, subject_type="team", subject_id=611,
               key="preferred_formation")  # → "4-3-3"
    memory_list(session, subject_type="team", subject_id=611)  # tüm key'ler

Asistan chat'i konuşma başında ilgili (team) hafızayı çekip system prompt'a
context olarak enjekte eder — "kullanıcının takım kimliği, oyun stili, geçmiş
kararları" hatırlansın.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models


def memory_set(
    session: Session, *, subject_type: str, subject_id: int,
    key: str, value: Any,
) -> models.AssistantMemory:
    """Upsert: aynı (type, id, key) varsa update; yoksa insert."""
    now = datetime.now(UTC)
    value_json = json.dumps(value, ensure_ascii=False)
    existing = session.execute(
        select(models.AssistantMemory).where(
            models.AssistantMemory.subject_type == subject_type,
            models.AssistantMemory.subject_id == subject_id,
            models.AssistantMemory.key == key,
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.value_json = value_json
        existing.updated_at = now
        session.flush()
        return existing
    row = models.AssistantMemory(
        subject_type=subject_type,
        subject_id=subject_id,
        key=key,
        value_json=value_json,
        created_at_=now,
        updated_at=now,
    )
    session.add(row)
    session.flush()
    return row


def memory_get(
    session: Session, *, subject_type: str, subject_id: int, key: str,
) -> Any | None:
    row = session.execute(
        select(models.AssistantMemory).where(
            models.AssistantMemory.subject_type == subject_type,
            models.AssistantMemory.subject_id == subject_id,
            models.AssistantMemory.key == key,
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    try:
        return json.loads(row.value_json)
    except json.JSONDecodeError:
        return None


def memory_list(
    session: Session, *, subject_type: str, subject_id: int,
) -> dict[str, Any]:
    """Tüm key'leri tek dict olarak döner (system prompt'a enjekte için)."""
    rows = session.execute(
        select(models.AssistantMemory).where(
            models.AssistantMemory.subject_type == subject_type,
            models.AssistantMemory.subject_id == subject_id,
        )
    ).scalars()
    out: dict[str, Any] = {}
    for r in rows:
        try:
            out[r.key] = json.loads(r.value_json)
        except json.JSONDecodeError:
            out[r.key] = r.value_json
    return out


def memory_delete(
    session: Session, *, subject_type: str, subject_id: int, key: str,
) -> bool:
    row = session.execute(
        select(models.AssistantMemory).where(
            models.AssistantMemory.subject_type == subject_type,
            models.AssistantMemory.subject_id == subject_id,
            models.AssistantMemory.key == key,
        )
    ).scalar_one_or_none()
    if row is None:
        return False
    session.delete(row)
    session.flush()
    return True
