"""Koç işareti: öneri sahada uygulandı mı? (`decisions.applied`)

Külliyat bulgusu: 502 ölçülmüş öneride hiçbir sinyal sonucu ayırt etmiyor,
çünkü kararlar hiç UYGULANMADI — `outcome` yalnız "sonra ne oldu"yu ölçüyor.
Bu dosya karşı-olgunun kaydedilebildiğini ve geri beslemenin YALNIZ uygulanan
kararlardan öğrendiğini kilitler.

Uplift ucu için maç kurgusu `test_api_decision_quality` ile aynıdır: 15 dk'lık
dilimlerde baskın taraf değişir, dilim sınırındaki kararların hükmü kesindir
(30' pozitif, 45' negatif, 60' pozitif, 75' negatif).
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.db import models
from app.db.session import get_session
from app.sports import football

MATCH, US, THEM = 9820, 217, 213
SEGMENTS = [(15.0, THEM), (30.0, US), (45.0, THEM), (60.0, US), (75.0, THEM)]


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


def _tenant(session) -> None:
    session.add(models.Tenant(id="t-default", slug="t-default", name="X",
                              settings_json="{}", active=True,
                              created_at=datetime.now(UTC)))
    session.commit()


def _decision(session, *, minute: float = 70.0, recommended: bool = True,
              applied: bool | None = None, outcome: str = "pending",
              confidence: float | None = 0.8, match_id: int = MATCH) -> models.Decision:
    row = models.Decision(
        sport=football.SPORT_NAME, tenant_id="t-default", match_external_id=match_id,
        team_external_id=US, minute=minute, period=1 if minute < 45 else 2,
        decision_type="tactical_instruction", recommended=recommended,
        confidence=confidence, applied=applied, outcome=outcome,
        created_at=datetime.now(UTC),
    )
    session.add(row)
    session.commit()
    return row


# --- kayıt ------------------------------------------------------------------ #

def _post(client, **extra):
    body = {"team_external_id": US, "minute": 70.0,
            "decision_type": "tactical_instruction", **extra}
    r = client.post(f"/admin/matches/{MATCH}/decisions", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_not_applied_recommendation_is_recorded_as_counterfactual(session, client):
    """'Uygulamadım' boş bir tık değil: kayıt düşer, applied=false."""
    _tenant(session)
    body = _post(client, recommended=True, applied=False, confidence=0.7)
    assert body["applied"] is False and body["recommended"] is True
    row = session.get(models.Decision, body["id"])
    assert row.applied is False and row.applied_at is not None


def test_unmarked_recommendation_stays_unknown(session, client):
    """Koç işaretlemediyse uydurulmaz — None kalır, applied_at boş."""
    _tenant(session)
    body = _post(client, recommended=True)
    assert body["applied"] is None
    assert session.get(models.Decision, body["id"]).applied_at is None


def test_coach_own_move_is_applied_by_definition(session, client):
    """Koçun kendi hamlesi kaydediliyorsa yapılmıştır."""
    _tenant(session)
    body = _post(client)
    assert body["recommended"] is False and body["applied"] is True


def test_non_boolean_applied_is_rejected(session, client):
    _tenant(session)
    r = client.post(f"/admin/matches/{MATCH}/decisions", json={
        "team_external_id": US, "minute": 70.0,
        "decision_type": "tactical_instruction", "applied": "evet",
    })
    assert r.status_code == 400


# --- sonradan işaretleme ---------------------------------------------------- #

def test_mark_endpoint_sets_and_clears_the_flag(session, client):
    _tenant(session)
    row = _decision(session, applied=None)

    r = client.post(f"/admin/decisions/{row.id}/applied", json={"applied": True})
    assert r.status_code == 200, r.text
    assert r.json()["applied"] is True and r.json()["applied_at"]
    session.refresh(row)
    assert row.applied is True and row.applied_at is not None

    r = client.post(f"/admin/decisions/{row.id}/applied", json={"applied": None})
    assert r.status_code == 200
    session.refresh(row)
    assert row.applied is None and row.applied_at is None


def test_mark_endpoint_validates(session, client):
    _tenant(session)
    row = _decision(session)
    assert client.post(f"/admin/decisions/{row.id}/applied", json={}).status_code == 400
    assert client.post(f"/admin/decisions/{row.id}/applied",
                       json={"applied": 1}).status_code == 400
    assert client.post("/admin/decisions/999999/applied",
                       json={"applied": True}).status_code == 404


def test_list_and_recent_expose_the_flag(session, client):
    _tenant(session)
    _decision(session, applied=True, minute=60.0)
    _decision(session, applied=False, minute=65.0)
    _decision(session, applied=None, minute=70.0)

    listed = client.get(f"/admin/matches/{MATCH}/decisions").json()
    assert [d["applied"] for d in listed] == [True, False, None]

    recent = client.get("/admin/decisions/recent?limit=20").json()
    assert recent["summary"]["applied"] == {"yes": 1, "no": 1, "unknown": 1}
    assert {d["applied"] for d in recent["decisions"]} == {True, False, None}


# --- geri besleme yalnız uygulanandan öğrenir ------------------------------- #

def test_feedback_counts_only_applied_decisions(session, client):
    """Uygulanmayan önerinin sonucu öneriyi tartmaz; işaretsiz olan uydurulmaz."""
    _tenant(session)
    _decision(session, applied=True, outcome="positive", match_id=1)
    _decision(session, applied=False, outcome="negative", match_id=2)
    _decision(session, applied=None, outcome="negative", match_id=3)

    body = client.get(f"/admin/teams/{US}/decisions/feedback").json()
    assert body["evaluated"] == 1
    assert body["excluded"] == {"not_applied": 1, "unknown": 1}
    assert body["by_decision_type"] == {
        "tactical_instruction": {"n": 1, "hit_rate": 1.0},
    }


# --- uplift: uygulanan vs uygulanmayan, aynı cetvelle ----------------------- #

def _seed_match(session, decisions: list[tuple[float, bool | None]]) -> None:
    """(dakika, applied) listesi — hepsi öneri (recommended=True)."""
    now = datetime.now(UTC)
    _tenant(session)
    session.add(models.Match(
        sport=football.SPORT_NAME, external_id=MATCH, league_external_id=11, season=90,
        kickoff=now - timedelta(days=1), status="FT",
        home_team_external_id=US, away_team_external_id=THEM,
        home_score=3, away_score=3, tenant_id="t-default",
    ))
    i = 0

    def ev(**kw):
        nonlocal i
        i += 1
        base = dict(
            sport=football.SPORT_NAME, tenant_id="t-default", source="statsbomb_open",
            source_event_id=f"u{i}", match_external_id=MATCH, player_external_id=1,
            period=1, body_part=None, pattern="regular", possession_id=i,
            key_pass=False, raw_json=None, created_at=now,
        )
        base.update(kw)
        session.add(models.EventRow(**base))

    for lo, owner in SEGMENTS:
        period = 1 if lo < 45 else 2
        for k in range(12):
            m = lo + k * 1.2
            ev(team_external_id=owner, event_type="shot", minute=m, period=period,
               start_x=88.0, start_y=50.0, end_x=None, end_y=None,
               outcome="off_t", is_goal=False)
            fwd = owner == US
            ev(team_external_id=US, event_type="pass", minute=m + 0.4, period=period,
               start_x=50.0, start_y=50.0,
               end_x=88.0 if fwd else 25.0, end_y=50.0, outcome="completed")
    ev(team_external_id=US, event_type="pass", minute=92.0, period=2,
       start_x=50.0, start_y=50.0, end_x=55.0, end_y=50.0, outcome="completed")
    session.commit()
    for minute, applied in decisions:
        _decision(session, minute=minute, applied=applied, confidence=0.7)


def test_uplift_separates_the_arms_on_the_same_ruler(session, client):
    """30' ve 60' pozitif, 45' ve 75' negatif — hükümler cetvelden gelir."""
    _seed_match(session, [(30.0, True), (45.0, False), (60.0, True), (75.0, None)])
    r = client.get(f"/admin/teams/{US}/decisions/uplift")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["measured_recommendations"] == 4 and body["matches_used"] == 1
    assert body["applied"] == {"n": 2, "positive": 2, "hit_rate": 1.0,
                               "mean_xg_delta": body["applied"]["mean_xg_delta"]}
    assert body["not_applied"]["n"] == 1 and body["not_applied"]["hit_rate"] == 0.0
    assert body["unknown"] == 1
    assert body["raw_hit_rate_diff"] == 1.0
    # 4 karar hüküm için az — sayı var, hüküm yok
    assert body["verdict"] == "yetersiz veri"
    assert "formula" in body


def test_uplift_without_counterfactual_says_so(session, client):
    _seed_match(session, [(30.0, True), (45.0, True), (60.0, None), (75.0, True)])
    body = client.get(f"/admin/teams/{US}/decisions/uplift").json()
    assert body["verdict"] == "karşı-olgu yok"
    assert body["not_applied"]["n"] == 0 and body["unknown"] == 1
    assert body["stratified_hit_rate_diff"] is None


def test_quality_excludes_unapplied_recommendations(session, client):
    """Kalibrasyon ve 'öneriden' grubu yalnız uygulanan önerileri sayar."""
    _seed_match(session, [(30.0, True), (45.0, False), (60.0, None), (75.0, True)])
    body = client.get(f"/admin/teams/{US}/decisions/quality").json()
    assert body["measured_decisions"] == 4
    assert body["confidence_calibration"]["n"] == 2          # 30' + 75'
    cmp_ = body["recommended_vs_own"]
    assert cmp_["recommended"]["n"] == 2
    assert cmp_["not_applied"] == 1 and cmp_["unknown"] == 1
    assert cmp_["own"]["n"] == 0
