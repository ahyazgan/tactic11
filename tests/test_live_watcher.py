"""Live match watcher HTML render testleri."""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.responses import HTMLResponse

from app.api.html_views import match_live_watcher_view


def test_live_watcher_returns_html() -> None:
    resp = match_live_watcher_view(match_id=9100)
    assert isinstance(resp, HTMLResponse)
    body = resp.body.decode("utf-8")
    assert body.lstrip().startswith("<!DOCTYPE html>")
    assert "window.MATCH_ID = 9100;" in body
    assert "Canlı Maç" in body


def test_live_watcher_rejects_invalid_id() -> None:
    with pytest.raises(HTTPException) as exc:
        match_live_watcher_view(match_id=0)
    assert exc.value.status_code == 400


def test_live_watcher_uses_websocket_endpoint() -> None:
    """Sayfa WebSocket /ws/matches/{id}/live endpoint'ine bağlanıyor."""
    resp = match_live_watcher_view(match_id=42)
    body = resp.body.decode("utf-8")
    assert "/ws/matches/" in body
    assert "/live" in body
    assert "new WebSocket(" in body


def test_live_watcher_wss_for_https() -> None:
    """Browser HTTPS'te wss: protokolü seçilmeli."""
    resp = match_live_watcher_view(match_id=42)
    body = resp.body.decode("utf-8")
    assert "wss:" in body
    assert "ws:" in body
    assert "location.protocol === 'https:'" in body


def test_live_watcher_renders_momentum_gauge() -> None:
    resp = match_live_watcher_view(match_id=42)
    body = resp.body.decode("utf-8")
    assert "momentum-fill" in body
    assert "momentum-bar" in body


def test_live_watcher_handles_vaep_snapshot() -> None:
    """VAEP feed eklenince render'da gösterilmeli."""
    resp = match_live_watcher_view(match_id=42)
    body = resp.body.decode("utf-8")
    assert "snap.vaep" in body
    assert "top_players" in body
    assert "my_team_total" in body


def test_live_watcher_renders_primary_context_alert() -> None:
    """Faz 8 context engine primary alert banner var."""
    resp = match_live_watcher_view(match_id=42)
    body = resp.body.decode("utf-8")
    assert "primary-alert" in body
    assert "snap.context" in body
    assert "primary.headline" in body


def test_live_watcher_deep_links_to_game_plan_and_warmup() -> None:
    resp = match_live_watcher_view(match_id=42)
    body = resp.body.decode("utf-8")
    assert "/game-plan" in body
    assert "/warmup" in body


def test_live_watcher_interval_5_to_60_seconds() -> None:
    """WebSocket aralığı UI'da 5..60sn arası — backend kontratıyla uyumlu."""
    resp = match_live_watcher_view(match_id=42)
    body = resp.body.decode("utf-8")
    assert 'min="5"' in body
    assert 'max="60"' in body


def test_live_watcher_persists_team_id_per_match() -> None:
    """my_team_id ayar maç başına localStorage'da izole."""
    resp = match_live_watcher_view(match_id=42)
    body = resp.body.decode("utf-8")
    assert "manager2_live_team_" in body
