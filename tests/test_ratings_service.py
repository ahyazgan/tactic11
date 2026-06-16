"""Player match rating persistence + Maçı Notla endpoint testleri."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.db.tenant_context import DEFAULT_TENANT_ID, set_current_tenant_id
from app.ratings.service import (
    RatingInput,
    list_match_ratings,
    list_player_ratings,
    save_match_ratings,
)


@pytest.fixture()
def tenant_ctx(default_tenant):
    """Tenant context set'le ki insert tenant_id autofill + filter çalışsın."""
    set_current_tenant_id(DEFAULT_TENANT_ID)
    yield
    set_current_tenant_id(None)


def test_save_and_list_match_ratings(session, tenant_ctx):
    res = save_match_ratings(
        session, match_external_id=100,
        ratings=[
            RatingInput(player_external_id=1, rating=7.5),
            RatingInput(player_external_id=2, rating=6.0, minute_played=70),
        ],
    )
    assert res == {"created": 2, "updated": 0}
    rows = list_match_ratings(session, match_external_id=100)
    assert len(rows) == 2
    assert {r.player_external_id for r in rows} == {1, 2}


def test_save_is_idempotent_upsert(session, tenant_ctx):
    save_match_ratings(
        session, match_external_id=100,
        ratings=[RatingInput(player_external_id=1, rating=7.0)],
    )
    res2 = save_match_ratings(
        session, match_external_id=100,
        ratings=[RatingInput(player_external_id=1, rating=8.5)],
    )
    assert res2 == {"created": 0, "updated": 1}
    rows = list_match_ratings(session, match_external_id=100)
    assert len(rows) == 1
    assert rows[0].rating == 8.5


def test_player_series_chronological(session, tenant_ctx):
    base = datetime.now(UTC)
    # 3 maç, ters sırada kaydet — kickoff'a göre sıralanmalı
    for i, mid in enumerate([30, 10, 20]):
        save_match_ratings(
            session, match_external_id=mid,
            kickoff=base + timedelta(days=mid),
            ratings=[RatingInput(player_external_id=5, rating=7.0 + i * 0.1)],
        )
    series = list_player_ratings(session, player_external_id=5)
    assert [r.match_external_id for r in series] == [10, 20, 30]


def test_flags_and_context_persisted(session, tenant_ctx):
    save_match_ratings(
        session, match_external_id=100,
        ratings=[RatingInput(
            player_external_id=1, rating=8.0,
            opp_rating=8.5, fatigue_proxy=0.6,
            flags={"big_match": True, "knockout": True},
            note="derbi performansı",
        )],
    )
    rows = list_match_ratings(session, match_external_id=100)
    r = rows[0]
    assert r.opp_rating == 8.5
    assert r.fatigue_proxy == 0.6
    assert '"big_match": true' in r.flags_json
    assert r.note == "derbi performansı"


# --------------------------------------------------------------------------- #
# Endpoint testleri (TestClient + JWT)
# --------------------------------------------------------------------------- #


@pytest.fixture()
def auth_client(session, test_user):
    from fastapi.testclient import TestClient

    from app.api.main import app
    from app.auth.jwt_tokens import create_access_token
    from app.db.session import get_session

    set_current_tenant_id(DEFAULT_TENANT_ID)

    def _override():
        yield session

    app.dependency_overrides[get_session] = _override
    token = create_access_token(
        user_id=test_user.id, tenant_id=test_user.tenant_id, role="admin",
    )
    try:
        client = TestClient(app)
        client.headers.update({"Authorization": f"Bearer {token}"})
        yield client
    finally:
        app.dependency_overrides.clear()
        set_current_tenant_id(None)


def test_save_ratings_endpoint(auth_client):
    r = auth_client.post("/admin/ratings/match", json={
        "match_external_id": 200,
        "ratings": [
            {"player_external_id": 1, "rating": 7.5},
            {"player_external_id": 2, "rating": 6.8, "minute_played": 80},
        ],
    })
    assert r.status_code == 200
    body = r.json()
    assert body["created"] == 2
    assert body["total"] == 2


def test_get_match_ratings_endpoint(auth_client):
    auth_client.post("/admin/ratings/match", json={
        "match_external_id": 201,
        "ratings": [{"player_external_id": 1, "rating": 7.0}],
    })
    r = auth_client.get("/admin/ratings/match/201")
    assert r.status_code == 200
    assert len(r.json()["ratings"]) == 1


def test_player_performance_from_ratings_endpoint(auth_client):
    base = datetime.now(UTC)
    # 6 maç kaydet — performans motorlarını besle
    for i in range(6):
        auth_client.post("/admin/ratings/match", json={
            "match_external_id": 300 + i,
            "kickoff": (base + timedelta(days=i)).isoformat(),
            "ratings": [{
                "player_external_id": 9,
                "rating": 7.0 + i * 0.3,
                "opp_rating": 7.5,
            }],
        })
    r = auth_client.get("/admin/ratings/player/9/performance")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 6
    results = body["results"]
    assert "consistency" in results
    assert "trajectory" in results
    assert "anomaly" in results
    assert "clutch" in results
    assert "opponent_adjusted" in results
    # Yükselen seri → trajectory improving
    assert results["trajectory"]["value"]["direction"] == "improving"


def test_player_performance_empty_when_no_ratings(auth_client):
    r = auth_client.get("/admin/ratings/player/99999/performance")
    assert r.status_code == 200
    assert r.json()["count"] == 0


def test_save_requires_match_id(auth_client):
    r = auth_client.post("/admin/ratings/match", json={
        "ratings": [{"player_external_id": 1, "rating": 7.0}],
    })
    assert r.status_code == 422
