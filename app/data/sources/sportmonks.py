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

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.data.sources.base import DataSource
from app.domain import League, LineupEntry, Match, Player, PlayerMatchStats, Team
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


# Standings details type_id → bizim alan (gerçek Süper Lig yanıtından doğrulandı).
_STANDING_DETAIL_BY_TYPE: dict[int, str] = {
    129: "played",          # OVERALL_MATCHES
    130: "won",             # OVERALL_WINS
    131: "draw",            # OVERALL_DRAWS
    132: "lost",            # OVERALL_LOST
    133: "goals_for",       # OVERALL_SCORED
    134: "goals_against",   # OVERALL_CONCEDED
    179: "goal_diff",       # OVERALL_GOAL_DIFFERENCE
    187: "points",          # TOTAL_POINTS
    7939: "xpoints",        # EXPECTED_POINTS (xPTS) — Sportmonks zengini
}


# Sezon-squad details type_id → season-stats anahtarı (mevcut /season-stats
# yanıt şekliyle uyumlu). Temel sayaçlar bu planda doğrulandı; pas/şut/rating
# gibi zenginler üst planda gelir (Beşiktaş playground örneğinde mevcuttu).
_SQUAD_SEASON_DETAIL_BY_TYPE: dict[int, str] = {
    52: "goals",            # ✓ GOALS
    79: "assists",          # ✓ ASSISTS
    119: "minutes",         # ✓ MINUTES_PLAYED
    321: "appearances",     # ✓ APPEARANCES
    88: "goals_conceded",   # ✓ GOALS_CONCEDED
    194: "clean_sheets",    # ✓ CLEANSHEET
    84: "yellow_cards",     # ✓ YELLOWCARDS
    83: "red_cards",        # ✓ REDCARDS
    324: "own_goals",       # ✓ OWN_GOALS
    # Zengin (üst plan) — aynı parser otomatik alır:
    42: "shots", 86: "shots_on", 1584: "pass_accuracy", 117: "key_passes",
    108: "dribbles_att", 109: "dribbles_succ", 78: "tackles",
    100: "interceptions", 105: "duels", 106: "duels_won",
    107: "aerials_won", 56: "fouls", 57: "saves",
}


@dataclass(frozen=True)
class SquadMember:
    """Kadro üyesi: master veri + foto + sezon-toplam istatistik (tek çağrıda).

    season dict'i mevcut GET /players/{id}/season-stats player_agg şekliyle
    uyumludur (eksik metrikler 0/None)."""

    player_external_id: int
    name: str
    position: str | None = None
    jersey: int | None = None
    photo_url: str | None = None
    birth_date: str | None = None  # ISO; yoksa None
    nationality: str | None = None
    captain: bool = False
    season: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StandingRow:
    """Puan durumu satırı (lig tablosu). Domain'e ait değil — sunum/UI yapısı."""

    position: int
    team_external_id: int
    team_name: str
    played: int = 0
    won: int = 0
    draw: int = 0
    lost: int = 0
    goals_for: int = 0
    goals_against: int = 0
    goal_diff: int = 0
    points: int = 0
    xpoints: float | None = None
    form: list[str] = field(default_factory=list)  # eski→yeni "W"/"D"/"L"
    qualification: str | None = None  # rule.type.name (ör. "UEFA Champions League")


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


def _season_year_from_name(name: Any) -> int | None:
    """Sezon adı → başlangıç yılı. "2025/2026"→2025, "2025"→2025."""
    if not name:
        return None
    head = str(name).strip().split("/")[0].strip()
    return _as_int(head)


