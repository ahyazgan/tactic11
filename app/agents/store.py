"""Agent çıktılarının kalıcı saklanması.

Engine pure → DB ayrı modülde (Predictions store pattern'iyle aynı).
Idempotent upsert: aynı (agent_name, version, subject_type, subject_id)
yeniden gelirse update; yoksa insert.

Orchestrator (scheduler job ya da CLI) Agent.run sonucunu save_agent_output
ile DB'ye yazar.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.base import AgentResult
from app.db import models


def save_agent_output(
    session: Session,
    *,
    result: AgentResult,
    agent_name: str,
    agent_version: str,
) -> models.AgentOutput:
    """Agent sonucunu idempotent yaz; mevcut satır varsa output + summary
    yenile, updated_at güncelle.
    """
    now = datetime.now(UTC)
    output_json_str = json.dumps(result.output_json, ensure_ascii=False)

    existing = session.execute(
        select(models.AgentOutput).where(
            models.AgentOutput.agent_name == agent_name,
            models.AgentOutput.agent_version == agent_version,
            models.AgentOutput.subject_type == result.subject_type,
            models.AgentOutput.subject_id == result.subject_id,
        )
    ).scalar_one_or_none()

    if existing is not None:
        existing.output_json = output_json_str
        existing.summary = result.summary
        existing.updated_at = now
        session.flush()
        return existing

    row = models.AgentOutput(
        agent_name=agent_name,
        agent_version=agent_version,
        subject_type=result.subject_type,
        subject_id=result.subject_id,
        output_json=output_json_str,
        summary=result.summary,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    session.flush()
    return row
