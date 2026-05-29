"""Çoklu kullanıcı not/yorum endpoint'leri (Faz 5 #41).

- POST   /notes — yeni not (opsiyonel parent_note_id ile yanıt)
- GET    /notes?subject_type=&subject_id=&include_replies=  — liste
- GET    /notes/{id}/replies — bir notun cevapları
- DELETE /notes/{id} — yumuşak değil sert silme (CASCADE alt cevapları)

Auth korumalı router'a takılır; author_user_id authentication context'inden
gelecek (gelecek auth integration), şu an payload'dan kabul ediliyor.
"""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models
from app.db.session import get_session

router = APIRouter(tags=["notes"])

VALID_SUBJECT_TYPES = (
    "team", "player", "match", "decision", "agent_output", "league",
)


class NotePayload(BaseModel):
    subject_type: str = Field(..., max_length=32)
    subject_id: int
    body: str = Field(..., min_length=1, max_length=4096)
    parent_note_id: int | None = None
    author_user_id: int | None = None


class NoteOut(BaseModel):
    id: int
    subject_type: str
    subject_id: int
    parent_note_id: int | None
    author_user_id: int | None
    body: str
    created_at: datetime
    updated_at: datetime
    reply_count: int


def _note_to_out(row: models.Note, reply_count: int = 0) -> NoteOut:
    return NoteOut(
        id=row.id,
        subject_type=row.subject_type,
        subject_id=row.subject_id,
        parent_note_id=row.parent_note_id,
        author_user_id=row.author_user_id,
        body=row.body,
        created_at=row.created_at,
        updated_at=row.updated_at,
        reply_count=reply_count,
    )


def _count_replies(session: Session, note_id: int) -> int:
    from sqlalchemy import func
    return int(session.execute(
        select(func.count(models.Note.id))
        .where(models.Note.parent_note_id == note_id)
    ).scalar() or 0)


@router.post("/notes", response_model=NoteOut)
def create_note(
    payload: NotePayload,
    session: Session = Depends(get_session),
) -> NoteOut:
    """Yeni not oluştur — parent_note_id verilirse yanıt zincirine eklenir."""
    if payload.subject_type not in VALID_SUBJECT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"subject_type {payload.subject_type} geçersiz — "
                f"{VALID_SUBJECT_TYPES}"
            ),
        )
    if payload.parent_note_id is not None:
        parent = session.execute(
            select(models.Note).where(models.Note.id == payload.parent_note_id)
        ).scalar_one_or_none()
        if parent is None:
            raise HTTPException(
                status_code=404,
                detail=f"parent_note_id {payload.parent_note_id} bulunamadı",
            )
        # Tutarlılık: yanıt ana notla aynı subject'i taşımalı
        if (parent.subject_type != payload.subject_type
                or parent.subject_id != payload.subject_id):
            raise HTTPException(
                status_code=400,
                detail="parent note farklı subject'e ait",
            )
    now = datetime.now(UTC)
    row = models.Note(
        subject_type=payload.subject_type,
        subject_id=payload.subject_id,
        parent_note_id=payload.parent_note_id,
        author_user_id=payload.author_user_id,
        body=payload.body,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    session.flush()
    session.commit()
    return _note_to_out(row, reply_count=0)


@router.get("/notes", response_model=list[NoteOut])
def list_notes(
    subject_type: str,
    subject_id: int,
    include_replies: bool = False,
    session: Session = Depends(get_session),
) -> list[NoteOut]:
    """Bir konunun notları — default sadece top-level (parent_note_id IS NULL)."""
    if subject_type not in VALID_SUBJECT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"subject_type {subject_type} geçersiz — {VALID_SUBJECT_TYPES}",
        )
    q = select(models.Note).where(
        models.Note.subject_type == subject_type,
        models.Note.subject_id == subject_id,
    )
    if not include_replies:
        q = q.where(models.Note.parent_note_id.is_(None))
    q = q.order_by(models.Note.created_at)
    rows = list(session.execute(q).scalars())
    out: list[NoteOut] = []
    for r in rows:
        rc = _count_replies(session, r.id) if r.parent_note_id is None else 0
        out.append(_note_to_out(r, reply_count=rc))
    return out


@router.get("/notes/{note_id}/replies", response_model=list[NoteOut])
def list_replies(
    note_id: int,
    session: Session = Depends(get_session),
) -> list[NoteOut]:
    """Bir notun yanıt zinciri (sadece doğrudan child'lar)."""
    parent = session.execute(
        select(models.Note).where(models.Note.id == note_id)
    ).scalar_one_or_none()
    if parent is None:
        raise HTTPException(status_code=404, detail=f"note {note_id} bulunamadı")
    rows = list(session.execute(
        select(models.Note)
        .where(models.Note.parent_note_id == note_id)
        .order_by(models.Note.created_at)
    ).scalars())
    return [_note_to_out(r, reply_count=0) for r in rows]


@router.delete("/notes/{note_id}", response_model=dict)
def delete_note(
    note_id: int,
    session: Session = Depends(get_session),
) -> dict:
    """Notu sil (CASCADE yanıtları da siler)."""
    row = session.execute(
        select(models.Note).where(models.Note.id == note_id)
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"note {note_id} bulunamadı")
    session.delete(row)
    session.commit()
    return {"deleted": True, "id": note_id}
