"""Takipten çıkarılan pasların `events` tablosuna yazılması.

Neden ayrı test: pas çıkarımı vardı ama pasları HİÇBİR YERE yazmıyordu —
hesaplanıp JSON'da kalıyorlardı. Dolayısıyla xT / ileri pas / karar etkisi
motorları kulüp videosundan beslenemiyordu. Zincirin bu halkası kopuksa
"kulüp kendi kamerasıyla ölçüm yapabilir" iddiası boştur.

Kritik davranışlar: kaynak AYRIMI (tahmin verisi sağlayıcı verisiyle
karışmamalı), IDEMPOTENS (canlı segment akışında aynı pas iki kez yazılmamalı)
ve canlı akışta ÖNCEKİ segmentlerin korunması.
"""
from __future__ import annotations

import json

from sqlalchemy import select

from app.db import models
from app.sports import football
from scripts.ingest_tracking_json import (
    DERIVED_PASS_SOURCE,
    ingest_derived_passes,
)

MATCH, BIZ, RAKIP = 990500, 217, 213


def _pas(minute: float, frm: int, to: int, *, complete: bool = True) -> dict:
    return {
        "minute": minute, "team_external_id": BIZ,
        "from_player_external_id": frm, "to_player_external_id": to,
        "start_x": 40.0, "start_y": 50.0, "end_x": 60.0, "end_y": 55.0,
        "distance_m": 21.0, "flight_seconds": 0.8,
        "ball_estimated": False, "complete": complete, "estimated": True,
    }


def _tenant(session):
    from datetime import UTC, datetime
    session.add(models.Tenant(
        id="t-test", slug="t-test", name="T", settings_json="{}",
        active=True, created_at=datetime.now(UTC),
    ))
    session.info["tenant_id"] = "t-test"


def _rows(session):
    return session.execute(select(models.EventRow).where(
        models.EventRow.match_external_id == MATCH,
    )).scalars().all()


def test_passes_land_in_events_with_a_distinct_source(session) -> None:
    """Zincirin kopuk halkası: paslar artık motorların okuduğu tabloda."""
    _tenant(session)
    n = ingest_derived_passes(
        session, {"derived_passes": [_pas(10.0, 901, 902), _pas(12.0, 902, 903)]},
        tenant_id="t-test", match_id=MATCH, replace=True,
    )
    session.commit()
    assert n == 2
    rows = _rows(session)
    assert len(rows) == 2
    assert all(r.event_type == "pass" for r in rows)
    # Kaynak AYRI: sağlayıcı verisiyle karışmamalı, istenmezse dışlanabilmeli.
    assert all(r.source == DERIVED_PASS_SOURCE for r in rows)
    assert all(json.loads(r.raw_json)["derived"] is True for r in rows)


def test_incomplete_passes_are_marked_not_dropped(session) -> None:
    """Kesilen pas atılırsa isabet oranı HER ZAMAN %100 çıkar ve veri yalan söyler."""
    _tenant(session)
    ingest_derived_passes(
        session, {"derived_passes": [
            _pas(10.0, 901, 902), _pas(11.0, 901, 903, complete=False),
        ]},
        tenant_id="t-test", match_id=MATCH, replace=True,
    )
    session.commit()
    sonuclar = {r.outcome for r in _rows(session)}
    assert sonuclar == {"completed", "incomplete"}


def test_loader_actually_sees_them_as_completed(session) -> None:
    """SÖZCÜK BİRLİĞİ — bu testin varlık sebebi gerçek bir hata.

    İlk yazımda `outcome="complete"` (d'siz) yazılmıştı. Sağlayıcı ingest'i
    "completed" yazıyor ve loader `completed` alanını ondan türetiyor. Tek
    harflik fark yüzünden çıkarılan HER pas "tamamlanmamış" sayılıyor, xT
    SESSİZCE sıfır çıkıyordu — özellik çalışıyor görünüp hiçbir şey üretmiyordu.

    Bu yüzden test sabit metne değil, LOADER'IN GÖRDÜĞÜNE bakar.
    """
    from app.data.loaders import load_match_events

    _tenant(session)
    ingest_derived_passes(
        session, {"derived_passes": [
            _pas(10.0, 901, 902), _pas(11.0, 901, 903, complete=False),
        ]},
        tenant_id="t-test", match_id=MATCH, replace=True,
    )
    session.commit()

    yuklenen = load_match_events(session, MATCH)
    paslar = list(yuklenen.passes)
    assert len(paslar) == 2
    assert sum(1 for x in paslar if x.completed) == 1,         "loader tamamlanan pası görmüyor — sözcük ayrışmış"


def test_reingest_is_idempotent(session) -> None:
    """Aynı segment yeniden işlenirse pas ÇİFTLENMEMELİ."""
    _tenant(session)
    veri = {"derived_passes": [_pas(10.0, 901, 902)]}
    ingest_derived_passes(session, veri, tenant_id="t-test", match_id=MATCH,
                          replace=False)
    session.commit()
    ikinci = ingest_derived_passes(session, veri, tenant_id="t-test",
                                   match_id=MATCH, replace=False)
    session.commit()
    assert ikinci == 0
    assert len(_rows(session)) == 1


