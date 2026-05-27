"""Chat konuşma + mesaj kalıcı saklama.

API tarafından çağırılır: yeni konuşma başlat, mesajları sırayla yaz, geçmişi
oku. Stateless `chat()` orchestrator'unun history parametresine bu satırlardan
Anthropic-format mesajlar inşa edilir.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models


@dataclass(frozen=True)
class ConversationRecord:
    id: int
    team_external_id: int | None
    title: str | None
    created_at: datetime
    updated_at: datetime


def create_conversation(
    session: Session, *,
    team_external_id: int | None = None,
    title: str | None = None,
) -> ConversationRecord:
    now = datetime.now(UTC)
    row = models.ChatConversation(
        team_external_id=team_external_id,
        title=title,
        created_at=now, updated_at=now,
    )
    session.add(row)
    session.flush()
    return ConversationRecord(
        id=row.id, team_external_id=row.team_external_id,
        title=row.title, created_at=row.created_at, updated_at=row.updated_at,
    )


def append_message(
    session: Session, *,
    conversation_id: int,
    role: str,
    content: Any,
    tool_traces: list[dict[str, Any]] | None = None,
    total_tokens: int = 0,
) -> models.ChatMessage:
    """Konuşmaya yeni mesaj ekle. seq otomatik artar."""
    if role not in ("user", "assistant"):
        raise ValueError(f"role: 'user' veya 'assistant' olmalı, geldi {role!r}")
    max_seq = session.execute(
        select(models.ChatMessage.seq)
        .where(models.ChatMessage.conversation_id == conversation_id)
        .order_by(models.ChatMessage.seq.desc())
        .limit(1)
    ).scalar_one_or_none()
    seq = (max_seq or 0) + 1
    now = datetime.now(UTC)
    row = models.ChatMessage(
        conversation_id=conversation_id,
        seq=seq, role=role,
        content_json=json.dumps(content, ensure_ascii=False),
        tool_traces_json=(
            json.dumps(tool_traces, ensure_ascii=False) if tool_traces else None
        ),
        total_tokens=total_tokens,
        created_at=now,
    )
    session.add(row)
    # Konuşma updated_at güncelle
    conv = session.get(models.ChatConversation, conversation_id)
    if conv is not None:
        conv.updated_at = now
    session.flush()
    return row


def get_conversation_history(
    session: Session, conversation_id: int,
) -> list[dict[str, Any]]:
    """Konuşmadaki tüm mesajları Anthropic format'ında döner (chat() history arg'ı)."""
    rows = list(
        session.execute(
            select(models.ChatMessage)
            .where(models.ChatMessage.conversation_id == conversation_id)
            .order_by(models.ChatMessage.seq)
        ).scalars()
    )
    history: list[dict[str, Any]] = []
    for r in rows:
        try:
            content = json.loads(r.content_json)
        except json.JSONDecodeError:
            content = r.content_json
        history.append({"role": r.role, "content": content})
    return history


def list_conversations(
    session: Session, *,
    team_external_id: int | None = None, limit: int = 20,
) -> list[ConversationRecord]:
    q = select(models.ChatConversation)
    if team_external_id is not None:
        q = q.where(models.ChatConversation.team_external_id == team_external_id)
    q = q.order_by(models.ChatConversation.updated_at.desc()).limit(limit)
    rows = list(session.execute(q).scalars())
    return [
        ConversationRecord(
            id=r.id, team_external_id=r.team_external_id, title=r.title,
            created_at=r.created_at, updated_at=r.updated_at,
        )
        for r in rows
    ]
