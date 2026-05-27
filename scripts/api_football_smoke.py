"""api-football production smoke — 3 endpoint'i gerçek anahtarla dene.

Bu script production credential ile ÜRETİM API'sine HTTP atar. CI'da
çalışmaz (gerçek key + kota harcaması istemez). Amaç: deploy öncesi
"anahtarım doğru çalışıyor mu, response şekli adapter'ın beklediği gibi mi"
sorularını manuel doğrulamak.

Kullanım:
    python scripts/api_football_smoke.py --key XXX --league 203 --season 2024

Çıktı: 3 endpoint için ✔ / ✘ tablosu + sample alanlar. Tüm doğrulamalar
geçerse exit 0; herhangi biri başarısızsa exit 1.

Endpoint'ler (api-football v3):
    GET /leagues               — top-level meta
    GET /teams?league&season   — lig × sezon takım listesi
    GET /fixtures?team&last=5  — bir takımın son 5 maçı

Adapter (`app/data/sources/api_football.py`) bu 3 path'i okuyor; smoke
aynı endpoint'leri kullanarak adapter-prod uyumunu doğrular.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import httpx

# Proje kökünü sys.path'e ekle ki `python scripts/...` doğrudan çalışsın.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.core.config import get_settings  # noqa: E402

DEFAULT_BASE_URL = "https://v3.football.api-sports.io"
TIMEOUT_SECONDS = 15.0


class SmokeError(Exception):
    """Smoke kontrolü beklenti karşılanmadı."""


def _http_get(base_url: str, path: str, params: dict[str, Any], key: str) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/{path}"
    with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
        r = client.get(url, params=params, headers={"x-apisports-key": key})
        if r.status_code != 200:
            raise SmokeError(
                f"{path}: HTTP {r.status_code} — body: {r.text[:200]}"
            )
        data = r.json()
    if not isinstance(data, dict):
        raise SmokeError(f"{path}: response root dict değil ({type(data).__name__})")
    errors = data.get("errors")
    # api-football "errors" alanı:
    #   - boş liste / boş dict → OK
    #   - non-empty → kota aşımı veya parametre hatası
    if errors:
        raise SmokeError(f"{path}: api errors → {errors}")
    if "response" not in data:
        raise SmokeError(f"{path}: response anahtarı eksik (keys={list(data.keys())})")
    return data


def smoke_leagues(base_url: str, key: str, league_id: int) -> dict[str, Any]:
    """`/leagues` döndürdüğü dizide aranan league_id'yi bul."""
    data = _http_get(base_url, "leagues", {"id": league_id}, key)
    items = data["response"]
    if not items:
        raise SmokeError(f"leagues: id={league_id} için kayıt yok")
    item = items[0]
    league = item.get("league", {})
    seasons = item.get("seasons") or []
    return {
        "id": league.get("id"),
        "name": league.get("name"),
        "season_count": len(seasons),
        "raw_results": data.get("results"),
    }


def smoke_teams(base_url: str, key: str, league_id: int, season: int) -> dict[str, Any]:
    """`/teams?league&season` — sezon takım listesi."""
    data = _http_get(
        base_url, "teams", {"league": league_id, "season": season}, key
    )
    items = data["response"]
    if not items:
        raise SmokeError(
            f"teams: league={league_id} season={season} için takım yok"
        )
    sample_team = items[0].get("team", {})
    return {
        "count": len(items),
        "sample_id": sample_team.get("id"),
        "sample_name": sample_team.get("name"),
        "raw_results": data.get("results"),
    }


def smoke_fixtures(
    base_url: str, key: str, team_id: int, last_n: int = 5
) -> dict[str, Any]:
    """`/fixtures?team&last=N` — bir takımın son N maçı."""
    data = _http_get(base_url, "fixtures", {"team": team_id, "last": last_n}, key)
    items = data["response"]
    if not items:
        raise SmokeError(f"fixtures: team={team_id} için maç yok")
    sample = items[0]
    fix = sample.get("fixture", {})
    teams = sample.get("teams", {})
    return {
        "count": len(items),
        "sample_id": fix.get("id"),
        "sample_date": fix.get("date"),
        "sample_status": (fix.get("status") or {}).get("short"),
        "sample_home": (teams.get("home") or {}).get("name"),
        "sample_away": (teams.get("away") or {}).get("name"),
        "raw_results": data.get("results"),
    }


def _print_result(label: str, ok: bool, detail: str) -> None:
    mark = "✔" if ok else "✘"
    print(f"  {mark} {label:<24s} {detail}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="api-football production smoke (3 endpoint)",
    )
    parser.add_argument(
        "--key", default=None,
        help="x-apisports-key (boşsa settings.api_football_key okunur)",
    )
    parser.add_argument(
        "--league", type=int, required=True,
        help="API-Football league.id (örn. Süper Lig=203, EPL=39)",
    )
    parser.add_argument("--season", type=int, required=True, help="Sezon yılı, örn. 2024")
    parser.add_argument(
        "--base-url", default=None,
        help=f"override (default: settings.api_football_base_url ya da {DEFAULT_BASE_URL})",
    )
    args = parser.parse_args()

    s = get_settings()
    key = args.key or s.api_football_key
    base_url = args.base_url or s.api_football_base_url or DEFAULT_BASE_URL
    if not key:
        print("HATA: --key verilmedi ve settings.api_football_key boş.")
        return 2

    print(f"api-football smoke @ {base_url}")
    print(f"  league={args.league} season={args.season}\n")

    failures = 0

    print("[1/3] /leagues")
    try:
        info = smoke_leagues(base_url, key, args.league)
        _print_result(
            "leagues",
            True,
            f"id={info['id']} name={info['name']!r} seasons={info['season_count']}",
        )
    except SmokeError as e:
        failures += 1
        _print_result("leagues", False, str(e))

    print("\n[2/3] /teams")
    try:
        info = smoke_teams(base_url, key, args.league, args.season)
        _print_result(
            "teams",
            True,
            f"count={info['count']} sample={info['sample_id']}:{info['sample_name']!r}",
        )
        sample_team_id = info["sample_id"]
    except SmokeError as e:
        failures += 1
        _print_result("teams", False, str(e))
        sample_team_id = None

    print("\n[3/3] /fixtures")
    if sample_team_id is None:
        _print_result("fixtures", False, "teams smoke fail → atlandı")
        failures += 1
    else:
        try:
            info = smoke_fixtures(base_url, key, sample_team_id, last_n=5)
            _print_result(
                "fixtures",
                True,
                f"count={info['count']} sample={info['sample_id']} "
                f"{info['sample_home']!r} vs {info['sample_away']!r} "
                f"status={info['sample_status']}",
            )
        except SmokeError as e:
            failures += 1
            _print_result("fixtures", False, str(e))

    print()
    if failures == 0:
        print("OK — 3/3 endpoint passed.")
        return 0
    print(f"FAIL — {failures}/3 endpoint(s) failed.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
