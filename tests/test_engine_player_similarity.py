"""engine.player_similarity — cosine similarity tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from app.engine.player_similarity import (
    FEATURE_NAMES,
    compute_player_profile,
    compute_similar_players,
)


@dataclass(frozen=True)
class _App:
    """Test-only PlayerAppearance proxy (PlayerAppearanceLike + ekstra alanlar)."""
    sport: str
    player_external_id: int
    match_external_id: int
    minutes: int
    kickoff: datetime
    rating_apifootball: float | None = None
    passes_total: int | None = None
    passes_accuracy: int | None = None
    shots_total: int | None = None
    dribbles_success: int | None = None
    fouls_drawn: int | None = None


def _app(pid: int, mid: int, mins: int, **kw) -> _App:
    base = dict(
        sport="football", player_external_id=pid, match_external_id=mid,
        minutes=mins, kickoff=datetime(2024, 8, 15, tzinfo=UTC),
    )
    base.update(kw)
    return _App(**base)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# Profile
# --------------------------------------------------------------------------- #


def test_profile_per_90_normalization():
    """3 maç × 90 dk = 270 dk; 30 pas/maç = 90 pas total → 30/90 = 30 per 90."""
    apps = [
        _app(1, i, 90, rating_apifootball=7.0, passes_total=30, passes_accuracy=85,
             shots_total=2, dribbles_success=1, fouls_drawn=1)
        for i in range(3)
    ]
    r = compute_player_profile(1, apps)
    f = r.value.features
    assert r.value.total_minutes == 270
    assert r.value.matches_played == 3
    assert f["passes_per_90"] == 30.0
    assert f["shots_per_90"] == 2.0
    assert f["dribbles_success_per_90"] == 1.0
    assert f["rating_avg"] == 7.0
    assert f["passes_accuracy_avg"] == 85.0


def test_profile_handles_missing_stats():
    """Stats None ise 0 olarak sayar — graceful degradation."""
    apps = [_app(1, 1, 90)]  # tüm stats None
    r = compute_player_profile(1, apps)
    f = r.value.features
    assert f["passes_per_90"] == 0.0
    assert f["rating_avg"] == 0.0


def test_profile_minutes_weighted_pass_accuracy():
    """30 dk %50 + 90 dk %90 → (30*50 + 90*90) / 120 = 80."""
    apps = [
        _app(1, 1, 30, passes_accuracy=50),
        _app(1, 2, 90, passes_accuracy=90),
    ]
    r = compute_player_profile(1, apps)
    assert r.value.features["passes_accuracy_avg"] == 80.0


def test_profile_audit_includes_feature_names():
    apps = [_app(1, 1, 90)]
    r = compute_player_profile(1, apps)
    assert r.audit.engine == "engine.player_similarity"
    assert r.audit.inputs["feature_names"] == list(FEATURE_NAMES)


# --------------------------------------------------------------------------- #
# Similarity
# --------------------------------------------------------------------------- #


def _striker_apps(pid: int, *, shots_per_90: int = 4, rating: float = 7.5) -> list[_App]:
    """4 maç × 90 dk, hücum profili."""
    return [
        _app(pid, pid * 100 + i, 90,
             rating_apifootball=rating,
             passes_total=20, passes_accuracy=75,
             shots_total=shots_per_90, dribbles_success=2, fouls_drawn=3)
        for i in range(4)
    ]


def _defender_apps(pid: int) -> list[_App]:
    """4 maç × 90 dk, defansif profil — düşük şut, yüksek pas isabeti."""
    return [
        _app(pid, pid * 100 + i, 90,
             rating_apifootball=7.0,
             passes_total=60, passes_accuracy=92,
             shots_total=0, dribbles_success=0, fouls_drawn=1)
        for i in range(4)
    ]


def test_similar_strikers_have_high_similarity():
    target_apps = _striker_apps(1, shots_per_90=4)
    candidates = {
        2: _striker_apps(2, shots_per_90=4),     # benzer striker
        3: _defender_apps(3),                     # farklı (defender)
        4: _striker_apps(4, shots_per_90=5, rating=8.0),  # biraz farklı striker
    }
    r = compute_similar_players(1, target_apps, candidates, top_n=3)
    top = r.value.top_matches
    assert len(top) == 3
    # En benzer 2 olmalı (aynı profil)
    assert top[0].player_external_id == 2
    assert top[0].similarity > 0.99
    # Defender (3) son sırada veya düşük skor
    defender_match = next(m for m in top if m.player_external_id == 3)
    striker_match = top[0]
    assert defender_match.similarity < striker_match.similarity


def test_similarity_filters_low_minute_candidates():
    """min_minutes altında oyuncular eligible'a girmemeli."""
    target_apps = _striker_apps(1)
    # 2 saat (2*60 = 120 dk) — 270 default eşiğin altında
    low_minute = [_app(2, 999, 60, shots_total=2)]
    candidates = {2: low_minute, 3: _striker_apps(3)}
    r = compute_similar_players(1, target_apps, candidates)
    assert r.value.candidates_considered == 2
    assert r.value.candidates_eligible == 1  # sadece 3
    pids_in_top = {m.player_external_id for m in r.value.top_matches}
    assert 2 not in pids_in_top
    assert 3 in pids_in_top


def test_similarity_excludes_target_from_candidates():
    """Hedef oyuncu kendi candidate'lar arasındaysa atlanmalı."""
    target_apps = _striker_apps(1)
    candidates = {1: target_apps, 2: _striker_apps(2)}  # 1 yine içinde
    r = compute_similar_players(1, target_apps, candidates)
    pids = {m.player_external_id for m in r.value.top_matches}
    assert 1 not in pids
    assert 2 in pids


def test_similarity_zero_vectors_returns_zero():
    """Hiç stat olmayan oyuncular için cosine 0 dönmeli (numerical guard)."""
    empty = [_app(1, 1, 300)]  # tüm stats None
    candidates = {2: [_app(2, 2, 300)]}
    r = compute_similar_players(1, empty, candidates)
    # 0-vektör için cosine = 0
    if r.value.top_matches:
        assert r.value.top_matches[0].similarity == 0.0


def test_similarity_audit_records_formula():
    target_apps = _striker_apps(1)
    candidates = {2: _striker_apps(2)}
    r = compute_similar_players(1, target_apps, candidates)
    assert "cosine_similarity" in r.audit.formula
    assert r.audit.subject_id == 1


def test_top_n_limits_results():
    target_apps = _striker_apps(1)
    candidates = {pid: _striker_apps(pid) for pid in range(2, 12)}
    r = compute_similar_players(1, target_apps, candidates, top_n=3)
    assert len(r.value.top_matches) == 3
    # candidates_eligible = 10 (target hariç)
    assert r.value.candidates_eligible == 10
