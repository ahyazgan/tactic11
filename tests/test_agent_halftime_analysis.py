"""HalftimeAnalysisAgent tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.agents import HalftimeAnalysisAgent
from app.ai import AnthropicClient, ClaudeCommentator
from app.db import models
from app.sports import football


@pytest.fixture()
def agent():
    return HalftimeAnalysisAgent(
        commentator=ClaudeCommentator(AnthropicClient(api_key=None)),
    )


def _seed(session):
    now = datetime.now(UTC)
    session.add(models.Tenant(
        id="t-default", slug="t-default", name="X",
        settings_json="{}", active=True, created_at=now,
    ))
    session.add(models.Match(
        sport=football.SPORT_NAME, external_id=1001,
        league_external_id=203, season=2024,
        kickoff=now - timedelta(days=1), status="FT",
        home_team_external_id=11, away_team_external_id=22,
        home_score=1, away_score=0, tenant_id="t-default",
    ))
    session.flush()


def _add_event(session, *, match_id: int, ev_type: str, team: int,
               player: int = 1, sb_id: str = "e1", minute: float = 10.0,
               start_x: float = 50.0, end_x: float = 70.0, end_y: float = 50.0,
               outcome: str = "completed", is_goal: bool = False,
               pattern: str = "regular", poss: int | None = None):
    session.add(models.EventRow(
        sport=football.SPORT_NAME, tenant_id="t-default",
        source="statsbomb_open", source_event_id=sb_id,
        match_external_id=match_id, team_external_id=team,
        player_external_id=player, event_type=ev_type,
        minute=minute, period=1,
        start_x=start_x, start_y=50.0, end_x=end_x, end_y=end_y,
        outcome=outcome if ev_type != "shot" else ("goal" if is_goal else None),
        body_part="right_foot" if ev_type == "shot" else None,
        pattern=pattern, possession_id=poss,
        is_goal=is_goal if ev_type == "shot" else None,
        key_pass=False, raw_json=None,
        created_at=datetime.now(UTC),
    ))


def test_no_events_returns_empty_brief(session, agent):
    _seed(session)
    session.commit()
    result = agent.run(
        session, context={"match_external_id": 1001, "my_team_external_id": 11},
    )
    assert result.output_json["events_loaded"] == 0
    assert "stub:halftime" in result.output_json["ai_brief"]


def test_full_halftime_report(session, agent):
    _seed(session)
    # 1. yarı içinde 40 pas (20 erken + 20 geç), 10 defansif, 3 şut
    for i in range(20):
        _add_event(session, match_id=1001, ev_type="pass", team=11,
                   sb_id=f"early_p{i}", minute=float(5 + i),
                   end_x=80, end_y=15)  # sol kanal
    for i in range(20):
        _add_event(session, match_id=1001, ev_type="pass", team=11,
                   sb_id=f"late_p{i}", minute=float(30 + i // 2),
                   end_x=80, end_y=15)
    for i in range(10):
        _add_event(session, match_id=1001, ev_type="defensive_action",
                   team=11, sb_id=f"d{i}", minute=float(10 + i),
                   pattern="tackle", outcome="successful")
    for i in range(3):
        _add_event(session, match_id=1001, ev_type="shot", team=11,
                   sb_id=f"s{i}", minute=float(20 + i * 5),
                   start_x=90, pattern="open_play", is_goal=(i == 0))
    # 2. yarı event'leri (filtre etmeli)
    for i in range(50):
        _add_event(session, match_id=1001, ev_type="pass", team=11,
                   sb_id=f"2h_p{i}", minute=float(50 + i // 5))
    session.commit()

    result = agent.run(
        session, context={"match_external_id": 1001, "my_team_external_id": 11},
    )
    out = result.output_json
    assert out["events_loaded"] > 0
    # 2. yarı pasları filtre edilmeli
    assert out["first_half_event_counts"]["passes"] == 40
    assert out["first_half_event_counts"]["shots"] == 3
    assert out["my_team_external_id"] == 11
    assert out["opponent_team_external_id"] == 22
    assert out["my_side"] == "home"
    assert "stats" in out
    assert "opponent_weakness" in out
    assert out["opponent_weakness"]["most_vulnerable_channel"] in ("left", "central", "right")


def test_invalid_team_raises(session, agent):
    _seed(session)
    session.commit()
    with pytest.raises(ValueError, match="bu maçta yok"):
        agent.run(session, context={
            "match_external_id": 1001, "my_team_external_id": 999,
        })


def test_missing_context_raises(session, agent):
    _seed(session)
    session.commit()
    with pytest.raises(ValueError, match="zorunlu"):
        agent.run(session, context={"match_external_id": 1001})


def test_missing_match_raises(session, agent):
    _seed(session)
    session.commit()
    with pytest.raises(ValueError, match="bulunamadı"):
        agent.run(session, context={
            "match_external_id": 9999, "my_team_external_id": 11,
        })


def test_fatigue_alerts_surfaced(session, agent):
    """Erken aktif, geç pasif oyuncu fatigue_alerts'e girer."""
    _seed(session)
    # Player 100: erken 15 pas (hep tamamlandı), geç 2 pas
    for i in range(15):
        _add_event(session, match_id=1001, ev_type="pass", team=11,
                   player=100, sb_id=f"p100_e{i}", minute=float(5 + i),
                   outcome="completed")
    for i in range(2):
        _add_event(session, match_id=1001, ev_type="pass", team=11,
                   player=100, sb_id=f"p100_l{i}", minute=float(40 + i),
                   outcome="incomplete")
    session.commit()

    result = agent.run(
        session, context={"match_external_id": 1001, "my_team_external_id": 11},
    )
    alerts = result.output_json["fatigue_alerts"]
    assert any(a["player_id"] == 100 for a in alerts)


def test_summary_includes_key_signals(session, agent):
    _seed(session)
    for i in range(15):
        _add_event(session, match_id=1001, ev_type="pass", team=11,
                   sb_id=f"p{i}", minute=float(10 + i))
    session.commit()
    result = agent.run(
        session, context={"match_external_id": 1001, "my_team_external_id": 11},
    )
    assert "halftime brief" in result.summary
