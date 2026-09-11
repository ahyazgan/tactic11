"""Karar kalitesi ucu: güven kalibrasyonu + öneri vs koçun kendi kararı.

Kurgu: maç 15 dk'lık dilimlere bölünür, her dilimde bir taraf baskın. Karar
dilim sınırlarına konunca öncesi/sonrası net şekilde ters yöne döner, böylece
`decision_impact` hükmü deterministik olur:

    dilim   [15,30) [30,45) [45,60) [60,75) [75,90)
    baskın   RAKİP    BİZ    RAKİP    BİZ    RAKİP
    karar        30'     45'     60'     75'
    hüküm      pozitif negatif pozitif negatif
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.db import models
from app.db.session import get_session
from app.sports import football

MATCH, US, THEM = 9810, 217, 213
SEGMENTS = [(15.0, THEM), (30.0, US), (45.0, THEM), (60.0, US), (75.0, THEM)]
# (dakika, öneri mi, güven) — hükümler yukarıdaki dilim kurgusundan gelir
DECISIONS = [
    (30.0, True, 0.8),    # pozitif → isabet
    (45.0, True, 0.7),    # negatif → ıska
    (60.0, True, 0.4),    # pozitif → isabet
    (75.0, False, None),  # negatif, koçun kendi kararı (öneri değil)
]


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


def _seed(session, *, decisions=DECISIONS):
    now = datetime.now(UTC)
    session.add(models.Tenant(id="t-default", slug="t-default", name="X",
                              settings_json="{}", active=True, created_at=now))
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
            source_event_id=f"q{i}", match_external_id=MATCH, player_external_id=1,
            period=1, body_part=None, pattern="regular", possession_id=i,
            key_pass=False, raw_json=None, created_at=now,
        )
        base.update(kw)
        session.add(models.EventRow(**base))

    for lo, owner in SEGMENTS:
        period = 1 if lo < 45 else 2
        for k in range(12):
            m = lo + k * 1.2
            # Baskın taraf şut atar → xG farkı o yöne kayar
            ev(team_external_id=owner, event_type="shot", minute=m, period=period,
               start_x=88.0, start_y=50.0, end_x=None, end_y=None,
               outcome="off_t", is_goal=False)
            # xT ikincil onayı: biz baskınken ileri, rakip baskınken geri pas
            fwd = owner == US
            ev(team_external_id=US, event_type="pass", minute=m + 0.4, period=period,
               start_x=50.0, start_y=50.0,
               end_x=88.0 if fwd else 25.0, end_y=50.0, outcome="completed")
    # Maçın sonunu sabitle (son kararın sonrası penceresi dolsun)
    ev(team_external_id=US, event_type="pass", minute=92.0, period=2,
       start_x=50.0, start_y=50.0, end_x=55.0, end_y=50.0, outcome="completed")

    for minute, recommended, confidence in decisions:
        session.add(models.Decision(
            sport=football.SPORT_NAME, tenant_id="t-default", match_external_id=MATCH,
            team_external_id=US, minute=minute, period=1 if minute < 45 else 2,
            decision_type="tactical", notes=f"karar @{minute:.0f}",
            recommended=recommended, confidence=confidence, created_at=now,
            # Öneri tarafı yalnız koçun UYGULADIĞI önerileri sayar
            applied=True,
        ))
    session.commit()


def test_segment_setup_produces_alternating_verdicts(session, client):
    """Kalibrasyon testinin dayandığı kurgu gerçekten bu hükümleri üretiyor mu."""
    _seed(session)
    body = client.get(f"/admin/matches/{MATCH}/decisions/learning").json()
    verdicts = {i["minute"]: i["verdict"] for i in body["impacts"]}
    assert verdicts == {30.0: "positive", 45.0: "negative",
                        60.0: "positive", 75.0: "negative"}


def test_quality_reports_confidence_calibration(session, client):
    _seed(session)
    r = client.get(f"/admin/teams/{US}/decisions/quality")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["team_id"] == US and body["matches_used"] == 1
    assert body["measured_decisions"] == 4

    cal = body["confidence_calibration"]
    # Örneklem yalnız öneri-kaynaklı + güveni kayıtlı kararlar (3 tane)
    assert cal["n"] == 3
    # accuracy = 0.5 eşiğinde sınıflandırma isabeti: 0.8→poz ✓, 0.7→neg ✗, 0.4→poz ✗
    assert cal["accuracy"] == pytest.approx(1 / 3, abs=1e-3)
    assert "hit_rate" not in cal, "kalibrasyonda hit_rate adı kullanılmamalı (anlam çakışması)"
    assert cal["mean_predicted"] == pytest.approx((0.8 + 0.7 + 0.4) / 3, abs=1e-3)
    # observed_rate = gerçekleşen pozitif ORANI (accuracy'den farklı)
    assert cal["observed_rate"] == pytest.approx(2 / 3, abs=1e-3)
    assert 0.0 <= cal["brier_score"] <= 1.0
    assert sum(b["n"] for b in cal["bins"]) == 3
    # Sistem %63 güven diyor, %67 tutuyor → fazla temkinli
    assert "temkinli" in body["verdict"]


def test_quality_compares_recommended_against_coach_own(session, client):
    _seed(session)
    body = client.get(f"/admin/teams/{US}/decisions/quality").json()
    cmp_ = body["recommended_vs_own"]
    assert cmp_["recommended"]["n"] == 3
    assert cmp_["recommended"]["hit_rate"] == pytest.approx(2 / 3, abs=1e-3)
    assert cmp_["own"]["n"] == 1 and cmp_["own"]["hit_rate"] == 0.0
    # Öneriler koçun tek kararından daha iyi → lift pozitif
    assert cmp_["xg_lift"] is not None and cmp_["xg_lift"] > 0
    assert "%" in body["verdict"]


def test_quality_without_confidence_says_so_instead_of_crashing(session, client):
    """Güven kaydı olmayan kararlar: kalibrasyon boş ama uç 200 dönmeli."""
    _seed(session, decisions=[(30.0, False, None), (45.0, False, None)])
    r = client.get(f"/admin/teams/{US}/decisions/quality")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["confidence_calibration"]["n"] == 0
    assert "yeterli uygulanmış öneri yok" in body["verdict"]
    assert body["recommended_vs_own"]["own"]["n"] == 2
    assert body["recommended_vs_own"]["xg_lift"] is None


def test_quality_for_team_without_decisions_is_empty_not_error(session, client):
    _seed(session)
    body = client.get(f"/admin/teams/{THEM}/decisions/quality").json()
    assert body["matches_used"] == 0 and body["measured_decisions"] == 0
    assert body["confidence_calibration"]["n"] == 0
