"""Team decisions dashboard render testleri (Faz 5 #39)."""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.responses import HTMLResponse

from app.api.html_views import team_decisions_dashboard_view


def test_decisions_dashboard_returns_html() -> None:
    resp = team_decisions_dashboard_view(team_id=11)
    assert isinstance(resp, HTMLResponse)
    body = resp.body.decode("utf-8")
    assert body.lstrip().startswith("<!DOCTYPE html>")
    assert "window.TEAM_ID = 11;" in body
    assert "Karar İsabet Dashboard" in body


def test_decisions_dashboard_rejects_invalid_id() -> None:
    with pytest.raises(HTTPException) as exc:
        team_decisions_dashboard_view(team_id=0)
    assert exc.value.status_code == 400


def test_decisions_dashboard_uses_admin_feedback_endpoint() -> None:
    resp = team_decisions_dashboard_view(team_id=11)
    body = resp.body.decode("utf-8")
    assert "/admin/teams/${TEAM_ID}/decisions/feedback" in body


def test_decisions_dashboard_uses_match_decisions_endpoint() -> None:
    resp = team_decisions_dashboard_view(team_id=11)
    body = resp.body.decode("utf-8")
    assert "/admin/matches/" in body
    assert "/decisions" in body


def test_decisions_dashboard_posts_outcome() -> None:
    """Outcome dropdown POST'u /admin/decisions/{id}/outcome'a gidiyor."""
    resp = team_decisions_dashboard_view(team_id=11)
    body = resp.body.decode("utf-8")
    assert "/admin/decisions/" in body
    assert "/outcome" in body
    assert "method: 'POST'" in body


def test_decisions_dashboard_includes_all_outcome_values() -> None:
    """Outcome dropdown 4 değeri içeriyor."""
    resp = team_decisions_dashboard_view(team_id=11)
    body = resp.body.decode("utf-8")
    # OUTCOME_OPTIONS array
    assert "'positive'" in body
    assert "'negative'" in body
    assert "'neutral'" in body
    assert "'pending'" in body


def test_decisions_dashboard_filters_to_team() -> None:
    """Maç decisions response'u team_id ile client-side filtreleniyor."""
    resp = team_decisions_dashboard_view(team_id=11)
    body = resp.body.decode("utf-8")
    assert "r.team_id === TEAM_ID" in body