def test_append_mode_keeps_earlier_segments(session) -> None:
    """CANLI akışta önceki segmentlerin pasları SİLİNMEMELİ.

    `replace=True` canlı yolda çağrılsaydı her yeni segment, maçın o ana kadarki
    tüm paslarını yok ederdi.
    """
    _tenant(session)
    ingest_derived_passes(session, {"derived_passes": [_pas(10.0, 901, 902)]},
                          tenant_id="t-test", match_id=MATCH, replace=False)
    ingest_derived_passes(session, {"derived_passes": [_pas(20.0, 903, 904)]},
                          tenant_id="t-test", match_id=MATCH, replace=False)
    session.commit()
    assert len(_rows(session)) == 2


def test_replace_mode_clears_only_derived_passes(session) -> None:
    """Tam-video yeniden ingest'i SAĞLAYICI event'lerine dokunmamalı."""
    from datetime import UTC, datetime
    _tenant(session)
    session.add(models.EventRow(
        sport=football.SPORT_NAME, tenant_id="t-test", source="statsbomb_open",
        source_event_id="gercek-1", match_external_id=MATCH,
        team_external_id=BIZ, player_external_id=5, event_type="shot",
        minute=30.0, period=1, created_at=datetime.now(UTC),
    ))
    ingest_derived_passes(session, {"derived_passes": [_pas(10.0, 901, 902)]},
                          tenant_id="t-test", match_id=MATCH, replace=False)
    session.commit()

    ingest_derived_passes(session, {"derived_passes": [_pas(15.0, 905, 906)]},
                          tenant_id="t-test", match_id=MATCH, replace=True)
    session.commit()
    rows = _rows(session)
    assert {r.source for r in rows} == {"statsbomb_open", DERIVED_PASS_SOURCE}
    assert sum(1 for r in rows if r.source == DERIVED_PASS_SOURCE) == 1


def test_no_passes_is_not_an_error(session) -> None:
    """Sabit kamera videosunda pas çıkmayabilir; hat çökmemeli."""
    _tenant(session)
    assert ingest_derived_passes(session, {}, tenant_id="t-test",
                                 match_id=MATCH, replace=True) == 0


def test_explicit_empty_replace_clears_stale_passes_but_absent_key_preserves(session):
    _tenant(session)
    ingest_derived_passes(session, {"derived_passes": [_pas(10, 1, 2)]},
                          tenant_id="t-test", match_id=MATCH, replace=False)
    session.commit()
    ingest_derived_passes(session, {}, tenant_id="t-test", match_id=MATCH, replace=True)
    assert len(_rows(session)) == 1
    ingest_derived_passes(session, {"derived_passes": []}, tenant_id="t-test", match_id=MATCH, replace=True)
    assert not _rows(session)


def test_stoppage_time_period_and_estimated_provenance_survive_loader(session):
    from app.data.loaders import load_match_events
    _tenant(session)
    ingest_derived_passes(session, {"derived_passes": [{**_pas(47, 1, 2), "period": 1}]},
                          tenant_id="t-test", match_id=MATCH, replace=False)
    session.commit()
    p = load_match_events(session, MATCH).passes[0]
    assert p.period == 1 and p.estimated


def test_recovery_ingest_loader_and_engine_coverage_contract(session):
    from dataclasses import asdict

    from app.data.loaders import load_match_events
    from app.engine.ppda.compute import compute_ppda
    from app.engine.spatial_control.compute import compute_spatial_control
    from app.tracking.recoveries import DerivedDefensiveAction
    from scripts.ingest_tracking_json import DERIVED_DEFENSE_SOURCE, ingest_derived_defenses

    _tenant(session)
    event = DerivedDefensiveAction(minute=47, period=1, team_external_id=RAKIP,
                                  player_external_id=2, previous_player_external_id=1,
                                  previous_team_external_id=BIZ, x=50, y=50,
                                  control_seconds=.3, flight_seconds=.2)
    payload = {"derived_defensive_actions": [asdict(event), asdict(event)]}
    args = {"tenant_id": "t-test", "match_id": MATCH, "replace": False}
    assert ingest_derived_defenses(session, payload, **args) == 1
    session.commit()
    assert ingest_derived_defenses(session, payload, **args) == 0
    loaded = load_match_events(session, MATCH).defensive_actions
    assert len(loaded) == 1 and loaded[0].estimated and loaded[0].period == 1
    assert _rows(session)[0].source == DERIVED_DEFENSE_SOURCE
    assert compute_ppda(RAKIP, [], loaded).value.team_def_actions_in_press_zone == 0
    spatial = compute_spatial_control(BIZ, RAKIP, [], loaded, current_minute=48).value
    assert spatial.note and not spatial.gap_between_lines and spatial.superiority_flank is None
    # Separate event sources: replacing recovery output preserves passes.
    ingest_derived_passes(session, {"derived_passes": [_pas(10, 1, 2)]}, **args)
    session.commit()
    ingest_derived_defenses(session, {"derived_defensive_actions": []}, **{**args, "replace": True})
    session.commit()
    assert len(_rows(session)) == 1 and _rows(session)[0].source == DERIVED_PASS_SOURCE
