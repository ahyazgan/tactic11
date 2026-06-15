"""Faz 6 live-decision endpoint tests."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.db import models
from app.db.session import get_session
from app.sports import football


@pytest.fixture()
def client(session):
    session.info["tenant_id"] = "t-default"

    def _override():
        yield session
    app.dependency_overrides[get_session] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _seed_match_events(session, match_id: int = 9300):
    now = datetime.now(UTC)
    session.add(models.Tenant(
        id="t-default", slug="t-default", name="X",
        settings_json="{}", active=True, created_at=now,
    ))
    session.add(models.Match(
        sport=football.SPORT_NAME, external_id=match_id,
        league_external_id=203, season=2024,
        kickoff=now - timedelta(days=1), status="FT",
        home_team_external_id=11, away_team_external_id=22,
        home_score=1, away_score=2, tenant_id="t-default",
    ))
    for i in range(30):
        session.add(models.EventRow(
            sport=football.SPORT_NAME, tenant_id="t-default",
            source="statsbomb_open", source_event_id=f"p{i}",
            match_external_id=match_id, team_external_id=11,
            player_external_id=1, event_type="pass",
            minute=float(i * 2), period=1 if i * 2 < 45 else 2,
            start_x=50.0, start_y=50.0, end_x=70.0, end_y=50.0,
            outcome="completed", body_part=None, pattern="regular",
            possession_id=i, is_goal=None, key_pass=False,
            raw_json=None, created_at=now,
        ))
    session.commit()


def test_live_decision_404(session, client):
    session.add(models.Tenant(
        id="t-default", slug="t-default", name="X",
        settings_json="{}", active=True, created_at=datetime.now(UTC),
    ))
    session.commit()
    r = client.get("/admin/matches/99999/live-decision?my_team_id=11&current_minute=60")
    assert r.status_code == 404


def test_live_decision_no_events(session, client):
    session.add(models.Tenant(
        id="t-default", slug="t-default", name="X",
        settings_json="{}", active=True, created_at=datetime.now(UTC),
    ))
    session.add(models.Match(
        sport=football.SPORT_NAME, external_id=9300,
        league_external_id=203, season=2024,
        kickoff=datetime.now(UTC) - timedelta(days=1), status="FT",
        home_team_external_id=11, away_team_external_id=22,
        home_score=1, away_score=2, tenant_id="t-default",
    ))
    session.commit()
    r = client.get("/admin/matches/9300/live-decision?my_team_id=11&current_minute=60")
    assert r.status_code == 200
    assert r.json()["events_loaded"] == 0


def test_live_decision_full_panel(session, client):
    _seed_match_events(session)
    r = client.get("/admin/matches/9300/live-decision?my_team_id=11&current_minute=70")
    assert r.status_code == 200
    body = r.json()
    assert "momentum" in body
    assert "sub_timing" in body
    assert "tactical_triggers" in body
    assert "risk_monitor" in body


def test_opponent_reaction_endpoint(session, client):
    _seed_match_events(session)
    r = client.post(
        "/admin/matches/9300/opponent-reaction?my_team_id=11&current_minute=70&momentum_score=-0.5",
        json={"opponent_subs": [{"position_in": "F", "minute": 65}]},
    )
    assert r.status_code == 200
    v = r.json()["value"]
    assert v["opp_subs_detected"] == 1
    assert v["momentum_break_advice"] is not None


def test_live_risk_endpoint(session, client):
    _seed_match_events(session)
    r = client.post(
        "/admin/matches/9300/live-risk?my_team_id=11&current_minute=80",
        json={"player_states": [
            {"player_id": 100, "yellow_card": True, "duel_count": 5},
            {"player_id": 200, "fatigue": 0.85},
        ]},
    )
    assert r.status_code == 200
    v = r.json()["value"]
    assert len(v["card_flags"]) == 1
    assert len(v["injury_flags"]) == 1
    # Geride (1-2) + 80. dk → tempoyu artır
    assert "tempoyu artır" in v["time_management"]


def test_live_risk_404(session, client):
    session.add(models.Tenant(
        id="t-default", slug="t-default", name="X",
        settings_json="{}", active=True, created_at=datetime.now(UTC),
    ))
    session.commit()
    r = client.post(
        "/admin/matches/99999/live-risk?my_team_id=11&current_minute=80",
        json={"player_states": []},
    )
    assert r.status_code == 404


def test_closing_strategy_endpoint(session, client):
    """Geride 1-2, 80. dk → tempo=agresif + risk=true."""
    _seed_match_events(session)
    r = client.get(
        "/admin/matches/9300/closing-strategy"
        "?my_team_id=11&current_minute=80",
    )
    assert r.status_code == 200
    v = r.json()["value"]
    assert v["score_state"] == "trailing"  # 1-2 → trailing
    assert v["closing_phase"] == "late"
    assert v["recipe"]["tempo"] == "agresif"
    assert v["risk_reward"]["take_risk"] is True


def test_closing_strategy_in_live_decision_panel(session, client):
    """live-decision birleşik panelinde closing_strategy var."""
    _seed_match_events(session)
    r = client.get(
        "/admin/matches/9300/live-decision"
        "?my_team_id=11&current_minute=80",
    )
    assert r.status_code == 200
    body = r.json()
    assert "closing_strategy" in body
    cs = body["closing_strategy"]
    assert "recipe" in cs
    assert "risk_reward" in cs


def test_closing_strategy_404(session, client):
    session.add(models.Tenant(
        id="t-default", slug="t-default", name="X",
        settings_json="{}", active=True, created_at=datetime.now(UTC),
    ))
    session.commit()
    r = client.get(
        "/admin/matches/99999/closing-strategy"
        "?my_team_id=11&current_minute=80",
    )
    assert r.status_code == 404


def test_foul_pressure_endpoint(session, client):
    """Rakip ritim kırma + sarılı oyuncu → iki sinyal birden."""
    _seed_match_events(session)
    r = client.post(
        "/admin/matches/9300/foul-pressure"
        "?my_team_id=11&current_minute=75&total_yellows_match=7",
        json={
            "foul_events": [
                {"team_id": 22, "minute": 62.0},
                {"team_id": 22, "minute": 64.0},
                {"team_id": 22, "minute": 67.0},
                {"team_id": 22, "minute": 70.0},
                {"team_id": 22, "minute": 73.0},
                {"team_id": 11, "minute": 60.0, "player_id": 99},
                {"team_id": 11, "minute": 65.0, "player_id": 99},
                {"team_id": 11, "minute": 70.0, "player_id": 99},
            ],
            "player_yellow_cards": {"99": 1},
        },
    )
    assert r.status_code == 200
    v = r.json()["value"]
    assert v["tactical_fouling_alert"] is True
    assert v["referee_card_pressure"] == "high"
    assert len(v["player_flags"]) == 1
    assert v["player_flags"][0]["risk_level"] == "critical"


def test_foul_pressure_404(session, client):
    session.add(models.Tenant(
        id="t-default", slug="t-default", name="X",
        settings_json="{}", active=True, created_at=datetime.now(UTC),
    ))
    session.commit()
    r = client.post(
        "/admin/matches/99999/foul-pressure"
        "?my_team_id=11&current_minute=75",
        json={"foul_events": []},
    )
    assert r.status_code == 404


def test_foul_pressure_empty_payload(session, client):
    """Payload yok + ingest edilmiş faul yok → normal advice + 0 faul."""
    _seed_match_events(session)
    r = client.post(
        "/admin/matches/9300/foul-pressure?my_team_id=11&current_minute=70",
    )
    assert r.status_code == 200
    v = r.json()["value"]
    assert v["our_fouls_total"] == 0
    assert v["opp_fouls_total"] == 0
    assert "normal" in v["tactical_advice"].lower()


def test_foul_pressure_reads_ingested_fouls(session, client):
    """Payload boş ama DB'de foul EventRow var → engine onları okur."""
    _seed_match_events(session)
    # 5 rakip faul + 1 sarı bizden
    from datetime import UTC, datetime
    now = datetime.now(UTC)
    for i in range(5):
        session.add(models.EventRow(
            sport=football.SPORT_NAME, tenant_id="t-default",
            source="statsbomb_open", source_event_id=f"foul-opp-{i}",
            match_external_id=9300, team_external_id=22,
            player_external_id=100 + i, event_type="foul",
            minute=float(62 + i), period=2,
            start_x=60.0, start_y=40.0, end_x=None, end_y=None,
            outcome="foul", body_part=None, pattern=None,
            possession_id=None, is_goal=None, key_pass=None,
            raw_json=None, created_at=now,
        ))
    session.add(models.EventRow(
        sport=football.SPORT_NAME, tenant_id="t-default",
        source="statsbomb_open", source_event_id="foul-our-1",
        match_external_id=9300, team_external_id=11,
        player_external_id=200, event_type="foul",
        minute=60.0, period=2,
        start_x=60.0, start_y=40.0, end_x=None, end_y=None,
        outcome="yellow", body_part=None, pattern=None,
        possession_id=None, is_goal=None, key_pass=None,
        raw_json=None, created_at=now,
    ))
    session.commit()
    r = client.post(
        "/admin/matches/9300/foul-pressure?my_team_id=11&current_minute=75",
    )
    assert r.status_code == 200
    v = r.json()["value"]
    assert v["opp_fouls_total"] == 5
    assert v["our_fouls_total"] == 1
    assert v["tactical_fouling_alert"] is True
    # 1 sarı maçta → low (eşik moderate=4)
    assert v["referee_card_pressure"] == "low"


