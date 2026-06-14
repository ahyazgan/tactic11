"""Hot Hand — sıcak el yakalama (G.2).

Son N dakikalık pencerede bizim takımın şut hacmi + xG seviyesi maç
baselineından belirgin yüksek mi → "sıcak el". Aktif şut atan oyuncuları
sıralar; en üstte hot_player.

Pure compute. Shot listesi (domain.Shot) + current_minute + window_min input.
TD'nin "Şu an gol kokusu geliyor mu, bastıralım mı?" sorusuna sayıyla cevap.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from app.audit import AuditRecord, EngineResult
from app.domain import Shot

ENGINE_NAME = "engine.hot_hand"
ENGINE_VERSION = "1"

DEFAULT_WINDOW_MIN = 15.0
BASELINE_MIN = 30.0  # baseline pencere — window'un öncesi

# Sıcak el eşikleri
HOT_SHOT_RATIO = 1.6        # window_shots_per_15 / baseline_per_15 ≥ 1.6 → hot
HOT_SHOT_ABS_MIN = 3        # mutlak alt sınır: pencerede en az 3 şut
HOT_PLAYER_MIN_SHOTS = 2    # bir oyuncu hot sayılması için window'da 2 şut


def _xg_proxy(shot: Shot) -> float:
    """Şutun lokasyonuna göre kaba xG proxy (penal 0.76, ceza 6 0.45, dış 0.04).

    Gerçek xG modeli `engine.xg`'de var; hot_hand pure-compute kalsın diye
    küçük bir lokasyon-bazlı kestirim kullanılır.
    """
    x, y = shot.x, shot.y
    if shot.pattern == "penalty":
        return 0.76
    # Ceza alanı içi (x>=83, y 21..79) — yakın şut
    if x >= 83 and 21 <= y <= 79:
        center_dy = abs(50 - y) / 30  # 0..1
        return max(0.18, 0.45 - center_dy * 0.20)
    if x >= 75:
        return 0.10
    return 0.04


@dataclass(frozen=True)
class HotPlayer:
    player_external_id: int
    shots_in_window: int
    xg_in_window: float
    is_hot: bool


@dataclass(frozen=True)
class HotHandReport:
    team_external_id: int
    current_minute: float
    window_min: float
    # Window
    shots_window: int
    xg_window: float
    shots_per_15min_window: float
    # Baseline
    shots_baseline_per_15min: float
    xg_baseline_per_15min: float
    # Karar
    shot_volume_ratio: float          # window vs baseline
    hot_streak: bool
    hot_player: HotPlayer | None
    hot_players: tuple[HotPlayer, ...] = field(default_factory=tuple)
    tactical_advice: str = ""


def _rate_per_15(count: float, window: float) -> float:
    if window <= 0:
        return 0.0
    return round((count / window) * 15.0, 2)


def _build_advice(
    *, hot_streak: bool, hot_player: HotPlayer | None,
    shots_window: int, xg_window: float,
) -> str:
    if not hot_streak:
        if shots_window == 0:
            return "Son pencerede şut yok — top tutuyoruz ama bitiriciliğe geçemiyoruz, dik pas dene"
        return "Şut hacmi normal — mevcut tempo koru"
    base = "Sıcak el — şut açıklarını zorla, ön cep paslarını artır"
    if hot_player and hot_player.shots_in_window >= 3:
        base += (
            f" · player {hot_player.player_external_id} "
            f"{hot_player.shots_in_window} şut/{xg_window:.2f} xG: ona besle"
        )
    return base


def compute_hot_hand(
    team_external_id: int,
    shots: Iterable[Shot],
    *,
    current_minute: float,
    window_min: float = DEFAULT_WINDOW_MIN,
    baseline_min: float = BASELINE_MIN,
) -> EngineResult[HotHandReport]:
    """Sıcak el sinyali — son N dk şut volume × xG vs baseline."""
    window_lo = current_minute - window_min
    base_hi = window_lo
    base_lo = max(0.0, base_hi - baseline_min)

    window_shots: list[Shot] = []
    baseline_shots: list[Shot] = []
    for s in shots:
        if s.team_external_id != team_external_id:
            continue
        if window_lo <= s.minute <= current_minute:
            window_shots.append(s)
        elif base_lo <= s.minute < base_hi:
            baseline_shots.append(s)

    xg_window = sum(_xg_proxy(s) for s in window_shots)
    xg_baseline = sum(_xg_proxy(s) for s in baseline_shots)

    shots_per_15_window = _rate_per_15(len(window_shots), window_min)
    shots_per_15_baseline = _rate_per_15(len(baseline_shots), baseline_min)
    xg_per_15_baseline = _rate_per_15(xg_baseline, baseline_min)

    if shots_per_15_baseline > 0:
        ratio = round(shots_per_15_window / shots_per_15_baseline, 2)
    elif shots_per_15_window > 0:
        ratio = 2.0  # baseline 0 + window var → sıcak
    else:
        ratio = 0.0

    hot_streak = (
        len(window_shots) >= HOT_SHOT_ABS_MIN
        and (ratio >= HOT_SHOT_RATIO or shots_per_15_baseline == 0)
    )

    # Per-player sıcaklık
    by_player: dict[int, list[Shot]] = {}
    for s in window_shots:
        pid = s.player_external_id
        if pid is None:
            continue
        by_player.setdefault(int(pid), []).append(s)
    players = [
        HotPlayer(
            player_external_id=pid,
            shots_in_window=len(lst),
            xg_in_window=round(sum(_xg_proxy(x) for x in lst), 4),
            is_hot=len(lst) >= HOT_PLAYER_MIN_SHOTS,
        )
        for pid, lst in by_player.items()
    ]
    players.sort(key=lambda p: (p.shots_in_window, p.xg_in_window), reverse=True)
    hot_player = next((p for p in players if p.is_hot), None)

    advice = _build_advice(
        hot_streak=hot_streak, hot_player=hot_player,
        shots_window=len(window_shots), xg_window=xg_window,
    )

    report = HotHandReport(
        team_external_id=team_external_id,
        current_minute=current_minute,
        window_min=window_min,
        shots_window=len(window_shots),
        xg_window=round(xg_window, 4),
        shots_per_15min_window=shots_per_15_window,
        shots_baseline_per_15min=shots_per_15_baseline,
        xg_baseline_per_15min=xg_per_15_baseline,
        shot_volume_ratio=ratio,
        hot_streak=hot_streak,
        hot_player=hot_player,
        hot_players=tuple(players),
        tactical_advice=advice,
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="team", subject_id=team_external_id,
        metric="hot_hand",
        value={
            "hot_streak": hot_streak,
            "shots_window": len(window_shots),
            "xg_window": round(xg_window, 4),
            "shot_volume_ratio": ratio,
            "hot_player_id": hot_player.player_external_id if hot_player else None,
            "tactical_advice": advice,
        },
        inputs={
            "current_minute": current_minute,
            "window_min": window_min,
            "baseline_min": baseline_min,
            "thresholds": {
                "hot_shot_ratio": HOT_SHOT_RATIO,
                "hot_shot_abs_min": HOT_SHOT_ABS_MIN,
                "hot_player_min_shots": HOT_PLAYER_MIN_SHOTS,
            },
        },
        formula=(
            "ratio = window_shots_per_15 / baseline_shots_per_15; "
            "hot = window_shots≥3 AND (ratio≥1.6 OR baseline=0)"
        ),
    )
    return EngineResult(value=report, audit=audit)
