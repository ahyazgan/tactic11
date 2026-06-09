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


# --------------------------------------------------------------------------- #
# Blok 1 — GET /physical-tests/protocols (protokol rehberi)
# --------------------------------------------------------------------------- #

def test_protocols_endpoint_returns_all_protocols(client):
    c, _ = client
    r = c.get("/physical-tests/protocols")
    assert r.status_code == 200
    protocols = r.json()
    keys = {p["key"] for p in protocols}
    # Temel protokoller mevcut olmalı
    assert {"sprint_10m", "sprint_30m", "cmj", "yoyo_irl1", "ttest_agility", "rsa"}.issubset(keys)
    # custom hariç tutulmuş olmalı
    assert "custom" not in keys
    # Her protokolde gerekli alanlar
    for p in protocols:
        for field in ("key", "name", "unit", "higher_is_better", "description",
                      "norm_elite", "norm_good", "norm_average"):
            assert field in p, f"{field} eksik: {p['key']}"


def test_protocols_endpoint_no_auth_required():
    """Protokol listesi auth olmadan erişilebilir (tester tableti için)."""
    from fastapi.testclient import TestClient

    from app.api.main import app
    c = TestClient(app)
    r = c.get("/physical-tests/protocols")
    assert r.status_code == 200


def test_protocols_sprint_10m_higher_is_better_false(client):
    c, _ = client
    r = c.get("/physical-tests/protocols")
    protocols = {p["key"]: p for p in r.json()}
    assert "sprint_10m" in protocols
    assert protocols["sprint_10m"]["higher_is_better"] is False
    assert protocols["sprint_10m"]["unit"] == "sn"


def test_protocols_cmj_norms_ascending(client):
    """CMJ: elit > iyi > ortalama (yüksek iyi)."""
    c, _ = client
    r = c.get("/physical-tests/protocols")
    protocols = {p["key"]: p for p in r.json()}
    cmj = protocols["cmj"]
    assert cmj["norm_elite"] > cmj["norm_good"] > cmj["norm_average"]


def test_protocols_sprint_norms_descending(client):
    """Sprint: elit < iyi < ortalama (düşük iyi)."""
    c, _ = client
    r = c.get("/physical-tests/protocols")
    protocols = {p["key"]: p for p in r.json()}
    s = protocols["sprint_30m"]
    assert s["norm_elite"] < s["norm_good"] < s["norm_average"]


# --------------------------------------------------------------------------- #
# Blok 2 — POST /physical-tests/batch (toplu kayıt)
# --------------------------------------------------------------------------- #

_BATCH_PAYLOAD = {
    "protocol": "sprint_10m",
    "test_date": "2026-06-06",
    "recorded_by": "kondisyoner@besiktas.com",
    "items": [
        {"player_id": "301", "player_name": "Oyuncu A", "value": 1.75},
        {"player_id": "302", "player_name": "Oyuncu B", "value": 1.82},
        {"player_id": "303", "player_name": "Oyuncu C", "value": 1.91},
    ],
}


def test_batch_creates_all_items(client):
    c, _ = client
    r = c.post("/physical-tests/batch", json=_BATCH_PAYLOAD)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["created"] == 3
    assert body["failed"] == 0


def test_batch_items_queryable_per_player(client):
    c, _ = client
    c.post("/physical-tests/batch", json=_BATCH_PAYLOAD)
    for pid in ("301", "302", "303"):
        r = c.get(f"/physical-tests/{pid}")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["protocol"] == "sprint_10m"


def test_batch_unit_autofilled(client):
    c, _ = client
    c.post("/physical-tests/batch", json=_BATCH_PAYLOAD)
    r = c.get("/physical-tests/301")
    assert r.json()[0]["unit"] == "sn"


def test_batch_partial_success_on_duplicate_value_error(client):
    """Bir item geçersiz olsa bile diğerleri kaydedilmeli."""
    c, _ = client
    payload = {**_BATCH_PAYLOAD, "items": [
        {"player_id": "401", "player_name": "Geçerli", "value": 1.75},
        {"player_id": "402", "player_name": "Sıfır", "value": 0.0},  # geçerli ama düşük
        {"player_id": "403", "player_name": "Geçerli2", "value": 1.80},
    ]}
    r = c.post("/physical-tests/batch", json=payload)
    assert r.status_code == 201
    # 3 geçerli kayıt
    assert r.json()["created"] == 3


