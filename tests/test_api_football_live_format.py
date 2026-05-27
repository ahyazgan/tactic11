"""api-football "real shape" parser doğrulaması.

Network'e dokunmaz. Amaç: api-football v3 dokümantasyonundan alınmış
GERÇEK response şekillerini (örn. extra metadata alanları, country.flag,
team.logo, fixture.venue) adapter'a verdiğimizde

  - parse hatasız geçiyor mu (extra alanlar break etmiyor mu)
  - domain modellerine çevrilen alanlar beklenen değerlerde mi
  - 'errors' field non-empty olduğunda smoke script doğru davranıyor mu

doğrulamak. Sentetik fixture'lar (`tests/fixtures/*.json`) sadeleştirilmiş;
production response'lar daha kalabalık — bu testler "kalabalık şekle"
karşı garanti.
"""

from __future__ import annotations

import httpx
import pytest

from app.data.sources.api_football import APIFootball
from scripts.api_football_smoke import (
    SmokeError,
    smoke_fixtures,
    smoke_leagues,
    smoke_teams,
)

# --------------------------------------------------------------------------- #
# Real-shape örnekler — api-football v3 docs'tan alınmış sahanlık şekilleri.
# --------------------------------------------------------------------------- #

LEAGUES_REAL_SHAPE = {
    "get": "leagues",
    "parameters": {"id": "203"},
    "errors": [],
    "results": 1,
    "paging": {"current": 1, "total": 1},
    "response": [
        {
            "league": {
                "id": 203,
                "name": "Süper Lig",
                "type": "League",
                "logo": "https://media.api-sports.io/football/leagues/203.png",
            },
            "country": {
                "name": "Turkey",
                "code": "TR",
                "flag": "https://media.api-sports.io/flags/tr.svg",
            },
            "seasons": [
                {
                    "year": 2023,
                    "start": "2023-08-11",
                    "end": "2024-05-25",
                    "current": False,
                    "coverage": {"standings": True, "players": True},
                },
                {
                    "year": 2024,
                    "start": "2024-08-09",
                    "end": "2025-05-24",
                    "current": True,
                    "coverage": {"standings": True, "players": True},
                },
            ],
        }
    ],
}

TEAMS_REAL_SHAPE = {
    "get": "teams",
    "parameters": {"league": "203", "season": "2024"},
    "errors": [],
    "results": 2,
    "paging": {"current": 1, "total": 1},
    "response": [
        {
            "team": {
                "id": 611,
                "name": "Galatasaray",
                "code": "GAL",
                "country": "Turkey",
                "founded": 1905,
                "national": False,
                "logo": "https://media.api-sports.io/football/teams/611.png",
            },
            "venue": {
                "id": 1001,
                "name": "Türk Telekom Stadium",
                "city": "Istanbul",
                "capacity": 52223,
                "surface": "grass",
            },
        },
        {
            "team": {
                "id": 607,
                "name": "Fenerbahce",
                "country": "Turkey",
                "founded": 1907,
                "national": False,
                "logo": "https://media.api-sports.io/football/teams/607.png",
            },
            "venue": {"id": 1002, "name": "Şükrü Saracoğlu", "city": "Istanbul"},
        },
    ],
}

FIXTURES_REAL_SHAPE = {
    "get": "fixtures",
    "parameters": {"team": "611", "last": "5"},
    "errors": [],
    "results": 1,
    "paging": {"current": 1, "total": 1},
    "response": [
        {
            "fixture": {
                "id": 1234567,
                "referee": "Halil Umut Meler",
                "timezone": "UTC",
                "date": "2025-04-19T16:00:00+00:00",
                "timestamp": 1745078400,
                "periods": {"first": 1745078400, "second": 1745082000},
                "venue": {"id": 1001, "name": "Türk Telekom Stadium", "city": "Istanbul"},
                "status": {"long": "Match Finished", "short": "FT", "elapsed": 90},
            },
            "league": {
                "id": 203,
                "name": "Süper Lig",
                "country": "Turkey",
                "logo": "https://media.api-sports.io/football/leagues/203.png",
                "flag": "https://media.api-sports.io/flags/tr.svg",
                "season": 2024,
                "round": "Regular Season - 33",
            },
            "teams": {
                "home": {
                    "id": 611,
                    "name": "Galatasaray",
                    "logo": "https://media.api-sports.io/football/teams/611.png",
                    "winner": True,
                },
                "away": {
                    "id": 607,
                    "name": "Fenerbahce",
                    "logo": "https://media.api-sports.io/football/teams/607.png",
                    "winner": False,
                },
            },
            "goals": {"home": 2, "away": 1},
            "score": {
                "halftime": {"home": 1, "away": 0},
                "fulltime": {"home": 2, "away": 1},
                "extratime": {"home": None, "away": None},
                "penalty": {"home": None, "away": None},
            },
        }
    ],
}


# --------------------------------------------------------------------------- #
# Adapter parser tests — gerçek response şekli → domain modeli
# --------------------------------------------------------------------------- #


def test_to_league_handles_real_shape_with_extra_fields():
    """leagues real-shape: logo, flag, coverage gibi extra alanlar parser'ı bozmamalı."""
    item = LEAGUES_REAL_SHAPE["response"][0]
    league = APIFootball._to_league(item)
    assert league is not None
    assert league.external_id == 203
    assert league.name == "Süper Lig"
    assert league.season == 2024  # current=True olan sezon
    assert league.country == "Turkey"


def test_to_team_handles_real_shape_with_venue():
    """teams real-shape: venue + logo + code gibi alanlar parser'ı bozmamalı."""
    item = TEAMS_REAL_SHAPE["response"][0]
    team = APIFootball._to_team(item)
    assert team.external_id == 611
    assert team.name == "Galatasaray"
    assert team.country == "Turkey"
    assert team.founded == 1905


