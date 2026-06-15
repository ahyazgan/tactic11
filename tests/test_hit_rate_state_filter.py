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
