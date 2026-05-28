"""Expected Threat (xT) — Karun Singh 2019 modeli.

Saha 12×8 zone grid'e bölünür. Her zone için "buradan gol olma olasılığı"
(threat value) hesaplanır. Bir pas/dribble zone A'dan zone B'ye giderse,
threat eklenir/azaltır: `xT_added = T[B] - T[A]` (eğer pas tamamlandıysa).

Önceden hesaplanmış threat values — Karun Singh blog'unda yayınlanan
literatür değerleri (Opta event verisi üzerinde train edilmiş, public).
12 row (x), 8 col (y). x=0 defansif kale, x=11 hücum kalesi.

Saf hesap — DB/HTTP yok. PassEvent / Carry listesinden agregat hesaplar.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.audit import AuditRecord, EngineResult
from app.domain import Carry, PassEvent

ENGINE_NAME = "engine.xt"
ENGINE_VERSION = "1"

# Pitch grid: 12 columns (x: defansif → hücum), 8 rows (y: top → bot)
GRID_X = 12
GRID_Y = 8

# Karun Singh's published xT matrix (12×8) — Opta verisinde train edilmiş.
# Kaynak: https://karun.in/blog/expected-threat.html (2019)
# Her hücre: o zone'dan gol olma olasılığı (0..1).
# Defansif zone'da ~0; hücum kale önünde ~0.5+.
# [x_idx (0=defansif kale, 11=hücum kalesi)][y_idx (0=top, 7=bot)]
XT_MATRIX: tuple[tuple[float, ...], ...] = (
    # x=0 (defansif kale önü — kendi sahamız)
    (0.006, 0.008, 0.009, 0.010, 0.010, 0.009, 0.008, 0.006),
    # x=1
    (0.008, 0.010, 0.012, 0.014, 0.014, 0.012, 0.010, 0.008),
    # x=2
    (0.010, 0.013, 0.016, 0.018, 0.018, 0.016, 0.013, 0.010),
    # x=3
    (0.013, 0.017, 0.021, 0.024, 0.024, 0.021, 0.017, 0.013),
    # x=4 (orta saha başı)
    (0.017, 0.022, 0.027, 0.031, 0.031, 0.027, 0.022, 0.017),
    # x=5
    (0.022, 0.029, 0.036, 0.041, 0.041, 0.036, 0.029, 0.022),
    # x=6 (orta saha sonu / hücum başı)
    (0.029, 0.038, 0.048, 0.055, 0.055, 0.048, 0.038, 0.029),
    # x=7
    (0.038, 0.050, 0.063, 0.073, 0.073, 0.063, 0.050, 0.038),
    # x=8 (final third girişi)
    (0.050, 0.066, 0.084, 0.098, 0.098, 0.084, 0.066, 0.050),
    # x=9 (final third)
    (0.066, 0.088, 0.114, 0.137, 0.137, 0.114, 0.088, 0.066),
    # x=10 (kale önü)
    (0.085, 0.118, 0.165, 0.218, 0.218, 0.165, 0.118, 0.085),
    # x=11 (kale içi — penaltı noktası civarı)
    (0.105, 0.155, 0.270, 0.510, 0.510, 0.270, 0.155, 0.105),
)


@dataclass(frozen=True)
class PlayerXTReport:
    """Bir oyuncunun xT katkısı (toplam + per-90)."""
    player_external_id: int
    minutes: int  # ne kadar oynadı (per-90 için)
    xt_added: float       # Σ pozitif xT artışları (tamamlanan paslar/carry'ler)
    xt_lost: float        # Σ kayıp paslarda yitirilen xT
    xt_net: float         # xt_added - xt_lost
    actions: int          # toplam pas + carry sayısı
    xt_per_90: float


@dataclass(frozen=True)
class TeamXTReport:
    team_external_id: int
    minutes: int  # tipik 90
    total_xt: float
    actions: int


def _xy_to_zone(x: float, y: float) -> tuple[int, int]:
    """100×100 koordinat → (x_idx, y_idx) 12×8 grid'de.

    x_idx: 0 (defansif) → 11 (hücum). y_idx: 0 (top) → 7 (bot).
    """
    xi = min(GRID_X - 1, max(0, int(x / 100.0 * GRID_X)))
    yi = min(GRID_Y - 1, max(0, int(y / 100.0 * GRID_Y)))
    return xi, yi


def xt_value_at(x: float, y: float) -> float:
    xi, yi = _xy_to_zone(x, y)
    return XT_MATRIX[xi][yi]


def _action_xt(
    start_x: float, start_y: float,
    end_x: float, end_y: float,
    completed: bool,
) -> float:
    """Bir aksiyonun xT katkısı.

    Tamamlanmış pas/carry → end zone xT - start zone xT (pozitifse threat eklendi)
    Tamamlanmamış pas → -start zone xT (threat kaybedildi)
    """
    if completed:
        return xt_value_at(end_x, end_y) - xt_value_at(start_x, start_y)
    return -xt_value_at(start_x, start_y)


def compute_player_xt(
    player_external_id: int,
    passes: Iterable[PassEvent],
    carries: Iterable[Carry],
    *,
    minutes_played: int = 90,
) -> EngineResult[PlayerXTReport]:
    """Bir oyuncunun pas + carry kombinasyonundan xT katkısı."""
    xt_added = 0.0
    xt_lost = 0.0
    actions = 0
    for p in passes:
        if p.player_external_id != player_external_id:
            continue
        actions += 1
        delta = _action_xt(p.start_x, p.start_y, p.end_x, p.end_y, p.completed)
        if delta > 0:
            xt_added += delta
        else:
            xt_lost += abs(delta)
    for c in carries:
        if c.player_external_id != player_external_id:
            continue
        actions += 1
        # Carry tamamlandı varsayımı (StatsBomb carry'leri zaten "tamamlanan" sayılır)
        delta = _action_xt(c.start_x, c.start_y, c.end_x, c.end_y, True)
        if delta > 0:
            xt_added += delta
        # Carry kayıp olmaz (ardından gelen bir loss event olsa bile ayrı sayılır)

    xt_net = xt_added - xt_lost
    per_90 = (xt_net / max(1, minutes_played)) * 90.0

    report = PlayerXTReport(
        player_external_id=player_external_id,
        minutes=minutes_played,
        xt_added=round(xt_added, 4),
        xt_lost=round(xt_lost, 4),
        xt_net=round(xt_net, 4),
        actions=actions,
        xt_per_90=round(per_90, 4),
    )
    audit = AuditRecord(
        engine=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        subject_type="player",
        subject_id=player_external_id,
        metric="player_xt",
        value={
            "xt_added": report.xt_added,
            "xt_lost": report.xt_lost,
            "xt_net": report.xt_net,
            "actions": report.actions,
            "xt_per_90": report.xt_per_90,
            "minutes": report.minutes,
        },
        inputs={
            "grid_x": GRID_X, "grid_y": GRID_Y,
            "xt_matrix_max": max(max(row) for row in XT_MATRIX),
        },
        formula=(
            "completed pass/carry: xT_added += max(0, T[end] - T[start]); "
            "incomplete pass: xT_lost += T[start]; "
            "T[zone] = Karun Singh 2019 12x8 matrix"
        ),
    )
    return EngineResult(value=report, audit=audit)


def compute_team_xt(
    team_external_id: int,
    passes: Iterable[PassEvent],
    carries: Iterable[Carry],
    *,
    minutes_played: int = 90,
) -> EngineResult[TeamXTReport]:
    """Takım toplam xT — oyuncularının agregatı."""
    total = 0.0
    actions = 0
    for p in passes:
        if p.team_external_id != team_external_id:
            continue
        actions += 1
        delta = _action_xt(p.start_x, p.start_y, p.end_x, p.end_y, p.completed)
        total += delta if p.completed else delta  # negative when incomplete
    for c in carries:
        if c.team_external_id != team_external_id:
            continue
        actions += 1
        delta = _action_xt(c.start_x, c.start_y, c.end_x, c.end_y, True)
        if delta > 0:
            total += delta
    report = TeamXTReport(
        team_external_id=team_external_id,
        minutes=minutes_played,
        total_xt=round(total, 4),
        actions=actions,
    )
    audit = AuditRecord(
        engine=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        subject_type="team",
        subject_id=team_external_id,
        metric="team_xt",
        value={"total_xt": report.total_xt, "actions": report.actions, "minutes": report.minutes},
        inputs={"grid_x": GRID_X, "grid_y": GRID_Y},
        formula="sum of player xT deltas, team-filtered",
    )
    return EngineResult(value=report, audit=audit)