class Sportmonks(DataSource):
    """Sportmonks Football API istemcisi (API-Football adapter'ıyla aynı sözleşme).

    DataSource ABC'sini doldurur (get_leagues/get_teams/get_team_matches) → sync
    hattı `DATA_SOURCE=sportmonks` ile değişmeden çalışır. Ayrıca AppearanceSource
    (lineup + player-stats) ve standings/squad gibi zengin uçları sağlar."""

    name = _SOURCE_NAME

    # Tek fixture için yeterli include seti (lineups.details = oyuncu istatistiği,
    # xgfixture = gerçek xG). participants/state/scores/events karar+skor için.
    # Base include — her planda çalışır (kadro + oyuncu-başı detay dahil).
    FIXTURE_BASE_INCLUDE = (
        "participants;league;state;scores;events;periods;lineups.details"
    )
    # xG include'ları — yalnız xG'li planlarda. Erişim yoksa Sportmonks TÜM
    # isteği 403 yapar; bu yüzden ayrı tutulur ve 403'te otomatik düşülür.
    FIXTURE_XG_INCLUDE = "lineups.xglineup;xgfixture"
    # Geriye uyumluluk (eski testler/koda): tam include.
    FIXTURE_INCLUDE = f"{FIXTURE_BASE_INCLUDE};{FIXTURE_XG_INCLUDE}"

    # Fikstür listesi (takım programı) için yeterli include — skor/karar/kimlik.
    # Oyuncu-başı detay gerekmez (o, fixture başına FIXTURE_INCLUDE ile çekilir).
    SCHEDULE_INCLUDE = "participants;league;state;scores"

    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        s = get_settings()
        self._key = api_key if api_key is not None else s.sportmonks_api_key
        self._base_url = (base_url or s.sportmonks_base_url).rstrip("/")
        self._fixture_cache: dict[int, dict[str, Any]] = {}
        self._season_id_cache: dict[tuple[int, int], int | None] = {}
        # xG include'larına erişim var mı? İlk 403'te False'a düşer (plan kapsamı).
        self._xg_enabled = True

    def _require_key(self) -> None:
        if not self._key:
            raise RuntimeError(
                "SPORTMONKS_API_KEY boş. .env'e anahtar girin ya da testte "
                "saf parse_* fonksiyonlarını doğrudan kullanın."
            )

    def _get_json(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        """Tek GET → tam JSON gövdesi (data + pagination + subscription)."""
        self._require_key()
        url = f"{self._base_url}/{path.lstrip('/')}"
        s = get_settings()
        with httpx.Client(timeout=s.http_timeout_seconds) as client:
            r = client.get(url, params={"api_token": self._key, **params})
            r.raise_for_status()
            return r.json()

    def _resolve_season_id(self, league_id: int, season_year: int) -> int | None:
        """(lig, yıl) → Sportmonks season_id. Bulunamazsa None (sessiz).

        DataSource sözleşmesi sezon YILI (2025) alır; Sportmonks season_id
        (25682) ile çalışır. /leagues/{id}?include=seasons ile eşlenir + cache."""
        key = (league_id, season_year)
        if key in self._season_id_cache:
            return self._season_id_cache[key]
        body = self._get_json(f"leagues/{league_id}", {"include": "seasons"})
        seasons = (body.get("data") or {}).get("seasons") or []
        found: int | None = None
        for s in seasons:
            if _season_year_from_name(s.get("name")) == season_year:
                found = _as_int(s.get("id"))
                break
        if found is None:
            log.warning(
                "sportmonks: lig %d için %d sezonu bulunamadı (abonelik/kapsam?)",
                league_id, season_year,
            )
        self._season_id_cache[key] = found
        return found

    # ── HTTP ────────────────────────────────────────────────────────────────
    def _fixture_include(self) -> str:
        """Plan kapsamına göre include — xG erişimi yoksa base."""
        if self._xg_enabled:
            return f"{self.FIXTURE_BASE_INCLUDE};{self.FIXTURE_XG_INCLUDE}"
        return self.FIXTURE_BASE_INCLUDE

    def get_fixture(self, fixture_id: int) -> dict[str, Any]:
        """Tek fixture'ı include'larla çek (instance cache: aynı id bir kez).

        xG include'ına erişim yoksa (plan kapsamı) Sportmonks tüm isteği 403 yapar;
        bu durumda xG düşülüp bir kez yeniden denenir ve instance bunu hatırlar."""
        fid = int(fixture_id)
        if fid in self._fixture_cache:
            return self._fixture_cache[fid]
        self._require_key()
        url = f"{self._base_url}/fixtures/{fid}"
        s = get_settings()
        log.info("sportmonks GET fixtures/%d", fid)
        with httpx.Client(timeout=s.http_timeout_seconds) as client:
            for attempt in range(2):
                params = {"api_token": self._key, "include": self._fixture_include()}
                r = client.get(url, params=params)
                if r.status_code == 403 and self._xg_enabled:
                    # xG'siz plan: include'ı düşür, bir kez daha dene.
                    log.warning(
                        "sportmonks: xG include'una erişim yok — xG'siz devam "
                        "(plan kapsamı). Detay: %s",
                        r.json().get("message", "")[:120],
                    )
                    self._xg_enabled = False
                    continue
                r.raise_for_status()
                raw = r.json().get("data", {})
                break
        self._fixture_cache[fid] = raw
        return raw

    def _get_team_fixtures(
        self, team_id: int, *, days_back: int = 365, days_forward: int = 120,
    ) -> list[dict[str, Any]]:
        """Takımın [bugün−days_back, bugün+days_forward] penceresindeki
        fixture'ları (data listesi). Sportmonks: `fixtures/between/{from}/{to}/
        {teamId}`. Sayfalama varsa tüm sayfalar toplanır (pagination.has_more)."""
        if not self._key:
            raise RuntimeError(
                "SPORTMONKS_API_KEY boş. .env'e anahtar girin ya da testte "
                "parse_schedule saf fonksiyonunu doğrudan kullanın."
            )
        today = datetime.now(tz=UTC).date()
        start = today - timedelta(days=days_back)
        end = today + timedelta(days=days_forward)
        url = f"{self._base_url}/fixtures/between/{start}/{end}/{team_id}"
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

    def _get_standings(self, season_id: int) -> list[dict[str, Any]]:
        """Sezon puan durumu ham listesi (standings/seasons/{id})."""
        if not self._key:
            raise RuntimeError(
                "SPORTMONKS_API_KEY boş. .env'e anahtar girin ya da testte "
                "parse_standings saf fonksiyonunu doğrudan kullanın."
            )
        url = f"{self._base_url}/standings/seasons/{season_id}"
        params = {"api_token": self._key, "include": "participant;details;form;rule.type"}
        s = get_settings()
        log.info("sportmonks GET standings/seasons/%d", season_id)
        with httpx.Client(timeout=s.http_timeout_seconds) as client:
            r = client.get(url, params=params)
            r.raise_for_status()
            return r.json().get("data", []) or []

    def get_standings(self, season_id: int) -> list[StandingRow]:
        return self.parse_standings(self._get_standings(season_id))

    def get_squad_season(self, team_id: int, season: int) -> list[SquadMember]:
        """Takımın sezon kadrosu + sezon-toplam istatistik + foto (tek çağrı).

        DataSource sözleşmesi sezon YILI alır → season_id'ye çözülür. Çözülemezse
        boş liste."""
        season_id = self._resolve_season_id_for_team(team_id, season)
        if season_id is None:
            return []
        body = self._get_json(
            f"squads/seasons/{season_id}/teams/{team_id}",
            {"include": "player;details", "per_page": 100},
        )
        return self.parse_squad_season(body.get("data", []))

    def _resolve_season_id_for_team(self, team_id: int, season_year: int) -> int | None:
        """Takımın bir sezon-yılına ait season_id'si. team→seasons üzerinden.

        Lig bilinmeden takımın sezonlarını çeker (bir takım birden çok ligde
        olabilir; yıl eşleşmesi yeterli)."""
        key = (-team_id, season_year)  # league cache'inden ayrı namespace
        if key in self._season_id_cache:
            return self._season_id_cache[key]
        body = self._get_json(f"teams/{team_id}", {"include": "seasons"})
        seasons = (body.get("data") or {}).get("seasons") or []
        found: int | None = None
        for s in seasons:
            if _season_year_from_name(s.get("name")) == season_year:
                found = _as_int(s.get("id"))
                break
        if found is None and seasons:
            # yıl eşleşmedi → en güncel sezonu kullan (son eleman ya da en büyük id)
            found = _as_int(max(seasons, key=lambda s: _as_int(s.get("id")) or 0).get("id"))
        self._season_id_cache[key] = found
        return found

    # ── DataSource ABC (sync sözleşmesi) ──────────────────────────────────────
    def get_leagues(self) -> list[League]:
        """Abone olunan ligler (current sezon yılıyla)."""
        body = self._get_json("leagues", {"include": "currentSeason", "per_page": 100})
        return self.parse_leagues(body.get("data", []))

    def get_teams(self, league_id: int, season: int) -> list[Team]:
        """Lig+sezon (yıl) takımları. season_id'ye çözüp /teams/seasons çeker.

        Çözülemezse (abonelikte yoksa) boş liste — sync sessizce o ligi atlar."""
        season_id = self._resolve_season_id(league_id, season)
        if season_id is None:
            return []
        body = self._get_json(f"teams/seasons/{season_id}", {"per_page": 100})
        return self.parse_season_teams(body.get("data", []))

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

    def get_team_schedule(self, team_id: int, last_n: int = 10) -> dict[str, Any]:
        """Takım programı: bitenler + yaklaşanlar + takım adı haritası (tek pencere).

        UI için tek çağrı: aynı fixtures/between yanıtından hem maçlar hem
        participants adları çıkar (ekstra HTTP yok). Dönen yapı:
        {"finished": [Match...yeni→eski, ≤last_n], "upcoming": [Match...yakın→uzak],
         "team_names": {team_external_id: ad}}"""
        raw_list = self._get_team_fixtures(team_id)
        matches = self.parse_schedule(raw_list)
        names: dict[int, str] = {}
        for f in raw_list:
            if not isinstance(f, dict):
                continue
            for p in f.get("participants") or []:
                pid = _as_int(p.get("id"))
                if pid is not None and p.get("name"):
                    names[pid] = str(p["name"])
        finished = [m for m in matches if m.status in football.FINISHED_STATUSES]
        finished.sort(key=lambda m: m.kickoff, reverse=True)
        upcoming = [m for m in matches if m.status not in football.FINISHED_STATUSES]
        upcoming.sort(key=lambda m: m.kickoff)
        return {
            "finished": finished[: max(0, last_n)],
            "upcoming": upcoming,
            "team_names": names,
        }

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
    def parse_standings(data: list[dict[str, Any]]) -> list[StandingRow]:
        """Puan durumu (standings/seasons/{id}) → StandingRow listesi (pozisyona göre).

        details[] type_id'li metrikler; form[] sort_order ile sıralanır (eski→yeni).
        Bozuk satır atlanır."""
        rows: list[StandingRow] = []
        for st in data or []:
            if not isinstance(st, dict):
                continue
            pid = _as_int(st.get("participant_id"))
            pos = _as_int(st.get("position"))
            if pid is None or pos is None:
                continue
            part = st.get("participant") or {}
            vals: dict[str, Any] = {}
            for d in st.get("details", []):
                field_name = _STANDING_DETAIL_BY_TYPE.get(_as_int(d.get("type_id")) or -1)
                if field_name is None:
                    continue
                raw_v = d.get("value")
                vals[field_name] = (
                    _as_float(raw_v) if field_name == "xpoints" else _as_int(raw_v)
                )
            # Form: sort_order'a göre (eski→yeni), sadece harf
            form_sorted = sorted(
                (f for f in st.get("form", []) if isinstance(f, dict)),
                key=lambda f: _as_int(f.get("sort_order")) or 0,
            )
            form = [str(f.get("form")) for f in form_sorted if f.get("form")]
            qual = ((st.get("rule") or {}).get("type") or {}).get("name")
            rows.append(StandingRow(
                position=pos,
                team_external_id=pid,
                team_name=str(part.get("name") or "unknown"),
                played=vals.get("played") or 0,
                won=vals.get("won") or 0,
                draw=vals.get("draw") or 0,
                lost=vals.get("lost") or 0,
                goals_for=vals.get("goals_for") or 0,
                goals_against=vals.get("goals_against") or 0,
                goal_diff=vals.get("goal_diff") or 0,
                points=vals.get("points") or 0,
                xpoints=vals.get("xpoints"),
                form=form,
                qualification=qual,
            ))
        rows.sort(key=lambda r: r.position)
        return rows

    @staticmethod
    def parse_teams_from_standings(data: list[dict[str, Any]]) -> list[Team]:
        """Puan durumundaki participant'lardan Team listesi (get_teams için).

        Standings tüm ligi kapsar → ligin tam takım kimliği buradan çıkar."""
        by_id: dict[int, Team] = {}
        for st in data or []:
            if not isinstance(st, dict):
                continue
            p = st.get("participant") or {}
            tid = _as_int(p.get("id"))
            if tid is None or tid in by_id:
                continue
            by_id[tid] = Team(
                sport=football.SPORT_NAME,
                external_id=tid,
                name=str(p.get("name") or "unknown"),
                country=None,
                founded=_as_int(p.get("founded")),
            )
        return list(by_id.values())

    @staticmethod
    def _detail_value(value: Any) -> float | int | None:
        """Sezon-detay value'su → sayı. {'total':N}/{'average':x}/{'expected':x}."""
        if isinstance(value, dict):
            for k in ("total", "average", "expected", "value"):
                if k in value:
                    return _as_float(value[k])
            return None
        return _as_float(value)

    @staticmethod
    def parse_squad_season(data: list[dict[str, Any]]) -> list[SquadMember]:
        """Sezon-squad (squads/seasons/{sid}/teams/{tid}, include=player;details) →
        SquadMember listesi. details[] sezon-TOPLAM stat (tek çağrı, backfill'siz).

        İnt sayaçlar int'e yuvarlanır; pass_accuracy float kalır. Eksik metrik 0."""
        out: list[SquadMember] = []
        for e in data or []:
            if not isinstance(e, dict):
                continue
            p = e.get("player")
            if not isinstance(p, dict):
                continue
            pid = _as_int(p.get("id")) or _as_int(e.get("player_id"))
            if pid is None:
                continue
            season: dict[str, Any] = {}
            captain = False
            for d in e.get("details", []):
                tid = _as_int(d.get("type_id")) or -1
                if tid == 40:  # CAPTAIN
                    captain = True
                    continue
                key = _SQUAD_SEASON_DETAIL_BY_TYPE.get(tid)
                if key is None:
                    continue
                num = Sportmonks._detail_value(d.get("value"))
                if num is None:
                    continue
                season[key] = num if key == "pass_accuracy" else int(round(num))
            dob = None
            raw_dob = p.get("date_of_birth")
            if raw_dob:
                try:
                    dob = str(datetime.strptime(str(raw_dob), "%Y-%m-%d").date())
                except ValueError:
                    dob = None
            nat_obj = p.get("nationality")
            nat = nat_obj.get("name") if isinstance(nat_obj, dict) else None
            pos = _POSITION_MAP.get(
                _as_int(p.get("position_id")) or _as_int(e.get("position_id")) or -1
            )
            out.append(SquadMember(
                player_external_id=pid,
                name=str(p.get("display_name") or p.get("name") or "unknown"),
                position=pos,
                jersey=_as_int(e.get("jersey_number")),
                photo_url=p.get("image_path") or None,
                birth_date=dob,
                nationality=nat,
                captain=captain,
                season=season,
            ))
        return out

    @staticmethod
    def parse_leagues(data: list[dict[str, Any]]) -> list[League]:
        """/leagues (include=currentSeason) → League listesi (sezon = current yıl).

        League.season int yıl ister; currentseason.name "2026/2027" → 2026."""
        out: list[League] = []
        for lg in data or []:
            if not isinstance(lg, dict):
                continue
            lid = _as_int(lg.get("id"))
            if lid is None:
                continue
            cs = lg.get("currentseason") or lg.get("current_season") or {}
            year = _season_year_from_name(cs.get("name")) or 0
            out.append(League(
                sport=football.SPORT_NAME,
                external_id=lid,
                name=str(lg.get("name") or "unknown"),
                season=year,
                country=None,
            ))
        return out

    @staticmethod
    def parse_season_teams(data: list[dict[str, Any]]) -> list[Team]:
        """/teams/seasons/{id} → Team listesi (düz takım objeleri)."""
        by_id: dict[int, Team] = {}
        for t in data or []:
            if not isinstance(t, dict):
                continue
            tid = _as_int(t.get("id"))
            if tid is None or tid in by_id:
                continue
            by_id[tid] = Team(
                sport=football.SPORT_NAME,
                external_id=tid,
                name=str(t.get("name") or "unknown"),
                country=None,
                founded=_as_int(t.get("founded")),
            )
        return list(by_id.values())

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
