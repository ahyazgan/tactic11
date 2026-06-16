"""LiveDecisionDigestAgent — live snapshot → AI brief."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.agents.live_decision_digest import LiveDecisionDigestAgent
from app.ai import AnthropicClient, ClaudeCommentator
from app.db import models
from app.sports import football


@pytest.fixture()
def seeded(session):
    session.info["tenant_id"] = "t-test"
    now = datetime.now(UTC)
    session.add(models.Tenant(
        id="t-test", slug="t-test", name="T",
        settings_json="{}", active=True, created_at=now,
    ))
    session.add(models.Match(
        sport=football.SPORT_NAME, external_id=9301,
        league_external_id=11, season=2018,
        kickoff=now - timedelta(days=1), status="FT",
        home_team_external_id=11, away_team_external_id=22,
        home_score=1, away_score=1, tenant_id="t-test",
    ))
    # 30 pass event — momentum/sub_timing engineları çalışır olsun
    for i in range(30):
        session.add(models.EventRow(
            sport=football.SPORT_NAME, tenant_id="t-test",
            source="statsbomb_open", source_event_id=f"p{i}",
            match_external_id=9301, team_external_id=11,
            player_external_id=1, event_type="pass",
            minute=float(i * 2 + 30), period=2 if i * 2 + 30 >= 45 else 1,
            start_x=50.0, start_y=50.0, end_x=70.0, end_y=50.0,
            outcome="completed", body_part=None, pattern="regular",
            possession_id=i, is_goal=None, key_pass=False,
            raw_json=None, created_at=now,
        ))
    session.commit()
    return session


def test_agent_runs_with_stub_commentator(seeded):
    """ANTHROPIC_API_KEY yok → stub brief döner, AgentResult valid."""
    agent = LiveDecisionDigestAgent(
        commentator=ClaudeCommentator(AnthropicClient()),
    )
    result = agent.run(seeded, context={
        "match_external_id": 9301, "my_team_id": 11,
        "current_minute": 80.0,
    })
    assert result.subject_type == "match"
    assert result.subject_id == 9301
    out = result.output_json
    assert out["match_external_id"] == 9301
    assert out["current_minute"] == 80.0
    assert out["score"] == "1-1"
    assert "ai_brief" in out
    # Stub mode imzası
    assert out["ai_brief"].startswith("[stub:live_digest]")
    # Snapshot meta'sı dolu
    assert "snapshot_keys" in out
    assert "momentum" in out["snapshot_keys"]


def test_agent_summary_includes_minute_and_score(seeded):
    agent = LiveDecisionDigestAgent()
    result = agent.run(seeded, context={
        "match_external_id": 9301, "my_team_id": 11,
        "current_minute": 80.0,
    })
    assert "9301" in result.summary
    assert "80" in result.summary
    assert "1-1" in result.summary


def test_agent_raises_on_missing_match(seeded):
    agent = LiveDecisionDigestAgent()
    with pytest.raises(ValueError, match="bulunamadı"):
        agent.run(seeded, context={
            "match_external_id": 999999, "my_team_id": 11,
            "current_minute": 80.0,
        })


def test_agent_with_star_player_id(seeded):
    """star_player_id verilirse snapshot'a star_feed dahil edilir."""
    agent = LiveDecisionDigestAgent()
    result = agent.run(seeded, context={
        "match_external_id": 9301, "my_team_id": 11,
        "current_minute": 80.0, "star_player_id": 1,
    })
    assert "star_feed" in result.output_json["snapshot_keys"]
