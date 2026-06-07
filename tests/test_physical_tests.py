"""Fiziksel test modülü testleri — saf engine + endpoint (in-memory SQLite)."""

import types

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

import app.db.physical_test  # noqa: F401 — PhysicalTest tablosunu metadata'ya kaydet
from app.api.auth import get_current_user
from app.api.main import app
from app.db import models
from app.db.session import get_session
from app.engine.physical.load_risk import (
    compute_load_risk,
    compute_protocol_trend,
    format_critical_alert,
)


def test_no_tests_returns_no_data():
    report = compute_load_risk("p1", "Test Oyuncu", [])
    assert report.risk_label == "Veri Yok"
    assert report.risk_score == 0.0


def test_good_values_low_risk():
    tests = [
        {"protocol": "sprint_10m", "value": 1.72, "unit": "sn", "test_date": "2026-06-01"},
        {"protocol": "cmj", "value": 40.0, "unit": "cm", "test_date": "2026-06-01"},
        {"protocol": "yoyo_irl1", "value": 18.5, "unit": "seviye", "test_date": "2026-06-01"},
    ]
    report = compute_load_risk("p2", "İyi Oyuncu", tests)
    assert report.risk_label == "Düşük"
    assert report.risk_score < 0.20


def test_bad_values_high_risk():
    tests = [
        {"protocol": "sprint_10m", "value": 2.10, "unit": "sn", "test_date": "2026-06-01"},
        {"protocol": "cmj", "value": 24.0, "unit": "cm", "test_date": "2026-06-01"},
        {"protocol": "yoyo_irl1", "value": 13.5, "unit": "seviye", "test_date": "2026-06-01"},
        {"protocol": "vo2max", "value": 44.0, "unit": "ml/kg/min", "test_date": "2026-06-01"},
    ]
    report = compute_load_risk("p3", "Yorgun Oyuncu", tests)
    assert report.risk_label in ("Yüksek", "Kritik")
    assert len(report.flags) >= 3


def test_flags_contain_protocol_name():
    tests = [{"protocol": "cmj", "value": 20.0, "unit": "cm", "test_date": "2026-06-01"}]
    report = compute_load_risk("p4", "Test", tests)
    assert any("cmj" in f["protocol"] for f in report.flags)


def test_trend_lower_is_better_improving():
    # sprint süresi düşüyor → iyileşme (lower_is_better)
    pts = [
        {"test_date": "2026-01-01", "value": 1.95},
        {"test_date": "2026-02-01", "value": 1.88},
        {"test_date": "2026-03-01", "value": 1.80},
    ]
    t = compute_protocol_trend("sprint_10m", pts)
    assert t.direction == "improving"
    assert t.lower_is_better is True
    assert len(t.points) == 3


def test_trend_higher_is_better_worsening():
    # YoYo seviyesi düşüyor → kötüleşme
    pts = [
        {"test_date": "2026-01-01", "value": 18.0},
        {"test_date": "2026-02-01", "value": 16.0},
        {"test_date": "2026-03-01", "value": 14.0},
    ]
    t = compute_protocol_trend("yoyo_irl1", pts)
    assert t.direction == "worsening"


def test_trend_insufficient_with_one_point():
    t = compute_protocol_trend("cmj", [{"test_date": "2026-01-01", "value": 30.0}])
    assert t.direction == "insufficient"
    assert t.slope == 0.0


def test_format_critical_alert_contains_player_and_flags():
    tests = [
        {"protocol": "sprint_10m", "value": 2.10, "test_date": "2026-06-01"},
        {"protocol": "cmj", "value": 24.0, "test_date": "2026-06-01"},
        {"protocol": "yoyo_irl1", "value": 13.5, "test_date": "2026-06-01"},
        {"protocol": "vo2max", "value": 44.0, "test_date": "2026-06-01"},
    ]
    report = compute_load_risk("p5", "Yorgun", tests)
    assert report.risk_label == "Kritik"
    msg = format_critical_alert(report)
    assert "Kritik" in msg
    assert "Yorgun" in msg
    assert "•" in msg