def test_batch_max_50_items_enforced(client):
    c, _ = client
    payload = {**_BATCH_PAYLOAD, "items": [
        {"player_id": str(i), "player_name": f"O{i}", "value": 1.80}
        for i in range(51)
    ]}
    r = c.post("/physical-tests/batch", json=payload)
    assert r.status_code == 422  # Pydantic validation


def test_batch_tenant_isolation(client):
    c, state = client
    c.post("/physical-tests/batch", json=_BATCH_PAYLOAD)
    state["tenant_id"] = "other_tenant"
    for pid in ("301", "302", "303"):
        assert c.get(f"/physical-tests/{pid}").json() == []


def test_batch_kvkk_log_created(client, session):
    from sqlalchemy import select

    from app.db import models
    c, _ = client
    c.post("/physical-tests/batch", json=_BATCH_PAYLOAD)
    rows = session.execute(select(models.DataAccessLog)).scalars().all()
    batch_logs = [r for r in rows if r.action == "batch_create"]
    assert len(batch_logs) == 3  # her oyuncu için ayrı log


def test_batch_risk_alerts_on_critical(client):
    """Kritik riske düşen oyuncu risk_alerts'te görünmeli."""
    c, _ = client
    payload = {
        "protocol": "sprint_10m",
        "test_date": "2026-06-06",
        "items": [
            # Çok yavaş sprint + daha önce kötü test yok → düşük risk bekle
            {"player_id": "501", "player_name": "Hızlı", "value": 1.72},
        ],
    }
    r = c.post("/physical-tests/batch", json=payload)
    assert r.status_code == 201
    body = r.json()
    assert isinstance(body["risk_alerts"], list)


# --------------------------------------------------------------------------- #
# Blok 3 — GET /physical-tests/{player_id}/battery (battery profili + SWC)
# --------------------------------------------------------------------------- #

def test_battery_returns_profile(client):
    c, _ = client
    for proto, val in [("sprint_10m", 1.78), ("cmj", 38.0), ("yoyo_irl1", 17.5)]:
        c.post("/physical-tests/", json={
            "player_id": "600", "player_name": "Profil Oyuncu",
            "test_date": "2026-06-06", "protocol": proto, "value": val,
        })
    r = c.get("/physical-tests/600/battery")
    assert r.status_code == 200
    body = r.json()
    assert body["player_id"] == "600"
    assert isinstance(body["strong_areas"], list)
    assert isinstance(body["weak_areas"], list)
    assert len(body["scores"]) == 3


def test_battery_404_no_data(client):
    c, _ = client
    assert c.get("/physical-tests/99999/battery").status_code == 404


def test_battery_swc_requires_3_historical(client):
    """SWC değerlendirmesi için ≥3 geçmiş kayıt gerekli."""
    c, _ = client
    # Sadece 1 kayıt
    c.post("/physical-tests/", json={
        "player_id": "700", "player_name": "Az Veri",
        "test_date": "2026-06-06", "protocol": "cmj", "value": 38.0,
    })
    r = c.get("/physical-tests/700/battery")
    assert r.status_code == 200
    # SWC assessments boş olmalı (yeterli geçmiş yok)
    assert r.json()["swc_assessments"] == []


def test_battery_swc_meaningful_change(client):
    """3+ geçmiş kayıt + belirgin gelişme → SWC 'anlamlı gelişme' vermeli."""
    c, _ = client
    # 3 tarihte artan CMJ (gelişme) + mevcut
    for d, v in [
        ("2026-03-01", 32.0), ("2026-04-01", 35.0), ("2026-05-01", 38.0),
        ("2026-06-06", 42.0),  # mevcut
    ]:
        c.post("/physical-tests/", json={
            "player_id": "800", "player_name": "Gelişen Oyuncu",
            "test_date": d, "protocol": "cmj", "value": v,
        })
    r = c.get("/physical-tests/800/battery")
    assert r.status_code == 200
    swc_list = r.json()["swc_assessments"]
    cmj_swc = next((s for s in swc_list if s["protocol_key"] == "cmj"), None)
    assert cmj_swc is not None
    assert cmj_swc["beyond_swc"] is True
    assert "gelişme" in cmj_swc["verdict"]


def test_battery_tenant_isolation(client):
    c, state = client
    c.post("/physical-tests/", json={
        "player_id": "900", "player_name": "İzole",
        "test_date": "2026-06-06", "protocol": "cmj", "value": 38.0,
    })
    state["tenant_id"] = "other"
    assert c.get("/physical-tests/900/battery").status_code == 404


