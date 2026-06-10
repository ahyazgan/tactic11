"""Sportmonks catalog router + medya proxy — ağsız (saf yardımcı + guard) testler.

Canlı uçlar (standings/squad/schedule) gerçek API'ye gider; burada test edilmez.
Burada: foto URL proxy yeniden yazma, medya yol guard'ı, Sportmonks kapalıyken 503.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api import sportmonks_catalog as cat


def test_proxy_photo_rewrites_cdn_url():
    url = "https://cdn.sportmonks.com/images/soccer/players/30/5332062.png"
    assert cat._proxy_photo(url) == "/media/sportmonks/images/soccer/players/30/5332062.png"


def test_proxy_photo_passthrough_and_none():
    assert cat._proxy_photo(None) is None
    assert cat._proxy_photo("https://other.example/x.png") == "https://other.example/x.png"


def test_media_guard_rejects_traversal():
    with pytest.raises(HTTPException) as ei:
        cat.media_sportmonks("../etc/passwd")
    assert ei.value.status_code == 400


def test_media_guard_rejects_absolute_url():
    with pytest.raises(HTTPException) as ei:
        cat.media_sportmonks("http://evil.example/x")
    assert ei.value.status_code == 400


def test_client_503_when_sportmonks_disabled(monkeypatch):
    from app.core import config

    config.get_settings.cache_clear()
    monkeypatch.setenv("DATA_SOURCE", "api_football")
    monkeypatch.setenv("SPORTMONKS_API_KEY", "")
    try:
        with pytest.raises(HTTPException) as ei:
            cat._client()
        assert ei.value.status_code == 503
    finally:
        config.get_settings.cache_clear()
