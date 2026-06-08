"""StatsBomb Open Data adapter — GitHub raw JSON ingest.

StatsBomb GitHub raw URL pattern:
    https://raw.githubusercontent.com/statsbomb/open-data/master/data/
        competitions.json
        matches/{competition_id}/{season_id}.json
        events/{match_id}.json
        lineups/{match_id}.json

Rate limit: GitHub raw 60 req/saat unauth → cache şart. Bu adapter cache layer'ı
zaten kullanır (DataSource base + cache_entries).

Lisans: StatsBomb Open data **non-commercial license** altında. Production
deploy için ticari kullanım hakkı doğrulanmalı. Bu adapter eğitim/test için.

Shot event parse: event.type.id == 16 ("Shot"). Output Shot domain modeli
(app/domain/shot.py). is_goal: event.shot.outcome.name == "Goal".

NOT: Bu modül production'da gerçek HTTP atar; testler `_fetch_json`'ı
monkeypatch'leyerek sample fixture'larla parser'ı doğrular.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.core.logging import get_logger
from app.domain import Shot

log = get_logger(__name__)

STATSBOMB_RAW_BASE = (
    "https://raw.githubusercontent.com/statsbomb/open-data/master/data"
)
HTTP_TIMEOUT = 30.0

# StatsBomb saha koordinatları: 120 (uzunluk) × 80 (genişlik). Domain modelimiz
# 100x100 normalize — burada dönüştürürüz.
STATSBOMB_PITCH_LENGTH = 120.0
STATSBOMB_PITCH_WIDTH = 80.0

# StatsBomb play_pattern.id → bizim Shot.pattern enum mapping
# Kaynak: StatsBomb event docs (play_pattern table)
_PLAY_PATTERN_MAP: dict[int, str] = {
    1: "open_play",       # Regular Play
    2: "fast_break",      # From Counter
    3: "fast_break",      # From Keeper
    4: "corner_kick",     # From Corner
    5: "free_kick",       # From Free Kick
    6: "set_piece",       # From Throw In
    7: "open_play",       # Other
    8: "open_play",       # From Kick Off
    9: "open_play",       # From Goal Kick
}

# StatsBomb body_part.id → bizim BodyPart
_BODY_PART_MAP: dict[int, str] = {
    37: "head",           # Head
    38: "left_foot",      # Left Foot
    40: "right_foot",     # Right Foot
    70: "other",          # Other
}

# StatsBomb event.type.id == 16 → Shot
SHOT_EVENT_TYPE_ID = 16

# Lineup/substitution event tipleri (Faz B — maç-içi kadro farkındalığı)
STARTING_XI_EVENT_TYPE_ID = 35   # tactics.lineup ilk 11'i taşır
SUBSTITUTION_EVENT_TYPE_ID = 19  # player = çıkan, substitution.replacement = giren


class StatsBombOpen:
    """StatsBomb Open Data adapter — GitHub raw ingest.

    `name = "statsbomb_open"`; DataSource ABC ile uyumlu değil çünkü domain
    şekli farklı (per-match event listesi). Manager2'nin DataSource base'i
    league/team/match için — bu adapter shot event'lerine odaklı.
    """

    name = "statsbomb_open"

    def __init__(self, base_url: str | None = None, timeout: float = HTTP_TIMEOUT):
        self._base_url = (base_url or STATSBOMB_RAW_BASE).rstrip("/")
        self._timeout = timeout

    def _fetch_json(self, path: str) -> Any:
        """GitHub raw'dan JSON çek. HTTP 4xx → RuntimeError; 5xx + network → retry yok."""
        url = f"{self._base_url}/{path}"
        log.info("statsbomb fetch: %s", path)
        with httpx.Client(timeout=self._timeout) as client:
            r = client.get(url)
            if r.status_code != 200:
                raise RuntimeError(
                    f"StatsBomb fetch fail {path}: HTTP {r.status_code} — "
                    f"{r.text[:200]}"
                )
            return r.json()

    def get_competitions(self) -> list[dict[str, Any]]:
        return self._fetch_json("competitions.json")

    def get_matches(self, *, competition_id: int, season_id: int) -> list[dict[str, Any]]:
        return self._fetch_json(f"matches/{competition_id}/{season_id}.json")

    def get_events(self, match_id: int) -> list[dict[str, Any]]:
        return self._fetch_json(f"events/{match_id}.json")

    def get_shots_for_match(self, match_id: int) -> list[Shot]:
        """Bir maçın tüm shot event'lerini Shot listesine çevir."""
        events = self.get_events(match_id)
        shots = []
        for ev in events:
            if not _is_shot_event(ev):
                continue
            shot = _event_to_shot(ev, match_id=match_id)
            if shot is not None:
                shots.append(shot)
        return shots


def _is_shot_event(event: dict[str, Any]) -> bool:
    type_block = event.get("type") or {}
    return int(type_block.get("id", 0)) == SHOT_EVENT_TYPE_ID


