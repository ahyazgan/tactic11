"""Canlı maç servisi — maç SÜRERKEN skor, olaylar, sahiplik payı ve devre saatleri.

Video hattı "nerede"yi (oyuncu konumları) verir; bu katman "ne oldu"yu verir:
gol, kart, oyuncu değişikliği, toplam topa sahip olma ve devrelerin gerçek
başlama anı (duvar saati). İki sağlayıcı aynı `ServiceSnapshot`'a çevrilir:

- **Sportmonks** (`/fixtures/{id}?include=...`) — bugünkü abonelik Danimarka ve
  İskoçya liglerini veriyor; `trends` (dakika başı istatistik) bu planda YOK.
- **API-Football** (`/fixtures?id=`, `/fixtures/events`, `/fixtures/statistics`).

## Ne VERMEZ (ölçüldü, 2026-11-01)

İki ucuz servis de "top şu saniyede kimde" bilgisini vermez; olaylar dakika
çözünürlüğündedir (saniye yok) ve şut/pas akışı bu planlarda yoktur. Bu yüzden
kare düzeyindeki savunan takım servisten gelmez; servis yalnız birkaç dakikalık
pencerede **sahiplik payını** verir (`PossessionHistory.window_share`).

## Pencere payı nasıl çıkar

Servis maç başından beri birikmiş yüzdeyi verir: p(t). Ev sahibinin topla geçen
süresi H(t) = p(t)·t olduğundan [t1, t2] penceresindeki pay
(p2·t2 − p1·t1) / (t2 − t1). Yüzdeler tam sayıya yuvarlı geldiği için kısa
pencerede gürültü büyür (60. dakikada ±0,5 puan → 5 dk'lık pencerede ±6 puan);
`MIN_WINDOW_MIN` altı pencere için pay verilmez.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

SPORTMONKS_LIVE_INCLUDE = "participants;scores;events.type;statistics.type;periods;state"
MIN_WINDOW_MIN = 5.0
DEFAULT_POLL_S = 20.0

_SPORTMONKS_KINDS = {
    "GOAL": "goal", "OWNGOAL": "own_goal", "PENALTY": "penalty_goal",
    "YELLOWCARD": "yellow", "REDCARD": "red", "YELLOWREDCARD": "red",
    "SUBSTITUTION": "substitution", "VAR": "var", "VAR_CARD": "var",
    "MISSED_PENALTY": "missed_penalty",
}
_SPORTMONKS_STATUS = {
    "NS": "not_started", "INPLAY_1ST_HALF": "live", "INPLAY_2ND_HALF": "live",
    "INPLAY_ET": "live", "INPLAY_PENALTIES": "live", "HT": "half_time", "BREAK": "half_time",
    "FT": "finished", "AET": "finished", "FT_PEN": "finished",
}
_API_FOOTBALL_STATUS = {
    "NS": "not_started", "TBD": "not_started", "1H": "live", "2H": "live", "ET": "live",
    "P": "live", "LIVE": "live", "HT": "half_time", "BT": "half_time",
    "FT": "finished", "AET": "finished", "PEN": "finished",
}
GOAL_KINDS = frozenset({"goal", "own_goal", "penalty_goal"})


@dataclass(frozen=True)
class ServiceEvent:
    """Servisin bildirdiği bir olay. `team`: 0 = ev sahibi, 1 = deplasman.

    Kendi kalesine golde `team` golü ATAN (yararlanan) takım değil, oyuncunun
    takımıdır; skoru `ServiceSnapshot.score` verir, olaydan hesaplanmaz."""

    kind: str
    minute: int
    extra_minute: int = 0
    team: int | None = None
    player: str | None = None
    related_player: str | None = None

    @property
    def clock_minute(self) -> float:
        """Sıralama için dakika (uzatma dakikası eklenir)."""
        return self.minute + self.extra_minute


@dataclass(frozen=True)
class ServiceSnapshot:
    """Bir sorgu anındaki maç durumu (sağlayıcıdan bağımsız)."""

    provider: str
    fixture_id: int
    status: str                      # not_started | live | half_time | finished | other
    minute: int | None
    home_name: str
    away_name: str
    score: tuple[int, int]
    events: tuple[ServiceEvent, ...]
    possession: tuple[float, float] | None   # maç başından beri birikmiş yüzde
    period_starts: tuple[datetime, ...]      # devrelerin gerçek başlama anı (UTC)
    fetched_at: datetime

    def goals(self) -> list[ServiceEvent]:
        return [e for e in self.events if e.kind in GOAL_KINDS]


def _utc(ts: Any) -> datetime | None:
    if ts in (None, "", 0):
        return None
    return datetime.fromtimestamp(int(ts), tz=UTC)


def _int(v: Any) -> int | None:
    try:
        return None if v is None else int(v)
    except (TypeError, ValueError):
        return None


def parse_sportmonks(body: dict[str, Any], *, fetched_at: datetime | None = None) -> ServiceSnapshot:
    """Sportmonks `/fixtures/{id}` gövdesi (`SPORTMONKS_LIVE_INCLUDE` ile) → anlık görüntü."""
    f = body.get("data") or body
    side: dict[int, int] = {}
    names = ["", ""]
    for p in f.get("participants") or []:
        loc = (p.get("meta") or {}).get("location")
        if loc in ("home", "away"):
            idx = 0 if loc == "home" else 1
            side[int(p["id"])] = idx
            names[idx] = p.get("name") or ""
    score = [0, 0]
    for s in f.get("scores") or []:
        if s.get("description") == "CURRENT":
            sc = s.get("score") or {}
            idx = 0 if sc.get("participant") == "home" else 1
            score[idx] = int(sc.get("goals") or 0)
    events = []
    for e in f.get("events") or []:
        dev = ((e.get("type") or {}).get("developer_name") or "").upper()
        events.append(ServiceEvent(
            kind=_SPORTMONKS_KINDS.get(dev, "other"), minute=int(e.get("minute") or 0),
            extra_minute=int(e.get("extra_minute") or 0), team=side.get(_int(e.get("participant_id")) or -1),
            player=e.get("player_name"), related_player=e.get("related_player_name")))
    possession = None
    pos: dict[int, float] = {}
    for s in f.get("statistics") or []:
        if ((s.get("type") or {}).get("developer_name") or "").upper() == "BALL_POSSESSION":
            team_idx = side.get(_int(s.get("participant_id")) or -1)
            value = (s.get("data") or {}).get("value")
            if team_idx is not None and value is not None:
                pos[team_idx] = float(value)
    if len(pos) == 2:
        possession = (pos[0], pos[1])
    periods = sorted((p for p in f.get("periods") or [] if p.get("started")), key=lambda p: p.get("sort_order") or 0)
    starts = tuple(t for t in (_utc(p.get("started")) for p in periods) if t is not None)
    ticking = [p for p in periods if p.get("ticking")]
    minute: int | None = _int(ticking[-1].get("minutes")) if ticking else None
    dev_state = ((f.get("state") or {}).get("developer_name") or "").upper()
    status = _SPORTMONKS_STATUS.get(dev_state, "other")
    if minute is None and status == "finished" and periods:
        minute = _int(periods[-1].get("minutes"))
    return ServiceSnapshot(
        provider="sportmonks", fixture_id=int(f["id"]), status=status, minute=minute,
        home_name=names[0], away_name=names[1], score=(score[0], score[1]),
        events=tuple(sorted(events, key=lambda e: e.clock_minute)), possession=possession,
        period_starts=starts, fetched_at=fetched_at or datetime.now(UTC))


def parse_api_football(fixture: dict[str, Any], events: list[dict[str, Any]] | None = None,
                       statistics: list[dict[str, Any]] | None = None, *,
                       fetched_at: datetime | None = None) -> ServiceSnapshot:
    """API-Football `/fixtures?id=` öğesi (+ isteğe bağlı events/statistics yanıtı) → anlık görüntü.

    `/fixtures?id=` yanıtı olayları ve istatistiği zaten içerir; ayrı uç verilirse o kullanılır."""
    fx = fixture.get("fixture") or {}
    teams = fixture.get("teams") or {}
    home_id = _int((teams.get("home") or {}).get("id"))
    away_id = _int((teams.get("away") or {}).get("id"))
    side = {home_id: 0, away_id: 1}
    status_raw = ((fx.get("status") or {}).get("short") or "").upper()
    goals = fixture.get("goals") or {}
    evs = []
    for e in (events if events is not None else fixture.get("events")) or []:
        typ, detail = (e.get("type") or "").lower(), (e.get("detail") or "").lower()
        if typ == "goal":
            kind = ("own_goal" if "own" in detail else "penalty_goal" if "penalty" in detail and "missed" not in detail
                    else "missed_penalty" if "missed" in detail else "goal")
        elif typ == "card":
            kind = "red" if "red" in detail else "yellow"
        elif typ == "subst":
            kind = "substitution"
        elif typ == "var":
            kind = "var"
        else:
            kind = "other"
        t = e.get("time") or {}
        evs.append(ServiceEvent(
            kind=kind, minute=int(t.get("elapsed") or 0), extra_minute=int(t.get("extra") or 0),
            team=side.get(_int((e.get("team") or {}).get("id"))),
            player=(e.get("player") or {}).get("name"), related_player=(e.get("assist") or {}).get("name")))
    pos: dict[int, float] = {}
    for block in (statistics if statistics is not None else fixture.get("statistics")) or []:
        idx = side.get(_int((block.get("team") or {}).get("id")))
        for st in block.get("statistics") or []:
            if (st.get("type") or "").lower() == "ball possession" and idx is not None:
                raw = str(st.get("value") or "").strip().rstrip("%")
                if raw:
                    pos[idx] = float(raw)
    periods = fx.get("periods") or {}
    starts = tuple(t for t in (_utc(periods.get("first")), _utc(periods.get("second"))) if t is not None)
    return ServiceSnapshot(
        provider="api_football", fixture_id=int(fx.get("id") or 0),
        status=_API_FOOTBALL_STATUS.get(status_raw, "other"), minute=_int((fx.get("status") or {}).get("elapsed")),
        home_name=(teams.get("home") or {}).get("name") or "", away_name=(teams.get("away") or {}).get("name") or "",
        score=(int(goals.get("home") or 0), int(goals.get("away") or 0)),
        events=tuple(sorted(evs, key=lambda e: e.clock_minute)),
        possession=(pos[0], pos[1]) if len(pos) == 2 else None,
        period_starts=starts, fetched_at=fetched_at or datetime.now(UTC))


@dataclass
class PossessionHistory:
    """Birikmiş sahiplik örneklerinden pencere payı (bkz. modül notu)."""

    samples: list[tuple[float, float]] = field(default_factory=list)   # (dakika, ev sahibi %)

    def add(self, minute: float | None, home_pct: float | None) -> None:
        if minute is None or home_pct is None or minute <= 0:
            return
        if self.samples and minute <= self.samples[-1][0]:
            if minute == self.samples[-1][0]:
                self.samples[-1] = (minute, home_pct)
            return
        self.samples.append((float(minute), float(home_pct)))

    def window_share(self, start: float, end: float, min_window: float = MIN_WINDOW_MIN) -> float | None:
        """[start, end] dakikalarında ev sahibinin sahiplik payı (%); örnek yoksa ya da
        pencere `min_window`'dan kısaysa None. Uçlar en yakın örneğe oturtulur."""
        if len(self.samples) < 2 or end - start < min_window:
            return None
        before = [s for s in self.samples if s[0] <= start]
        after = [s for s in self.samples if s[0] <= end]
        if not after:
            return None
        t2, p2 = after[-1]
        t1, p1 = before[-1] if before else (0.0, 50.0)
        if t2 - t1 < min_window:
            return None
        share = (p2 * t2 - p1 * t1) / (t2 - t1)
        return round(min(100.0, max(0.0, share)), 1)