def test_hot_hand_endpoint(session, client):
    """live-decision panele otomatik dahil + standalone çağrılabilir."""
    _seed_match_events(session)
    r = client.get(
        "/admin/matches/9300/hot-hand?my_team_id=11&current_minute=70",
    )
    assert r.status_code == 200
    v = r.json()["value"]
    assert "hot_streak" in v
    assert "shots_window" in v


def test_hot_hand_404(session, client):
    session.add(models.Tenant(
        id="t-default", slug="t-default", name="X",
        settings_json="{}", active=True, created_at=datetime.now(UTC),
    ))
    session.commit()
    r = client.get("/admin/matches/99999/hot-hand?my_team_id=11&current_minute=70")
    assert r.status_code == 404


def test_set_piece_opportunity_endpoint(session, client):
    _seed_match_events(session)
    r = client.get(
        "/admin/matches/9300/set-piece-opportunity"
        "?my_team_id=11&current_minute=70",
    )
    assert r.status_code == 200
    v = r.json()["value"]
    assert "total_set_pieces" in v
    assert "tactical_advice" in v


def test_congestion_risk_endpoint(client):
    from datetime import datetime as _dt, timedelta as _td
    base = _dt.utcnow() + _td(days=1)
    r = client.post(
        "/admin/teams/11/congestion-risk",
        json={
            "window_days": 14,
            "fixtures": [
                {"kickoff": (base + _td(days=0)).isoformat(),
                 "competition": "league", "travel_km": 100},
                {"kickoff": (base + _td(days=3)).isoformat(),
                 "competition": "cup", "travel_km": 200},
                {"kickoff": (base + _td(days=6)).isoformat(),
                 "competition": "league", "travel_km": 150},
            ],
        },
    )
    assert r.status_code == 200
    v = r.json()["value"]
    assert v["fixtures_count"] == 3
    assert v["phase"] in ("low", "moderate", "high", "critical")


