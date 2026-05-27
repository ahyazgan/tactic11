"""PreMatchReportAgent + run_pre_match_reports scheduler job (PR G2)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.agents import PreMatchReportAgent
from app.ai import AnthropicClient, ClaudeCommentator
from app.db import models
from app.scheduler.registry import get
from app.sports import football


@pytest.fixture()
def commentator_stub():
    """ANTHROPIC_API_KEY yokken stub mode'da çalışır."""
    return ClaudeCommentator(AnthropicClient())


def _seed_match_with_history(session, base: datetime):
    rows = [
        # Gala'nın geçmiş 3 maçı
        models.Match(
            sport=football.SPORT_NAME, external_id=10, league_external_id=203,
            season=2024, kickoff=base - timedelta(days=20), status="FT",
            home_team_external_id=611, away_team_external_id=614,
            home_score=2, away_score=1,
        ),
        models.Match(
            sport=football.SPORT_NAME, external_id=11, league_external_id=203,
            season=2024, kickoff=base - timedelta(days=10), status="FT",
            home_team_external_id=998, away_team_external_id=611,
            home_score=0, away_score=2,
        ),
        # Fener'in 1 geçmiş maçı
        models.Match(
            sport=football.SPORT_NAME, external_id=12, league_external_id=203,
            season=2024, kickoff=base - timedelta(days=8), status="FT",
            home_team_external_id=607, away_team_external_id=614,
            home_score=3, away_score=0,
        ),
        # H2H: Gala vs Fener — kickoff'tan önce
        models.Match(
            sport=football.SPORT_NAME, external_id=13, league_external_id=203,
            season=2024, kickoff=base - timedelta(days=30), status="FT",
            home_team_external_id=611, away_team_external_id=607,
            home_score=1, away_score=1,
        ),
        # Asıl maç — NS, 2 gün sonra
        models.Match(
            sport=football.SPORT_NAME, external_id=99, league_external_id=203,
            season=2024, kickoff=base + timedelta(days=2), status="NS",
            home_team_external_id=611, away_team_external_id=607,
            home_score=None, away_score=None,
        ),
    ]
    session.add_all(rows)
    session.flush()


def test_pre_match_agent_runs_and_produces_output(session, commentator_stub):
    _seed_match_with_history(session, datetime.now(UTC))
    agent = PreMatchReportAgent(commentator=commentator_stub)
    result = agent.run(session, context={"match_external_id": 99})

    assert result.subject_type == "match"
    assert result.subject_id == 99
    # Form ve h2h dolu
    assert result.output_json["home_team_external_id"] == 611
    assert result.output_json["away_team_external_id"] == 607
    assert "home_form" in result.output_json
    assert "away_form" in result.output_json
    assert "head_to_head" in result.output_json
    # H2H 1 maç (kickoff öncesi)
    assert result.output_json["head_to_head"]["value"]["matches_played"] == 1
    # AI brief stub (key yok)
    assert "stub" in result.output_json["ai_brief"].lower()
    # Summary kısa metin
    assert "611" in result.summary and "607" in result.summary


def test_pre_match_agent_raises_for_unknown_match(session, commentator_stub):
    agent = PreMatchReportAgent(commentator=commentator_stub)
    with pytest.raises(ValueError, match="bulunamadı"):
        agent.run(session, context={"match_external_id": 9999999})


def test_pre_match_agent_raises_for_missing_context(session, commentator_stub):
    agent = PreMatchReportAgent(commentator=commentator_stub)
    with pytest.raises(ValueError, match="match_external_id"):
        agent.run(session, context={})


def test_pre_match_agent_excludes_post_kickoff_matches(session, commentator_stub):
    """Form/h2h kickoff'tan ÖNCEKİ maçlardan (leakage guard)."""
    base = datetime.now(UTC)
    _seed_match_with_history(session, base)
    # Kickoff'tan SONRA bir maç ekle — form'a girmemeli
    session.add(models.Match(
        sport=football.SPORT_NAME, external_id=100, league_external_id=203,
        season=2024, kickoff=base + timedelta(days=10), status="FT",
        home_team_external_id=611, away_team_external_id=999,
        home_score=5, away_score=0,
    ))
    session.flush()
    agent = PreMatchReportAgent(commentator=commentator_stub)
    result = agent.run(session, context={"match_external_id": 99})
    # Form'da kickoff'tan sonraki maç görünmemeli
    home_match_ids = result.output_json["home_form"]["audit"]["inputs"]["considered_match_ids"]
    assert 100 not in home_match_ids


def test_run_pre_match_reports_job_registered():
    spec = get("run_pre_match_reports")
    assert spec.name == "run_pre_match_reports"
    assert callable(spec.handler)