# --------------------------------------------------------------------------- #
# Endpoint testleri — JWT + tenant izolasyonu (sahte get_current_user override)
# --------------------------------------------------------------------------- #

_SPRINT_OK = {
    "player_id": "12345", "player_name": "Rafa Silva",
    "test_date": "2026-06-06", "protocol": "sprint_10m", "value": 1.78,
}


@pytest.fixture()
def client(session):
    """TestClient + override edilmiş DB session ve current_user.

    `state["tenant_id"]` değiştirilerek cross-tenant senaryosu kurulur."""
    state = {"tenant_id": "t1", "email": "coach@besiktas.com"}

    def _fake_user():
        return types.SimpleNamespace(
            id="u1", tenant_id=state["tenant_id"], email=state["email"],
        )

    def _override_session():
        yield session

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_current_user] = _fake_user
    try:
        yield TestClient(app), state
    finally:
        app.dependency_overrides.clear()


def test_post_returns_201_autofills_unit_and_recorded_by(client):
    c, _ = client
    r = c.post("/physical-tests/", json=_SPRINT_OK)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["protocol"] == "sprint_10m"
    assert body["unit"] == "sn"                       # protokolden otomatik
    assert body["recorded_by"] == "coach@besiktas.com"  # current_user.email
    assert body["player_id"] == "12345"


def test_post_ignores_tenant_from_body(client):
    """tenant_id gövdeden gelse bile current_user'dan alınır (sızıntı yok)."""
    c, state = client
    payload = {**_SPRINT_OK, "tenant_id": "baska-kulup"}
    r = c.post("/physical-tests/", json=payload)
    assert r.status_code == 201
    # t2 olarak bakınca görünmemeli → tenant t1'e yazılmış demektir
    state["tenant_id"] = "t2"
    assert c.get("/physical-tests/12345").json() == []


def test_get_risk_schema(client):
    c, _ = client
    c.post("/physical-tests/", json=_SPRINT_OK)
    r = c.get("/physical-tests/12345/risk")
    assert r.status_code == 200
    body = r.json()
    for key in (
        "player_id", "player_name", "risk_score",
        "risk_label", "flags", "summary", "recommendations",
    ):
        assert key in body


def test_get_risk_404_when_no_data(client):
    c, _ = client
    assert c.get("/physical-tests/99999/risk").status_code == 404


def test_cross_tenant_isolation(client):
    c, state = client
    r = c.post("/physical-tests/", json=_SPRINT_OK)
    assert r.status_code == 201
    test_id = r.json()["id"]

    # Başka kulüp (t2) ne listeyi, ne riski, ne silmeyi yapabilmeli.
    state["tenant_id"] = "t2"
    assert c.get("/physical-tests/12345").json() == []
    assert c.get("/physical-tests/12345/risk").status_code == 404
    assert c.delete(f"/physical-tests/{test_id}").status_code == 404

    # Sahibi (t1) silebilmeli.
    state["tenant_id"] = "t1"
    assert c.delete(f"/physical-tests/{test_id}").status_code == 204
    assert c.get("/physical-tests/12345").json() == []


def test_list_players_summary(client):
    c, state = client
    # iki oyuncu, t1
    c.post("/physical-tests/", json={**_SPRINT_OK, "player_id": "100", "player_name": "Oyuncu A"})
    c.post("/physical-tests/", json={
        "player_id": "200", "player_name": "Oyuncu B",
        "test_date": "2026-06-06", "protocol": "cmj", "value": 24.0,  # kötü → riskli
    })
    r = c.get("/physical-tests/players")
    assert r.status_code == 200
    players = r.json()
    assert {p["player_id"] for p in players} == {"100", "200"}
    # şema alanları
    for p in players:
        for key in ("player_id", "player_name", "test_count", "risk_label", "risk_score"):
            assert key in p
    # en riskli üstte
    assert players[0]["risk_score"] >= players[-1]["risk_score"]


def test_list_players_cross_tenant_empty(client):
    c, state = client
    c.post("/physical-tests/", json=_SPRINT_OK)
    state["tenant_id"] = "t2"
    assert c.get("/physical-tests/players").json() == []


