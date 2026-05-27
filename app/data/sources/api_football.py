"""API-Football adapter.

`USE_FIXTURES=true` ise `tests/fixtures/*.json`'dan okur — kota yakmaz, anahtar
gerektirmez. Aksi halde `x-apisports-key` header'ı ile HTTP isteği atar.

Sözleşme `DataSource`'ta; bu sınıf ham yanıtı `domain/` modellerine çevirir.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.usage import consume_quota
from app.data.cache import cache_get, cache_set
from app.data.sources.base import DataSource
from app.db.session import SessionLocal
from app.domain import League, LineupEntry, Match, PlayerMatchStats, Team
from app.sports import football

log = get_logger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_DIR = _PROJECT_ROOT / "tests" / "fixtures"

_SOURCE_NAME = "api_football"
# Veriye göre TTL: lig/takım listesi nadiren değişir, fikstür sıklıkla.
_TTL_SECONDS: dict[str, int] = {
    "leagues": 86_400,
    "teams": 86_400,
    "fixtures": 3_600,
}
_DEFAULT_TTL = 600


def _cache_key(path: str, params: dict[str, Any]) -> str:
    return f"{path}?{json.dumps(params, sort_keys=True)}"


class APIFootball(DataSource):
    name = "api_football"

    def __init__(self) -> None:
        s = get_settings()
        self._use_fixtures = s.use_fixtures
        self._base_url = s.api_football_base_url.rstrip("/")
        self._key = s.api_football_key

    # DataSource -----------------------------------------------------------

    def get_leagues(self) -> list[League]:
        raw = self._get("leagues", {})
        return [lg for lg in (self._to_league(item) for item in raw.get("response", [])) if lg is not None]

    def get_teams(self, league_id: int, season: int) -> list[Team]:
        raw = self._get("teams", {"league": league_id, "season": season})
        return [self._to_team(item) for item in raw.get("response", [])]

    def get_team_matches(self, team_id: int, last_n: int) -> list[Match]:
        raw = self._get("fixtures", {"team": team_id, "last": last_n})
        return [self._to_match(item) for item in raw.get("response", [])]

    # ---- Prompt 4: lineup + per-player stats --------------------------------

    def get_fixture_lineups(self, fixture_id: int) -> list[LineupEntry]:
        """Bir maçın ilk-11 + bench oyuncularını döner.

        API yanıtı `response: [{team, formation, startXI: [...], substitutes: [...]}]`
        — iki takımlık liste; her takım için ayrı LineupEntry üretiriz.
        """
        raw = self._get("fixtures/lineups", {"fixture": fixture_id})
        out: list[LineupEntry] = []
        for team_block in raw.get("response", []):
            team_id = int(team_block["team"]["id"])
            formation = team_block.get("formation")
            for slot in team_block.get("startXI", []):
                p = slot.get("player", slot)
                out.append(self._to_lineup_entry(
                    fixture_id=fixture_id, team_id=team_id,
                    raw_player=p, is_starter=True, formation=formation,
                ))
            for slot in team_block.get("substitutes", []):
                p = slot.get("player", slot)
                out.append(self._to_lineup_entry(
                    fixture_id=fixture_id, team_id=team_id,
                    raw_player=p, is_starter=False, formation=formation,
                ))
        return out

    def get_fixture_player_stats(self, fixture_id: int) -> list[PlayerMatchStats]:
        """Bir maçın per-player istatistikleri (rating, pas, şut, dakika, kart).

        API yanıtı `response: [{team, players: [{player, statistics: [{...}]}]}]`.
        statistics tek-elemanlı liste (maç başına bir kayıt).
        """
        raw = self._get("fixtures/players", {"fixture": fixture_id})
        out: list[PlayerMatchStats] = []
        for team_block in raw.get("response", []):
            team_id = int(team_block["team"]["id"])
            for p in team_block.get("players", []):
                stat = self._to_player_match_stats(
                    fixture_id=fixture_id, team_id=team_id, raw=p,
                )
                if stat is not None:
                    out.append(stat)
        return out

    @staticmethod
    def _to_lineup_entry(
        *, fixture_id: int, team_id: int, raw_player: dict[str, Any],
        is_starter: bool, formation: str | None,
    ) -> LineupEntry:
        return LineupEntry(
            match_external_id=fixture_id,
            team_external_id=team_id,
            player_external_id=int(raw_player["id"]),
            player_name=str(raw_player.get("name") or "unknown"),
            position_code=raw_player.get("pos"),
            jersey=raw_player.get("number"),
            is_starter=is_starter,
            captain=bool(raw_player.get("captain", False)),
            formation_played=formation,
        )

    @staticmethod
    def _to_player_match_stats(
        *, fixture_id: int, team_id: int, raw: dict[str, Any],
    ) -> PlayerMatchStats | None:
        player = raw.get("player") or {}
        stats_list = raw.get("statistics") or []
        if not stats_list:
            return None
        s = stats_list[0]
        games = s.get("games") or {}
        passes = s.get("passes") or {}
        shots = s.get("shots") or {}
        dribbles = s.get("dribbles") or {}
        fouls = s.get("fouls") or {}
        cards = s.get("cards") or {}
        subs = s.get("substitutes") or {}
        minutes = games.get("minutes")
        if minutes is None:
            return None  # oynamamış oyuncu
        try:
            pid = int(player["id"])
        except (KeyError, TypeError, ValueError):
            return None
        rating_raw = games.get("rating")
        rating: float | None = (
            None if rating_raw is None or rating_raw == ""
            else float(rating_raw)
        )
        return PlayerMatchStats(
            match_external_id=fixture_id,
            team_external_id=team_id,
            player_external_id=pid,
            minutes=int(minutes),
            rating=rating,
            passes_total=passes.get("total"),
            passes_accuracy=passes.get("accuracy"),
            shots_total=shots.get("total"),
            shots_on=shots.get("on"),
            dribbles_attempts=dribbles.get("attempts"),
            dribbles_success=dribbles.get("success"),
            fouls_committed=fouls.get("committed"),
            fouls_drawn=fouls.get("drawn"),
            yellow_cards=cards.get("yellow"),
            red_cards=cards.get("red"),
            second_yellow=cards.get("yellowred") if cards.get("yellowred") else None,
            substituted_in_minute=subs.get("in"),
            substituted_out_minute=subs.get("out"),
        )

    # Internals ------------------------------------------------------------

    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        if self._use_fixtures:
            return self._read_fixture(path, params)
        return self._http_get(path, params)

    def _http_get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self._key:
            raise RuntimeError(
                "API_FOOTBALL_KEY boş. USE_FIXTURES=true ile fixture'tan okuyun "
                "ya da .env içine anahtar girin."
            )
        cache_key = _cache_key(path, params)

        with SessionLocal() as session:
            cached = cache_get(session, source=_SOURCE_NAME, key=cache_key)
            if cached is not None:
                log.info("api_football cache hit: %s", cache_key)
                return cached
            # Atomik: önce kaydet+sayıp limitin altında olduğumuzu doğrula, sonra HTTP.
            # Bu pessimistic sayım — HTTP başarısız olsa bile kota düşülmüş kalır
            # (real-world rate limiter normu; sürpriz fatura önler).
            consume_quota(session, source=_SOURCE_NAME, endpoint=path)
            session.commit()

        url = f"{self._base_url}/{path}"
        log.info("api_football GET %s params=%s", path, params)
        with httpx.Client(timeout=10.0) as client:
            r = client.get(url, params=params, headers={"x-apisports-key": self._key})
            r.raise_for_status()
            data = r.json()

        ttl = _TTL_SECONDS.get(path, _DEFAULT_TTL)
        with SessionLocal() as session:
            cache_set(session, source=_SOURCE_NAME, key=cache_key, value=data, ttl_seconds=ttl)
            session.commit()
        return data

    def _read_fixture(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        if path == "leagues":
            name = "leagues.json"
        elif path == "teams":
            name = f"teams_{params['league']}.json"
        elif path == "fixtures":
            name = f"matches_{params['team']}.json"
        elif path == "fixtures/lineups":
            name = f"lineups_{params['fixture']}.json"
        elif path == "fixtures/players":
            name = f"player_stats_{params['fixture']}.json"
        else:
            raise ValueError(f"fixture eşlemesi yok: {path}")
        fp = FIXTURE_DIR / name
        log.info("api_football fixture okuma: %s", fp.name)
        with fp.open("r", encoding="utf-8") as f:
            return json.load(f)

    # Map raw → domain -----------------------------------------------------

    @staticmethod
    def _to_league(item: dict[str, Any]) -> League | None:
        league = item["league"]
        country = item.get("country", {}) or {}
        seasons = item.get("seasons") or []
        current = next((s for s in seasons if s.get("current")), seasons[0] if seasons else None)
        if current is None:
            # API geçici olarak seasons=[] döndü; sessiz reject yerine açıkça atla.
            log.warning("api_football: league=%s sezon listesi boş, atlandı", league.get("id"))
            return None
        return League(
            sport=football.SPORT_NAME,
            external_id=int(league["id"]),
            name=str(league["name"]),
            season=int(current["year"]),
            country=country.get("name"),
        )

    @staticmethod
    def _to_team(item: dict[str, Any]) -> Team:
        team = item["team"]
        return Team(
            sport=football.SPORT_NAME,
            external_id=int(team["id"]),
            name=str(team["name"]),
            country=team.get("country"),
            founded=team.get("founded"),
        )

    @staticmethod
    def _to_match(item: dict[str, Any]) -> Match:
        fix = item["fixture"]
        lg = item["league"]
        teams = item["teams"]
        goals = item.get("goals") or {}
        kickoff_raw = fix["date"]
        kickoff = (
            datetime.fromisoformat(kickoff_raw.replace("Z", "+00:00"))
            if isinstance(kickoff_raw, str)
            else kickoff_raw
        )
        return Match(
            sport=football.SPORT_NAME,
            external_id=int(fix["id"]),
            league_external_id=int(lg["id"]),
            season=int(lg["season"]),
            kickoff=kickoff,
            status=str(fix["status"]["short"]),
            home_team_external_id=int(teams["home"]["id"]),
            away_team_external_id=int(teams["away"]["id"]),
            home_score=goals.get("home"),
            away_score=goals.get("away"),
        )
