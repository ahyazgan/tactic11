"""context_pipeline._hit_rate state-filtered behavior."""
from __future__ import annotations

import json
from datetime import UTC, datetime

from app.api.context_pipeline import _hit_rate
from app.db import models
from app.sports import football


def _seed(session, *, team_id: int, decisions: list[dict]):
    session.add(models.Tenant(
        id="t-test", slug="t-test", name="T",
        settings_json="{}", active=True,
        created_at=datetime.now(UTC),
    ))
    for d in decisions:
        ctx = d.get("context") or {}
        session.add(models.Decision(
            sport=football.SPORT_NAME, tenant_id="t-test",
            match_external_id=d.get("match_id", 100),
            team_external_id=team_id, minute=d.get("minute", 70.0),
            period=2, decision_type=d.get("type", "tactical_instruction"),
            outcome=d.get("outcome", "positive"),
            context_json=json.dumps(ctx) if ctx else None,
            created_at=datetime.now(UTC),
        ))
    session.commit()


def test_no_filter_aggregates_all(session):
    session.info["tenant_id"] = "t-test"
    _seed(session, team_id=11, decisions=[
        {"type": "tactical_instruction", "outcome": "positive"},
        {"type": "tactical_instruction", "outcome": "positive"},
        {"type": "tactical_instruction", "outcome": "negative"},
    ])
    out = _hit_rate(session, 11)
    # tactical → "tactical","spatial","matchup" spread
    assert "tactical" in out
    # 2 pos / 3 = 0.667
    assert abs(out["tactical"] - 0.667) < 0.01


def test_state_filter_isolates_trailing(session):
    """trailing pozitif × 3, leading negatif × 2 → trailing filter %100."""
    session.info["tenant_id"] = "t-test"
    _seed(session, team_id=11, decisions=[
        {"type": "tactical_instruction", "outcome": "positive",
         "context": {"score_state": "trailing"}},
        {"type": "tactical_instruction", "outcome": "positive",
         "context": {"score_state": "trailing"}},
        {"type": "tactical_instruction", "outcome": "positive",
         "context": {"score_state": "trailing"}},
        {"type": "tactical_instruction", "outcome": "negative",
         "context": {"score_state": "leading"}},
        {"type": "tactical_instruction", "outcome": "negative",
         "context": {"score_state": "leading"}},
    ])
    trailing = _hit_rate(session, 11, score_state="trailing")
    leading = _hit_rate(session, 11, score_state="leading")
    assert trailing["tactical"] == 1.0
    assert leading["tactical"] == 0.0


def test_state_filter_no_matches_returns_empty(session):
    session.info["tenant_id"] = "t-test"
    _seed(session, team_id=11, decisions=[
        {"type": "tactical_instruction", "outcome": "positive",
         "context": {"score_state": "trailing"}},
    ])
    out = _hit_rate(session, 11, score_state="leading")
    assert out == {}


def test_state_filter_skips_rows_with_no_context_json(session):
    """context_json yoksa state filter onları atlar."""
    session.info["tenant_id"] = "t-test"
    _seed(session, team_id=11, decisions=[
        {"type": "tactical_instruction", "outcome": "positive"},  # context yok
        {"type": "tactical_instruction", "outcome": "positive",
         "context": {"score_state": "leading"}},
    ])
    out = _hit_rate(session, 11, score_state="leading")
    assert "tactical" in out
    assert out["tactical"] == 1.0  # sadece leading row sayıldı


# --- sinyal tipine özel oran (ölçümle bulunan kusur) ----------------------- #

def test_signal_type_rate_overrides_the_coarse_spread(session):
    """ASIL KUSUR: kaba yayma zıt durumlara AYNI oranı veriyordu.

    `_HITRATE_SPREAD` tek bir decision_type oranını "tactical, spatial,
    matchup, momentum_us, momentum_opp"un HEPSİNE dağıtıyordu. Oysa gerçek
    veride ölçüldü (n=437): momentum_opp %44 tutuyor, momentum_us %21.
    Tek kovaya koymak bu farkı öğrenilemez kılıyordu — sistem zıt iki durumu
    aynı güvenle sunuyordu.
    """
    session.info["tenant_id"] = "t-test"
    kararlar = []
    # momentum_opp: 12 karar, 9'u olumlu (%75)
    for i in range(12):
        kararlar.append({"type": "tactical_instruction", "match_id": 200 + i,
                         "outcome": "positive" if i < 9 else "negative",
                         "context": {"signal_type": "momentum_opp"}})
    # momentum_us: 12 karar, 3'ü olumlu (%25)
    for i in range(12):
        kararlar.append({"type": "tactical_instruction", "match_id": 300 + i,
                         "outcome": "positive" if i < 3 else "negative",
                         "context": {"signal_type": "momentum_us"}})
    _seed(session, team_id=11, decisions=kararlar)

    out = _hit_rate(session, 11)
    assert out["momentum_opp"] == 0.75
    assert out["momentum_us"] == 0.25
    # Kaba oran (24 kararın 12'si olumlu = %50) ince oranı EZMEMELİ
    assert out["momentum_opp"] != out["momentum_us"]


def test_thin_signal_type_keeps_the_coarse_rate(session):
    """Az örnekte ince orana geçilmez: n=2'lik bir tip %0 der ve güveni uçurur."""
    session.info["tenant_id"] = "t-test"
    kararlar = [
        {"type": "tactical_instruction", "match_id": 400,
         "outcome": "negative", "context": {"signal_type": "momentum_us"}},
        {"type": "tactical_instruction", "match_id": 401,
         "outcome": "negative", "context": {"signal_type": "momentum_us"}},
    ]
    # kaba havuzu doldur (hepsi olumlu)
    kararlar += [{"type": "tactical_instruction", "match_id": 500 + i,
                  "outcome": "positive"} for i in range(8)]
    _seed(session, team_id=11, decisions=kararlar)

    out = _hit_rate(session, 11)
    # 2 örnek eşiğin altında → %0 değil, kaba oran (8/10 = %80) korunur
    assert out["momentum_us"] == 0.8


def test_rows_without_signal_type_still_feed_the_coarse_rate(session):
    """Eski kayıtlarda `signal_type` yok — geri besleme yine de çalışmalı."""
    session.info["tenant_id"] = "t-test"
    _seed(session, team_id=11, decisions=[
        {"type": "tactical_instruction", "outcome": "positive", "match_id": 600},
        {"type": "tactical_instruction", "outcome": "negative", "match_id": 601},
    ])
    out = _hit_rate(session, 11)
    assert out["tactical"] == 0.5
    assert out["momentum_us"] == 0.5    # kaba yayma yeni tiplere de ulaşır