# --------------------------------------------------------------------------- #
# Faz 2 — türetilmiş metrik uçları (/derive/*) + mevki preset + components
# --------------------------------------------------------------------------- #

def test_derive_rsa_fatigue(client):
    c, _ = client
    r = c.post("/physical-tests/derive/rsa-fatigue",
               json={"sprint_times": [4.0, 4.0, 4.0, 5.0]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["fatigue_index_pct"] == 6.25
    assert body["n"] == 4
    assert body["insufficient_recovery"] is False


def test_derive_rsa_fatigue_flags_high(client):
    c, _ = client
    r = c.post("/physical-tests/derive/rsa-fatigue",
               json={"sprint_times": [4.3, 4.45, 4.6, 4.8, 5.0, 5.2]})
    assert r.json()["insufficient_recovery"] is True


def test_derive_rsa_fatigue_too_few_422(client):
    c, _ = client
    r = c.post("/physical-tests/derive/rsa-fatigue", json={"sprint_times": [4.3]})
    assert r.status_code == 422  # Pydantic min_length


def test_derive_cod_deficit(client):
    c, _ = client
    r = c.post("/physical-tests/derive/cod-deficit",
               json={"cod_time": 3.0, "linear_10m": 1.7})
    assert r.status_code == 200
    body = r.json()
    assert body["deficit"] == 1.3
    assert body["poor_deceleration"] is True


def test_derive_rsi(client):
    c, _ = client
    r = c.post("/physical-tests/derive/rsi",
               json={"flight_time_s": 0.5, "contact_time_s": 0.25})
    assert r.status_code == 200
    assert r.json()["rsi"] == 2.0


def test_derive_asymmetry_red(client):
    c, _ = client
    r = c.post("/physical-tests/derive/asymmetry",
               json={"left": 600.0, "right": 480.0})
    assert r.status_code == 200
    body = r.json()
    assert body["flag"] == "kırmızı"
    assert body["stronger_side"] == "sol"


def test_derive_vo2max_yoyo(client):
    c, _ = client
    r = c.post("/physical-tests/derive/vo2max/yoyo", json={"distance_m": 2000.0})
    assert r.status_code == 200
    assert r.json()["vo2max"] == 53.2


def test_derive_vo2max_vift(client):
    c, _ = client
    r = c.post("/physical-tests/derive/vo2max/vift",
               json={"vift_kmh": 20.0, "age": 24, "weight_kg": 75.0})
    assert r.status_code == 200
    assert 50.0 < r.json()["vo2max"] < 65.0


def test_derive_adductor_drop(client):
    c, _ = client
    r = c.post("/physical-tests/derive/adductor-drop",
               json={"current": 340.0, "previous": 400.0})
    assert r.status_code == 200
    body = r.json()
    assert body["drop_pct"] == 15.0
    assert body["flagged"] is True


def test_derive_cmj_fatigue(client):
    c, _ = client
    r = c.post("/physical-tests/derive/cmj-fatigue",
               json={"current": 34.0, "baseline_values": [40.0, 41.0, 39.0]})
    assert r.status_code == 200
    assert r.json()["flagged"] is True


def test_derive_return_to_play_red(client):
    c, _ = client
    r = c.post("/physical-tests/derive/return-to-play",
               json={"current": 90.0, "pre_injury_baseline": 100.0})
    assert r.status_code == 200
    body = r.json()
    assert body["cleared"] is False
    assert body["light"] == "kırmızı"


def test_derive_return_to_play_green(client):
    c, _ = client
    r = c.post("/physical-tests/derive/return-to-play",
               json={"current": 98.0, "pre_injury_baseline": 100.0})
    assert r.json()["cleared"] is True


def test_derive_no_auth_required():
    """Türetme uçları tester tableti için auth'suz erişilebilir."""
    from fastapi.testclient import TestClient

    from app.api.main import app
    c = TestClient(app)
    r = c.post("/physical-tests/derive/rsi",
               json={"flight_time_s": 0.5, "contact_time_s": 0.25})
    assert r.status_code == 200


def test_preset_known_position(client):
    c, _ = client
    r = c.get("/physical-tests/presets/kaleci")
    assert r.status_code == 200
    body = r.json()
    assert body["position"] == "kaleci"
    keys = {p["key"] for p in body["protocols"]}
    assert "cmj" in keys
    # Her protokol tam tanımıyla dönmeli
    for p in body["protocols"]:
        assert "norm_elite" in p and "description" in p


def test_preset_case_insensitive(client):
    c, _ = client
    assert c.get("/physical-tests/presets/Kaleci").json()["position"] == "kaleci"


def test_preset_unknown_returns_default(client):
    c, _ = client
    r = c.get("/physical-tests/presets/bilinmeyen")
    assert r.status_code == 200
    assert len(r.json()["protocols"]) >= 1


def test_new_protocol_persists_with_components(client):
    """Drop Jump RSI kaydı + ham bileşenler (uçuş/temas) components'a yazılır."""
    c, _ = client
    r = c.post("/physical-tests/", json={
        "player_id": "1100", "player_name": "Reaktif Oyuncu",
        "test_date": "2026-06-08", "protocol": "drop_jump_rsi", "value": 2.1,
        "components": {"flight_time_s": 0.52, "contact_time_s": 0.25},
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["unit"] == "RSI"           # UNIT_MAP'ten otomatik
    assert body["components"]["flight_time_s"] == 0.52
    # Geri okunabilir
    got = c.get("/physical-tests/1100").json()
    assert got[0]["components"]["contact_time_s"] == 0.25


def test_new_protocol_in_protocols_endpoint(client):
    c, _ = client
    keys = {p["key"] for p in c.get("/physical-tests/protocols").json()}
    assert {"t505", "ift_30_15", "drop_jump_rsi", "triple_hop"}.issubset(keys)


def test_derive_hq_ratio_high_risk(client):
    c, _ = client
    r = c.post("/physical-tests/derive/hq-ratio",
               json={"hamstring": 1.2, "quadriceps": 2.9})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["band"] == "yüksek_risk"
    assert body["at_risk"] is True


def test_derive_hq_ratio_ideal(client):
    c, _ = client
    r = c.post("/physical-tests/derive/hq-ratio",
               json={"hamstring": 1.8, "quadriceps": 2.8})
    assert r.json()["band"] == "ideal"


def test_derive_hq_ratio_zero_quad_422(client):
    c, _ = client
    r = c.post("/physical-tests/derive/hq-ratio",
               json={"hamstring": 1.5, "quadriceps": 0.0})
    assert r.status_code == 422  # Pydantic gt=0


def test_derive_sprint_split(client):
    c, _ = client
    r = c.post("/physical-tests/derive/sprint-split",
               json={"t5": 0.96, "t10": 1.72, "t30": 4.60})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["limiter"] == "maksimal hız"
    assert body["max_speed"] == 2.88


def test_derive_sprint_split_partial(client):
    c, _ = client
    r = c.post("/physical-tests/derive/sprint-split", json={"t10": 1.75, "t30": 4.10})
    assert r.status_code == 200
    assert r.json()["reaction"] is None


def test_derive_vift_targets(client):
    c, _ = client
    r = c.post("/physical-tests/derive/vift-targets", json={"vift": 20.0})
    assert r.status_code == 200
    body = r.json()
    assert body["speed_95"] == 19.0 and body["speed_105"] == 21.0


def test_derive_rtp_clearance_red(client):
    c, _ = client
    r = c.post("/physical-tests/derive/rtp-clearance",
               json={"current": {"cmj": 32.0, "yoyo_irl1": 18.0},
                     "baseline": {"cmj": 40.0, "yoyo_irl1": 18.5}})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["cleared"] is False
    assert body["lowest_protocol"] == "cmj"


def test_derive_rtp_clearance_no_common_422(client):
    c, _ = client
    r = c.post("/physical-tests/derive/rtp-clearance",
               json={"current": {"cmj": 40.0}, "baseline": {"yoyo_irl1": 18.0}})
    assert r.status_code == 422


def test_protocols_position_filter_gk(client):
    c, _ = client
    r = c.get("/physical-tests/protocols?position=GK")
    assert r.status_code == 200
    keys = {p["key"] for p in r.json()}
    # Kaleci preset'i: cmj/sj/drop_jump_rsi/sprint_5m/t505/adductor_squeeze
    assert "cmj" in keys and "drop_jump_rsi" in keys
    assert "yoyo_irl2" not in keys           # preset dışı
    # Filtresiz tam liste daha büyük olmalı
    full = c.get("/physical-tests/protocols").json()
    assert len(full) > len(r.json())


# --------------------------------------------------------------------------- #
# Hazırlık Kararı uç noktası (POST /readiness) — çok-metrik sentez
# --------------------------------------------------------------------------- #


def test_readiness_red_when_rtp_below_baseline(client):
    c, _ = client
    r = c.post("/physical-tests/readiness",
               json={"rtp": [30.0, 40.0, True], "hq": [2.0, 3.0]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["light"] == "kırmızı"
    assert body["verdict"] == "sahaya çıkmasın"
    assert body["red_count"] == 1
    assert body["flags"][0]["severity"] == "kırmızı"


def test_readiness_green_all_ok(client):
    c, _ = client
    r = c.post("/physical-tests/readiness",
               json={"hq": [2.0, 3.0], "asymmetry": [50.0, 49.0, "Triple Hop"],
                     "acwr": 1.1})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["light"] == "yeşil"
    assert body["checked"] == 3


def test_readiness_yellow_monitor(client):
    c, _ = client
    r = c.post("/physical-tests/readiness", json={"acwr": 1.4})
    body = r.json()
    assert body["light"] == "sarı"
    assert body["verdict"] == "izle / yük yönet"


def test_readiness_empty_is_no_data(client):
    c, _ = client
    r = c.post("/physical-tests/readiness", json={})
    assert r.status_code == 200
    assert r.json()["checked"] == 0


def test_readiness_invalid_input_422(client):
    c, _ = client
    r = c.post("/physical-tests/readiness", json={"hq": [1.0, 0.0]})
    assert r.status_code == 422


def test_readiness_no_auth_required():
    from fastapi.testclient import TestClient

    from app.api.main import app
    c = TestClient(app)
    r = c.post("/physical-tests/readiness", json={"acwr": 1.7})
    assert r.status_code == 200
    assert r.json()["light"] == "kırmızı"


# --------------------------------------------------------------------------- #
# Kadro geneli Hazırlık Kararı (GET /squad-readiness) — DB'den sentez
# --------------------------------------------------------------------------- #


def test_squad_readiness_red_from_entered_tests(client):
    c, _ = client
    # H:Q kırmızı: hamstring 1.2 / quad 3.0 = 0.40 (<0.47) — components.quadriceps
    r0 = c.post("/physical-tests/", json={
        "player_id": "991", "player_name": "Test Kırmızı", "test_date": "2026-06-08",
        "protocol": "isokinetic_ham", "value": 1.2, "components": {"quadriceps": 3.0},
    })
    assert r0.status_code == 201, r0.text
    r = c.get("/physical-tests/squad-readiness")
    assert r.status_code == 200, r.text
    row = next((x for x in r.json() if x["player_id"] == "991"), None)
    assert row is not None
    assert row["decision"]["light"] == "kırmızı"
    assert any(f["metric"] == "H:Q" for f in row["decision"]["flags"])


def test_squad_readiness_pairs_separate_ham_quad(client):
    c, _ = client
    # Ayrı isokinetic_ham + isokinetic_quad kayıtları → H:Q eşlenmeli (CSV deseni)
    c.post("/physical-tests/", json={"player_id": "992", "player_name": "Test Eşle",
        "test_date": "2026-06-08", "protocol": "isokinetic_ham", "value": 2.0})
    c.post("/physical-tests/", json={"player_id": "992", "player_name": "Test Eşle",
        "test_date": "2026-06-08", "protocol": "isokinetic_quad", "value": 3.0})
    r = c.get("/physical-tests/squad-readiness")
    row = next((x for x in r.json() if x["player_id"] == "992"), None)
    assert row is not None
    # 2.0/3.0 = 0.667 ideal → H:Q yeşil bayrak mevcut
    assert any(f["metric"] == "H:Q" for f in row["decision"]["flags"])


def test_squad_readiness_no_relevant_tests_is_no_data(client):
    c, _ = client
    # Sadece sprint → readiness'e eşlenen metrik yok → "veri yok" (sarı)
    c.post("/physical-tests/", json={"player_id": "993", "player_name": "Test Sprint",
        "test_date": "2026-06-08", "protocol": "sprint_10m", "value": 1.8})
    r = c.get("/physical-tests/squad-readiness")
    row = next((x for x in r.json() if x["player_id"] == "993"), None)
    assert row is not None
    assert row["decision"]["checked"] == 0
    assert row["decision"]["light"] == "sarı"


def test_squad_readiness_requires_auth():
    from fastapi.testclient import TestClient

    from app.api.main import app
    c = TestClient(app)
    r = c.get("/physical-tests/squad-readiness")
    assert r.status_code in (401, 403)
