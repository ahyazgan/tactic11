"""HTML görünüm endpoint'leri (Faz 5 #15, #17, #29).

Sunucu tarafından render edilen tek-HTML sayfaları. JS sayfa içinde mevcut
JSON endpoint'lerini fetch eder; X-API-Key localStorage'tan gelir.

- GET /matches/{match_id}/game-plan     — birleşik game-plan ekranı (#29)
- GET /teams/{team_id}/dashboard        — takım merkezli landing (#15)
- GET /roles/{role}/dashboard           — rol bazlı landing composer (#17)

Template'ler `app/api/templates/` altında, dashboard.html ile aynı stil.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["html-views"])

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
_MATCH_GAME_PLAN_HTML = _TEMPLATES_DIR / "match_game_plan.html"
_TEAM_DASHBOARD_HTML = _TEMPLATES_DIR / "team_dashboard.html"
_ROLE_DASHBOARD_HTML = _TEMPLATES_DIR / "role_dashboard.html"

VALID_ROLES = ("tactical", "analyst", "conditioning", "scout")


def _inject_js_constant(html: str, name: str, value: int | str) -> str:
    """Template'in ilk <script> bloğunun başına `window.NAME = value;` enjekte et.

    Jinja2 yerine basit string-replace: pattern bir kez geçer, hızlı, log temiz.
    Değer int veya safe-string (sayı, kebab) olmalı — XSS koruması yok, sadece
    tip kontrolü.
    """
    if isinstance(value, int):
        literal = str(value)
    elif isinstance(value, str):
        # str_value sadece alfanümerik + - / izinli
        if not value.replace("-", "").replace("/", "").isalnum():
            raise ValueError(f"unsafe value for JS injection: {value!r}")
        literal = f'"{value}"'
    else:  # pragma: no cover — type guard
        raise TypeError(f"unsupported type: {type(value).__name__}")
    snippet = f"window.{name} = {literal};\n"
    marker = "<script>"
    if marker not in html:
        raise RuntimeError("template <script> bloğu yok")
    return html.replace(marker, marker + "\n" + snippet, 1)


@router.get(
    "/matches/{match_id}/game-plan",
    response_class=HTMLResponse,
    summary="Birleşik game-plan ekranı (Faz 5 #29)",
)
def match_game_plan_view(match_id: int) -> HTMLResponse:
    """Bir maç için game-plan + canlı eşleştirme HTML sayfası.

    Sayfa içindeki JS `GET /matches/{id}/plan/vs-live?my_team_id=N`
    endpoint'ini fetch eder; my_team_id kullanıcıdan input olarak alınır
    (localStorage'a yazılır).
    """
    if match_id <= 0:
        raise HTTPException(status_code=400, detail="match_id > 0 olmalı")
    try:
        html = _MATCH_GAME_PLAN_HTML.read_text(encoding="utf-8")
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=500,
            detail="template eksik: match_game_plan.html",
        ) from e
    html = _inject_js_constant(html, "MATCH_ID", match_id)
    return HTMLResponse(html)


@router.get(
    "/teams/{team_id}/dashboard",
    response_class=HTMLResponse,
    summary="Takım merkezli landing sayfası (Faz 5 #15)",
)
def team_dashboard_view(team_id: int) -> HTMLResponse:
    """Bir takım için form + rating + maç fikstürü + agent çıktıları sayfası.

    Sayfa içindeki JS mevcut JSON endpoint'lerini fetch eder:
    `/teams/{id}/form`, `/teams/{id}/rating`, `/teams/{id}/matches`,
    `/admin/agent-outputs`.
    """
    if team_id <= 0:
        raise HTTPException(status_code=400, detail="team_id > 0 olmalı")
    try:
        html = _TEAM_DASHBOARD_HTML.read_text(encoding="utf-8")
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=500,
            detail="template eksik: team_dashboard.html",
        ) from e
    html = _inject_js_constant(html, "TEAM_ID", team_id)
    return HTMLResponse(html)


@router.get(
    "/roles/{role}/dashboard",
    response_class=HTMLResponse,
    summary="Rol bazlı landing dashboard composer (Faz 5 #17)",
)
def role_dashboard_view(role: str) -> HTMLResponse:
    """Rol bazlı kart kümesi: TD, analist, kondisyon, scout.

    Sayfa içindeki JS role parametresine göre farklı endpoint setlerini
    fetch'ler ve role-specific kartlar render eder. team_id ve player_id
    input olarak kullanıcıdan alınır; rolün gereksinimi yoksa boş bırakılır.
    """
    if role not in VALID_ROLES:
        raise HTTPException(
            status_code=404,
            detail=f"role '{role}' geçersiz — {VALID_ROLES}",
        )
    try:
        html = _ROLE_DASHBOARD_HTML.read_text(encoding="utf-8")
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=500,
            detail="template eksik: role_dashboard.html",
        ) from e
    html = _inject_js_constant(html, "ROLE", role)
    return HTMLResponse(html)
