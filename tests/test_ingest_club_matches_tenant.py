"""A misspelled/import-only tenant ID must never create orphan match data."""
import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.db import models
from scripts import ingest_club_matches


@pytest.mark.parametrize("exists", [False, True])
def test_import_requires_existing_tenant(session, tmp_path, monkeypatch, capsys, exists):
    if exists:
        session.add(models.Tenant(id="import-club", slug="import-club", name="Import test", active=False,
                                  settings_json="{}", created_at=datetime.now(UTC)))
        session.commit()
    matches = tmp_path / "matches.json"
    matches.write_text(json.dumps([{
        "match_id": 123, "match_date": "2026-10-10", "competition": {"competition_id": 7},
        "season": {"season_id": 27}, "home_team": {"home_team_id": 131}, "away_team": {"away_team_id": 1},
    }]))
    (tmp_path / "123.json").write_text("[]")
    monkeypatch.setattr(ingest_club_matches, "SessionLocal", sessionmaker(bind=session.get_bind()))
    monkeypatch.setattr(ingest_club_matches, "LocalStatsBomb", lambda path: object())
    monkeypatch.setattr(ingest_club_matches, "ingest_events_for_match", lambda *args, **kwargs: SimpleNamespace(rows_inserted=0))
    monkeypatch.setattr("sys.argv", ["ingest_club_matches", "--tenant", "import-club", "--team", "131",
                                    "--matches", str(matches), "--events-dir", str(tmp_path)])
    assert ingest_club_matches.main() == (0 if exists else 2)
    row = session.scalar(select(models.Match).where(models.Match.tenant_id == "import-club"))
    assert (row is not None) is exists
    if not exists:
        assert "Kulüp kaydı bulunamadı" in capsys.readouterr().err