def _event_to_shot(event: dict[str, Any], *, match_id: int) -> Shot | None:
    """StatsBomb shot event → Shot domain. None döner if parse fail."""
    try:
        player = event.get("player") or {}
        location = event.get("location") or []
        if len(location) < 2:
            return None
        # StatsBomb 120x80 → 100x100 normalize
        x_120 = float(location[0])
        y_80 = float(location[1])
        x_100 = (x_120 / STATSBOMB_PITCH_LENGTH) * 100.0
        y_100 = (y_80 / STATSBOMB_PITCH_WIDTH) * 100.0
        # Clamp 0-100 (corner cases)
        x_100 = max(0.0, min(100.0, x_100))
        y_100 = max(0.0, min(100.0, y_100))

        play_pattern = event.get("play_pattern") or {}
        pattern_id = int(play_pattern.get("id", 1))
        pattern = _PLAY_PATTERN_MAP.get(pattern_id, "open_play")

        shot_block = event.get("shot") or {}
        body_part_block = shot_block.get("body_part") or {}
        body_part_id = int(body_part_block.get("id", 40))  # default right_foot
        body_part = _BODY_PART_MAP.get(body_part_id, "right_foot")

        # Penalty: shot.type.name == "Penalty"
        shot_type_block = shot_block.get("type") or {}
        if str(shot_type_block.get("name", "")).lower() == "penalty":
            pattern = "penalty"

        outcome_block = shot_block.get("outcome") or {}
        is_goal = str(outcome_block.get("name", "")).lower() == "goal"

        minute = float(event.get("minute", 0))

        team_block = event.get("team") or {}
        team_id = int(team_block.get("id", 0)) or None
        return Shot(
            sport="football",
            match_external_id=int(match_id),
            player_external_id=int(player.get("id", 0)),
            minute=minute,
            x=round(x_100, 2),
            y=round(y_100, 2),
            body_part=body_part,  # type: ignore[arg-type]
            pattern=pattern,  # type: ignore[arg-type]
            is_goal=is_goal,
            team_external_id=team_id,
        )
    except (KeyError, ValueError, TypeError) as e:
        log.warning("statsbomb shot parse fail: %s", e)
        return None


def shots_from_events_json(events_json: list[dict[str, Any]], *, match_id: int) -> list[Shot]:
    """Test helper — events JSON listesini doğrudan parse et (HTTP yok)."""
    return [
        s for s in (_event_to_shot(ev, match_id=match_id) for ev in events_json if _is_shot_event(ev))
        if s is not None
    ]


def appearances_from_events_json(
    events_json: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """StatsBomb events JSON → oyuncu görünümleri (Faz B kadro/sub farkındalığı).

    Saf parse, HTTP yok. İki event tipinden türetir:
    - Starting XI (tip 35): `tactics.lineup` içindeki her oyuncu → ilk 11,
      `start_minute = 0.0`.
    - Substitution (tip 19): event'in `player` = SAHADAN ÇIKAN (end = event
      dakikası), `substitution.replacement` = SAHAYA GİREN (start = event dakikası).

    Dönüş: `{player_external_id, team_external_id, start_minute, end_minute}`
    dict listesi. `end_minute=None` → çıkmadı (maç sonuna kadar). Kadrosuz/bozuk
    event'ler atlanır (sahadaki gerçeği bozmadan).
    """
    appearances: dict[int, dict[str, Any]] = {}

    for ev in events_json:
        type_id = int((ev.get("type") or {}).get("id", 0))
        team_id = int((ev.get("team") or {}).get("id", 0)) or None

        if type_id == STARTING_XI_EVENT_TYPE_ID:
            lineup = ((ev.get("tactics") or {}).get("lineup")) or []
            for slot in lineup:
                pid = (slot.get("player") or {}).get("id")
                if pid is None or team_id is None:
                    continue
                appearances[int(pid)] = {
                    "player_external_id": int(pid),
                    "team_external_id": team_id,
                    "start_minute": 0.0,
                    "end_minute": None,
                }

        elif type_id == SUBSTITUTION_EVENT_TYPE_ID:
            minute = float(ev.get("minute", 0))
            off_player = (ev.get("player") or {}).get("id")
            sub_block = ev.get("substitution") or {}
            on_player = (sub_block.get("replacement") or {}).get("id")
            # Çıkan oyuncunun penceresini kapat
            if off_player is not None and int(off_player) in appearances:
                appearances[int(off_player)]["end_minute"] = minute
            # Giren oyuncu için yeni pencere aç
            if on_player is not None and team_id is not None:
                appearances[int(on_player)] = {
                    "player_external_id": int(on_player),
                    "team_external_id": team_id,
                    "start_minute": minute,
                    "end_minute": None,
                }

    return list(appearances.values())
