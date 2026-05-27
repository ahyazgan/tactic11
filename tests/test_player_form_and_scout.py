"""A2 player_form + A4 sub advice + B8 scout + C9 manager perf + C11 media brief."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.agents import (
    MediaBriefAgent,
    ScoutWatchlistDigestAgent,
    SubstitutionAdviceAgent,
)
from app.ai import AnthropicClient, ClaudeCommentator
from app.api.main import app
from app.db import models
from app.db.session import get_session
from app.engine.player_form import compute_player_form
from app.scout import (
    add_to_watchlist,
    list_watchlist,
    remove_from_watchlist,
)
from app.sports import football


@pytest.fixture()
def commentator_stub():
    return ClaudeCommentator(AnthropicClient())


@pytest.fixture()
def client(session):
    def _override():
        yield session

    app.dependency_overrides[get_session] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@dataclass(frozen=True)
class _App:
    sport: str
    player_external_id: int
    match_external_id: int
    minutes: int
    kickoff: datetime


# ===== A2 — engine.player_form =====


def test_player_form_recent_vs_baseline():
    """Son 5 maç 90 dk, baseline 60-80 dk → Z-score > 1 (recent yüksek)."""
    now = datetime.now(UTC)
    # Baseline: 10 maç (60-80 dk varyans), days_ago 60-150
    apps = [
        _App("football", 1, 100 + i, 60 + (i % 3) * 10,
             now - timedelta(days=60 + i * 10))
        for i in range(10)
    ]
    # Recent: 5 maç 90 dk, son 25 günde
    apps += [_App("football", 1, 200 + i, 90, now - timedelta(days=2 + i * 5)) for i in range(5)]
    r = compute_player_form(1, apps, recent_n=5, now=now)
    assert r.value.recent_matches == 5
    assert r.value.recent_minutes_per_match == 90.0
    assert r.value.baseline_matches == 10
    assert r.value.z_score is not None
    assert r.value.z_score > 1.0  # belirgin yüksek


def test_player_form_zero_baseline_stdev_returns_none():
    """Tüm baseline aynı dakikada → stdev=0 → z None (NaN guard)."""
    now = datetime.now(UTC)
    apps = [_App("football", 1, 100 + i, 60, now - timedelta(days=60 + i * 10)) for i in range(5)]
    apps += [_App("football", 1, 200 + i, 90, now - timedelta(days=2 + i * 5)) for i in range(3)]
    r = compute_player_form(1, apps, recent_n=3, now=now)
    assert r.value.z_score is None


def test_player_form_no_appearances_returns_unknown():
    r = compute_player_form(999, [])
    assert r.value.recent_matches == 0
    assert r.value.trend == "unknown"
    assert r.value.z_score is None


def test_player_form_trend_rising():
    """İlk yarı 30dk, son yarı 80dk → rising."""
    now = datetime.now(UTC)
    apps = [
        _App("football", 1, 1, 30, now - timedelta(days=30)),
        _App("football", 1, 2, 30, now - timedelta(days=25)),
        _App("football", 1, 3, 80, now - timedelta(days=15)),
        _App("football", 1, 4, 80, now - timedelta(days=10)),
        _App("football", 1, 5, 80, now - timedelta(days=5)),
    ]
    r = compute_player_form(1, apps, recent_n=5, now=now)
    assert r.value.trend == "rising"


def test_player_form_trend_declining():
    now = datetime.now(UTC)
    apps = [
        _App("football", 1, 1, 90, now - timedelta(days=30)),
        _App("football", 1, 2, 90, now - timedelta(days=25)),
        _App("football", 1, 3, 30, now - timedelta(days=15)),
        _App("football", 1, 4, 30, now - timedelta(days=10)),
        _App("football", 1, 5, 30, now - timedelta(days=5)),
    ]
    r = compute_player_form(1, apps, recent_n=5, now=now)
    assert r.value.trend == "declining"


def test_player_form_endpoint(session, client):
    now = datetime.now(UTC)
    for i in range(6):
        session.add(models.PlayerAppearance(
            sport=football.SPORT_NAME, player_external_id=42,
            match_external_id=100 + i, minutes=80 + (i % 3) * 10,
            kickoff=now - timedelta(days=5 + i * 7),
        ))
    session.flush()
    r = client.get("/players/42/form?recent_n=3")
    assert r.status_code == 200
    body = r.json()
    assert body["value"]["recent_matches"] == 3
    assert "trend" in body["value"]


def test_player_form_endpoint_404_for_unknown(client):
    r = client.get("/players/9999999/form")
    assert r.status_code == 404


# ===== A4 — SubstitutionAdviceAgent v2 (bench impact + minute) =====


def test_sub_advice_includes_bench_impact_and_minute(session, commentator_stub):
    base = datetime.now(UTC)
    session.add(models.Match(
        sport=football.SPORT_NAME, external_id=99, league_external_id=203,
        season=2024, kickoff=base + timedelta(days=1), status="NS",
        home_team_external_id=611, away_team_external_id=607,
        home_score=None, away_score=None,
    ))
    # Bench oyuncularına yakın geçmiş appearance ekle
    for pid in (611010, 611011):
        for i in range(3):
            session.add(models.PlayerAppearance(
                sport=football.SPORT_NAME, player_external_id=pid,
                match_external_id=200 + i, minutes=60,
                kickoff=base - timedelta(days=10 + i * 7),
            ))
    # On-pitch oyuncuları load için
    for pid in (611001, 611002, 611003):
        session.add(models.PlayerAppearance(
            sport=football.SPORT_NAME, player_external_id=pid,
            match_external_id=300, minutes=90,
            kickoff=base - timedelta(days=1),
        ))
    session.flush()
    agent = SubstitutionAdviceAgent(commentator=commentator_stub)
    r = agent.run(session, context={
        "match_external_id": 99, "team_external_id": 611,
        "minute": 65, "current_home_score": 0, "current_away_score": 1,
        "on_pitch_player_ids": [611001, 611002, 611003],
        "bench_player_ids": [611010, 611011],
    })
    out = r.output_json
    assert "bench_impact" in out
    # Her bench player için tier dolu
    assert "611010" in out["bench_impact"]
    assert out["bench_impact"]["611010"]["tier"] in ("regular", "squad", "fringe")
    # Proposed subs'ta suggested_minute var
    assert len(out["proposed_subs"]) >= 1
    assert "suggested_minute" in out["proposed_subs"][0]
    assert "in_tier" in out["proposed_subs"][0]


# ===== B8 — scout watchlist =====


def test_add_to_watchlist_idempotent(session):
    e1 = add_to_watchlist(session, player_external_id=42, notes="watch")
    e2 = add_to_watchlist(session, player_external_id=42, notes="updated")
    session.commit()
    assert e1.id == e2.id  # aynı satır
    entries = list_watchlist(session)
    assert len(entries) == 1
    assert entries[0].notes == "updated"


def test_remove_from_watchlist(session):
    add_to_watchlist(session, player_external_id=42)
    session.commit()
    assert remove_from_watchlist(session, player_external_id=42) is True
    assert remove_from_watchlist(session, player_external_id=42) is False
    assert list_watchlist(session) == []


def test_watchlist_endpoint_crud(client):
    # Add
    r = client.post("/admin/scout/watchlist", json={"player_external_id": 42, "notes": "izle"})
    assert r.status_code == 200
    # List
    r = client.get("/admin/scout/watchlist")
    assert r.status_code == 200
    assert r.json()["count"] == 1
    # Delete
    r = client.delete("/admin/scout/watchlist/42")
    assert r.status_code == 200
    assert r.json()["deleted"] is True


def test_scout_watchlist_digest_agent(session, commentator_stub):
    add_to_watchlist(session, player_external_id=42)
    session.commit()
    agent = ScoutWatchlistDigestAgent(commentator=commentator_stub)
    r = agent.run(session, context={})
    assert r.output_json["player_count"] == 1
    assert "snapshots" in r.output_json
    assert "alerts" in r.output_json


def test_scout_digest_empty_watchlist(session, commentator_stub):
    agent = ScoutWatchlistDigestAgent(commentator=commentator_stub)
    r = agent.run(session, context={})
    assert r.output_json["player_count"] == 0
    assert "boş" in r.output_json["ai_brief"].lower()


# ===== C9 — manager performance =====


def test_manager_performance_endpoint_empty(client):
    r = client.get("/admin/manager-performance?team_external_id=611&days=90")
    assert r.status_code == 200
    body = r.json()
    assert body["matches_considered"] == 0
    assert body["xpts"] == 0.0


def test_manager_performance_calculates_xpts(session, client):
    now = datetime.now(UTC)
    # 611 vs 999: ev (611) sahibi 2-1 kazandı; tahmin home %50/draw %25/away %25
    # xpts = 0.5*3 + 0.25*1 = 1.75; actual = 3; delta = +1.25
    session.add(models.Match(
        sport=football.SPORT_NAME, external_id=500, league_external_id=203,
        season=2024, kickoff=now - timedelta(days=5), status="FT",
        home_team_external_id=611, away_team_external_id=999,
        home_score=2, away_score=1,
    ))
    session.add(models.Prediction(
        sport=football.SPORT_NAME, match_external_id=500,
        engine="engine.predict", engine_version="2",
        params_hash="h", params_json="{}",
        predicted_value_json=json.dumps({
            "prob_home_win": 0.5, "prob_draw": 0.25, "prob_away_win": 0.25,
        }),
        created_at=now - timedelta(days=10), updated_at=now - timedelta(days=10),
        actual_outcome="home", actual_home_score=2, actual_away_score=1,
        reconciled_at=now - timedelta(days=4),
    ))
    session.commit()
    r = client.get("/admin/manager-performance?team_external_id=611&days=90")
    assert r.status_code == 200
    body = r.json()
    assert body["matches_considered"] == 1
    assert body["actual_points"] == 3
    assert abs(body["xpts"] - 1.75) < 0.001
    assert body["overperformance"] > 1.0  # outperformer


# ===== C11 — MediaBriefAgent =====


def test_media_brief_basic_finished_match(session, commentator_stub):
    now = datetime.now(UTC)
    session.add(models.Match(
        sport=football.SPORT_NAME, external_id=600, league_external_id=203,
        season=2024, kickoff=now - timedelta(days=1), status="FT",
        home_team_external_id=611, away_team_external_id=607,
        home_score=2, away_score=1,
    ))
    session.flush()
    agent = MediaBriefAgent(commentator=commentator_stub)
    r = agent.run(session, context={"match_external_id": 600})
    assert r.subject_type == "match" and r.subject_id == 600
    out = r.output_json
    assert out["outcome"] == "ev_galip"
    assert out["score"] == "2-1"
    assert "press_release_paragraphs" in out
    assert "tweet_drafts" in out
    assert "key_moments" in out


def test_media_brief_raises_for_unfinished(session, commentator_stub):
    now = datetime.now(UTC)
    session.add(models.Match(
        sport=football.SPORT_NAME, external_id=601, league_external_id=203,
        season=2024, kickoff=now + timedelta(days=1), status="NS",
        home_team_external_id=611, away_team_external_id=607,
        home_score=None, away_score=None,
    ))
    session.flush()
    agent = MediaBriefAgent(commentator=commentator_stub)
    with pytest.raises(ValueError, match="bitmedi"):
        agent.run(session, context={"match_external_id": 601})


def test_media_brief_invalid_tone(session, commentator_stub):
    agent = MediaBriefAgent(commentator=commentator_stub)
    with pytest.raises(ValueError, match="tone"):
        agent.run(session, context={"match_external_id": 1, "tone": "biased"})
