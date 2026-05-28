"""Live Shape Drift — rakibin formasyonu değişti mi?

Gerçek tracking olmadan event proxy: bir takımın oyuncularının
pass start_x ortalamasının zamana göre nasıl değiştiğini bak.

Algoritma:
1. Bir takımın TÜM pasları al
2. Her oyuncu için early_window (0-30 dk) ortalama pas konumu
3. Recent_window (current-10 ... current) ortalama pas konumu
4. Oyuncu pozisyon "drift" = |Δx| + |Δy|
5. Takım ortalama drift threshold geçerse "formation changed" alert

Pratik notlar:
- 5-10 oyuncuda significant drift varsa shape değişti
- Tek oyuncu (örn. winger içe çekildi) → "individual_shift"
- Kullanım: 60-70. dk civarı periyodik kontrol

Pure-compute. PassEvent + minute_window input.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

from app.audit import AuditRecord, EngineResult
from app.domain import PassEvent

ENGINE_NAME = "engine.live_shape_drift"
ENGINE_VERSION = "1"

# Drift sayılması için min hareket (saha birimi)
SIGNIFICANT_DRIFT = 8.0
# Form değişikliği eşiği: kaç oyuncuda significant drift
FORMATION_SHIFT_PLAYERS = 4
# Recent window
RECENT_WINDOW_MIN = 10.0


@dataclass(frozen=True)
class PlayerShift:
    player_external_id: int
    early_avg_x: float
    early_avg_y: float
    recent_avg_x: float
    recent_avg_y: float
    drift_distance: float       # Euclidean
    is_significant: bool


@dataclass(frozen=True)
class ShapeDriftReport:
    team_external_id: int
    current_minute: float
    early_window: tuple[float, float]    # (start, end)
    recent_window: tuple[float, float]
    n_players_analyzed: int
    n_players_significant_drift: int
    shape_changed: bool
    player_shifts: tuple[PlayerShift, ...]  # significant only, sorted by drift
    alert_text: str


def _player_avg_position(
    passes: list[PassEvent], window: tuple[float, float],
) -> tuple[float, float, int]:
    """(avg_x, avg_y, count) bir oyuncu + zaman penceresi."""
    w_start, w_end = window
    filtered = [p for p in passes if w_start <= p.minute <= w_end]
    if not filtered:
        return (0.0, 0.0, 0)
    avg_x = sum(p.start_x for p in filtered) / len(filtered)
    avg_y = sum(p.start_y for p in filtered) / len(filtered)
    return (avg_x, avg_y, len(filtered))


def compute_live_shape_drift(
    team_external_id: int,
    all_passes: Iterable[PassEvent],
    *,
    current_minute: float,
    early_window_end: float = 30.0,
    min_passes_per_player: int = 4,
) -> EngineResult[ShapeDriftReport]:
    """Rakip (veya bizim) takım formasyon değişikliği detect.

    Early window: (0, early_window_end). Recent: (current-10, current).
    Min pas/oyuncu eşiği gürültüyü filtre eder.
    """
    early_window = (0.0, early_window_end)
    recent_window = (max(0.0, current_minute - RECENT_WINDOW_MIN), current_minute)

    team_passes = [
        p for p in all_passes if p.team_external_id == team_external_id
    ]
    # Oyuncu bazında grupla
    by_player: dict[int, list[PassEvent]] = {}
    for p in team_passes:
        by_player.setdefault(p.player_external_id, []).append(p)

    shifts: list[PlayerShift] = []
    n_significant = 0
    for pid, plist in by_player.items():
        early_x, early_y, n_early = _player_avg_position(plist, early_window)
        recent_x, recent_y, n_recent = _player_avg_position(plist, recent_window)
        if n_early < min_passes_per_player or n_recent < min_passes_per_player:
            continue
        drift = math.hypot(recent_x - early_x, recent_y - early_y)
        is_sig = drift >= SIGNIFICANT_DRIFT
        if is_sig:
            n_significant += 1
        shifts.append(PlayerShift(
            player_external_id=pid,
            early_avg_x=round(early_x, 2), early_avg_y=round(early_y, 2),
            recent_avg_x=round(recent_x, 2), recent_avg_y=round(recent_y, 2),
            drift_distance=round(drift, 2),
            is_significant=is_sig,
        ))

    shifts.sort(key=lambda s: -s.drift_distance)
    significant_only = tuple(s for s in shifts if s.is_significant)
    shape_changed = n_significant >= FORMATION_SHIFT_PLAYERS

    if shape_changed:
        alert = (
            f"FORMATION DEĞİŞİKLİĞİ tespit edildi: {n_significant} oyuncuda "
            f"belirgin pozisyon kayması (eşik {FORMATION_SHIFT_PLAYERS})"
        )
    elif n_significant > 0:
        top_player = significant_only[0]
        alert = (
            f"Individual shift: player {top_player.player_external_id} "
            f"pozisyonunu {top_player.drift_distance:.1f} birim değiştirdi "
            f"(genel formasyon stabil)"
        )
    else:
        alert = "Takım şekli stabil; significant drift yok"

    report = ShapeDriftReport(
        team_external_id=team_external_id,
        current_minute=current_minute,
        early_window=early_window, recent_window=recent_window,
        n_players_analyzed=len(shifts),
        n_players_significant_drift=n_significant,
        shape_changed=shape_changed,
        player_shifts=significant_only,
        alert_text=alert,
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="team", subject_id=team_external_id,
        metric="live_shape_drift",
        value={
            "current_minute": current_minute,
            "shape_changed": shape_changed,
            "n_players_significant_drift": n_significant,
            "alert_text": alert,
        },
        inputs={
            "significant_drift": SIGNIFICANT_DRIFT,
            "formation_shift_players": FORMATION_SHIFT_PLAYERS,
            "recent_window_min": RECENT_WINDOW_MIN,
            "early_window_end": early_window_end,
            "min_passes_per_player": min_passes_per_player,
        },
        formula=(
            "per-player avg(x,y) early vs recent window; "
            "Euclidean drift >= significant_drift counts; "
            "shape_changed if N players drifted >= formation_shift_players"
        ),
    )
    return EngineResult(value=report, audit=audit)