def test_minutes_management_endpoint(client):
    r = client.post(
        "/admin/teams/11/minutes-management",
        json={
            "matches_next_2_weeks": 4,
            "players": [
                {"player_external_id": 7, "age": 28,
                 "weekly_minutes_recent": [90, 90, 85, 90]},
                {"player_external_id": 14, "age": 33,
                 "weekly_minutes_recent": [60, 60, 60, 60]},
            ],
        },
    )
    assert r.status_code == 200
    v = r.json()["value"]
    assert v["marathon_window"] is True
    assert v["total_players"] == 2
    # Yüksek yüklü 28 yaş + maraton → rest_advised
    assert v["rest_count"] >= 1


def test_return_to_play_endpoint(client):
    r = client.post(
        "/admin/players/7/return-to-play",
        json={"tests": [
            {"test_name": "cmj", "current": 38.0, "pre_injury_baseline": 40.0},
            {"test_name": "sprint10", "current": 1.78,
             "pre_injury_baseline": 1.75, "higher_is_better": False},
            {"test_name": "y_balance", "current": 70.0,
             "pre_injury_baseline": 100.0, "weight": 1.5},
        ]},
    )
    assert r.status_code == 200
    v = r.json()["value"]
    assert v["phase"] in (1, 2, 3, 4, 5)
    assert "advice" in v
    assert v["test_count"] == 3


