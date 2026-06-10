"""Sportmonks adapter saf parser testleri — gerçek Süper Lig yanıt şekliyle.

Değerler kullanıcının sağladığı gerçek Gaziantep F.K. vs Beşiktaş (fixture
19443213) yanıtından: Ndidi 21 dk / 19 pas / %89 / 1 şut(1 isabet) / 3 duel
(2 kazanılan) / 1 faul; sub 69' giriş; maç 0-2 FT; Süper Lig (600).
"""

from __future__ import annotations

from app.data.sources.sportmonks import Sportmonks, StandingRow
from app.sports import football

# Gerçek Sportmonks fixture şeklinin sadık, kompakt bir alt-kümesi (test girdisi).
FIXTURE = {
    "id": 19443213,
    "league_id": 600,
    "starting_at": "2026-05-01 17:00:00",
    "starting_at_timestamp": 1777654800,
    "state": {"developer_name": "FT"},
    "participants": [
        {"id": 4192, "name": "Gaziantep F.K.", "founded": 1988, "meta": {"location": "home"}},
        {"id": 554, "name": "Beşiktaş", "founded": 1903, "meta": {"location": "away"}},
    ],
    "scores": [
        {"description": "CURRENT", "participant_id": 4192, "score": {"goals": 0}},
        {"description": "CURRENT", "participant_id": 554, "score": {"goals": 2}},
        {"description": "1ST_HALF", "participant_id": 554, "score": {"goals": 2}},
    ],
    "events": [
        # Gol: Djaló (skorer), Asllani (asist)
        {"type_id": 14, "player_id": 540319, "related_player_id": 37532950, "minute": 7},
        # Penaltı golü: Asllani
        {"type_id": 16, "player_id": 37532950, "related_player_id": None, "minute": 22},
        # Değişiklik: Ndidi (giren) ← Salih Uçan (çıkan), 69'
        {"type_id": 18, "player_id": 5319, "related_player_id": 129416, "minute": 69},
        # Sarı kart: bir Gaziantep oyuncusu
        {"type_id": 19, "player_id": 23717944, "related_player_id": None, "minute": 31},
    ],
    "lineups": [
        {  # Ndidi — yedek (type 12), sonradan girdi
            "player_id": 5319, "team_id": 554, "position_id": 26,
            "player_name": "Wilfred Ndidi", "jersey_number": 4, "type_id": 12,
            "details": [
                {"type_id": 119, "data": {"value": 21}},     # minutes
                {"type_id": 80, "data": {"value": 19}},      # passes
                {"type_id": 1584, "data": {"value": 89}},    # accurate passes %
                {"type_id": 42, "data": {"value": 1}},       # shots total
                {"type_id": 86, "data": {"value": 1}},       # shots on
                {"type_id": 108, "data": {"value": 1}},      # dribble attempts
                {"type_id": 105, "data": {"value": 3}},      # total duels
                {"type_id": 106, "data": {"value": 2}},      # duels won
                {"type_id": 56, "data": {"value": 1}},       # fouls
                {"type_id": 117172, "data": {"value": 25}},  # bilinmeyen → atlanır
            ],
        },
        {  # Djaló — ilk 11 (type 11), gol attı
            "player_id": 540319, "team_id": 554, "position_id": 25,
            "player_name": "Tiago Djaló", "jersey_number": 4, "type_id": 11,
            "details": [{"type_id": 119, "data": {"value": 80}}],
        },
        {  # Asllani — ilk 11, gol + asist
            "player_id": 37532950, "team_id": 554, "position_id": 26,
            "player_name": "Kristjan Asllani", "jersey_number": 20, "type_id": 11,
            "details": [{"type_id": 119, "data": {"value": 90}}],
        },
        {  # Salih Uçan — ilk 11, tam istatistik (gerçek değerler)
            "player_id": 129416, "team_id": 554, "position_id": 26,
            "player_name": "Salih Uçan", "jersey_number": 8, "type_id": 11,
            "details": [
                {"type_id": 119, "data": {"value": 69}},     # minutes
                {"type_id": 80, "data": {"value": 51}},      # passes
                {"type_id": 1584, "data": {"value": 94}},    # accurate passes %
                {"type_id": 106, "data": {"value": 3}},      # duels won
                {"type_id": 105, "data": {"value": 4}},      # total duels
                {"type_id": 117, "data": {"value": 2}},      # key passes
                {"type_id": 118, "data": {"value": 7.32}},   # rating
                {"type_id": 78, "data": {"value": 1}},       # tackles
                {"type_id": 100, "data": {"value": 1}},      # interceptions
                {"type_id": 109, "data": {"value": 2}},      # successful dribbles
                {"type_id": 56, "data": {"value": 1}},       # fouls
            ],
        },
        {  # Oynamamış yedek — details yok → istatistikte atlanmalı
            "player_id": 999001, "team_id": 554, "position_id": 27,
            "player_name": "Oynamayan", "jersey_number": 30, "type_id": 12,
            "details": [],
        },
    ],
}


