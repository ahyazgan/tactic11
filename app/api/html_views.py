"""HTML görünüm endpoint'leri (Faz 5 #15, #17, #26, #29, #36, #39 + live).

Sunucu tarafından render edilen tek-HTML sayfaları. JS sayfa içinde mevcut
JSON endpoint'lerini ya da WebSocket'i tüketir; X-API-Key localStorage'tan
gelir.

- GET /matches/{match_id}/game-plan         — birleşik game-plan ekranı (#29)
- GET /matches/{match_id}/warmup            — kickoff -60 dk checklist (#26)
- GET /matches/{match_id}/live              — canlı WebSocket izleyici
- GET /teams/{team_id}/dashboard            — takım merkezli landing (#15)
- GET /players/{player_id}/dashboard        — oyuncu gelişim trendi (#36)
- GET /teams/{team_id}/decisions-dashboard  — karar isabet + outcome (#39)
- GET /roles/{role}/dashboard               — rol bazlı landing composer (#17)

Template'ler `app/api/templates/` altında, dashboard.html ile aynı stil.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["html-views"])

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
_MATCH_GAME_PLAN_HTML = _TEMPLATES_DIR / "match_game_plan.html"
_MATCH_WARMUP_HTML = _TEMPLATES_DIR / "match_warmup.html"
_MATCH_LIVE_HTML = _TEMPLATES_DIR / "match_live_watcher.html"
_TEAM_DASHBOARD_HTML = _TEMPLATES_DIR / "team_dashboard.html"
_PLAYER_DASHBOARD_HTML = _TEMPLATES_DIR / "player_dashboard.html"
_TEAM_DECISIONS_HTML = _TEMPLATES_DIR / "team_decisions_dashboard.html"
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


def _render_template(path: Path, var_name: str, var_value: int | str) -> HTMLResponse:
    try:
        html = path.read_text(encoding="utf-8")
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=500, detail=f"template eksik: {path.name}",
        ) from e
    html = _inject_js_constant(html, var_name, var_value)
    return HTMLResponse(html)


@router.get(
    "/matches/{match_id}/game-plan",
    response_class=HTMLResponse,
    summary="Birleşik game-plan ekranı (Faz 5 #29)",
)
def match_game_plan_view(match_id: int) -> HTMLResponse:
    """Maç game-plan + canlı eşleştirme sayfası."""
    if match_id <= 0:
        raise HTTPException(status_code=400, detail="match_id > 0 olmalı")
    return _render_template(_MATCH_GAME_PLAN_HTML, "MATCH_ID", match_id)


@router.get(
    "/matches/{match_id}/warmup",
    response_class=HTMLResponse,
    summary="Kickoff -60 dk hazırlık checklist (Faz 5 #26)",
)
def match_warmup_view(match_id: int) -> HTMLResponse:
    """5 bölümlü kickoff -60 dk checklist."""
    if match_id <= 0:
        raise HTTPException(status_code=400, detail="match_id > 0 olmalı")
    return _render_template(_MATCH_WARMUP_HTML, "MATCH_ID", match_id)


@router.get(
    "/matches/{match_id}/live",
    response_class=HTMLResponse,
    summary="Canlı maç izleyici (WebSocket-tüketici sayfa)",
)
def match_live_watcher_view(match_id: int) -> HTMLResponse:
    """WebSocket `/ws/matches/{id}/live` snapshot'larını gerçek-zamanlı render et.

    Skor tablosu + dakika + primary context banner (urgent/warn renkli) +
    momentum gauge (sol/sağ yarıçap) + PPDA + field_tilt + match_dominance +
    tactical_triggers + spatial+matchup alarmları + sub_timing + VAEP top
    oyuncular + score_time recipe. Reconnect manuel.
    """
    if match_id <= 0:
        raise HTTPException(status_code=400, detail="match_id > 0 olmalı")
    try:
        html = _MATCH_LIVE_HTML.read_text(encoding="utf-8")
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=500,
            detail="template eksik: match_live_watcher.html",
        ) from e
    html = _inject_js_constant(html, "MATCH_ID", match_id)
    return HTMLResponse(html)


@router.get(
    "/teams/{team_id}/dashboard",
    response_class=HTMLResponse,
    summary="Takım merkezli landing sayfası (Faz 5 #15)",
)
def team_dashboard_view(team_id: int) -> HTMLResponse:
    """Takım için form + rating + maç fikstürü + agent çıktıları."""
    if team_id <= 0:
        raise HTTPException(status_code=400, detail="team_id > 0 olmalı")
    return _render_template(_TEAM_DASHBOARD_HTML, "TEAM_ID", team_id)


@router.get(
    "/players/{player_id}/dashboard",
    response_class=HTMLResponse,
    summary="Oyuncu gelişim trendi sayfası (Faz 5 #36)",
)
def player_dashboard_view(player_id: int) -> HTMLResponse:
    """Oyuncu için info + load + form + appearance trendi."""
    if player_id <= 0:
        raise HTTPException(status_code=400, detail="player_id > 0 olmalı")
    return _render_template(_PLAYER_DASHBOARD_HTML, "PLAYER_ID", player_id)


@router.get(
    "/teams/{team_id}/decisions-dashboard",
    response_class=HTMLResponse,
    summary="Karar geçmişi + isabet dashboard'u (Faz 5 #39, Faz 8 #4)",
)
def team_decisions_dashboard_view(team_id: int) -> HTMLResponse:
    """Takım için decision feedback özeti + maç-bazlı outcome girişi."""
    if team_id <= 0:
        raise HTTPException(status_code=400, detail="team_id > 0 olmalı")
    return _render_template(_TEAM_DECISIONS_HTML, "TEAM_ID", team_id)


@router.get(
    "/roles/{role}/dashboard",
    response_class=HTMLResponse,
    summary="Rol bazlı landing dashboard composer (Faz 5 #17)",
)
def role_dashboard_view(role: str) -> HTMLResponse:
    """Rol bazlı kart kümesi: TD, analist, kondisyon, scout."""
    if role not in VALID_ROLES:
        raise HTTPException(
            status_code=404,
            detail=f"role '{role}' geçersiz — {VALID_ROLES}",
        )
    return _render_template(_ROLE_DASHBOARD_HTML, "ROLE", role)
