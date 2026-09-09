"""Karar etkisi uçları: learning (ölçüm), auto-outcome (döngüyü kapat), track-record."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.db import models
from app.db.session import get_session
from app.sports import football

MATCH, US, THEM = 9800, 217, 213


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


def _seed(session, *, with_events: bool = True, with_decisions: bool = True):
    now = datetime.now(UTC)
    session.add(models.Tenant(id="t-default", slug="t-default", name="X",
                              settings_json="{}", active=True, created_at=now))
    session.add(models.Match(
        sport=football.SPORT_NAME, external_id=MATCH, league_external_id=11, season=90,
        kickoff=now - timedelta(days=1), status="FT",
        home_team_external_id=US, away_team_external_id=THEM,
        home_score=2, away_score=1, tenant_id="t-default",
    ))
    if with_events:
        i = 0

        def ev(**kw):
            nonlocal i
            i += 1
            base = dict(
                sport=football.SPORT_NAME, tenant_id="t-default", source="statsbomb_open",
                source_event_id=f"e{i}", match_external_id=MATCH, player_external_id=1,
                period=2, body_part=None, pattern="regular", possession_id=i,
                key_pass=False, raw_json=None, created_at=now,
            )
            base.update(kw)
            session.add(models.EventRow(**base))

        # 60. dk kararı: öncesi rakip baskın, sonrası biz baskın
        for k in range(20):
            ev(team_external_id=US, event_type="pass", minute=46.0 + k * 0.5,
               start_x=40.0, start_y=50.0, end_x=55.0, end_y=50.0, outcome="completed")
            ev(team_external_id=US, event_type="pass", minute=60.0 + k * 0.5,
               start_x=50.0, start_y=50.0, end_x=85.0, end_y=50.0, outcome="completed")
        for k in range(6):
            ev(team_external_id=THEM, event_type="shot", minute=48.0 + k,
               start_x=88.0, start_y=50.0, end_x=None, end_y=None, outcome="off_t", is_goal=False)
            ev(team_external_id=US, event_type="shot", minute=61.0 + k,
               start_x=88.0, start_y=50.0, end_x=None, end_y=None, outcome="goal" if k == 0 else "off_t",
               is_goal=k == 0)
    if with_decisions:
        session.add(models.Decision(
            sport=football.SPORT_NAME, tenant_id="t-default", match_external_id=MATCH,
            team_external_id=US, minute=60.0, period=2, decision_type="substitution",
            subject_player_external_id=5, related_player_external_id=9,
            notes="yorgun 8 numara çıktı", recommended=True, confidence=0.7, created_at=now,
        ))
        session.add(models.Decision(
            sport=football.SPORT_NAME, tenant_id="t-default", match_external_id=MATCH,
            team_external_id=US, minute=89.0, period=2, decision_type="time_management",
            notes="oyunu yavaşlat", recommended=False, created_at=now,
        ))
    session.commit()


def test_learning_measures_impact_per_decision(session, client):
    _seed(session)
    r = client.get(f"/admin/matches/{MATCH}/decisions/learning")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["decisions_analyzed"] == 2
    imp = {i["minute"]: i for i in body["impacts"]}
    sub = imp[60.0]
    assert sub["decision_type"] == "substitution" and sub["decision_label"] == "İkame"
    assert sub["verdict"] == "positive", sub["verdict_reason"]
    assert sub["xg_diff_delta"] > 0 and sub["goals_delta"] > 0
    assert sub["pre"]["minutes"] == 15.0 and sub["post"]["minutes"] == 15.0
    # 89. dk kararı: sonrası penceresi kısa → ölçülemez
    assert imp[89.0]["verdict"] == "insufficient_data"


def test_auto_outcome_closes_the_loop_and_respects_manual(session, client):
    _seed(session)
    r = client.post(f"/admin/matches/{MATCH}/decisions/auto-outcome")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["written"] == 1 and body["skipped_insufficient"] == 1
    rows = {d.minute: d for d in session.query(models.Decision).all()}
    assert rows[60.0].outcome == "positive"
    assert rows[60.0].outcome_value > 0
    assert rows[60.0].outcome_notes.startswith("[oto]")
    assert rows[60.0].outcome_recorded_at is not None
    assert rows[89.0].outcome is None          # ölçülemeyen dokunulmadı

    # feedback artık dolu → context_engine güven kalibrasyonu besleniyor
    fb = client.get(f"/admin/teams/{US}/decisions/feedback").json()
    assert fb["by_decision_type"]["substitution"]["n"] == 1

    # Elle girilen sonucu ezmez
    rows[60.0].outcome = "negative"
    rows[60.0].outcome_notes = "koç: işe yaramadı"
    session.commit()
    again = client.post(f"/admin/matches/{MATCH}/decisions/auto-outcome").json()
    assert again["written"] == 0 and again["skipped_manual"] == 1
    assert session.query(models.Decision).filter_by(minute=60.0).one().outcome == "negative"

    forced = client.post(f"/admin/matches/{MATCH}/decisions/auto-outcome?overwrite_manual=true").json()
    assert forced["written"] == 1
    assert session.query(models.Decision).filter_by(minute=60.0).one().outcome == "positive"


def test_track_record_aggregates_team_decisions(session, client):
    _seed(session)
    r = client.get(f"/admin/teams/{US}/decisions/track-record")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["team_id"] == US and body["matches"] == 1 and body["matches_with_events"] == 1
    assert body["decisions"] == 2 and body["measured"] == 1
    assert body["positive"] == 1 and body["hit_rate"] == 1.0
    types = {t["decision_type"]: t for t in body["by_type"]}
    assert types["substitution"]["label"] == "İkame" and types["substitution"]["n"] == 1
    assert any(b["band"] == "46-70" for b in body["by_minute_band"])
    assert body["best"]["decision_id"] is not None
    assert "hit_rate" in body["formula"]


def test_no_events_or_no_decisions_is_reported_not_crashed(session, client):
    _seed(session, with_events=False)
    body = client.get(f"/admin/matches/{MATCH}/decisions/learning").json()
    assert body["events_loaded"] == 0 and "note" in body
    auto = client.post(f"/admin/matches/{MATCH}/decisions/auto-outcome").json()
    assert auto["written"] == 0 and "note" in auto
    assert client.get(f"/admin/matches/424242/decisions/learning").status_code == 404
