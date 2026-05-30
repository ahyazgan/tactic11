"""Match warmup checklist render testleri (Faz 5 #26)."""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.responses import HTMLResponse

from app.api.html_views import match_warmup_view


def test_warmup_returns_html() -> None:
    resp = match_warmup_view(match_id=9100)
    assert isinstance(resp, HTMLResponse)
    body = resp.body.decode("utf-8")
    assert body.lstrip().startswith("<!DOCTYPE html>")
    assert "window.MATCH_ID = 9100;" in body
    assert "Isınma" in body
    assert "Son Kontrol" in body


def test_warmup_rejects_invalid_id() -> None:
    with pytest.raises(HTTPException) as exc:
        match_warmup_view(match_id=0)
    assert exc.value.status_code == 400


def test_warmup_has_five_sections() -> None:
    """T-60, T-30, T-15, T-5, maç-içi — 5 ayrı section."""
    resp = match_warmup_view(match_id=42)
    body = resp.body.decode("utf-8")
    assert 'data-section="prep"' in body
    assert 'data-section="warmup"' in body
    assert 'data-section="tactical"' in body
    assert 'data-section="kickoff"' in body
    assert 'data-section="match"' in body


def test_warmup_has_links_to_game_plan() -> None:
    """Üst başlıkta game-plan'a köprü var."""
    resp = match_warmup_view(match_id=42)
    body = resp.body.decode("utf-8")
    assert "/game-plan" in body
    assert "game-plan-link" in body


def test_warmup_localstorage_keyed_by_match() -> None:
    """İlerleme cihaz başına + match başına izole."""
    resp = match_warmup_view(match_id=42)
    body = resp.body.decode("utf-8")
    assert "manager2_warmup_checks_" in body
    assert "manager2_warmup_kickoff_" in body


def test_warmup_no_backend_dependencies() -> None:
    """Backend endpoint yok — saf static + localStorage. Sadece opsiyonel
    auto-fetch /admin/matches/{id} bilgisi var (api key varsa)."""
    resp = match_warmup_view(match_id=42)
    body = resp.body.decode("utf-8")
    # Tek dış çağrı: opsiyonel auto-fetch kickoff
    assert "tryAutoFetchKickoff" in body
    assert "/admin/matches/" in body


def test_warmup_countdown_color_thresholds() -> None:
    """Sayaç urgent (<=15dk), warn (<=60dk), ok (>60dk) renkleri."""
    resp = match_warmup_view(match_id=42)
    body = resp.body.decode("utf-8")
    assert "urgent" in body
    assert "totalMin <= 15" in body
    assert "totalMin <= 60" in body