def test_referee_tendency_endpoint(client):
    r = client.post(
        "/admin/referee/tendency",
        json={
            "referee_id": "r-001", "referee_name": "Cüneyt Çakır",
            "prior_matches": [
                {"yellows_total": 7, "reds_total": 0, "fouls_total": 28}
                for _ in range(6)
            ],
        },
    )
    assert r.status_code == 200
    v = r.json()["value"]
    assert v["severity"] == "strict"


def test_live_digest_endpoint_stub(session, client):
    """No ANTHROPIC_API_KEY → stub brief; AgentResult valid alanlar."""
    _seed_match_events(session)
    r = client.get(
        "/admin/matches/9300/live-digest?my_team_id=11&current_minute=80",
    )
    assert r.status_code == 200
    body = r.json()
    assert "summary" in body
    assert body["output"]["match_external_id"] == 9300
    assert body["output"]["current_minute"] == 80.0
    assert body["output"]["ai_brief"].startswith("[stub:live_digest]")


def test_live_digest_endpoint_404(session, client):
    session.add(models.Tenant(
        id="t-default", slug="t-default", name="X",
        settings_json="{}", active=True, created_at=datetime.now(UTC),
    ))
    session.commit()
    r = client.get(
        "/admin/matches/99999/live-digest?my_team_id=11&current_minute=70",
    )
    assert r.status_code == 404


def test_clip_for_decision_stub(session, client):
    """CLIP_BASE_URL set değil → stub, available=False."""
    r = client.get(
        "/admin/matches/9300/clip?minute=70&decision_type=substitution",
    )
    assert r.status_code == 200
    v = r.json()["value"]
    assert v["available"] is False
    assert v["video_url"] is None
    assert v["clip_id"].startswith("clip-9300-")
    assert v["duration_seconds"] == 25  # 20 back + 5 forward (substitution)


def test_clip_for_decision_with_env(session, client, monkeypatch):
    """CLIP_BASE_URL set → gerçek URL üretilir."""
    monkeypatch.setenv("CLIP_BASE_URL", "https://video.example.com/clips")
    r = client.get(
        "/admin/matches/9300/clip"
        "?minute=70&decision_type=substitution&tenant_id=t-bjk",
    )
    assert r.status_code == 200
    v = r.json()["value"]
    assert v["available"] is True
    assert "t-bjk" in v["video_url"]
    assert v["source"] == "broadcast"


def test_decisions_recent_cache_hit_miss(session, client):
    """1. çağrı miss, 2. çağrı aynı tenant+team+limit için hit (30sn TTL)."""
    from datetime import UTC, datetime, timedelta
    now = datetime.now(UTC)
    session.add(models.Tenant(
        id="t-default", slug="t-default", name="X",
        settings_json="{}", active=True, created_at=now,
    ))
    session.add(models.Decision(
        sport=football.SPORT_NAME, tenant_id="t-default",
        match_external_id=100, team_external_id=11,
        minute=70.0, period=2, decision_type="substitution",
        outcome="positive", created_at=now - timedelta(minutes=1),
    ))
    session.commit()

    r1 = client.get("/admin/decisions/recent?limit=20")
    assert r1.status_code == 200
    assert r1.json()["_cache"] == "miss"

    r2 = client.get("/admin/decisions/recent?limit=20")
    assert r2.status_code == 200
    assert r2.json()["_cache"] == "hit"
    # Cache body summary aynı
    assert r1.json()["summary"]["total"] == r2.json()["summary"]["total"]


