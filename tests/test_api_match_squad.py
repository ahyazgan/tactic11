"""Canlı kadro girişi: video hattı ile karar hattını bağlayan eksik halka.

Testler dört şeyi kilitler:
1. Kadro girilmeden `subs_used`/`sahada` boştur ve uç nokta bunu UYARI olarak
   söyler — sessizce boş öneri döndürmek en kötü davranıştır.
2. Aynı dakikadaki iki değişiklik İKİ hak kullanır (tekilleştirme yok).
3. Giren oyuncu çıkanın mevkisini devralır — `coach_iq` ve `validate_who_prior`
   aynı kuralı kullanıyor, canlı kayıt ile ölçüm aynı dünyayı anlatmalı.
4. Öneriyle uyuşma GÖZLEM olarak döner ama `applied` işaretini TÜRETMEZ.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.db import models
from app.db.session import get_session


@pytest.fixture
def client(session):
    session.info["tenant_id"] = "t-default"

    def _override():
        yield session

    app.dependency_overrides[get_session] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def match(session):
    row = models.Match(
        sport="football", external_id=7001, tenant_id="t-default",
        league_external_id=1, season=2026,
        home_team_external_id=11, away_team_external_id=22,
        kickoff=datetime(2026, 9, 14, 18, 0, tzinfo=UTC), status="live",
    )
    session.add(row)
    session.commit()
    return row


def _lineup(client, minute: float = 0.0, ids: range | None = None) -> dict:
    ids = ids or range(1, 12)
    positions = ["GK"] + ["DC"] * 4 + ["MC"] * 3 + ["FC"] * 3
    return client.put("/admin/matches/7001/lineup", json={
        "team_external_id": 11, "minute": minute,
        "starters": [{"player_external_id": p, "position": pos}
                     for p, pos in zip(ids, positions, strict=True)],
    }).json()


def test_squad_state_warns_loudly_when_no_lineup_was_entered(client, match) -> None:
    """Kadro yoksa uç nokta susmaz: iki tablonun devre dışı olduğunu söyler."""
    r = client.get("/admin/matches/7001/squad-state",
                   params={"team_external_id": 11, "minute": 60}).json()
    assert r["kadro_girildi"] is False
    assert r["sahada"] == []
    assert r["kullanilmis_hak"] == 0
    assert r["uyari"] is not None
    assert "devre dışı" in r["uyari"]


def test_lineup_then_substitution_drives_subs_used(client, match) -> None:
    out = _lineup(client)
    assert out["ilk11"] == 11
    assert out["kullanilmis_hak"] == 0
    assert sorted(out["sahada"]) == list(range(1, 12))

    sub = client.post("/admin/matches/7001/substitution", json={
        "team_external_id": 11, "minute": 62, "player_off": 9, "player_on": 20,
    }).json()
    assert sub["kullanilmis_hak"] == 1
    assert 9 not in sub["sahada"]           # yarı açık aralık: çıkış dakikasında dışarıda
    assert 20 in sub["sahada"]              # giriş dakikasında içeride
    state = client.get("/admin/matches/7001/squad-state",
                       params={"team_external_id": 11, "minute": 70}).json()
    assert state["kadro_girildi"] is True
    assert state["kullanilmis_hak"] == 1
    assert 20 in state["sahada"] and 9 not in state["sahada"]
    assert state["uyari"] is None


def test_two_substitutions_in_the_same_minute_use_two_slots(client, match) -> None:
    """Aynı dakikadaki iki oyuncu iki hak kullanır — hak sayımının temel kuralı."""
    _lineup(client)
    for off, on in ((9, 20), (10, 21)):
        client.post("/admin/matches/7001/substitution", json={
            "team_external_id": 11, "minute": 70, "player_off": off, "player_on": on,
        })
    state = client.get("/admin/matches/7001/squad-state",
                       params={"team_external_id": 11, "minute": 75}).json()
    assert state["kullanilmis_hak"] == 2
    assert len(state["sahada"]) == 11


def test_incoming_player_inherits_the_position_of_the_one_going_off(client, match) -> None:
    """Ölçüm tarafındaki kural (coach_iq, validate_who_prior) burada da geçerli."""
    _lineup(client)
    client.post("/admin/matches/7001/substitution", json={
        "team_external_id": 11, "minute": 60, "player_off": 2, "player_on": 30,
    })
    state = client.get("/admin/matches/7001/squad-state",
                       params={"team_external_id": 11, "minute": 65}).json()
    assert state["mevkiler"]["30"] == "DC"
    # açıkça verilirse devralma olmaz
    client.post("/admin/matches/7001/substitution", json={
        "team_external_id": 11, "minute": 65, "player_off": 3, "player_on": 31,
        "position": "MC",
    })
    state = client.get("/admin/matches/7001/squad-state",
                       params={"team_external_id": 11, "minute": 70}).json()
    assert state["mevkiler"]["31"] == "MC"


def test_substitution_reports_agreement_but_never_sets_applied(client, match, session) -> None:
    """Uyuşma GÖZLEMdir; `applied` koçun beyanıdır ve buradan türetilmez.

    Koçun zaten yapacağı değişikliği "listemizde vardı" diye uygulanmış saymak,
    ölçülmek istenen nedenselliği uydurmak olurdu.
    """
    _lineup(client)
    decision = models.Decision(
        sport="football", tenant_id="t-default", match_external_id=7001,
        team_external_id=11, minute=58.0, period=2, decision_type="substitution",
        recommended=True, created_at=datetime.now(UTC),
        context_json=json.dumps({"sub_candidates": [7, 9, 4]}),
    )
    session.add(decision)
    session.commit()

    out = client.post("/admin/matches/7001/substitution", json={
        "team_external_id": 11, "minute": 62, "player_off": 9, "player_on": 20,
    }).json()
    matched = out["oneriyle_uyusma"]["aday_listesinde_gecen_oneri"]
    assert len(matched) == 1
    assert matched[0]["decision_id"] == decision.id
    assert matched[0]["sira"] == 2          # listenin ikinci adayıydı
    assert matched[0]["applied"] is None    # ve işaret HÂLÂ boş

    session.refresh(decision)
    assert decision.applied is None
    assert decision.applied_at is None


def test_substitution_refuses_unknown_or_repeated_players(client, match) -> None:
    _lineup(client)
    unknown = client.post("/admin/matches/7001/substitution", json={
        "team_external_id": 11, "minute": 60, "player_off": 99, "player_on": 20,
    })
    assert unknown.status_code == 400
    assert "lineup" in unknown.json()["detail"]

    client.post("/admin/matches/7001/substitution", json={
        "team_external_id": 11, "minute": 60, "player_off": 9, "player_on": 20,
    })
    twice = client.post("/admin/matches/7001/substitution", json={
        "team_external_id": 11, "minute": 75, "player_off": 9, "player_on": 21,
    })
    assert twice.status_code == 409
    back_on = client.post("/admin/matches/7001/substitution", json={
        "team_external_id": 11, "minute": 75, "player_off": 8, "player_on": 20,
    })
    assert back_on.status_code == 409


def test_lineup_feeds_the_live_decision_panel(client, match, session) -> None:
    """Asıl amaç: kadro girilince panel kadro-farkında hale gelmeli."""
    from app.data.loaders.appearances import load_match_appearances

    _lineup(client)
    client.post("/admin/matches/7001/substitution", json={
        "team_external_id": 11, "minute": 62, "player_off": 9, "player_on": 20,
    })
    apps = load_match_appearances(session, 7001)
    assert len(apps) == 12                      # 11 + giren
    on_at_70 = [a for a in apps
                if a.start_minute <= 70 and (a.end_minute is None or a.end_minute >= 70)]
    assert len(on_at_70) == 11
    assert 20 in {a.player_external_id for a in on_at_70}


# --- maç içi yük girişi ------------------------------------------------------- #

def test_load_samples_are_cumulative_and_upserted(client, match, session) -> None:
    """Aynı oyuncu+dakika ikinci kez yazılınca yeni satır açılmaz, güncellenir."""
    from app.db.match_load import MatchLoadSample

    body = {
        "team_external_id": 11, "source": "gps",
        "speed_thresholds": "hsr>5.5,sprint>7.0 m/s",
        "samples": [
            {"player_external_id": 5, "minute": 30, "total_distance_m": 3100.0,
             "high_speed_m": 240.0},
            {"player_external_id": 5, "minute": 60, "total_distance_m": 6200.0,
             "high_speed_m": 480.0},
        ],
    }
    first = client.post("/admin/matches/7001/load-samples", json=body).json()
    assert first["yazilan"] == 2
    assert first["oyuncu"] == 1
    assert first["kaynak"] == "gps"

    body["samples"][1]["total_distance_m"] = 6400.0
    again = client.post("/admin/matches/7001/load-samples", json=body).json()
    assert again["maçtaki_toplam_ornek"] == 2      # yeni satır açılmadı
    rows = session.query(MatchLoadSample).order_by(MatchLoadSample.minute).all()
    assert [r.minute for r in rows] == [30.0, 60.0]
    assert rows[1].total_distance_m == 6400.0
    assert rows[0].speed_thresholds == "hsr>5.5,sprint>7.0 m/s"


def test_load_samples_reject_an_unknown_source(client, match) -> None:
    """Kaynak yalnız 'gps' ya da 'tracking' olabilir — ikisi ayrı güvende."""
    bad = client.post("/admin/matches/7001/load-samples", json={
        "team_external_id": 11, "source": "tahmin",
        "samples": [{"player_external_id": 5, "minute": 30, "total_distance_m": 100.0}],
    })
    assert bad.status_code == 422


def test_load_samples_need_an_existing_match(client) -> None:
    missing = client.post("/admin/matches/999999/load-samples", json={
        "team_external_id": 11, "source": "gps",
        "samples": [{"player_external_id": 5, "minute": 30, "total_distance_m": 100.0}],
    })
    assert missing.status_code == 404


# --- karşı-olgu paydası ve kapsama -------------------------------------------- #

def _rec(client, minute: float, applied=None, dtype="substitution") -> dict:
    return client.post("/admin/matches/7001/decisions", json={
        "team_external_id": 11, "minute": minute, "period": 2,
        "decision_type": dtype, "recommended": True, "applied": applied,
        "notes": "öneri",
    }).json()


def test_repeated_display_of_one_recommendation_does_not_inflate_the_denominator(
    client, match,
) -> None:
    """Canlı panel aynı öneriyi dakika ilerledikçe tekrar yazar; payda şişmemeli."""
    first = _rec(client, 60.0)
    assert first["guncellendi"] is False
    for minute in (61.0, 62.5, 64.0):
        again = _rec(client, minute)
        assert again["guncellendi"] is True
        assert again["id"] == first["id"]
    cov = client.get("/admin/matches/7001/decision-coverage",
                     params={"team_external_id": 11}).json()
    assert cov["gosterilen_oneri"] == 1
    # pencere dışına çıkınca yeni öneri sayılır
    later = _rec(client, 80.0)
    assert later["guncellendi"] is False
    assert later["id"] != first["id"]


def test_a_mark_is_never_erased_by_a_later_display(client, match) -> None:
    """Koç işaretledikten sonra gelen gösterim kaydı işareti null'a çevirmemeli."""
    shown = _rec(client, 60.0, applied=None)
    marked = _rec(client, 61.0, applied=True)
    assert marked["id"] == shown["id"] and marked["applied"] is True
    again = _rec(client, 62.0, applied=None)
    assert again["id"] == shown["id"]
    assert again["applied"] is True          # beyan korunur


