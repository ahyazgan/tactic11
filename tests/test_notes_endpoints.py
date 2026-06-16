"""Notes endpoint testleri (Faz 5 #41)."""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.notes import (
    NotePayload,
    create_note,
    delete_note,
    list_notes,
    list_replies,
)
from app.db.base import Base


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _payload(subject_type="team", subject_id=11, body="x", **kw) -> NotePayload:
    return NotePayload(
        subject_type=subject_type, subject_id=subject_id, body=body, **kw,
    )


def test_create_top_level_note(session: Session) -> None:
    out = create_note(_payload(body="Skor sonrası taktiksel not"), session=session)
    assert out.subject_type == "team"
    assert out.subject_id == 11
    assert out.parent_note_id is None
    assert out.reply_count == 0


def test_create_reply_increments_parent_reply_count(session: Session) -> None:
    parent = create_note(_payload(body="ana not"), session=session)
    reply = create_note(
        _payload(body="cevap", parent_note_id=parent.id),
        session=session,
    )
    assert reply.parent_note_id == parent.id
    listed = list_notes(
        subject_type="team", subject_id=11, session=session,
    )
    top = next(n for n in listed if n.id == parent.id)
    assert top.reply_count == 1


def test_invalid_subject_type_rejected(session: Session) -> None:
    with pytest.raises(HTTPException) as exc:
        create_note(_payload(subject_type="bogus"), session=session)
    assert exc.value.status_code == 400


def test_reply_to_unknown_parent_404(session: Session) -> None:
    with pytest.raises(HTTPException) as exc:
        create_note(
            _payload(body="cevap", parent_note_id=9999),
            session=session,
        )
    assert exc.value.status_code == 404


def test_reply_subject_mismatch_rejected(session: Session) -> None:
    parent = create_note(
        _payload(subject_type="team", subject_id=11, body="t11 notu"),
        session=session,
    )
    with pytest.raises(HTTPException) as exc:
        create_note(
            _payload(
                subject_type="player", subject_id=42,
                body="kötü", parent_note_id=parent.id,
            ),
            session=session,
        )
    assert exc.value.status_code == 400


def test_list_notes_top_level_only_by_default(session: Session) -> None:
    parent = create_note(_payload(body="ana"), session=session)
    create_note(
        _payload(body="cevap", parent_note_id=parent.id), session=session,
    )
    top_only = list_notes(
        subject_type="team", subject_id=11, session=session,
    )
    assert len(top_only) == 1
    assert top_only[0].id == parent.id

    all_n = list_notes(
        subject_type="team", subject_id=11,
        include_replies=True, session=session,
    )
    assert len(all_n) == 2


def test_list_replies_only_direct_children(session: Session) -> None:
    parent = create_note(_payload(body="p"), session=session)
    c1 = create_note(
        _payload(body="c1", parent_note_id=parent.id), session=session,
    )
    c2 = create_note(
        _payload(body="c2", parent_note_id=parent.id), session=session,
    )
    grandchild = create_note(
        _payload(body="gc", parent_note_id=c1.id), session=session,
    )
    replies = list_replies(note_id=parent.id, session=session)
    ids = {r.id for r in replies}
    assert ids == {c1.id, c2.id}
    assert grandchild.id not in ids


def test_delete_note_cascades_replies(session: Session) -> None:
    parent = create_note(_payload(body="ana"), session=session)
    create_note(
        _payload(body="cevap", parent_note_id=parent.id), session=session,
    )
    delete_note(note_id=parent.id, session=session)

    remaining = list_notes(
        subject_type="team", subject_id=11,
        include_replies=True, session=session,
    )
    assert remaining == []


def test_delete_unknown_returns_404(session: Session) -> None:
    with pytest.raises(HTTPException) as exc:
        delete_note(note_id=9999, session=session)
    assert exc.value.status_code == 404


def test_list_notes_invalid_subject_rejected(session: Session) -> None:
    with pytest.raises(HTTPException) as exc:
        list_notes(subject_type="bogus", subject_id=1, session=session)
    assert exc.value.status_code == 400
