"""Süper Lig 2024-25 sentetik fixture üreteci.

Deterministik (sabit seed) — aynı seed = aynı çıktı. Skorlar Poisson örneklenir;
takım gücü (`strength` 0..1) + ev avantajı `λ`'ı belirler. Veri uydurma ama
gerçek takım isim/ID'leriyle plausible — testlere ve demoya yeterli.

Kullanım:
    python scripts/generate_fixtures.py

Çıktılar (tests/fixtures/):
- leagues.json (Süper Lig + Premier League)
- teams_203.json (10 takım)
- matches_<id>.json (her takım için)
"""

from __future__ import annotations

import json
import math
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Sezon başlangıcına anlamlı bir seed (deterministic, aynı seed = aynı veri).
SEED = 20240809

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = _PROJECT_ROOT / "tests" / "fixtures"

# (api-football id, ad, kuruluş, strength 0..1 — sezon performans göstergesi)
# Strength gerçek 2024-25 sonuçlarına paralel bir sıralama; tam skor değil,
# Poisson λ kalibrasyonu için kullanılır.
TEAMS: list[tuple[int, str, int, float]] = [
    (611, "Galatasaray", 1905, 1.00),
    (607, "Fenerbahce", 1907, 0.95),
    (1009, "Samsunspor", 1965, 0.75),
    (999, "Basaksehir", 1990, 0.70),
    (998, "Trabzonspor", 1967, 0.68),
    (614, "Besiktas", 1903, 0.65),
    (1004, "Antalyaspor", 1966, 0.50),
    (627, "Konyaspor", 1922, 0.45),
    (1003, "Kayserispor", 1966, 0.40),
    (1014, "Alanyaspor", 1948, 0.35),
]

PAST_ROUNDS = 7  # tek devre + ekstra — tüm marquee karşılaşmalar finished
FUTURE_ROUNDS = 2  # 2 hafta NS (ufuk + tahmin uçları için yeterli)
FIRST_PAST_KICKOFF = datetime(2024, 8, 17, 18, 0, tzinfo=UTC)
FIRST_FUTURE_KICKOFF = datetime(2026, 6, 7, 18, 0, tzinfo=UTC)
FIXTURE_ID_BASE = 1234100

# Skor modeli — Poisson λ; sezon ortalaması ~1.3 gol/maç + güç farkı + ev avantajı
_LEAGUE_AVG_GOALS = 1.3
_STRENGTH_WEIGHT = 0.8
_HOME_ADVANTAGE = 0.3
_MAX_GOAL_CAP = 6  # tail uçlarına makul tavan; Poisson zaten ~0.1% üstü


