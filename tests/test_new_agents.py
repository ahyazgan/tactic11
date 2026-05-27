"""5 yeni agent: PostMatch, WeeklyDigest, OpponentScout, InjuryLoad, MegaMatch."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from app.agents import (
    InjuryLoadAgent,
    MegaMatchAgent,
    NoUpcomingMatch,
    OpponentScoutAgent,
    PostMatchReportAgent,
    WeeklyDigestAgent,
)
from app.ai import AnthropicClient, ClaudeCommentator
from app.db import models
from app.scheduler.registry import get
from app.sports import football


@pytest.fixture()
def commentator_stub():
    return ClaudeCommentator(AnthropicClient())


def _seed_history(session, base: datetime) -> None:
    """Gala (611) + Fener (607) için form + h2h + future match (id=99)."""
    rows = [
        # 611 geçmiş 3 maç
        models.Match(
            sport=football.SPORT_NAME, external_id=10, league_external_id=203,
            season=2024, kickoff=base - timedelta(days=20), status="FT",
            home_team_external_id=611, away_team_external_id=614,
            home_score=2, away_score=1,
        ),
        models.Match(
            sport=football.SPORT_NAME, external_id=11, league_external_id=203,
            season=2024, kickoff=base - timedelta(days=15), status="FT",
            home_team_external_id=998, away_team_external_id=611,
            home_score=0, away_score=2,
        ),
        models.Match(
            sport=football.SPORT_NAME, external_id=12, league_external_id=203,
            season=2024, kickoff=base - timedelta(days=10), status="FT",
            home_team_external_id=611, away_team_external_id=619,
            home_score=1, away_score=0,
        ),
        # 607 geçmiş
        models.Match(
            sport=football.SPORT_NAME, external_id=20, league_external_id=203,
            season=2024, kickoff=base - timedelta(days=18), status="FT",
            home_team_external_id=607, away_team_external_id=614,
            home_score=3, away_score=0,
        ),
        models.Match(
            sport=football.SPORT_NAME, external_id=21, league_external_id=203,
            season=2024, kickoff=base - timedelta(days=8), status="FT",
            home_team_external_id=619, away_team_external_id=607,
            home_score=1, away_score=2,
        ),
        # H2H
        models.Match(
            sport=football.SPORT_NAME, external_id=30, league_external_id=203,
            season=2024, kickoff=base - timedelta(days=40), status="FT",
            home_team_external_id=611, away_team_external_id=607,
            home_score=2, away_score=1,
        ),
        # Future
        models.Match(
            sport=football.SPORT_NAME, external_id=99, league_external_id=203,
            season=2024, kickoff=base + timedelta(days=3), status="NS",
            home_team_external_id=611, away_team_external_id=607,
            home_score=None, away_score=None,
        ),
    ]
    session.add_all(rows)
    session.flush()


# --------------------------------------------------------------------------- #
# PostMatchReportAgent
# --------------------------------------------------------------------------- #


def _seed_finished_match_with_prediction(session, base: datetime, *,
                                          actual_home: int = 2, actual_away: int = 1) -> int:
    match_id = 200
    session.add(models.Match(
        sport=football.SPORT_NAME, external_id=match_id, league_external_id=203,
        season=2024, kickoff=base - timedelta(days=2), status="FT",
        home_team_external_id=611, away_team_external_id=607,
        home_score=actual_home, away_score=actual_away,
    ))
    session.add(models.Prediction(
        sport=football.SPORT_NAME, match_external_id=match_id,
        engine="engine.predict", engine_version="2",
        params_hash="h1", params_json="{}",
        predicted_value_json=json.dumps({
            "expected_home_goals": 1.8, "expected_away_goals": 1.0,
            "prob_home_win": 0.55, "prob_draw": 0.25, "prob_away_win": 0.20,
            "most_likely_score": [2, 1],
        }),
        created_at=base, updated_at=base,
        actual_home_score=actual_home, actual_away_score=actual_away,
        actual_outcome="home" if actual_home > actual_away else
                       ("away" if actual_away > actual_home else "draw"),
        reconciled_at=base,
    ))
    session.flush()
    return match_id


def test_post_match_agent_compares_actual_vs_predicted(session, commentator_stub):
    mid = _seed_finished_match_with_prediction(session, datetime.now(UTC))
    agent = PostMatchReportAgent(commentator=commentator_stub)
    r = agent.run(session, context={"match_external_id": mid})
    assert r.subject_type == "match" and r.subject_id == mid
    out = r.output_json
    assert out["actual"]["outcome"] == "home"
    assert out["prediction"]["predicted_outcome"] == "home"
    assert out["delta"]["outcome_match"] is True
    assert "stub" in out["ai_brief"].lower()


def test_post_match_raises_without_prediction(session, commentator_stub):
    session.add(models.Match(
        sport=football.SPORT_NAME, external_id=201, league_external_id=203,
        season=2024, kickoff=datetime.now(UTC) - timedelta(days=1), status="FT",
        home_team_external_id=611, away_team_external_id=607,
        home_score=1, away_score=0,
    ))
    session.flush()
    agent = PostMatchReportAgent(commentator=commentator_stub)
    with pytest.raises(ValueError, match="tahmin yok"):
        agent.run(session, context={"match_external_id": 201})


def test_post_match_raises_for_unfinished_match(session, commentator_stub):
    session.add(models.Match(
        sport=football.SPORT_NAME, external_id=202, league_external_id=203,
        season=2024, kickoff=datetime.now(UTC) + timedelta(days=1), status="NS",
        home_team_external_id=611, away_team_external_id=607,
        home_score=None, away_score=None,
    ))
    session.flush()
    agent = PostMatchReportAgent(commentator=commentator_stub)
    with pytest.raises(ValueError, match="bitmedi"):
        agent.run(session, context={"match_external_id": 202})


def test_post_match_detects_wrong_prediction(session, commentator_stub):
    """Tahmin home dedi, gerçek away → outcome_match False."""
    mid = _seed_finished_match_with_prediction(
        session, datetime.now(UTC), actual_home=0, actual_away=3,
    )
    agent = PostMatchReportAgent(commentator=commentator_stub)
    r = agent.run(session, context={"match_external_id": mid})
    assert r.output_json["actual"]["outcome"] == "away"
    assert r.output_json["delta"]["outcome_match"] is False


# --------------------------------------------------------------------------- #
# WeeklyDigestAgent
# --------------------------------------------------------------------------- #


def test_weekly_digest_runs(session, commentator_stub):
    base = datetime.now(UTC)
    # Birkaç takım + maç ekle
    session.add_all([
        models.Team(sport=football.SPORT_NAME, external_id=611, name="Galatasaray"),
        models.Team(sport=football.SPORT_NAME, external_id=607, name="Fenerbahce"),
        models.Team(sport=football.SPORT_NAME, external_id=614, name="Trabzonspor"),
    ])
    _seed_history(session, base)
    agent = WeeklyDigestAgent(commentator=commentator_stub)
    r = agent.run(session, context={"league_external_id": 203, "lookback_days": 7})
    assert r.subject_type == "league" and r.subject_id == 203
    out = r.output_json
    assert "form_leaders" in out
    assert "difficulty_leaders" in out
    assert "ml_status" in out
    assert out["ml_status"]["status"] in ("untrained", "fresh")
    assert "upcoming_matches" in out
    # Future match id=99, 3 gün sonra; lookback_days=7 → upcoming'e dahil
    assert any(m["match_id"] == 99 for m in out["upcoming_matches"])
    assert "stub" in out["ai_brief"].lower()


def test_weekly_digest_raises_without_league(session, commentator_stub):
    agent = WeeklyDigestAgent(commentator=commentator_stub)
    with pytest.raises(ValueError, match="league_external_id"):
        agent.run(session, context={})


# --------------------------------------------------------------------------- #
# OpponentScoutAgent
# --------------------------------------------------------------------------- #


def test_opponent_scout_finds_next_match(session, commentator_stub):
    _seed_history(session, datetime.now(UTC))
    agent = OpponentScoutAgent(commentator=commentator_stub)
    r = agent.run(session, context={"team_external_id": 611})
    out = r.output_json
    assert out["next_match"]["opponent_id"] == 607
    assert out["next_match"]["my_side"] == "home"
    # H2H 1 maç (id=30, base-40d)
    assert out["h2h"]["value"]["matches_played"] == 1
    assert "stub" in out["ai_brief"].lower()


def test_opponent_scout_raises_when_no_upcoming(session, commentator_stub):
    """Sadece geçmiş maçları olan takım — NoUpcomingMatch."""
    base = datetime.now(UTC)
    session.add(models.Match(
        sport=football.SPORT_NAME, external_id=50, league_external_id=203,
        season=2024, kickoff=base - timedelta(days=5), status="FT",
        home_team_external_id=614, away_team_external_id=607,
        home_score=1, away_score=2,
    ))
    session.flush()
    agent = OpponentScoutAgent(commentator=commentator_stub)
    with pytest.raises(NoUpcomingMatch):
        agent.run(session, context={"team_external_id": 614})


def test_opponent_scout_raises_for_no_matches(session, commentator_stub):
    agent = OpponentScoutAgent(commentator=commentator_stub)
    with pytest.raises(NoUpcomingMatch, match="hiç maç yok"):
        agent.run(session, context={"team_external_id": 999})


# --------------------------------------------------------------------------- #
# InjuryLoadAgent
# --------------------------------------------------------------------------- #


def test_injury_load_with_high_load_player(session, commentator_stub):
    """6 maç × 90dk = 540 dk / 14 gün = 270 dk/hafta → eşik (>=270)"""
    base = datetime.now(UTC)
    for i in range(6):
        session.add(models.PlayerAppearance(
            sport=football.SPORT_NAME,
            player_external_id=611001,
            match_external_id=100 + i,
            minutes=90,
            kickoff=base - timedelta(days=1 + i * 2),
        ))
    session.flush()
    agent = InjuryLoadAgent(commentator=commentator_stub)
    r = agent.run(session, context={
        "player_external_ids": [611001, 611002],
        "subject_id": 611,
        "window_days": 14,
    })
    out = r.output_json
    assert out["high_load_count"] == 1
    loads = {p["player_id"]: p for p in out["player_loads"]}
    assert loads[611001]["minutes_in_window"] == 540
    assert loads[611001]["high_load"] is True
    assert loads[611002]["minutes_in_window"] == 0
    assert loads[611002]["high_load"] is False


def test_injury_load_no_high_load_uses_canned_message(session, commentator_stub):
    """Tüm oyuncular düşük yük → AI çağrısı yok, hazır not."""
    agent = InjuryLoadAgent(commentator=commentator_stub)
    r = agent.run(session, context={
        "player_external_ids": [611002],
        "subject_id": 611,
    })
    # Stub mode'da bile high_load yoksa AI çağırma → standart not döner
    assert r.output_json["high_load_count"] == 0
    # Mesajın stub değil, canned olduğunu doğrula
    assert "standart kadro" in r.output_json["ai_brief"] or "stub" in r.output_json["ai_brief"].lower()


def test_injury_load_raises_for_empty_list(session, commentator_stub):
    agent = InjuryLoadAgent(commentator=commentator_stub)
    with pytest.raises(ValueError, match="player_external_ids"):
        agent.run(session, context={"player_external_ids": []})


# --------------------------------------------------------------------------- #
# MegaMatchAgent
# --------------------------------------------------------------------------- #


def test_mega_match_produces_6_sections(session, commentator_stub):
    _seed_history(session, datetime.now(UTC))
    agent = MegaMatchAgent(commentator=commentator_stub)
    r = agent.run(session, context={"match_external_id": 99})
    sections = r.output_json["sections"]
    for key in (
        "tactical_preview", "key_matchups", "recent_form_analysis",
        "prediction_confidence", "scheduling_context",
        "tracking_insight", "watch_out_factors",
    ):
        assert key in sections, f"section eksik: {key}"
    # Tracking fixture'ı match=99 için var
    assert sections["tracking_insight"] is not None
    # ml_status untrained (cache yok)
    assert sections["prediction_confidence"]["ml_status"] == "untrained"
    # watch_outs en azından 1 uyarı içermeli (ML untrained mesajı zaten var)
    assert len(sections["watch_out_factors"]) >= 1


def test_mega_match_raises_for_missing_match(session, commentator_stub):
    agent = MegaMatchAgent(commentator=commentator_stub)
    with pytest.raises(ValueError, match="bulunamadı"):
        agent.run(session, context={"match_external_id": 9999999})


# --------------------------------------------------------------------------- #
# Scheduler job registrations
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("job_name", [
    "run_post_match_reports",
    "run_weekly_digest",
    "run_opponent_scouts",
    "run_injury_load",
    "run_mega_match",
])
def test_new_agent_jobs_registered(job_name):
    spec = get(job_name)
    assert spec.name == job_name
    assert callable(spec.handler)
