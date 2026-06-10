"""Sportmonks Football API adapter — ikinci veri kaynağı.

API-Football ile AYNI domain modellerine (Match / LineupEntry / PlayerMatchStats)
map'ler; böylece mevcut sync/ingest/season-stats hattı DEĞİŞMEDEN çalışır.
Sportmonks tek `api_token` (query param) + iç içe `include` ile çalışır ve
API-Football'dan zengindir (gerçek xG + oyuncu-başı istatistik + foto).

Tasarım: tüm parse mantığı SAF @staticmethod'larda (fixture JSON'u alır) →
testler ham JSON'u doğrudan besler, HTTP gerekmez. Public fetch metotları
fixture'ı bir kez çekip (instance cache) parser'lara verir.

type_id eşlemeleri kullanıcının sağladığı gerçek Süper Lig yanıtından
doğrulandı; emin olunmayanlar yorumda işaretli ve None-güvenli (eksikse alan
boş kalır, kırılmaz).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.domain import LineupEntry, Match, Player, PlayerMatchStats, Team
from app.sports import football

log = get_logger(__name__)

_SOURCE_NAME = "sportmonks"

# Sportmonks position_id → bizim pozisyon kodu (G/D/M/F). Gerçek yanıttan:
# 24=GK, 25=Defender, 26=Midfielder, 27=Attacker.
_POSITION_MAP: dict[int, str] = {
    24: football.POSITION_GOALKEEPER,
    25: football.POSITION_DEFENDER,
    26: football.POSITION_MIDFIELDER,
    27: football.POSITION_FORWARD,
}

# lineups[].type_id: 11 = ilk 11, 12 = yedek (bench). Doğrulandı: Ndidi type 12
# + sonradan girdi (sub).
_LINEUP_TYPE_STARTER = 11

# Event type_id'leri (gerçek yanıttan doğrulandı):
_EV_GOAL = 14
_EV_PENALTY = 16
_EV_SUBSTITUTION = 18
_EV_YELLOW = 19
_EV_RED = 20

# lineups[].details type_id → PlayerMatchStats alanı.
# ✓ = gerçek Süper Lig yanıtında doğrudan doğrulandı. (?) = Sportmonks standart
# id, kaleci maçıyla teyit edilecek; eksikse None kalır (kırılmaz).
_DETAIL_FIELD_BY_TYPE: dict[int, str] = {
    119: "minutes",                 # ✓ Minutes Played
    118: "rating",                  # ✓ Rating
    80: "passes_total",             # ✓ Passes
    1584: "passes_accuracy",        # ✓ Accurate Passes Percentage
    42: "shots_total",              # ✓ Shots Total
    86: "shots_on",                 # ✓ Shots On Target
    108: "dribbles_attempts",       # ✓ Dribble Attempts
    109: "dribbles_success",        # ✓ Successful Dribbles
    105: "duels_total",             # ✓ Total Duels
    106: "duels_won",               # ✓ Duels Won
    56: "fouls_committed",          # ✓ Fouls
    78: "tackles_total",            # ✓ Tackles
    100: "interceptions",           # ✓ Interceptions
    117: "key_passes",              # ✓ Key Passes
    57: "saves",                    # (?) Saves (kaleci maçıyla teyit)
    88: "goals_conceded",           # ✓ Goals Conceded (squad yanıtı GOALS_CONCEDED)
}


def _as_int(v: Any) -> int | None:
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return None


def _as_float(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _season_start_year(kickoff: datetime) -> int:
    """Avrupa sezonu: Temmuz+ → o yıl başlar; öncesi → bir önceki yıl."""
    return kickoff.year if kickoff.month >= 7 else kickoff.year - 1


class Sportmonks:
    """Sportmonks Football API istemcisi (API-Football adapter'ıyla aynı sözleşme)."""

    # Tek fixture için yeterli include seti (lineups.details = oyuncu istatistiği,
    # xgfixture = gerçek xG). participants/state/scores/events karar+skor için.
    FIXTURE_INCLUDE = (
        "participants;league;state;scores;events;periods;"
        "lineups.details;lineups.xglineup;xgfixture"
    )

    # Fikstür listesi (takım programı) için yeterli include — skor/karar/kimlik.
    # Oyuncu-başı detay gerekmez (o, fixture başına FIXTURE_INCLUDE ile çekilir).
    SCHEDULE_INCLUDE = "participants;league;state;scores"

    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        s = get_settings()
        self._key = api_key if api_key is not None else s.sportmonks_api_key
        self._base_url = (base_url or s.sportmonks_base_url).rstrip("/")
        self._fixture_cache: dict[int, dict[str, Any]] = {}

    # ── HTTP ────────────────────────────────────────────────────────────────
    def get_fixture(self, fixture_id: int) -> dict[str, Any]:
        """Tek fixture'ı include'larla çek (instance cache: aynı id bir kez)."""
        fid = int(fixture_id)
        if fid in self._fixture_cache:
            return self._fixture_cache[fid]
        if not self._key:
            raise RuntimeError(
                "SPORTMONKS_API_KEY boş. .env'e anahtar girin ya da testte "
                "parse_* saf fonksiyonlarını doğrudan kullanın."
            )
        url = f"{self._base_url}/fixtures/{fid}"
        params = {"api_token": self._key, "include": self.FIXTURE_INCLUDE}
        s = get_settings()
        log.info("sportmonks GET fixtures/%d", fid)
        with httpx.Client(timeout=s.http_timeout_seconds) as client:
            r = client.get(url, params=params)
            r.raise_for_status()
            raw = r.json().get("data", {})
        self._fixture_cache[fid] = raw
        return raw

    def _get_team_fixtures(
        self, team_id: int, *, days_back: int = 365,
    ) -> list[dict[str, Any]]:
        """Takımın `days_back` günlük penceresindeki fixture'larını çek (data listesi).

        Sportmonks: `fixtures/between/{from}/{to}/{teamId}`. Sayfalama varsa
        tüm sayfalar toplanır (pagination.has_more)."""
        if not self._key:
            raise RuntimeError(
                "SPORTMONKS_API_KEY boş. .env'e anahtar girin ya da testte "
                "parse_schedule saf fonksiyonunu doğrudan kullanın."
            )
        today = datetime.now(tz=UTC).date()
        start = today - timedelta(days=days_back)
        url = f"{self._base_url}/fixtures/between/{start}/{today}/{team_id}"
        s = get_settings()
        out: list[dict[str, Any]] = []
        page = 1
        log.info("sportmonks GET fixtures/between team=%d", team_id)
        with httpx.Client(timeout=s.http_timeout_seconds) as client:
            while True:
                params = {
                    "api_token": self._key,
                    "include": self.SCHEDULE_INCLUDE,
                    "page": page,
                }
                r = client.get(url, params=params)
                r.raise_for_status()
                body = r.json()
                out.extend(body.get("data", []) or [])
                pag = body.get("pagination") or {}
                if not pag.get("has_more") or page >= 50:
                    break
                page += 1
        return out

    # ── Public (ingest sözleşmesi) ────────────────────────────────────────────
    def get_fixture_lineups(self, fixture_id: int) -> list[LineupEntry]:
        return self.parse_lineups(self.get_fixture(fixture_id))

    def get_fixture_player_stats(self, fixture_id: int) -> list[PlayerMatchStats]:
        return self.parse_player_stats(self.get_fixture(fixture_id))

    def get_match(self, fixture_id: int) -> Match:
        return self.parse_match(self.get_fixture(fixture_id))

    def get_team_matches(self, team_id: int, last_n: int) -> list[Match]:
        """Bir takımın son `last_n` (oynanmış) maçı — en yeni önce.

        Sportmonks `fixtures/between/{from}/{to}/{teamId}` ile tarih penceresi
        çekilir; bitmiş maçlar kickoff'a göre azalan sıralanıp ilk last_n alınır.
        """
        raw_list = self._get_team_fixtures(team_id)
        matches = self.parse_schedule(raw_list)
        finished = [m for m in matches if m.status in football.FINISHED_STATUSES]
        finished.sort(key=lambda m: m.kickoff, reverse=True)
        return finished[: max(0, last_n)]

    # ── Saf parser'lar (test girişi = ham fixture JSON) ───────────────────────
    @staticmethod
    def _participants(raw: dict[str, Any]) -> tuple[int | None, int | None]:
        """(home_team_id, away_team_id) — meta.location'dan."""
        home = away = None
        for p in raw.get("participants", []):
            loc = (p.get("meta") or {}).get("location")
            if loc == "home":
                home = _as_int(p.get("id"))
            elif loc == "away":
                away = _as_int(p.get("id"))
        return home, away

    @staticmethod
    def parse_match(raw: dict[str, Any]) -> Match:
        home_id, away_id = Sportmonks._participants(raw)
        ts = raw.get("starting_at_timestamp")
        if ts is not None:
            kickoff = datetime.fromtimestamp(int(ts), tz=UTC)
        else:
            kickoff = datetime.strptime(
                str(raw["starting_at"]), "%Y-%m-%d %H:%M:%S",
            ).replace(tzinfo=UTC)
        status = str((raw.get("state") or {}).get("developer_name") or "NS")

        # Skor: scores[] description="CURRENT", participant_id ile eşle.
        home_score = away_score = None
        for sc in raw.get("scores", []):
            if sc.get("description") != "CURRENT":
                continue
            goals = (sc.get("score") or {}).get("goals")
            pid = _as_int(sc.get("participant_id"))
            if pid == home_id:
                home_score = _as_int(goals)
            elif pid == away_id:
                away_score = _as_int(goals)

        return Match(
            sport=football.SPORT_NAME,
            external_id=_as_int(raw["id"]) or 0,
            league_external_id=_as_int(raw.get("league_id")) or 0,
            season=_season_start_year(kickoff),
            kickoff=kickoff,
            status=status,
            home_team_external_id=home_id or 0,
            away_team_external_id=away_id or 0,
            home_score=home_score,
            away_score=away_score,
        )

    @staticmethod
    def parse_schedule(data: list[dict[str, Any]]) -> list[Match]:
        """Fikstür listesi (takım programı) → Match listesi.

        Her eleman tek fixture objesidir (parse_match ile aynı yapı). Kimliği
        çözülemeyen (id yok) ya da bozuk kayıtlar atlanır — liste kırılmaz."""
        out: list[Match] = []
        for f in data or []:
            if not isinstance(f, dict) or f.get("id") is None:
                continue
            try:
                out.append(Sportmonks.parse_match(f))
            except (KeyError, ValueError, TypeError) as e:  # noqa: PERF203
                log.warning("schedule fixture atlandı id=%s: %s", f.get("id"), e)
        return out

    @staticmethod
    def parse_teams(raw: dict[str, Any]) -> list[Team]:
        """Fixture participants'tan Team listesi (sync için temel kimlik)."""
        out: list[Team] = []
        for p in raw.get("participants", []):
            tid = _as_int(p.get("id"))
            if tid is None:
                continue
            out.append(Team(
                sport=football.SPORT_NAME,
                external_id=tid,
                name=str(p.get("name") or "unknown"),
                country=None,
                founded=_as_int(p.get("founded")),
            ))
        return out

    @staticmethod
    def _player_to_domain(p: dict[str, Any]) -> Player | None:
        """Sportmonks player objesi → Player domain (master veri).

        Uyruk: `nationality` nested objesi varsa (squad include eder) adı alınır;
        yoksa None (fixture lineups yalnız nationality_id verir). Foto (image_path)
        Player modelinde yok; media proxy aşamasında ele alınır.
        """
        pid = _as_int(p.get("id"))
        if pid is None:
            return None
        dob = None
        raw_dob = p.get("date_of_birth")
        if raw_dob:
            try:
                dob = datetime.strptime(str(raw_dob), "%Y-%m-%d").date()
            except ValueError:
                dob = None
        nat = None
        nat_obj = p.get("nationality")
        if isinstance(nat_obj, dict):
            nat = nat_obj.get("name") or None
        return Player(
            sport=football.SPORT_NAME,
            external_id=pid,
            name=str(p.get("display_name") or p.get("name") or "unknown"),
            position=_POSITION_MAP.get(_as_int(p.get("position_id")) or -1),
            birth_date=dob,
            nationality=nat,
        )

    @staticmethod
    def parse_squad(data: list[dict[str, Any]]) -> list[Player]:
        """Takım kadrosu (squads/teams/{id}) → Player master listesi.

        Her eleman bir oyuncu-sezon kaydıdır; `player` nested objesinden master
        veri (ad/pozisyon/doğum/uyruk) türetilir. position_id kök seviyede de var
        (player objesinde yoksa fallback). Aynı oyuncu tekilleştirilir."""
        by_id: dict[int, Player] = {}
        for entry in data or []:
            if not isinstance(entry, dict):
                continue
            p = entry.get("player")
            if not isinstance(p, dict):
                continue
            # position_id player'da yoksa kök kayıttan al
            if p.get("position_id") is None and entry.get("position_id") is not None:
                p = {**p, "position_id": entry.get("position_id")}
            dom = Sportmonks._player_to_domain(p)
            if dom is not None and dom.external_id not in by_id:
                by_id[dom.external_id] = dom
        return list(by_id.values())

    @staticmethod
    def parse_players(raw: dict[str, Any]) -> list[Player]:
        """Fixture içindeki tüm oyuncu master kayıtları (lineups + events'ten).

        Player tablosunu (ad/pozisyon/doğum tarihi → gerçek yaş + avatar)
        besler. Aynı oyuncu birden çok yerde geçse de tekilleştirilir."""
        by_id: dict[int, Player] = {}
        sources: list[dict[str, Any]] = []
        for ln in raw.get("lineups", []):
            if isinstance(ln.get("player"), dict):
                sources.append(ln["player"])
        for ev in raw.get("events", []):
            if isinstance(ev.get("player"), dict):
                sources.append(ev["player"])
        for p in sources:
            dom = Sportmonks._player_to_domain(p)
            if dom is not None and dom.external_id not in by_id:
                by_id[dom.external_id] = dom
        return list(by_id.values())

    @staticmethod
    def parse_lineups(raw: dict[str, Any]) -> list[LineupEntry]:
        fixture_id = _as_int(raw.get("id")) or 0
        out: list[LineupEntry] = []
        for ln in raw.get("lineups", []):
            pid = _as_int(ln.get("player_id"))
            tid = _as_int(ln.get("team_id"))
            if pid is None or tid is None:
                continue
            pos_code = _POSITION_MAP.get(_as_int(ln.get("position_id")) or -1)
            out.append(LineupEntry(
                match_external_id=fixture_id,
                team_external_id=tid,
                player_external_id=pid,
                player_name=str(ln.get("player_name") or "unknown"),
                position_code=pos_code,
                jersey=_as_int(ln.get("jersey_number")),
                is_starter=_as_int(ln.get("type_id")) == _LINEUP_TYPE_STARTER,
                captain=bool(ln.get("captain", False)),
                formation_played=ln.get("formation_field") or None,
            ))
        return out

    @staticmethod
    def _events_index(raw: dict[str, Any]) -> dict[str, Any]:
        """Event'lerden oyuncu-başı gol/asist/kart + giriş/çıkış dakikası türet.

        Sportmonks sub konvansiyonu (yanıttan doğrulandı): substitution event'inde
        player_id = SAHAYA GİREN, related_player_id = ÇIKAN. (Ndidi 69' girdi →
        details'te 21 dk = 90−69.)
        """
        goals: dict[int, int] = {}
        assists: dict[int, int] = {}
        yellow: dict[int, int] = {}
        red: dict[int, int] = {}
        sub_in: dict[int, int] = {}
        sub_out: dict[int, int] = {}
        for ev in raw.get("events", []):
            t = _as_int(ev.get("type_id"))
            pid = _as_int(ev.get("player_id"))
            rid = _as_int(ev.get("related_player_id"))
            minute = _as_int(ev.get("minute"))
            if t in (_EV_GOAL, _EV_PENALTY):
                if pid is not None:
                    goals[pid] = goals.get(pid, 0) + 1
                if rid is not None:
                    assists[rid] = assists.get(rid, 0) + 1
            elif t == _EV_YELLOW and pid is not None:
                yellow[pid] = yellow.get(pid, 0) + 1
            elif t == _EV_RED and pid is not None:
                red[pid] = red.get(pid, 0) + 1
            elif t == _EV_SUBSTITUTION and minute is not None:
                if pid is not None:
                    sub_in[pid] = minute
                if rid is not None:
                    sub_out[rid] = minute
        return {
            "goals": goals, "assists": assists, "yellow": yellow,
            "red": red, "sub_in": sub_in, "sub_out": sub_out,
        }

    @staticmethod
    def parse_player_stats(raw: dict[str, Any]) -> list[PlayerMatchStats]:
        """lineups[].details (type_id'li) + events → PlayerMatchStats listesi.

        Sadece oynayan (details'i olan ya da sub-in) oyuncular döner; oynamamış
        yedekler hariç (minutes None ise atlanır)."""
        fixture_id = _as_int(raw.get("id")) or 0
        idx = Sportmonks._events_index(raw)

        out: list[PlayerMatchStats] = []
        for ln in raw.get("lineups", []):
            pid = _as_int(ln.get("player_id"))
            tid = _as_int(ln.get("team_id"))
            if pid is None or tid is None:
                continue
            fields: dict[str, Any] = {}
            for d in ln.get("details", []):
                field = _DETAIL_FIELD_BY_TYPE.get(_as_int(d.get("type_id")) or -1)
                if field is None:
                    continue
                val = (d.get("data") or {}).get("value")
                fields[field] = _as_float(val) if field == "rating" else _as_int(val)

            minutes = fields.get("minutes")
            if minutes is None:
                continue  # oynamamış (details yok) → atla

            out.append(PlayerMatchStats(
                match_external_id=fixture_id,
                team_external_id=tid,
                player_external_id=pid,
                minutes=int(minutes),
                rating=fields.get("rating"),
                passes_total=fields.get("passes_total"),
                passes_accuracy=fields.get("passes_accuracy"),
                shots_total=fields.get("shots_total"),
                shots_on=fields.get("shots_on"),
                dribbles_attempts=fields.get("dribbles_attempts"),
                dribbles_success=fields.get("dribbles_success"),
                fouls_committed=fields.get("fouls_committed"),
                fouls_drawn=None,
                yellow_cards=idx["yellow"].get(pid),
                red_cards=idx["red"].get(pid),
                second_yellow=None,
                substituted_in_minute=idx["sub_in"].get(pid),
                substituted_out_minute=idx["sub_out"].get(pid),
                goals=idx["goals"].get(pid),
                assists=idx["assists"].get(pid),
                goals_conceded=fields.get("goals_conceded"),
                saves=fields.get("saves"),
                key_passes=fields.get("key_passes"),
                tackles_total=fields.get("tackles_total"),
                interceptions=fields.get("interceptions"),
                duels_total=fields.get("duels_total"),
                duels_won=fields.get("duels_won"),
            ))
        return out
