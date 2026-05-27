"""Süper Lig + Premier League 2024-25 sentetik fixture üreteci.

Deterministik (sabit seed) — aynı seed = aynı çıktı. Skorlar Poisson örneklenir;
takım gücü (`strength` 0..1) + ev avantajı `λ`'ı belirler. Veri uydurma ama
gerçek takım isim/ID'leriyle plausible — testlere ve demoya yeterli.

Kullanım:
    python scripts/generate_fixtures.py

Çıktılar (tests/fixtures/):
- leagues.json (Süper Lig + Premier League)
- teams_203.json, teams_39.json
- matches_<id>.json (her takım için, her iki ligden de)
"""

from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

SEED = 20240809

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = _PROJECT_ROOT / "tests" / "fixtures"


@dataclass(frozen=True)
class LeagueConfig:
    league_id: int
    name: str
    country: str
    country_code: str
    teams: list[tuple[int, str, int, float]]  # (api_id, name, founded, strength)
    fixture_id_base: int  # ligler arası ID çakışmasın
    first_past_kickoff: datetime
    first_future_kickoff: datetime
    season: int = 2024


SUPER_LIG = LeagueConfig(
    league_id=203,
    name="Süper Lig",
    country="Turkey",
    country_code="TR",
    teams=[
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
    ],
    fixture_id_base=1234100,
    first_past_kickoff=datetime(2024, 8, 17, 18, 0, tzinfo=UTC),
    first_future_kickoff=datetime(2026, 6, 7, 18, 0, tzinfo=UTC),
)

PREMIER_LEAGUE = LeagueConfig(
    league_id=39,
    name="Premier League",
    country="England",
    country_code="GB",
    teams=[
        # Strength: 2024-25 tipik final tablosu sırasına paralel
        (50, "Manchester City", 1880, 1.00),
        (42, "Arsenal", 1886, 0.95),
        (40, "Liverpool", 1892, 0.93),
        (49, "Chelsea", 1905, 0.80),
        (47, "Tottenham", 1882, 0.75),
        (33, "Manchester United", 1878, 0.70),
        (34, "Newcastle", 1892, 0.68),
        (35, "Everton", 1878, 0.50),
        (36, "Fulham", 1879, 0.45),
        (41, "Southampton", 1885, 0.30),
    ],
    fixture_id_base=1234300,
    first_past_kickoff=datetime(2024, 8, 16, 20, 0, tzinfo=UTC),
    first_future_kickoff=datetime(2026, 6, 12, 19, 0, tzinfo=UTC),
)

LEAGUES = [SUPER_LIG, PREMIER_LEAGUE]

PAST_ROUNDS = 7
FUTURE_ROUNDS = 2

# Skor modeli — Poisson λ
_LEAGUE_AVG_GOALS = 1.3
_STRENGTH_WEIGHT = 0.8
_HOME_ADVANTAGE = 0.3
_MAX_GOAL_CAP = 6