# ── parse_match ──────────────────────────────────────────────────────────────

def test_parse_match_basics():
    m = Sportmonks.parse_match(FIXTURE)
    assert m.sport == football.SPORT_NAME
    assert m.external_id == 19443213
    assert m.league_external_id == 600
    assert m.status == "FT"
    assert m.home_team_external_id == 4192   # Gaziantep
    assert m.away_team_external_id == 554    # Beşiktaş
    assert m.home_score == 0
    assert m.away_score == 2
    assert m.season == 2025                  # Mayıs 2026 → 2025/26 sezonu


# ── parse_lineups ────────────────────────────────────────────────────────────

def test_parse_lineups_starter_flag_and_position():
    lns = Sportmonks.parse_lineups(FIXTURE)
    by_id = {li.player_external_id: li for li in lns}
    assert by_id[5319].is_starter is False          # type 12 = yedek
    assert by_id[540319].is_starter is True         # type 11 = ilk 11
    assert by_id[540319].position_code == football.POSITION_DEFENDER   # 25
    assert by_id[37532950].position_code == football.POSITION_MIDFIELDER  # 26
    assert by_id[5319].jersey == 4
    assert by_id[5319].player_name == "Wilfred Ndidi"


# ── parse_player_stats ───────────────────────────────────────────────────────

def test_parse_player_stats_maps_detail_type_ids():
    stats = Sportmonks.parse_player_stats(FIXTURE)
    ndidi = next(s for s in stats if s.player_external_id == 5319)
    assert ndidi.minutes == 21
    assert ndidi.passes_total == 19
    assert ndidi.passes_accuracy == 89
    assert ndidi.shots_total == 1
    assert ndidi.shots_on == 1
    assert ndidi.dribbles_attempts == 1
    assert ndidi.duels_total == 3
    assert ndidi.duels_won == 2
    assert ndidi.fouls_committed == 1
    assert ndidi.team_external_id == 554
    assert ndidi.match_external_id == 19443213


def test_player_stats_substitution_in_minute():
    stats = Sportmonks.parse_player_stats(FIXTURE)
    ndidi = next(s for s in stats if s.player_external_id == 5319)
    # Sub konvansiyonu: player_id = giren → Ndidi 69'da girdi
    assert ndidi.substituted_in_minute == 69
    # related_player = çıkan → Salih Uçan 69'da çıktı (ilk 11'di)
    salih = next(s for s in stats if s.player_external_id == 129416)
    assert salih.substituted_out_minute == 69
    assert salih.substituted_in_minute is None


def test_player_stats_goals_assists_from_events():
    stats = Sportmonks.parse_player_stats(FIXTURE)
    by_id = {s.player_external_id: s for s in stats}
    # Djaló 1 gol; Asllani 1 gol (penaltı) + 1 asist (Djaló golünde related)
    assert by_id[540319].goals == 1
    assert by_id[37532950].goals == 1
    assert by_id[37532950].assists == 1


def test_parse_player_stats_full_detail_mapping():
    """Tüm doğrulanmış type_id'ler (tackle/interception/key pass/dribble/rating)."""
    stats = Sportmonks.parse_player_stats(FIXTURE)
    s = next(x for x in stats if x.player_external_id == 129416)  # Salih Uçan
    assert s.minutes == 69
    assert s.passes_total == 51
    assert s.passes_accuracy == 94
    assert s.duels_total == 4
    assert s.duels_won == 3
    assert s.key_passes == 2
    assert s.rating == 7.32
    assert s.tackles_total == 1
    assert s.interceptions == 1
    assert s.dribbles_success == 2
    assert s.fouls_committed == 1


def test_player_stats_skips_non_playing_bench():
    stats = Sportmonks.parse_player_stats(FIXTURE)
    ids = {s.player_external_id for s in stats}
    assert 999001 not in ids   # details yok → minutes None → atlandı


