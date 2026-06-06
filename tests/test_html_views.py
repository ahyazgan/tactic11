"""HTML görünüm endpoint testleri (Faz 5 #15, #29).

Template render + JS sabit enjeksiyonu + path validation.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.responses import HTMLResponse

from app.api.html_views import (
    _inject_js_constant,
    match_game_plan_view,
    team_dashboard_view,
)

# --------------------------------------------------------------------------- #
# Saf yardımcı: JS sabit enjeksiyonu
# --------------------------------------------------------------------------- #


def test_inject_js_constant_int() -> None:
    html = "<html><body><script>\nconsole.log('x');\n</script></body></html>"
    out = _inject_js_constant(html, "MATCH_ID", 9100)
    assert "window.MATCH_ID = 9100;" in out
    # Mevcut script bloğunun başına eklendi (sonradan değil)
    assert out.index("window.MATCH_ID") < out.index("console.log")


def test_inject_js_constant_safe_string() -> None:
    html = "<script>\nfoo();\n</script>"
    out = _inject_js_constant(html, "ROLE", "coach")
    assert 'window.ROLE = "coach";' in out


def test_inject_js_constant_rejects_unsafe_string() -> None:
    html = "<script></script>"
    with pytest.raises(ValueError):
        _inject_js_constant(html, "INJ", "</script><script>alert(1)")


def test_inject_js_constant_no_script_block_raises() -> None:
    html = "<html><body>no js</body></html>"
    with pytest.raises(RuntimeError):
        _inject_js_constant(html, "X", 1)


def test_inject_js_constant_only_first_script_block() -> None:
    html = "<script>a</script><script>b</script>"
    out = _inject_js_constant(html, "K", 1)
    # Sadece ilk <script>'a enjekte edildi
    assert out.count("window.K") == 1
    first_script = out.index("<script>")
    second_script = out.index("<script>", first_script + 1)
    assert out.index("window.K") < second_script


# --------------------------------------------------------------------------- #
# Endpoint testleri
# --------------------------------------------------------------------------- #


def test_match_game_plan_returns_html() -> None:
    resp = match_game_plan_view(match_id=9100)
    assert isinstance(resp, HTMLResponse)
    body = resp.body.decode("utf-8")
    assert body.lstrip().startswith("<!DOCTYPE html>")
    assert "window.MATCH_ID = 9100;" in body
    # Sayfanın game-plan başlığını içermesi
    assert "Game Plan" in body


def test_match_game_plan_rejects_invalid_id() -> None:
    with pytest.raises(HTTPException) as exc:
        match_game_plan_view(match_id=0)
    assert exc.value.status_code == 400


def test_team_dashboard_returns_html() -> None:
    resp = team_dashboard_view(team_id=549)
    assert isinstance(resp, HTMLResponse)
    body = resp.body.decode("utf-8")
    assert body.lstrip().startswith("<!DOCTYPE html>")
    assert "window.TEAM_ID = 549;" in body
    assert "Takım Dashboard" in body


def test_team_dashboard_rejects_invalid_id() -> None:
    with pytest.raises(HTTPException) as exc:
        team_dashboard_view(team_id=-1)
    assert exc.value.status_code == 400


def test_match_game_plan_html_fetches_plan_vs_live() -> None:
    """Sayfa JS'i plan/vs-live endpoint'ini çağırıyor — entegrasyon kontratı."""
    resp = match_game_plan_view(match_id=42)
    body = resp.body.decode("utf-8")
    assert "/plan/vs-live" in body
    assert "my_team_id" in body


def test_team_dashboard_html_uses_team_endpoints() -> None:
    """Team dashboard JS'i mevcut team endpoint'lerini çağırıyor."""
    resp = team_dashboard_view(team_id=11)
    body = resp.body.decode("utf-8")
    assert "/teams/${TEAM_ID}/form" in body
    assert "/teams/${TEAM_ID}/rating" in body
    assert "/teams/${TEAM_ID}/matches" in body
    assert "/admin/agent-outputs" in body


def test_team_dashboard_links_to_match_game_plan() -> None:
    """Yaklaşan maçlar listesi /matches/{id}/game-plan'a köprü kuruyor."""
    resp = team_dashboard_view(team_id=11)
    body = resp.body.decode("utf-8")
    assert "/matches/" in body
    assert "/game-plan" in body