def test_decisions_recent_cache_key_varies_by_filter(session, client):
    """team_external_id filter farklıysa cache miss (ayrı key)."""
    from datetime import UTC, datetime, timedelta
    now = datetime.now(UTC)
    session.add(models.Tenant(
        id="t-default", slug="t-default", name="X",
        settings_json="{}", active=True, created_at=now,
    ))
    session.add(models.Decision(
        sport=football.SPORT_NAME, tenant_id="t-default",
        match_external_id=200, team_external_id=11,
        minute=70.0, period=2, decision_type="substitution",
        outcome="pending", created_at=now - timedelta(minutes=1),
    ))
    session.commit()
    a = client.get("/admin/decisions/recent?team_external_id=11&limit=20")
    b = client.get("/admin/decisions/recent?team_external_id=22&limit=20")
    assert a.json()["_cache"] == "miss"
    assert b.json()["_cache"] == "miss"  # farklı team → farklı key


def test_matches_with_events_cache_hit_miss(session, client):
    """matches-with-events de cache'leniyor (60sn TTL)."""
    _seed_match_events(session)
    r1 = client.get("/admin/matches/with-events?limit=10")
    assert r1.status_code == 200
    assert r1.json()["_cache"] == "miss"
    r2 = client.get("/admin/matches/with-events?limit=10")
    assert r2.json()["_cache"] == "hit"


def test_decisions_recent_summary_and_list(session, client):
    """3 karar: 2 pozitif + 1 negatif → hit_rate=0.667, summary doğru."""
    from datetime import UTC, datetime, timedelta
    now = datetime.now(UTC)
    session.add(models.Tenant(
        id="t-default", slug="t-default", name="X",
        settings_json="{}", active=True, created_at=now,
    ))
    session.commit()
    for i, outcome in enumerate(["positive", "positive", "negative"]):
        session.add(models.Decision(
            sport=football.SPORT_NAME, tenant_id="t-default",
            match_external_id=100 + i, team_external_id=11,
            minute=60.0 + i * 5, period=2,
            decision_type="substitution",
            recommended=True, confidence=0.75,
            outcome=outcome,
            created_at=now - timedelta(minutes=i),
        ))
    session.commit()
    r = client.get("/admin/decisions/recent?limit=20")
    assert r.status_code == 200
    body = r.json()
    s = body["summary"]
    assert s["total"] == 3
    assert s["positive"] == 2
    assert s["negative"] == 1
    assert s["pending"] == 0
    assert s["hit_rate"] == 0.667
    assert "substitution" in s["by_decision_type"]
    assert len(body["decisions"]) == 3
    # En yeni önce (created_at desc) → i=0 (en eski) son sırada
    assert body["decisions"][0]["match_id"] == 100  # newest = i=0


def test_decisions_recent_filter_by_team(session, client):
    from datetime import UTC, datetime
    now = datetime.now(UTC)
    session.add(models.Tenant(
        id="t-default", slug="t-default", name="X",
        settings_json="{}", active=True, created_at=now,
    ))
    session.commit()
    for tid in (11, 11, 22):
        session.add(models.Decision(
            sport=football.SPORT_NAME, tenant_id="t-default",
            match_external_id=200, team_external_id=tid,
            minute=70.0, period=2, decision_type="formation_change",
            outcome="pending", created_at=now,
        ))
    session.commit()
    r = client.get("/admin/decisions/recent?team_external_id=11")
    assert r.status_code == 200
    body = r.json()
    assert body["summary"]["total"] == 2
    assert all(d["team_id"] == 11 for d in body["decisions"])


def test_decisions_recent_empty(session, client):
    session.add(models.Tenant(
        id="t-default", slug="t-default", name="X",
        settings_json="{}", active=True, created_at=datetime.now(UTC),
    ))
    session.commit()
    r = client.get("/admin/decisions/recent")
    assert r.status_code == 200
    body = r.json()
    assert body["summary"]["total"] == 0
    assert body["summary"]["hit_rate"] is None
    assert body["decisions"] == []


