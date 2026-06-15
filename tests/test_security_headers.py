"""Security headers — OWASP baseline + CSP + CORP/COOP."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.main import app


@pytest.fixture()
def client():
    return TestClient(app)


def test_baseline_security_headers_on_health(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    h = r.headers
    assert h.get("X-Content-Type-Options") == "nosniff"
    assert h.get("X-Frame-Options") == "DENY"
    assert h.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert "geolocation=()" in h.get("Permissions-Policy", "")


def test_csp_header_present(client):
    r = client.get("/healthz")
    csp = r.headers.get("Content-Security-Policy", "")
    # Temel direktifler
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "object-src 'none'" in csp
    assert "base-uri 'self'" in csp


def test_corp_coop_headers_present(client):
    r = client.get("/healthz")
    assert r.headers.get("Cross-Origin-Opener-Policy") == "same-origin"
    assert r.headers.get("Cross-Origin-Resource-Policy") == "same-origin"