def new_events(previous: ServiceSnapshot | None, current: ServiceSnapshot) -> list[ServiceEvent]:
    """Önceki sorguda olmayan olaylar (uyarı akışı için)."""
    if previous is None:
        return list(current.events)
    seen = set(previous.events)
    return [e for e in current.events if e not in seen]


class SportmonksLive:
    """Sportmonks canlı sorgusu (önbelleksiz; her çağrı bir istek)."""

    provider = "sportmonks"

    def __init__(self, client: Any | None = None) -> None:
        if client is None:
            from app.data.sources.sportmonks import Sportmonks  # noqa: PLC0415
            client = Sportmonks()
        self._client = client

    def fetch(self, fixture_id: int) -> ServiceSnapshot:
        return parse_sportmonks(self._client._get_json(f"fixtures/{fixture_id}", {"include": SPORTMONKS_LIVE_INCLUDE}))


class APIFootballLive:
    """API-Football canlı sorgusu. Önbellek kullanılmaz (canlı veri bayatlamasın);
    her istek günlük kotadan düşülür (`consume_quota`)."""

    provider = "api_football"

    def __init__(self, get: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None) -> None:
        self._get = get or _api_football_get

    def fetch(self, fixture_id: int) -> ServiceSnapshot:
        body = self._get("fixtures", {"id": fixture_id})
        items = body.get("response") or []
        if not items:
            raise ValueError(f"api_football: fixture {fixture_id} bulunamadı")
        return parse_api_football(items[0])


