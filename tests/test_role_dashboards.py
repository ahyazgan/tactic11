"""Role dashboard render testleri (Faz 5 #17)."""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.responses import HTMLResponse

from app.api.html_views import VALID_ROLES, role_dashboard_view


@pytest.mark.parametrize("role", VALID_ROLES)
def test_role_dashboard_returns_html_for_valid_role(role: str) -> None:
    resp = role_dashboard_view(role=role)
    assert isinstance(resp, HTMLResponse)
    body = resp.body.decode("utf-8")
    assert body.lstrip().startswith("<!DOCTYPE html>")
    assert f'window.ROLE = "{role}";' in body


def test_role_dashboard_404_for_invalid_role() -> None:
    with pytest.raises(HTTPException) as exc:
        role_dashboard_view(role="bogus")
    assert exc.value.status_code == 404
    assert "tactical" in exc.value.detail
    assert "scout" in exc.value.detail


def test_role_dashboard_has_4_role_tabs() -> None:
    resp = role_dashboard_view(role="tactical")
    body = resp.body.decode("utf-8")
    for r in VALID_ROLES:
        assert f'/roles/{r}/dashboard' in body


def test_role_dashboard_has_all_role_card_builders() -> None:
    """JS'in `ROLE_CARDS` dict'i 4 rolü kapsamalı."""
    resp = role_dashboard_view(role="tactical")
    body = resp.body.decode("utf-8")
    assert "tactical:" in body
    assert "analyst:" in body
    assert "conditioning:" in body
    assert "scout:" in body


def test_role_dashboard_tactical_links_to_team_views() -> None:
    resp = role_dashboard_view(role="tactical")
    body = resp.body.decode("utf-8")
    # TD kartlarının deep link'i: /teams/{id}/dashboard + /decisions-dashboard
    assert "/teams/${teamId}/dashboard" in body
    assert "/teams/${teamId}/decisions-dashboard" in body
    # Upcoming maç listesi game-plan + warmup link'i
    assert "/game-plan" in body
    assert "/warmup" in body


def test_role_dashboard_analyst_calls_ml_endpoints() -> None:
    resp = role_dashboard_view(role="analyst")
    body = resp.body.decode("utf-8")
    assert "/admin/ml-model-status" in body
    assert "/admin/predict-accuracy" in body


def test_role_dashboard_conditioning_calls_player_load() -> None:
    resp = role_dashboard_view(role="conditioning")
    body = resp.body.decode("utf-8")
    assert "/players/${playerId}/load" in body


def test_role_dashboard_scout_filters_agent_outputs() -> None:
    resp = role_dashboard_view(role="scout")
    body = resp.body.decode("utf-8")
    # Scout sadece scout-related agent çıktılarını filtrelemeli
    assert "opponent_scout" in body
    assert "scout_watchlist_digest" in body


def test_role_dashboard_active_tab_highlights() -> None:
    """JS document.querySelectorAll('.role-tabs a[data-r]')... `active` class."""
    resp = role_dashboard_view(role="tactical")
    body = resp.body.decode("utf-8")
    assert "a.dataset.r === ROLE" in body
    assert "classList.add('active')" in body