def test_parse_players_master_data():
    """lineups[].player + events[].player → Player (ad/pozisyon/doğum tarihi)."""
    from datetime import date
    fixture = {
        "id": 19443213,
        "lineups": [
            {"player_id": 5319, "team_id": 554, "position_id": 26, "type_id": 12,
             "player_name": "Wilfred Ndidi",
             "player": {"id": 5319, "display_name": "Wilfred Ndidi",
                        "position_id": 26, "date_of_birth": "1996-12-16"}},
        ],
        "events": [
            {"type_id": 14, "player_id": 540319, "related_player_id": None, "minute": 7,
             "player": {"id": 540319, "display_name": "Tiago Djaló",
                        "position_id": 25, "date_of_birth": "2000-04-09"}},
            # Aynı oyuncu tekrar → tekilleştirilmeli
            {"type_id": 19, "player_id": 5319, "related_player_id": None, "minute": 31,
             "player": {"id": 5319, "display_name": "Wilfred Ndidi",
                        "position_id": 26, "date_of_birth": "1996-12-16"}},
        ],
    }
    players = Sportmonks.parse_players(fixture)
    by_id = {p.external_id: p for p in players}
    assert len(players) == 2                       # tekilleştirildi
    assert by_id[5319].name == "Wilfred Ndidi"
    assert by_id[5319].position == football.POSITION_MIDFIELDER
    assert by_id[5319].birth_date == date(1996, 12, 16)
    assert by_id[540319].position == football.POSITION_DEFENDER
    assert by_id[540319].birth_date == date(2000, 4, 9)


def test_parse_teams():
    teams = Sportmonks.parse_teams(FIXTURE)
    by_id = {t.external_id: t for t in teams}
    assert by_id[554].name == "Beşiktaş"
    assert by_id[554].founded == 1903
    assert by_id[4192].founded == 1988


# ── parse_schedule (takım programı / fikstür listesi) ─────────────────────────

# Gerçek "fixtures between" yanıtının kompakt alt-kümesi (3 fixture):
# 1) Rizespor 2-2 Beşiktaş (lig 600, 2026-05-15) — beraberlik
# 2) Beşiktaş 4-1 Rizespor (Türkiye Kupası 606, 2026-03-04) — ev sahibi galip
# 3) Beşiktaş 1-0 Rizespor (lig 600, 2025-12-20) — ev sahibi galip
SCHEDULE = [
    {
        "id": 19443228,
        "league_id": 600,
        "starting_at": "2026-05-15 17:00:00",
        "starting_at_timestamp": 1778864400,
        "state": {"developer_name": "FT"},
        "participants": [
            {"id": 554, "name": "Beşiktaş", "meta": {"location": "away"}},
            {"id": 1041, "name": "Rizespor", "meta": {"location": "home"}},
        ],
        "scores": [
            {"description": "CURRENT", "participant_id": 554, "score": {"goals": 2}},
            {"description": "CURRENT", "participant_id": 1041, "score": {"goals": 2}},
        ],
    },
    {
        "id": 19609286,
        "league_id": 606,
        "starting_at": "2026-03-04 17:30:00",
        "starting_at_timestamp": 1772645400,
        "state": {"developer_name": "FT"},
        "participants": [
            {"id": 1041, "name": "Rizespor", "meta": {"location": "away"}},
            {"id": 554, "name": "Beşiktaş", "meta": {"location": "home"}},
        ],
        "scores": [
            {"description": "CURRENT", "participant_id": 554, "score": {"goals": 4}},
            {"description": "CURRENT", "participant_id": 1041, "score": {"goals": 1}},
        ],
    },
    {
        "id": 19443076,
        "league_id": 600,
        "starting_at": "2025-12-20 17:00:00",
        "starting_at_timestamp": 1766250000,
        "state": {"developer_name": "FT"},
        "participants": [
            {"id": 1041, "name": "Rizespor", "meta": {"location": "away"}},
            {"id": 554, "name": "Beşiktaş", "meta": {"location": "home"}},
        ],
        "scores": [
            {"description": "CURRENT", "participant_id": 554, "score": {"goals": 1}},
            {"description": "CURRENT", "participant_id": 1041, "score": {"goals": 0}},
        ],
    },
]


def test_parse_schedule_maps_each_fixture():
    matches = Sportmonks.parse_schedule(SCHEDULE)
    assert len(matches) == 3
    by_id = {m.external_id: m for m in matches}

    # 1) beraberlik 2-2, lig 600
    assert by_id[19443228].league_external_id == 600
    assert by_id[19443228].home_team_external_id == 1041   # Rizespor ev
    assert by_id[19443228].away_team_external_id == 554     # Beşiktaş deplasman
    assert by_id[19443228].home_score == 2
    assert by_id[19443228].away_score == 2

    # 2) kupa 606, Beşiktaş ev sahibi 4-1
    assert by_id[19609286].league_external_id == 606
    assert by_id[19609286].home_team_external_id == 554
    assert by_id[19609286].home_score == 4
    assert by_id[19609286].away_score == 1

    # 3) lig 600, Beşiktaş ev sahibi 1-0
    assert by_id[19443076].home_score == 1
    assert by_id[19443076].away_score == 0
    assert all(m.status == "FT" for m in matches)


