"""Chat persistence: konuşma + mesaj kayıt + endpoint entegrasyonu."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.assistant import (
    append_message,
    create_conversation,
    get_conversation_history,
    list_conversations,
)
from app.db.session import get_session


@pytest.fixture()
def client(session):
    def _override():
        yield session

    app.dependency_overrides[get_session] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_create_conversation_returns_id(session):
    conv = create_conversation(session, team_external_id=611, title="Fener maçı planı")
    session.commit()
    assert conv.id > 0
    assert conv.team_external_id == 611
    assert conv.title == "Fener maçı planı"


def test_append_message_increments_seq(session):
    conv = create_conversation(session)
    append_message(session, conversation_id=conv.id, role="user", content="hi")
    append_message(session, conversation_id=conv.id, role="assistant", content="hello")
    append_message(session, conversation_id=conv.id, role="user", content="ok")
    session.commit()
    history = get_conversation_history(session, conv.id)
    assert len(history) == 3
    assert [m["role"] for m in history] == ["user", "assistant", "user"]
    assert [m["content"] for m in history] == ["hi", "hello", "ok"]


def test_append_message_rejects_invalid_role(session):
    conv = create_conversation(session)
    with pytest.raises(ValueError, match="role"):
        append_message(session, conversation_id=conv.id, role="system", content="x")


def test_list_conversations_filters_by_team(session):
    create_conversation(session, team_external_id=611, title="A")
    create_conversation(session, team_external_id=607, title="B")
    create_conversation(session, team_external_id=611, title="C")
    session.commit()
    for_611 = list_conversations(session, team_external_id=611)
    assert len(for_611) == 2
    # Order by updated_at desc → C ilk
    titles = {c.title for c in for_611}
    assert titles == {"A", "C"}


def test_chat_endpoint_creates_conversation_when_no_id(client, session):
    r = client.post("/assistant/chat", json={"message": "Fener nasıl?"})
    assert r.status_code == 200
    data = r.json()
    assert "conversation_id" in data
    assert data["conversation_id"] > 0
    # DB'de 2 mesaj olmalı (user + assistant)
    session.expire_all()
    history = get_conversation_history(session, data["conversation_id"])
    assert len(history) == 2


def test_chat_endpoint_continues_existing_conversation(client, session):
    r1 = client.post("/assistant/chat", json={"message": "Birinci soru"})
    conv_id = r1.json()["conversation_id"]
    r2 = client.post("/assistant/chat", json={
        "message": "İkinci soru", "conversation_id": conv_id,
    })
    assert r2.status_code == 200
    assert r2.json()["conversation_id"] == conv_id
    session.expire_all()
    history = get_conversation_history(session, conv_id)
    # 2 user + 2 assistant = 4 mesaj
    assert len(history) == 4


def test_chat_endpoint_422_for_invalid_conversation_id(client):
    r = client.post("/assistant/chat", json={
        "message": "x", "conversation_id": "not_an_int",
    })
    assert r.status_code == 422


def test_list_conversations_endpoint(client, session):
    create_conversation(session, team_external_id=611, title="A")
    session.commit()
    r = client.get("/assistant/conversations?team_external_id=611")
    assert r.status_code == 200
    data = r.json()
    assert len(data["conversations"]) == 1
    assert data["conversations"][0]["title"] == "A"


def test_get_conversation_history_endpoint(client, session):
    conv = create_conversation(session)
    append_message(session, conversation_id=conv.id, role="user", content="hi")
    append_message(session, conversation_id=conv.id, role="assistant", content="merhaba")
    session.commit()
    r = client.get(f"/assistant/conversations/{conv.id}")
    assert r.status_code == 200
    data = r.json()
    assert data["conversation_id"] == conv.id
    assert len(data["messages"]) == 2


def test_get_nonexistent_conversation_returns_empty(client):
    r = client.get("/assistant/conversations/999999")
    assert r.status_code == 200
    assert r.json()["messages"] == []
