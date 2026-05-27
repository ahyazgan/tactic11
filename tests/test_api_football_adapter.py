"""APIFootball adapter testleri.

Fixture/HTTP davranışı sync_league smoke testi ile dolaylı kontrol ediliyor;
buradaki testler doğrudan ham JSON → domain çevirisini doğruluyor.
"""

from __future__ import annotations

from app.data.sources.api_football import APIFootball


def test_to_league_skips_when_seasons_missing(caplog):
    item = {"league": {"id": 999, "name": "Bilinmeyen Lig"}, "seasons": []}
    result = APIFootball._to_league(item)
    assert result is None
    assert any("sezon listesi boş" in r.message for r in caplog.records)


def test_to_league_picks_current_season():
    item = {
        "league": {"id": 203, "name": "Süper Lig"},
        "country": {"name": "Turkey"},
        "seasons": [
            {"year": 2023, "current": False},
            {"year": 2024, "current": True},
        ],
    }
    league = APIFootball._to_league(item)
    assert league is not None
    assert league.season == 2024
    assert league.country == "Turkey"


def test_to_league_falls_back_to_first_when_no_current():
    item = {
        "league": {"id": 1, "name": "Test"},
        "seasons": [{"year": 2022}],
    }
    league = APIFootball._to_league(item)
    assert league is not None
    assert league.season == 2022


def test_get_leagues_filters_out_none(monkeypatch):
    adapter = APIFootball.__new__(APIFootball)
    adapter._use_fixtures = True
    monkeypatch.setattr(
        adapter,
        "_get",
        lambda path, params: {
            "response": [
                {"league": {"id": 1, "name": "OK"}, "seasons": [{"year": 2024}]},
                {"league": {"id": 2, "name": "BAD"}, "seasons": []},
            ]
        },
    )
    leagues = adapter.get_leagues()
    assert len(leagues) == 1
    assert leagues[0].external_id == 1
