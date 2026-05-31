"""Content-Security-Policy — nonce enjeksiyonu + header davranışı (Faz 9 #5)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.csp import (
    STRICT_API_CSP,
    generate_nonce,
    html_csp_header,
    inject_nonce,
)
from app.api.main import app
from app.db.session import get_session


@pytest.fixture()
def client(session):
    def _override():
        yield session

    app.dependency_overrides[get_session] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


# --------------------------------------------------------------------------- #
# Birim — nonce enjeksiyonu
# --------------------------------------------------------------------------- #


def test_inject_nonce_adds_to_script_and_style():
    html = "<html><head><style>.a{}</style></head><body><script>x()</script></body></html>"
    out = inject_nonce(html, "ABC123")
    assert '<style nonce="ABC123">' in out
    assert '<script nonce="ABC123">' in out


def test_inject_nonce_does_not_touch_closing_tags():
    html = "<script>x</script>"
    out = inject_nonce(html, "N")
    assert "</script>" in out
    assert out.count('nonce="N"') == 1  # sadece açılış etiketi


def test_inject_nonce_skips_already_nonced():
    html = '<script nonce="old">x</script>'
    out = inject_nonce(html, "new")
    assert 'nonce="old"' in out
    assert 'nonce="new"' not in out


def test_inject_nonce_handles_script_with_attrs():
    html = '<script src="/a.js" defer>'
    out = inject_nonce(html, "N")
    assert out.startswith('<script nonce="N" src="/a.js" defer>')


def test_html_csp_header_contains_nonce():
    h = html_csp_header("XYZ")
    assert "script-src 'self' 'nonce-XYZ'" in h
    assert "object-src 'none'" in h
    assert "frame-ancestors 'none'" in h


def test_generate_nonce_unique():
    assert generate_nonce() != generate_nonce()


# --------------------------------------------------------------------------- #
# Entegrasyon — endpoint header'ları
# --------------------------------------------------------------------------- #


def test_dashboard_has_nonce_csp(client):
    r = client.get("/dashboard")
    assert r.status_code == 200
    csp = r.headers.get("content-security-policy", "")
    assert "script-src 'self' 'nonce-" in csp
    # Body'deki inline script nonce almış olmalı
    assert 'nonce="' in r.text


def test_json_endpoint_gets_strict_csp(client):
    r = client.get("/health")
    assert r.headers.get("content-security-policy") == STRICT_API_CSP


def test_dashboard_csp_not_strict(client):
    """HTML sayfa katı API CSP'sini ALMAMALI (kendi nonce'lu CSP'si var)."""
    r = client.get("/dashboard")
    assert r.headers.get("content-security-policy") != STRICT_API_CSP