def test_coverage_warns_when_most_recommendations_went_unanswered(client, match) -> None:
    """Kapsama düşükse uç nokta susmaz: örnek kendi kendini seçmiş olur."""
    _rec(client, 20.0, applied=True)
    for minute in (40.0, 60.0, 80.0):
        _rec(client, minute, applied=None)
    cov = client.get("/admin/matches/7001/decision-coverage",
                     params={"team_external_id": 11}).json()
    assert cov["gosterilen_oneri"] == 4
    assert cov["cevaplanan"] == 1
    assert cov["cevapsiz"] == 3
    assert cov["kapsama"] == 0.25
    assert cov["uyari"] is not None and "kapsama düşük" in cov["uyari"]


def test_coverage_is_quiet_when_both_arms_are_answered(client, match) -> None:
    _rec(client, 20.0, applied=True)
    _rec(client, 40.0, applied=False)
    cov = client.get("/admin/matches/7001/decision-coverage",
                     params={"team_external_id": 11}).json()
    assert cov["kapsama"] == 1.0
    assert cov["uygulandi"] == 1 and cov["uygulanmadi"] == 1
    assert cov["uyari"] is None


# --- kırmızı kart ------------------------------------------------------------- #

def test_dismissal_removes_the_player_without_spending_a_slot(client, match) -> None:
    """Kırmızı kart sahadan düşürür ama DEĞİŞİKLİK HAKKI harcamaz."""
    _lineup(client)
    client.post("/admin/matches/7001/substitution", json={
        "team_external_id": 11, "minute": 55, "player_off": 9, "player_on": 20,
    })
    out = client.post("/admin/matches/7001/dismissal", json={
        "team_external_id": 11, "minute": 70, "player_external_id": 4,
    }).json()
    assert out["kullanilmis_hak"] == 1          # değişiklik sayısı değişmedi
    assert out["hak_degisti_mi"] is False
    assert out["sahadaki_sayi"] == 10           # atılan oyuncu O ANDA düşer
    assert 4 not in out["sahada"]

    state = client.get("/admin/matches/7001/squad-state",
                       params={"team_external_id": 11, "minute": 80}).json()
    assert state["sahadaki_sayi"] == 10
    assert state["atilan"] == [4]
    assert state["kullanilmis_hak"] == 1


