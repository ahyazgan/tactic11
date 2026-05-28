"""engine.vaep.train — tabular ML training tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.db import models
from app.domain import PassEvent
from app.engine.vaep import (
    CACHE_KEY,
    CACHE_SOURCE,
    NotEnoughTrainingData,
    compute_vaep,
    train_vaep_model,
)
from app.engine.vaep.train import _zone_id
from app.sports import football


def _seed_tenant(session, tenant_id: str = "t-default"):
    session.add(models.Tenant(
        id=tenant_id, slug=tenant_id, name="X",
        settings_json="{}", active=True, created_at=datetime.now(UTC),
    ))
    session.flush()


def _add_event(session, *, match_id: int, ev_type: str, team: int,
               player: int = 1, sb_id: str = "e1", minute: float = 10.0,
               start_x: float = 50.0, start_y: float = 50.0,
               end_x: float = 60.0, end_y: float = 50.0,
               pattern: str = "regular", outcome: str = "completed",
               is_goal: bool = False, poss: int | None = None,
               tenant: str = "t-default"):
    session.add(models.EventRow(
        sport=football.SPORT_NAME, tenant_id=tenant,
        source="statsbomb_open", source_event_id=sb_id,
        match_external_id=match_id, team_external_id=team,
        player_external_id=player, event_type=ev_type,
        minute=minute, period=1,
        start_x=start_x, start_y=start_y, end_x=end_x, end_y=end_y,
        outcome=outcome if ev_type != "shot" else ("goal" if is_goal else None),
        body_part="right_foot" if ev_type == "shot" else None,
        pattern=pattern, possession_id=poss,
        is_goal=is_goal if ev_type == "shot" else None,
        key_pass=False, raw_json=None,
        created_at=datetime.now(UTC),
    ))


def test_zone_id_grid_corners():
    assert _zone_id(0, 0) == 0
    assert _zone_id(99, 99) == (4 - 1) * 3 + (3 - 1)  # 11
    # Saha ortası: x=50 → bin=2; y=50 → bin=1; 2*3+1=7
    assert _zone_id(50, 50) == 7


def test_train_raises_when_not_enough_data(session):
    _seed_tenant(session)
    with pytest.raises(NotEnoughTrainingData):
        train_vaep_model(session, tenant_id="t-default", min_samples=10)


def test_train_writes_cache_with_lookups(session):
    _seed_tenant(session)
    # 150 pass + bir kaç gol
    for i in range(150):
        _add_event(
            session, match_id=99, ev_type="pass", team=11,
            sb_id=f"p{i}", minute=float(i % 90),
            start_x=20 + (i % 50), start_y=30 + (i % 30),
            end_x=40 + (i % 50), end_y=40,
            poss=i // 5,
        )
    # Bir kaç gol (label_score için)
    for i in range(5):
        _add_event(
            session, match_id=99, ev_type="shot", team=11,
            sb_id=f"s{i}", minute=float(10 + i * 15),
            start_x=90, start_y=50, end_x=100, end_y=50,
            pattern="open_play", is_goal=True, poss=i,
        )
    session.commit()

    report = train_vaep_model(
        session, tenant_id="t-default", min_samples=50,
    )
    assert report.sample_count >= 50
    assert report.zones == 12
    assert report.cache_written is True
    assert len(report.score_lookup) == 12
    assert all(0.0 <= v <= 1.0 for v in report.score_lookup.values())


def test_compute_vaep_uses_trained_model(session):
    """Trained model verilirse model_version 2-tabular."""
    _seed_tenant(session)
    # Tabular lookup: zone 11'de score yüksek, zone 0'da düşük
    trained = {
        "score_lookup": {str(i): 0.1 if i < 6 else 0.4 for i in range(12)},
        "concede_lookup": {str(i): 0.05 for i in range(12)},
        "zone_x_bins": 4, "zone_y_bins": 3,
    }
    p = PassEvent(
        sport="football", match_external_id=99, player_external_id=1,
        team_external_id=11, minute=10.0, period=1,
        start_x=10, start_y=50, end_x=90, end_y=50,  # zone 1 → zone 10
    )
    r = compute_vaep(
        team_external_id=11, all_passes=[p], all_carries=[], all_shots=[],
        trained_model=trained,
    ).value
    # Trained model'le score artmalı (yüksek zone'da bittiği için)
    assert r.model_version == "2-tabular"
    assert r.vaep_value > 0


def test_compute_vaep_baseline_when_no_model(session):
    """Default: model_version=1-baseline."""
    p = PassEvent(
        sport="football", match_external_id=99, player_external_id=1,
        team_external_id=11, minute=10.0, period=1,
        start_x=20, start_y=50, end_x=80, end_y=50,
    )
    r = compute_vaep(
        team_external_id=11, all_passes=[p], all_carries=[], all_shots=[],
    ).value
    assert r.model_version == "1-baseline"


def test_cache_key_constants_stable():
    """CACHE_SOURCE + CACHE_KEY API'si stable."""
    assert CACHE_SOURCE == "vaep_model"
    assert CACHE_KEY == "tabular_v1"