def test_to_match_handles_real_shape_with_score_and_periods():
    """fixtures real-shape: referee, timestamp, venue, score gibi alanlar parser'ı bozmamalı."""
    item = FIXTURES_REAL_SHAPE["response"][0]
    match = APIFootball._to_match(item)
    assert match.external_id == 1234567
    assert match.league_external_id == 203
    assert match.season == 2024
    assert match.status == "FT"
    assert match.home_team_external_id == 611
    assert match.away_team_external_id == 607
    assert match.home_score == 2
    assert match.away_score == 1
    assert match.kickoff.year == 2025


def test_adapter_get_leagues_with_real_shape(monkeypatch):
    """get_leagues real-shape response'u → 1 domain League."""
    adapter = APIFootball.__new__(APIFootball)
    adapter._use_fixtures = True
    monkeypatch.setattr(adapter, "_get", lambda path, params: LEAGUES_REAL_SHAPE)
    leagues = adapter.get_leagues()
    assert len(leagues) == 1
    assert leagues[0].external_id == 203
    assert leagues[0].season == 2024


def test_adapter_get_teams_with_real_shape(monkeypatch):
    adapter = APIFootball.__new__(APIFootball)
    adapter._use_fixtures = True
    monkeypatch.setattr(adapter, "_get", lambda path, params: TEAMS_REAL_SHAPE)
    teams = adapter.get_teams(league_id=203, season=2024)
    assert len(teams) == 2
    assert {t.external_id for t in teams} == {611, 607}


def test_adapter_get_team_matches_with_real_shape(monkeypatch):
    adapter = APIFootball.__new__(APIFootball)
    adapter._use_fixtures = True
    monkeypatch.setattr(adapter, "_get", lambda path, params: FIXTURES_REAL_SHAPE)
    matches = adapter.get_team_matches(team_id=611, last_n=5)
    assert len(matches) == 1
    m = matches[0]
    assert m.external_id == 1234567
    assert m.status == "FT"
    assert m.home_score == 2 and m.away_score == 1


# --------------------------------------------------------------------------- #
# Smoke script parser tests — monkeypatched httpx.Client
# --------------------------------------------------------------------------- #


class _FakeResponse:
    def __init__(self, status_code: int, json_payload: dict | str):
        self.status_code = status_code
        self._payload = json_payload
        self.text = (
            json_payload if isinstance(json_payload, str) else "<json body>"
        )

    def json(self):
        if isinstance(self._payload, str):
            raise ValueError("not json")
        return self._payload


class _FakeClient:
    """Tek bir route haritasını sırayla cevaplayan minimal httpx.Client double."""

    def __init__(self, route_map: dict[str, _FakeResponse]):
        self._route_map = route_map
        self.calls: list[tuple[str, dict]] = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url: str, *, params: dict, headers: dict):
        for tail, response in self._route_map.items():
            if url.endswith(tail):
                self.calls.append((tail, dict(params)))
                return response
        raise AssertionError(f"unexpected URL: {url}")


def _patch_httpx(monkeypatch, route_map):
    client = _FakeClient(route_map)
    monkeypatch.setattr(httpx, "Client", lambda *a, **kw: client)
    return client


def test_smoke_leagues_happy_path(monkeypatch):
    _patch_httpx(monkeypatch, {"/leagues": _FakeResponse(200, LEAGUES_REAL_SHAPE)})
    info = smoke_leagues("https://x", "k", 203)
    assert info["id"] == 203
    assert info["season_count"] == 2


def test_smoke_teams_happy_path(monkeypatch):
    _patch_httpx(monkeypatch, {"/teams": _FakeResponse(200, TEAMS_REAL_SHAPE)})
    info = smoke_teams("https://x", "k", 203, 2024)
    assert info["count"] == 2
    assert info["sample_id"] in (611, 607)


def test_smoke_fixtures_happy_path(monkeypatch):
    _patch_httpx(monkeypatch, {"/fixtures": _FakeResponse(200, FIXTURES_REAL_SHAPE)})
    info = smoke_fixtures("https://x", "k", 611, last_n=5)
    assert info["count"] == 1
    assert info["sample_status"] == "FT"


def test_smoke_raises_on_non_200(monkeypatch):
    _patch_httpx(monkeypatch, {"/leagues": _FakeResponse(401, "Unauthorized")})
    with pytest.raises(SmokeError, match="HTTP 401"):
        smoke_leagues("https://x", "bad-key", 203)


def test_smoke_raises_on_api_errors_field(monkeypatch):
    """api-football kota aşımı / parametre hatasını errors içinde raporlar."""
    payload = {
        "get": "leagues",
        "errors": {"requests": "You have reached the request limit"},
        "response": [],
    }
    _patch_httpx(monkeypatch, {"/leagues": _FakeResponse(200, payload)})
    with pytest.raises(SmokeError, match="api errors"):
        smoke_leagues("https://x", "k", 203)


def test_smoke_raises_on_missing_response_key(monkeypatch):
    payload = {"get": "leagues", "errors": [], "results": 0}
    _patch_httpx(monkeypatch, {"/leagues": _FakeResponse(200, payload)})
    with pytest.raises(SmokeError, match="response anahtarı eksik"):
        smoke_leagues("https://x", "k", 203)


def test_smoke_raises_on_empty_response_for_known_league(monkeypatch):
    payload = {"get": "leagues", "errors": [], "response": []}
    _patch_httpx(monkeypatch, {"/leagues": _FakeResponse(200, payload)})
    with pytest.raises(SmokeError, match="kayıt yok"):
        smoke_leagues("https://x", "k", 999)
