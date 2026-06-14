"""Live decision replay smoke test — script importable, parse_args + tick logic OK."""
from __future__ import annotations

import io
from contextlib import redirect_stdout
from datetime import UTC, datetime, timedelta

from app.db import models
from app.sports import football
from scripts.live_decision_replay import _hr, _parse_args, _tick_panel


def test_parse_args_defaults():
    ns = _parse_args([])
    assert ns.match == 16029
    assert ns.star == 5503
    assert ns.tenant == "t-demo"


def test_parse_args_custom_ticks():
    ns = _parse_args(["--match", "999", "--ticks", "55,75,89"])
    assert ns.match == 999
    assert ns.ticks == "55,75,89"


def test_hr_format():
    assert len(_hr("═", w=70)) == 70


def test_tick_panel_prints_all_sections(session):
    """Mock match + event ile _tick_panel hatasız çalışıp tüm bölümleri basar."""
    session.info["tenant_id"] = "t-demo"
    now = datetime.now(UTC)
    session.add(models.Tenant(
        id="t-demo", slug="t-demo", name="Demo",
        settings_json="{}", active=True, created_at=now,
    ))
    session.add(models.Match(
        sport=football.SPORT_NAME, external_id=99001,
        league_external_id=11, season=2018,
        kickoff=now - timedelta(days=1), status="FT",
        home_team_external_id=11, away_team_external_id=22,
        home_score=1, away_score=2, tenant_id="t-demo",
    ))
    for i in range(40):
        session.add(models.EventRow(
            sport=football.SPORT_NAME, tenant_id="t-demo",
            source="statsbomb_open", source_event_id=f"p{i}",
            match_external_id=99001, team_external_id=11,
            player_external_id=5503, event_type="pass",
            minute=float(40 + i), period=2 if 40 + i >= 45 else 1,
            start_x=50.0, start_y=50.0, end_x=70.0, end_y=50.0,
            outcome="completed", body_part=None, pattern="regular",
            possession_id=i, is_goal=None, key_pass=False,
            raw_json=None, created_at=now,
        ))
    session.commit()
    match = session.query(models.Match).filter_by(
        sport=football.SPORT_NAME, external_id=99001,
    ).one()

    buf = io.StringIO()
    with redirect_stdout(buf):
        _tick_panel(session, match, my_team_id=11, minute=80.0,
                    star_player_id=5503)
    out = buf.getvalue()
    # Tüm engine bölümleri çıktıda var
    for section in ("Momentum", "Sub timing", "Tac trigger", "Risk monitor",
                    "Closing", "Star feed", "Foul pres."):
        assert section in out, f"{section} eksik"
    # Geride 1-2 + 80. dk → closing trailing + late
    assert "Geride" in out