def test_parse_schedule_skips_broken_rows():
    data = [
        {"id": None},                       # id yok → atla
        "garbage",                          # dict değil → atla
        SCHEDULE[0],                        # geçerli
    ]
    matches = Sportmonks.parse_schedule(data)  # type: ignore[arg-type]
    assert len(matches) == 1
    assert matches[0].external_id == 19443228


# ── parse_squad (takım kadrosu) ───────────────────────────────────────────────

# Gerçek squads/teams/554 yanıtının kompakt alt-kümesi (3 oyuncu):
SQUAD = [
    {
        "player_id": 37259977, "team_id": 554, "position_id": 25, "jersey_number": 39,
        "player": {
            "id": 37259977, "name": "David Jurásek", "display_name": "David Jurásek",
            "position_id": 25, "date_of_birth": "2000-08-07",
            "nationality": {"id": 245, "name": "Czech Republic"},
        },
    },
    {
        "player_id": 37650803, "team_id": 554, "position_id": 25, "jersey_number": 22,
        "player": {
            "id": 37650803, "name": "Taylan Bulut", "display_name": "Taylan Bulut",
            "position_id": 25, "date_of_birth": "2006-01-19",
            "nationality": {"id": 11, "name": "Germany"},
        },
    },
    {
        "player_id": 1441, "team_id": 554, "position_id": 25, "jersey_number": 3,
        "player": {
            "id": 1441, "name": "Gabriel Armando de Abreu", "display_name": "Gabriel Paulista",
            "position_id": 25, "date_of_birth": "1990-11-26",
            "nationality": {"id": 5, "name": "Brazil"},
        },
    },
]


def test_parse_squad_master_data():
    players = Sportmonks.parse_squad(SQUAD)
    by_id = {p.external_id: p for p in players}
    assert len(players) == 3

    # display_name tercih edilir
    assert by_id[1441].name == "Gabriel Paulista"
    # gerçek uyruk adı (nested nationality)
    assert by_id[37259977].nationality == "Czech Republic"
    assert by_id[37650803].nationality == "Germany"
    # pozisyon kodu (25 → Defender) + doğum tarihi
    assert by_id[1441].position == football.POSITION_DEFENDER
    bd = by_id[37650803].birth_date
    assert bd is not None and bd.year == 2006


def test_parse_squad_position_fallback_to_root():
    # player objesinde position_id yoksa kök kayıttan alınır
    data = [{
        "player_id": 99, "position_id": 27,  # 27 = Forward (kökte)
        "player": {"id": 99, "name": "Test FW", "date_of_birth": "1999-01-01"},
    }]
    players = Sportmonks.parse_squad(data)
    assert players[0].position == football.POSITION_FORWARD


def test_parse_squad_skips_entries_without_player():
    data = [
        {"player_id": 1},          # nested player yok → atla
        "garbage",                 # dict değil → atla
        SQUAD[0],                  # geçerli
    ]
    players = Sportmonks.parse_squad(data)  # type: ignore[arg-type]
    assert len(players) == 1
    assert players[0].external_id == 37259977


# ── parse_standings (puan durumu) ─────────────────────────────────────────────

def _standing_detail(type_id: int, value):
    return {"type_id": type_id, "value": value, "type": {"id": type_id}}


# Gerçek standings/seasons/25682 yanıtının kompakt alt-kümesi (ilk 3 sıra):
# Galatasaray 1. (77p, 24G-5B-5M, 77:30), Fenerbahçe 2. (74p), Trabzonspor 3. (69p)
STANDINGS = [
    {
        "participant_id": 34, "position": 1, "points": 77,
        "participant": {"id": 34, "name": "Galatasaray", "founded": 1905},
        "rule": {"type": {"name": "UEFA Champions League"}},
        "details": [
            _standing_detail(129, 34), _standing_detail(130, 24),
            _standing_detail(131, 5), _standing_detail(132, 5),
            _standing_detail(133, 77), _standing_detail(134, 30),
            _standing_detail(179, 47), _standing_detail(187, 77),
            _standing_detail(7939, 64),
        ],
        "form": [
            {"form": "W", "sort_order": 33}, {"form": "L", "sort_order": 34},
            {"form": "W", "sort_order": 32},
        ],
    },
    {
        "participant_id": 88, "position": 2, "points": 74,
        "participant": {"id": 88, "name": "Fenerbahçe", "founded": 1907},
        "rule": {"type": {"name": "UEFA Champions League Qualifiers"}},
        "details": [
            _standing_detail(129, 34), _standing_detail(130, 21),
            _standing_detail(131, 11), _standing_detail(132, 2),
            _standing_detail(133, 77), _standing_detail(134, 37),
            _standing_detail(179, 40), _standing_detail(187, 74),
            _standing_detail(7939, 66),
        ],
        "form": [],
    },
    {
        "participant_id": 688, "position": 3, "points": 69,
        "participant": {"id": 688, "name": "Trabzonspor", "founded": 1967},
        "rule": {"type": {"name": "UEFA Europa League Qualifiers"}},
        "details": [
            _standing_detail(129, 34), _standing_detail(130, 20),
            _standing_detail(131, 9), _standing_detail(132, 5),
            _standing_detail(133, 61), _standing_detail(134, 39),
            _standing_detail(179, 22), _standing_detail(187, 69),
            _standing_detail(7939, 53),
        ],
        "form": [],
    },
]