def test_dismissed_player_cannot_be_substituted_afterwards(client, match) -> None:
    """Atılan oyuncu sahada görünmemeli; motor onu 'çıkar' diye öneremez."""
    _lineup(client)
    client.post("/admin/matches/7001/dismissal", json={
        "team_external_id": 11, "minute": 60, "player_external_id": 7,
    })
    again = client.post("/admin/matches/7001/substitution", json={
        "team_external_id": 11, "minute": 70, "player_off": 7, "player_on": 20,
    })
    assert again.status_code == 409


def test_dismissal_refuses_unknown_or_repeated_players(client, match) -> None:
    _lineup(client)
    unknown = client.post("/admin/matches/7001/dismissal", json={
        "team_external_id": 11, "minute": 60, "player_external_id": 99,
    })
    assert unknown.status_code == 400
    client.post("/admin/matches/7001/dismissal", json={
        "team_external_id": 11, "minute": 60, "player_external_id": 6,
    })
    twice = client.post("/admin/matches/7001/dismissal", json={
        "team_external_id": 11, "minute": 75, "player_external_id": 6,
    })
    assert twice.status_code == 409


def test_dismissal_is_visible_to_the_live_decision_squad_awareness(client, match, session) -> None:
    """Kadro farkındalığı 10 kişiyi görmeli — yoksa panel 11'e bakıyormuş gibi davranır."""
    from app.data.loaders.appearances import load_match_appearances
    from app.engine.live_lineup import resolve_on_pitch

    _lineup(client)
    client.post("/admin/matches/7001/dismissal", json={
        "team_external_id": 11, "minute": 60, "player_external_id": 3,
    })
    apps = load_match_appearances(session, 7001)
    on_pitch = resolve_on_pitch(apps, 75.0, team_external_id=11)
    assert len(on_pitch.player_ids) == 10
    assert 3 not in on_pitch.player_ids


def test_squad_state_matches_the_engine_on_pitch_rule(client, match, session) -> None:
    """Uç nokta ile motor AYNI kadroyu döndürmeli — özellikle sınır dakikalarda.

    İki ayrı sözleşme tutmak (kapalı vs yarı açık aralık) aynı dakikada farklı
    kadro demekti. Bu test ikisini birbirine kilitler.
    """
    from app.data.loaders.appearances import load_match_appearances
    from app.engine.live_lineup import resolve_on_pitch

    _lineup(client)
    client.post("/admin/matches/7001/substitution", json={
        "team_external_id": 11, "minute": 62, "player_off": 9, "player_on": 20,
    })
    client.post("/admin/matches/7001/dismissal", json={
        "team_external_id": 11, "minute": 70, "player_external_id": 3,
    })
    apps = load_match_appearances(session, 7001)
    for minute in (0.0, 30.0, 61.0, 62.0, 63.0, 69.0, 70.0, 71.0, 90.0):
        api = client.get("/admin/matches/7001/squad-state",
                         params={"team_external_id": 11, "minute": minute}).json()
        engine = resolve_on_pitch(apps, minute, team_external_id=11)
        assert set(api["sahada"]) == set(engine.player_ids), f"{minute}. dakikada ayrışma"