def _api_football_get(path: str, params: dict[str, Any]) -> dict[str, Any]:
    import httpx  # noqa: PLC0415

    from app.core.config import get_settings  # noqa: PLC0415
    from app.core.usage.tracker import consume_quota  # noqa: PLC0415
    from app.db.session import SessionLocal  # noqa: PLC0415

    s = get_settings()
    if not s.api_football_key:
        raise RuntimeError("API_FOOTBALL_KEY boş — .env içine anahtar girin")
    with SessionLocal() as session:
        consume_quota(session, source="api_football", endpoint=f"{path}:live")
        session.commit()
    with httpx.Client(timeout=s.http_timeout_seconds) as client:
        r = client.get(f"{s.api_football_base_url}/{path}", params=params,
                       headers={"x-apisports-key": s.api_football_key})
        r.raise_for_status()
        return r.json()


def make_live_service(provider: str) -> SportmonksLive | APIFootballLive:
    if provider == "sportmonks":
        return SportmonksLive()
    if provider == "api_football":
        return APIFootballLive()
    raise ValueError(f"bilinmeyen canlı servis: {provider}")


@dataclass
class LiveServicePoller:
    """Servisi aralıkla sorgular; sahiplik geçmişini ve yeni olayları tutar.

    Sorgu hatası maçı durdurmaz: son başarılı görüntü kalır, hata `last_error`'da."""

    service: Any
    fixture_id: int
    interval_s: float = DEFAULT_POLL_S
    clock: Callable[[], float] = time.monotonic
    snapshot: ServiceSnapshot | None = None
    history: PossessionHistory = field(default_factory=PossessionHistory)
    last_error: str | None = None
    _last_poll: float | None = None

    def due(self) -> bool:
        return self._last_poll is None or self.clock() - self._last_poll >= self.interval_s

    def poll(self) -> list[ServiceEvent]:
        """Bir sorgu; bu sorguda ilk kez görülen olayları döndürür."""
        self._last_poll = self.clock()
        try:
            current = self.service.fetch(self.fixture_id)
        except Exception as exc:  # noqa: BLE001 — canlıda servis hatası panoyu düşürmemeli
            self.last_error = f"{type(exc).__name__}: {exc}"
            return []
        self.last_error = None
        fresh = new_events(self.snapshot, current)
        self.snapshot = current
        if current.possession is not None:
            self.history.add(current.minute, current.possession[0])
        return fresh
