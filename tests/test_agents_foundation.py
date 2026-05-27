"""Agent base + AgentResult + save_agent_output (PR G1)."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import select

from app.agents import Agent, AgentResult, save_agent_output
from app.db import models


def test_agent_is_abstract():
    """Concrete subclass olmadan Agent() patlamalı."""
    with pytest.raises(TypeError):
        Agent()  # type: ignore[abstract]


def test_agent_subclass_works(session):
    class DummyAgent(Agent):
        name = "dummy"
        version = "1"

        def run(self, session, *, context):
            return AgentResult(
                output_json={"hello": "world", "ctx": context},
                summary="dummy summary",
                subject_type="match",
                subject_id=42,
            )

    agent = DummyAgent()
    result = agent.run(session, context={"foo": "bar"})
    assert result.subject_type == "match"
    assert result.subject_id == 42
    assert result.output_json["hello"] == "world"


def test_save_agent_output_creates_row(session):
    result = AgentResult(
        output_json={"k": "v"}, summary="s",
        subject_type="match", subject_id=99,
    )
    row = save_agent_output(
        session, result=result,
        agent_name="test_agent", agent_version="1",
    )
    assert row.id is not None
    assert row.agent_name == "test_agent"
    assert row.subject_type == "match"
    assert json.loads(row.output_json) == {"k": "v"}


def test_save_agent_output_is_idempotent(session):
    r1 = AgentResult(
        output_json={"v": 1}, summary="s1",
        subject_type="match", subject_id=99,
    )
    row1 = save_agent_output(
        session, result=r1, agent_name="test_agent", agent_version="1",
    )

    # Tekrar — aynı subject, farklı output
    r2 = AgentResult(
        output_json={"v": 2}, summary="s2-updated",
        subject_type="match", subject_id=99,
    )
    row2 = save_agent_output(
        session, result=r2, agent_name="test_agent", agent_version="1",
    )

    assert row1.id == row2.id  # aynı satır (upsert)
    assert json.loads(row2.output_json) == {"v": 2}  # output yenilendi
    assert row2.summary == "s2-updated"
    # Sadece 1 satır var
    rows = session.execute(select(models.AgentOutput)).scalars().all()
    assert len(rows) == 1


def test_save_agent_output_different_subject_creates_new_row(session):
    r1 = AgentResult(
        output_json={}, summary="", subject_type="match", subject_id=1,
    )
    r2 = AgentResult(
        output_json={}, summary="", subject_type="match", subject_id=2,
    )
    save_agent_output(session, result=r1, agent_name="a", agent_version="1")
    save_agent_output(session, result=r2, agent_name="a", agent_version="1")
    rows = session.execute(select(models.AgentOutput)).scalars().all()
    assert len(rows) == 2


def test_save_agent_output_different_version_creates_new_row(session):
    r = AgentResult(
        output_json={}, summary="", subject_type="match", subject_id=1,
    )
    save_agent_output(session, result=r, agent_name="a", agent_version="1")
    save_agent_output(session, result=r, agent_name="a", agent_version="2")
    rows = session.execute(select(models.AgentOutput)).scalars().all()
    assert len(rows) == 2