def _round_robin(n: int) -> list[list[tuple[int, int]]]:
    if n % 2 != 0:
        raise ValueError("round-robin: çift sayıda takım gerek")
    teams = list(range(n))
    rounds: list[list[tuple[int, int]]] = []
    for r in range(n - 1):
        pairs: list[tuple[int, int]] = []
        for i in range(n // 2):
            home = teams[i]
            away = teams[n - 1 - i]
            if i == 0 and r % 2 == 1:
                home, away = away, home
            pairs.append((home, away))
        rounds.append(pairs)
        teams = [teams[0]] + [teams[-1]] + teams[1:-1]
    return rounds


def _poisson_sample(rng: random.Random, lam: float) -> int:
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
    league_id: int,
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
        "league": {"id": league_id, "season": season, "round": f"Regular Season - {round_no}"},
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


def _generate_for_league(
    cfg: LeagueConfig, rng: random.Random
) -> dict[int, list[dict]]:
    """Bir lig için round-robin + scoring; matches_per_team döner."""
    n = len(cfg.teams)
    # Berger team-0 sabit → 1. takıma karşı son tur; ters çevir → marquee maç erkene
    rounds = list(reversed(_round_robin(n)))
    if len(rounds) < PAST_ROUNDS + FUTURE_ROUNDS:
        raise RuntimeError(
            f"{cfg.name}: round-robin yeterli tur üretmedi"
        )

    fixture_id = cfg.fixture_id_base
    matches_per_team: dict[int, list[dict]] = {tid: [] for (tid, *_) in cfg.teams}

    for r_idx, pairs in enumerate(rounds[:PAST_ROUNDS]):
        kickoff = cfg.first_past_kickoff + timedelta(days=7 * r_idx)
        for (h_i, a_i) in pairs:
            home = cfg.teams[h_i]
            away = cfg.teams[a_i]
            home_lam = _expected_goals(home[3], away[3], _HOME_ADVANTAGE)
            away_lam = _expected_goals(away[3], home[3], 0.0)
            home_score = min(_poisson_sample(rng, home_lam), _MAX_GOAL_CAP)
            away_score = min(_poisson_sample(rng, away_lam), _MAX_GOAL_CAP)
            match = _build_match(
                fixture_id, kickoff, cfg.league_id, cfg.season, r_idx + 1,
                home, away, status="FT",
                home_score=home_score, away_score=away_score,
            )
            matches_per_team[home[0]].append(match)
            matches_per_team[away[0]].append(match)
            fixture_id += 1

    for r_idx, pairs in enumerate(rounds[PAST_ROUNDS:PAST_ROUNDS + FUTURE_ROUNDS]):
        kickoff = cfg.first_future_kickoff + timedelta(days=7 * r_idx)
        for (h_i, a_i) in pairs:
            home = cfg.teams[h_i]
            away = cfg.teams[a_i]
            match = _build_match(
                fixture_id, kickoff, cfg.league_id, 2026, r_idx + 1,
                home, away, status="NS",
                home_score=None, away_score=None,
            )
            matches_per_team[home[0]].append(match)
            matches_per_team[away[0]].append(match)
            fixture_id += 1

    # API-Football yeni → eski sıralar
    for tid in matches_per_team:
        matches_per_team[tid].sort(key=lambda m: m["fixture"]["date"], reverse=True)

    return matches_per_team


def main() -> None:
    rng = random.Random(SEED)
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)

    # Birleşik leagues.json
    leagues_payload = {
        "get": "leagues",
        "parameters": [],
        "errors": [],
        "results": len(LEAGUES),
        "paging": {"current": 1, "total": 1},
        "response": [
            {
                "league": {"id": cfg.league_id, "name": cfg.name, "type": "League"},
                "country": {"name": cfg.country, "code": cfg.country_code},
                "seasons": [
                    {"year": cfg.season, "current": True}
                ],
            }
            for cfg in LEAGUES
        ],
    }
    _write_json(FIXTURE_DIR / "leagues.json", leagues_payload)

    total_matches = 0
    for cfg in LEAGUES:
        matches_per_team = _generate_for_league(cfg, rng)
        total_matches += sum(len(m) for m in matches_per_team.values()) // 2  # her maç iki teamde

        # teams_<league_id>.json
        teams_payload = {
            "get": "teams",
            "parameters": {"league": str(cfg.league_id), "season": str(cfg.season)},
            "errors": [],
            "results": len(cfg.teams),
            "paging": {"current": 1, "total": 1},
            "response": [
                {
                    "team": {
                        "id": tid, "name": name, "country": cfg.country,
                        "founded": founded, "national": False,
                    },
                    "venue": {},
                }
                for (tid, name, founded, _s) in cfg.teams
            ],
        }
        _write_json(FIXTURE_DIR / f"teams_{cfg.league_id}.json", teams_payload)

        for (tid, _name, _f, _s) in cfg.teams:
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

    print(
        f"Generated: {len(LEAGUES)} leagues, "
        f"{sum(len(cfg.teams) for cfg in LEAGUES)} teams, "
        f"~{total_matches} unique matches"
    )


if __name__ == "__main__":
    main()