def test_matches_with_events_lists_ingested_only(session, client):
    """Sadece event'i olan maçlar listelenir; boş maç dışlanır."""
    _seed_match_events(session)
    # Bir tane daha maç ekle — event'siz
    from datetime import UTC, datetime, timedelta
    now = datetime.now(UTC)
    session.add(models.Match(
        sport=football.SPORT_NAME, external_id=9999,
        league_external_id=203, season=2024,
        kickoff=now - timedelta(days=2), status="FT",
        home_team_external_id=33, away_team_external_id=44,
        home_score=0, away_score=0, tenant_id="t-default",
    ))
    session.commit()
    r = client.get("/admin/matches/with-events")
    assert r.status_code == 200
    body = r.json()
    ids = [m["match_id"] for m in body["matches"]]
    assert 9300 in ids       # event'li
    assert 9999 not in ids   # event'siz
    m = next(x for x in body["matches"] if x["match_id"] == 9300)
    assert m["event_count"] == 30
    assert m["home_team_external_id"] == 11
    assert m["away_team_external_id"] == 22


def test_matches_with_events_empty_when_no_events(session, client):
    session.add(models.Tenant(
        id="t-default", slug="t-default", name="X",
        settings_json="{}", active=True, created_at=datetime.now(UTC),
    ))
    session.commit()
    r = client.get("/admin/matches/with-events")
    assert r.status_code == 200
    assert r.json() == {"matches": [], "total": 0}


def test_live_decision_panel_includes_foul_pressure_when_ingested(session, client):
    """Live decision panel ingest'lenmiş foul'ları otomatik içerir."""
    _seed_match_events(session)
    # 5 rakip foul ekle
    from datetime import UTC, datetime
    now = datetime.now(UTC)
    for i in range(5):
        session.add(models.EventRow(
            sport=football.SPORT_NAME, tenant_id="t-default",
            source="statsbomb_open", source_event_id=f"foul-{i}",
            match_external_id=9300, team_external_id=22,
            player_external_id=100, event_type="foul",
            minute=float(62 + i), period=2,
            start_x=60.0, start_y=40.0, end_x=None, end_y=None,
            outcome="foul", body_part=None, pattern=None,
            possession_id=None, is_goal=None, key_pass=None,
            raw_json=None, created_at=now,
        ))
    session.commit()
    r = client.get(
        "/admin/matches/9300/live-decision"
        "?my_team_id=11&current_minute=75",
    )
    assert r.status_code == 200
    body = r.json()
    assert "foul_pressure" in body
    assert body["foul_pressure"]["opp_fouls_total"] == 5


def test_star_feed_endpoint(session, client):
    """Seed match'te tek oyuncu (id=1) tüm pasları atıyor → well-fed."""
    _seed_match_events(session)
    r = client.get(
        "/admin/matches/9300/star-feed"
        "?my_team_id=11&star_player_id=1&current_minute=70&window_min=15",
    )
    assert r.status_code == 200
    v = r.json()["value"]
    # Seed'te tüm paslar player_id=1 → yıldız = %100
    assert v["pass_share_pct"] == 100.0
    assert v["involvement_state"] == "well-fed"


def test_star_feed_starved_when_other_player(session, client):
    """Yıldız = farklı oyuncu → starved."""
    _seed_match_events(session)
    r = client.get(
        "/admin/matches/9300/star-feed"
        "?my_team_id=11&star_player_id=999&current_minute=70&window_min=15",
    )
    assert r.status_code == 200
    v = r.json()["value"]
    assert v["involvement_state"] == "starved"
    assert "HİÇ pas" in v["tactical_advice"]


def test_star_feed_404(session, client):
    session.add(models.Tenant(
        id="t-default", slug="t-default", name="X",
        settings_json="{}", active=True, created_at=datetime.now(UTC),
    ))
    session.commit()
    r = client.get(
        "/admin/matches/99999/star-feed"
        "?my_team_id=11&star_player_id=1&current_minute=70",
    )
    assert r.status_code == 404
