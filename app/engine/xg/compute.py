"""xG hesabı — geometrik baseline.

Profesyonel xG modeli logistic regression ister:
    xg = sigmoid(β_dist · distance + β_angle · angle + β_body + β_pattern + ε)

Gerçek katsayı eğitimi shot-level veri lazım (StatsBomb Open / Opta). Bu modül
"veri akışı geldikten sonra logistic'e geçilebilir" iskeleti kuruyor:

- Bugün: literatür-türevi sabit katsayılar (Sumpter 2017, Caley 2014).
  Geometrik distance + angle + body/pattern modifikatörleri ile makul tahmin.
- Yarın: ShotXGModel parametreleri DB cache'inden okunup (predict_ml pattern'i
  gibi) sigmoid'e geçirilebilir.

Output: tek şut için ShotXG (xg + audit), takım için aggregate.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

from app.audit import AuditRecord, EngineResult
from app.domain import Shot

ENGINE_NAME = "engine.xg"
ENGINE_VERSION = "1"

# Saha kanonik: 100x100 normalize; gol (100, 50). Genişlik 100 birim ≈ 68m
# saha; gol post'ları yaklaşık y=46.5 / y=53.5 (genişlik 7m / 68m ≈ %10.3).
GOAL_X = 100.0
GOAL_Y = 50.0
GOAL_POST_HALF = 3.66  # 7.32m / 2, normalize 100/68 ≈ 5.4; literatür 3.66 daha tutarlı

# Literatür-türevi log-odds katsayıları (Caley 2014 + Sumpter 2017 türevi).
# distance birimi: normalize unit (1 = saha genişliğinin %1'i ≈ 0.68m).
_INTERCEPT = -0.5
_BETA_DISTANCE = -0.08
_BETA_ANGLE = 1.8  # radyan
_BODY_MODIFIER = {
    "head": -0.5,
    "right_foot": 0.0, "left_foot": 0.0,
    "other": -0.6,
}
_PATTERN_MODIFIER = {
    "open_play": 0.0,
    "fast_break": 0.4,
    "set_piece": -0.3,
    "corner_kick": -0.4,
    "free_kick": -0.5,
    "penalty": None,  # özel: xG = 0.76 (standart literatür)
}
_PENALTY_XG = 0.76


@dataclass(frozen=True)
class ShotXG:
    """Tek şut için xG değeri + bileşenleri."""
    xg: float
    distance: float
    angle_radians: float
    body_part: str
    pattern: str


@dataclass(frozen=True)
class TeamXGReport:
    """Bir maçtaki takım xG toplamı."""
    team_external_id: int
    shot_count: int
    total_xg: float
    goals_actual: int
    xg_minus_goals: float  # >0 → bekleneneni atamadı (şanssız); <0 → şanslı


def _distance(x: float, y: float) -> float:
    return math.sqrt((GOAL_X - x) ** 2 + (GOAL_Y - y) ** 2)


def _shot_angle(x: float, y: float) -> float:
    """Görünür kale alanı açısı (radyan).

    İki gol direği konumuna olan vektörlerin arasındaki açı. Atış noktası
    kale çizgisi üzerindeyse veya post arkasındaysa 0 dönüyoruz (gol mümkün değil).
    """
    dx = GOAL_X - x
    if dx <= 0:
        return 0.0
    # Üst ve alt post'lara olan açılar
    top = math.atan2(GOAL_Y + GOAL_POST_HALF - y, dx)
    bot = math.atan2(GOAL_Y - GOAL_POST_HALF - y, dx)
    return abs(top - bot)


def _sigmoid(x: float) -> float:
    if x > 35:
        return 1.0
    if x < -35:
        return 0.0
    return 1.0 / (1.0 + math.exp(-x))


def compute_shot_xg(shot: Shot) -> EngineResult[ShotXG]:
    """Tek bir şut için xG."""
    pattern_mod = _PATTERN_MODIFIER.get(shot.pattern, 0.0)
    if shot.pattern == "penalty":
        xg = _PENALTY_XG
        report = ShotXG(
            xg=xg, distance=11.0, angle_radians=math.pi / 2,
            body_part=shot.body_part, pattern="penalty",
        )
    else:
        dist = _distance(shot.x, shot.y)
        ang = _shot_angle(shot.x, shot.y)
        body_mod = _BODY_MODIFIER.get(shot.body_part, 0.0)
        # pattern_mod None olabilir mi? penalty'de evet — yukarıda yakaladık.
        assert pattern_mod is not None
        log_odds = (
            _INTERCEPT
            + _BETA_DISTANCE * dist
            + _BETA_ANGLE * ang
            + body_mod
            + pattern_mod
        )
        xg = round(_sigmoid(log_odds), 4)
        report = ShotXG(
            xg=xg, distance=round(dist, 2),
            angle_radians=round(ang, 4),
            body_part=shot.body_part, pattern=shot.pattern,
        )

    audit = AuditRecord(
        engine=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        subject_type="shot",
        subject_id=shot.match_external_id,  # match-level subject
        metric="shot_xg",
        value={
            "xg": report.xg, "distance": report.distance,
            "angle_radians": report.angle_radians,
            "body_part": report.body_part, "pattern": report.pattern,
        },
        inputs={
            "x": shot.x, "y": shot.y,
            "player_external_id": shot.player_external_id,
            "minute": shot.minute,
        },
        formula=(
            "penalty → 0.76; otherwise sigmoid("
            f"{_INTERCEPT} + {_BETA_DISTANCE}*dist + {_BETA_ANGLE}*angle "
            "+ body_mod + pattern_mod)"
        ),
    )
    return EngineResult(value=report, audit=audit)


def compute_team_xg(
    team_external_id: int,
    shots: Iterable[Shot],
    *,
    goals_actual: int = 0,
) -> EngineResult[TeamXGReport]:
    """Bir maç için takım xG toplamı."""
    total_xg = 0.0
    n = 0
    for shot in shots:
        result = compute_shot_xg(shot)
        total_xg += result.value.xg
        n += 1
    total_xg = round(total_xg, 4)
    report = TeamXGReport(
        team_external_id=team_external_id,
        shot_count=n,
        total_xg=total_xg,
        goals_actual=goals_actual,
        xg_minus_goals=round(total_xg - goals_actual, 4),
    )
    audit = AuditRecord(
        engine=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        subject_type="team",
        subject_id=team_external_id,
        metric="team_xg",
        value={
            "shot_count": n,
            "total_xg": total_xg,
            "goals_actual": goals_actual,
            "xg_minus_goals": report.xg_minus_goals,
        },
        inputs={"shot_count": n, "goals_actual": goals_actual},
        formula="total_xg = sum(compute_shot_xg(shot).value.xg)",
    )
    return EngineResult(value=report, audit=audit)
