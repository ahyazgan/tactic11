"""build_source() — DATA_SOURCE config'ine göre doğru adapter seçimi."""

from __future__ import annotations

from app.data.sources.api_football import APIFootball
from app.data.sources.factory import build_source
from app.data.sources.sportmonks import Sportmonks


def test_explicit_sportmonks_returns_sportmonks() -> None:
    assert isinstance(build_source("sportmonks"), Sportmonks)


def test_explicit_api_football_returns_api_football() -> None:
    assert isinstance(build_source("api_football"), APIFootball)


def test_case_insensitive_and_trimmed() -> None:
    assert isinstance(build_source("  SportMonks  "), Sportmonks)


def test_unknown_falls_back_to_api_football() -> None:
    # Bilinmeyen ad güvenli varsayılana düşer (boot'u kırmaz)
    assert isinstance(build_source("wyscout"), APIFootball)


def test_config_default_used_when_none(monkeypatch) -> None:
    from app.core import config

    config.get_settings.cache_clear()
    monkeypatch.setenv("DATA_SOURCE", "sportmonks")
    try:
        assert isinstance(build_source(), Sportmonks)
    finally:
        config.get_settings.cache_clear()


def test_both_adapters_satisfy_appearance_source_protocol() -> None:
    # Protocol uyumu — ingest/backfill bu iki metoda bağlı
    for src in (build_source("sportmonks"), build_source("api_football")):
        assert hasattr(src, "get_fixture_lineups")
        assert hasattr(src, "get_fixture_player_stats")