def test_kvkk_access_log_captures_user_and_subject(client, session):
    """KVKK: erişim DataAccessLog'a 'kim' (user_id) + 'hangi oyuncu' ile düşer."""
    c, _ = client
    c.post("/physical-tests/", json=_SPRINT_OK)  # player_id=12345 (sayısal)
    c.get("/physical-tests/12345/risk")
    rows = session.execute(select(models.DataAccessLog)).scalars().all()
    perf = [r for r in rows if r.data_category == "performance_test"]
    assert perf, "performance_test erişimi loglanmadı"
    assert all(r.user_id == "u1" for r in perf)        # kim erişti (str user.id)
    assert all(r.subject_id == 12345 for r in perf)    # hangi oyuncu
    assert {r.action for r in perf} >= {"create", "read"}


def test_rate_against_norms_bands():
    from app.engine.physical.load_risk import rate_against_norms
    # cmj: low=32, high=42 (yüksek iyi) → mid=37
    assert rate_against_norms("cmj", 43.0) == "elit"
    assert rate_against_norms("cmj", 38.0) == "iyi"
    assert rate_against_norms("cmj", 34.0) == "ortalama"
    assert rate_against_norms("cmj", 25.0) == "zayıf"
    # sprint_10m: low=1.90, high=1.70 (düşük iyi) → mid=1.80
    assert rate_against_norms("sprint_10m", 1.65) == "elit"
    assert rate_against_norms("sprint_10m", 2.05) == "zayıf"
    # bilinmeyen → None
    assert rate_against_norms("custom", 1.0) is None


def test_physical_test_out_includes_norm_rating(client):
    c, _ = client
    r = c.post("/physical-tests/", json=_SPRINT_OK)  # sprint_10m=1.78 → mid civarı
    assert r.status_code == 201
    body = r.json()
    assert "rating" in body
    assert body["rating"] in ("elit", "iyi", "ortalama", "zayıf")


def test_pdf_export_returns_pdf_bytes(client):
    c, _ = client
    c.post("/physical-tests/", json=_SPRINT_OK)
    r = c.get("/physical-tests/12345/pdf")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/pdf")
    assert r.content[:4] == b"%PDF"


def test_pdf_export_404_when_no_data(client):
    c, _ = client
    assert c.get("/physical-tests/99999/pdf").status_code == 404


def test_rate_against_norms_all_protocols_extremes():
    """Tüm REFERENCE protokollerinde uç-iyi→elit, uç-kötü→zayıf; yön doğru."""
    from app.engine.physical.load_risk import REFERENCE, rate_against_norms
    valid = {"elit", "iyi", "ortalama", "zayıf"}
    for p, ref in REFERENCE.items():
        lib = ref["lower_is_better"]
        best = ref["high"] * (0.9 if lib else 1.1)   # elit tarafı
        worst = ref["low"] * (1.2 if lib else 0.8)    # zayıf tarafı
        rb = rate_against_norms(p, best)
        rw = rate_against_norms(p, worst)
        assert rb in valid and rw in valid, (p, rb, rw)
        assert rb == "elit", (p, "best", best, rb)
        assert rw == "zayıf", (p, "worst", worst, rw)


def test_rate_against_norms_unknown_protocol_none():
    from app.engine.physical.load_risk import rate_against_norms
    assert rate_against_norms("bilinmeyen_protokol", 1.0) is None


def test_post_accepts_ttest_and_rsa_protocols(client):
    """ttest_agility + rsa artık kaydedilebilir (performans kütüphanesi ↔ B enum)."""
    c, _ = client
    for proto, val, unit in [("ttest_agility", 9.4, "sn"), ("rsa", 4.35, "sn")]:
        r = c.post("/physical-tests/", json={
            "player_id": "777", "player_name": "Çevik Oyuncu",
            "test_date": "2026-06-07", "protocol": proto, "value": val,
        })
        assert r.status_code == 201, r.text
        assert r.json()["protocol"] == proto
        assert r.json()["unit"] == unit  # UNIT_MAP'ten otomatik
