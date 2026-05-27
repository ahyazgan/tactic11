"""CORS middleware konfigürasyon ve davranış testleri (PR D4)."""

from __future__ import annotations

import importlib

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from app.api import main as api_main
from app.core import config


@pytest.fixture()
def reload_app(monkeypatch):
    """Settings cache + main module yeniden yükleme yardımcısı.

    CORS_ALLOWED_ORIGINS env'ini değiştirip main'i yeniden import etmek
    gerek — middleware app oluştururken eklenir.
    """
    def _do(origins: str) -> FastAPI:
        monkeypatch.setenv("CORS_ALLOWED_ORIGINS", origins)
        config.get_settings.cache_clear()
        # reload main module — CORS middleware app oluşturulurken eklenir
        importlib.reload(api_main)
        return api_main.app

    yield _do
    # Cleanup: settings cache + main reload
    config.get_settings.cache_clear()
    importlib.reload(api_main)


def test_cors_disabled_when_origins_empty(reload_app):
    """CORS_ALLOWED_ORIGINS boş → CORSMiddleware kayıtlı olmaz."""
    app = reload_app("")
    # CORSMiddleware kayıtlı OLMAMALI
    assert "CORSMiddleware" not in str(app.user_middleware)


def test_cors_enabled_when_origins_configured(reload_app):
    app = reload_app("https://app.example.com,https://admin.example.com")
    # Yapısal kontrol: middleware kayıtlı
    found = any(
        getattr(m, "cls", None) is CORSMiddleware for m in app.user_middleware
    )
    assert found


def test_cors_preflight_options_returns_origin_header(reload_app):
    app = reload_app("https://app.example.com")
    client = TestClient(app)
    # Preflight: OPTIONS isteği + Origin header + Access-Control-Request-Method
    r = client.options(
        "/leagues",
        headers={
            "Origin": "https://app.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    # CORS middleware preflight'ı handle etmeli (200)
    assert r.status_code == 200
    # Access-Control-Allow-Origin echo edilmeli
    assert r.headers.get("access-control-allow-origin") == "https://app.example.com"


def test_cors_disallows_non_whitelisted_origin(reload_app):
    app = reload_app("https://app.example.com")
    client = TestClient(app)
    r = client.options(
        "/leagues",
        headers={
            "Origin": "https://evil.example.com",  # whitelist'te değil
            "Access-Control-Request-Method": "GET",
        },
    )
    # Origin echo edilmemeli (CORS politikası)
    assert r.headers.get("access-control-allow-origin") != "https://evil.example.com"


def test_cors_settings_list_parsing():
    """Comma-separated string parsing — boş entries trim'lenir."""
    s = config.Settings(CORS_ALLOWED_ORIGINS="a.com, b.com ,, c.com")
    assert s.cors_origins_list() == ["a.com", "b.com", "c.com"]