def test_parse_standings_maps_table():
    rows = Sportmonks.parse_standings(STANDINGS)
    assert [r.position for r in rows] == [1, 2, 3]
    gala = rows[0]
    assert isinstance(gala, StandingRow)
    assert gala.team_external_id == 34
    assert gala.team_name == "Galatasaray"
    assert gala.played == 34
    assert gala.won == 24 and gala.draw == 5 and gala.lost == 5
    assert gala.goals_for == 77 and gala.goals_against == 30
    assert gala.goal_diff == 47
    assert gala.points == 77
    assert gala.xpoints == 64.0
    assert gala.qualification == "UEFA Champions League"


def test_parse_standings_form_ordered_old_to_new():
    rows = Sportmonks.parse_standings(STANDINGS)
    # sort_order 32,33,34 → eski→yeni: W, W, L
    assert rows[0].form == ["W", "W", "L"]


def test_parse_standings_sorts_by_position_and_skips_broken():
    shuffled = [STANDINGS[2], STANDINGS[0], {"participant_id": None}, "x", STANDINGS[1]]
    rows = Sportmonks.parse_standings(shuffled)  # type: ignore[list-item]
    assert [r.position for r in rows] == [1, 2, 3]


def test_parse_teams_from_standings():
    teams = Sportmonks.parse_teams_from_standings(STANDINGS)
    by_id = {t.external_id: t for t in teams}
    assert len(teams) == 3
    assert by_id[88].name == "Fenerbahçe"
    assert by_id[688].founded == 1967


# ── DataSource sözleşmesi: leagues + season-teams + sezon-yılı çözümü ──────────

def test_parse_leagues_season_year_from_name():
    data = [
        {"id": 271, "name": "Superliga", "currentseason": {"id": 27897, "name": "2026/2027"}},
        {"id": 600, "name": "Super Lig", "currentseason": {"id": 25682, "name": "2025/2026"}},
        {"id": 1, "name": "Boş Sezon"},  # currentseason yok → season 0
    ]
    lgs = Sportmonks.parse_leagues(data)
    by_id = {lg.external_id: lg for lg in lgs}
    assert by_id[271].season == 2026
    assert by_id[600].season == 2025
    assert by_id[600].name == "Super Lig"
    assert by_id[1].season == 0


def test_parse_season_teams():
    data = [
        {"id": 2447, "name": "Viborg FF", "founded": 1896},
        {"id": 1789, "name": "Odense BK", "founded": 1889},
        {"id": 2447, "name": "Viborg FF (dup)", "founded": 1896},  # tekrar → tekilleşir
        "garbage",
    ]
    teams = Sportmonks.parse_season_teams(data)  # type: ignore[arg-type]
    by_id = {t.external_id: t for t in teams}
    assert len(teams) == 2
    assert by_id[2447].name == "Viborg FF"
    assert by_id[1789].founded == 1889


def test_sportmonks_is_datasource():
    # DataSource ABC tam dolduruldu → sync hattı kabul eder
    from app.data.sources.base import DataSource
    sm = Sportmonks(api_key="x")
    assert isinstance(sm, DataSource)
    assert sm.name == "sportmonks"


def test_fixture_include_drops_xg_when_disabled():
    sm = Sportmonks(api_key="x")
    assert "xgfixture" in sm._fixture_include()      # varsayılan: xG dahil
    sm._xg_enabled = False
    inc = sm._fixture_include()
    assert "xgfixture" not in inc and "xglineup" not in inc
    assert "lineups.details" in inc                  # oyuncu-başı stat hep var
