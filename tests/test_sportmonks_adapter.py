"""Sportmonks adapter saf parser testleri — gerçek Süper Lig yanıt şekliyle.

Değerler kullanıcının sağladığı gerçek Gaziantep F.K. vs Beşiktaş (fixture
19443213) yanıtından: Ndidi 21 dk / 19 pas / %89 / 1 şut(1 isabet) / 3 duel
(2 kazanılan) / 1 faul; sub 69' giriş; maç 0-2 FT; Süper Lig (600).
"""

from __future__ import annotations

from app.data.sources.sportmonks import Sportmonks
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
    # Sub konvansiyonu: player_id = giren → 69'da girdi
    assert ndidi.substituted_in_minute == 69
    salih_out = next((s for s in stats if s.player_external_id == 129416), None)
    # Salih Uçan lineup'ta yok (bu kompakt fixture'da) → stat üretilmez; ama
    # çıkan-dakika indeksi yine de event'ten gelir (lineup'ta olsaydı dolardı).
    assert salih_out is None


def test_player_stats_goals_assists_from_events():
    stats = Sportmonks.parse_player_stats(FIXTURE)
    by_id = {s.player_external_id: s for s in stats}
    # Djaló 1 gol; Asllani 1 gol (penaltı) + 1 asist (Djaló golünde related)
    assert by_id[540319].goals == 1
    assert by_id[37532950].goals == 1
    assert by_id[37532950].assists == 1


def test_player_stats_skips_non_playing_bench():
    stats = Sportmonks.parse_player_stats(FIXTURE)
    ids = {s.player_external_id for s in stats}
    assert 999001 not in ids   # details yok → minutes None → atlandı


def test_parse_teams():
    teams = Sportmonks.parse_teams(FIXTURE)
    by_id = {t.external_id: t for t in teams}
    assert by_id[554].name == "Beşiktaş"
    assert by_id[554].founded == 1903
    assert by_id[4192].founded == 1988