def _round_robin(n: int) -> list[list[tuple[int, int]]]:
    """Berger algoritması — n çift sayıda takım için single round-robin."""
    if n % 2 != 0:
        raise ValueError("round-robin: çift sayıda takım gerek")
    teams = list(range(n))
    rounds: list[list[tuple[int, int]]] = []
    for r in range(n - 1):
        pairs: list[tuple[int, int]] = []
        for i in range(n // 2):
            home = teams[i]
            away = teams[n - 1 - i]
            # Ev/dep rotasyonu — turlar arası dengeli olsun
            if i == 0 and r % 2 == 1:
                home, away = away, home
            pairs.append((home, away))
        rounds.append(pairs)
        # Berger rotasyonu: takım 0 sabit, geri kalan kayar
        teams = [teams[0]] + [teams[-1]] + teams[1:-1]
    return rounds


def _poisson_sample(rng: random.Random, lam: float) -> int:
    """Knuth'un algoritması; küçük λ için yeterli."""
    if lam <= 0:
        return 0
    threshold = math.exp(-lam)
    k = 0
    p = 1.0
    while True:
        k += 1
        p *= rng.random()
        if p <= threshold:
            return k - 1


def _expected_goals(att_strength: float, def_strength: float, home_advantage: float) -> float:
    return max(0.2, _LEAGUE_AVG_GOALS + _STRENGTH_WEIGHT * (att_strength - def_strength) + home_advantage)


def _build_match(
    fixture_id: int,
    kickoff: datetime,
    season: int,
    round_no: int,
    home: tuple[int, str, int, float],
    away: tuple[int, str, int, float],
    *,
    status: str,
    home_score: int | None,
    away_score: int | None,
) -> dict:
    status_long = {"FT": "Match Finished", "NS": "Not Started"}.get(status, status)
    return {
        "fixture": {
            "id": fixture_id,
            "date": kickoff.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
            "status": {"short": status, "long": status_long},
        },
        "league": {"id": 203, "season": season, "round": f"Regular Season - {round_no}"},
        "teams": {
            "home": {"id": home[0], "name": home[1]},
            "away": {"id": away[0], "name": away[1]},
        },
        "goals": {"home": home_score, "away": away_score},
    }


def _write_json(path: Path, data: dict) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def main() -> None:
    rng = random.Random(SEED)
    n = len(TEAMS)
    # Berger team-0'ı sabit tuttuğu için 1. takıma karşı eşleşme HEP son
    # tura düşer (Gala–Fener bizim için kritik); tur sırasını çevirip
    # marquee karşılaşmayı geçmiş kısmına alıyoruz.
    rounds = list(reversed(_round_robin(n)))
    if len(rounds) < PAST_ROUNDS + FUTURE_ROUNDS:
        raise RuntimeError(
            f"round-robin yeterli tur üretmedi: {len(rounds)} < "
            f"{PAST_ROUNDS + FUTURE_ROUNDS}"
        )

    fixture_id = FIXTURE_ID_BASE
    matches_per_team: dict[int, list[dict]] = {tid: [] for (tid, *_) in TEAMS}

    # Past rounds (FT)
    for r_idx, pairs in enumerate(rounds[:PAST_ROUNDS]):
        kickoff = FIRST_PAST_KICKOFF + timedelta(days=7 * r_idx)
        for (h_i, a_i) in pairs:
            home = TEAMS[h_i]
            away = TEAMS[a_i]
            home_lam = _expected_goals(home[3], away[3], _HOME_ADVANTAGE)
            away_lam = _expected_goals(away[3], home[3], 0.0)
            home_score = min(_poisson_sample(rng, home_lam), _MAX_GOAL_CAP)
            away_score = min(_poisson_sample(rng, away_lam), _MAX_GOAL_CAP)
            match = _build_match(
                fixture_id, kickoff, 2024, r_idx + 1, home, away,
                status="FT", home_score=home_score, away_score=away_score,
            )
            matches_per_team[home[0]].append(match)
            matches_per_team[away[0]].append(match)
            fixture_id += 1

    # Future rounds (NS) — 2026 sezonu, scoreless
    for r_idx, pairs in enumerate(rounds[PAST_ROUNDS:PAST_ROUNDS + FUTURE_ROUNDS]):
        kickoff = FIRST_FUTURE_KICKOFF + timedelta(days=7 * r_idx)
        for (h_i, a_i) in pairs:
            home = TEAMS[h_i]
            away = TEAMS[a_i]
            match = _build_match(
                fixture_id, kickoff, 2026, r_idx + 1, home, away,
                status="NS", home_score=None, away_score=None,
            )
            matches_per_team[home[0]].append(match)
            matches_per_team[away[0]].append(match)
            fixture_id += 1

    # API-Football yeni → eski sıralar; biz de aynısını yapalım
    for tid in matches_per_team:
        matches_per_team[tid].sort(key=lambda m: m["fixture"]["date"], reverse=True)

    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)

    leagues_payload = {
        "get": "leagues",
        "parameters": [],
        "errors": [],
        "results": 2,
        "paging": {"current": 1, "total": 1},
        "response": [
            {
                "league": {"id": 203, "name": "Süper Lig", "type": "League"},
                "country": {"name": "Turkey", "code": "TR"},
                "seasons": [
                    {"year": 2024, "start": "2024-08-09", "end": "2025-05-25", "current": True}
                ],
            },
            {
                "league": {"id": 39, "name": "Premier League", "type": "League"},
                "country": {"name": "England", "code": "GB"},
                "seasons": [
                    {"year": 2024, "start": "2024-08-16", "end": "2025-05-25", "current": True}
                ],
            },
        ],
    }
    _write_json(FIXTURE_DIR / "leagues.json", leagues_payload)

    teams_payload = {
        "get": "teams",
        "parameters": {"league": "203", "season": "2024"},
        "errors": [],
        "results": len(TEAMS),
        "paging": {"current": 1, "total": 1},
        "response": [
            {
                "team": {
                    "id": tid,
                    "name": name,
                    "country": "Turkey",
                    "founded": founded,
                    "national": False,
                },
                "venue": {},
            }
            for (tid, name, founded, _s) in TEAMS
        ],
    }
    _write_json(FIXTURE_DIR / "teams_203.json", teams_payload)

    for (tid, _name, _f, _s) in TEAMS:
        matches = matches_per_team[tid]
        payload = {
            "get": "fixtures",
            "parameters": {"team": str(tid), "last": "10"},
            "errors": [],
            "results": len(matches),
            "paging": {"current": 1, "total": 1},
            "response": matches,
        }
        _write_json(FIXTURE_DIR / f"matches_{tid}.json", payload)

    total_unique = fixture_id - FIXTURE_ID_BASE
    print(
        f"Generated: {len(TEAMS)} teams, "
        f"{total_unique} unique matches "
        f"({PAST_ROUNDS} FT rounds + {FUTURE_ROUNDS} NS round)"
    )


if __name__ == "__main__":
    main()
