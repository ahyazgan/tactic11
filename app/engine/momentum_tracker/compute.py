"""Momentum Tracker — maç içi an yakalama (Faz 6 #1, #2, #3).

Üç canlı sinyal:
1. Momentum meter: son N dk pencere içinde iki takımın xT/şut/possession
   dalgası → kim baskı kuruyor
2. Pres kırılma: bizim defansif aksiyon yoğunluğu aniden düştü mü
   (orta saha geçiliyor)
3. xG swing: kısa pencerede rakibin xG'si patladı mı

Saf hesap. Event listesi + current_minute + window → momentum raporu.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.audit import AuditRecord, EngineResult
from app.domain import DefensiveAction, PassEvent, Shot
from app.engine.xt import xt_value_at

ENGINE_NAME = "engine.momentum_tracker"
ENGINE_VERSION = "1"

# Momentum penceresi (dakika)
MOMENTUM_WINDOW_MIN = 10.0
# Pres kırılma: window'da defansif aksiyon önceki window'a göre %40+ düştü
PRESS_DROP_THRESHOLD = 0.40
# xG swing: rakip window xG'si bizimkinin 2x'i + mutlak 0.5+
XG_SWING_RATIO = 2.0
XG_SWING_ABS = 0.5


@dataclass(frozen=True)
class MomentumReport:
    team_external_id: int
    opponent_external_id: int
    current_minute: float
    window_min: float
    # Momentum meter (-1 rakip baskın .. +1 biz baskın)
    momentum_score: float
    momentum_holder: str        # "us" | "opponent" | "balanced"
    our_window_xt: float
    opp_window_xt: float
    our_window_shots: int
    opp_window_shots: int
    # Pres kırılma
    press_breaking: bool
    press_drop_pct: float
    # xG swing
    xg_swing_alert: bool
    alert_text: str             # canlı bildirim


def _shot_xg_proxy(s: Shot) -> float:
    dx = 100.0 - s.x
    dy = 50.0 - s.y
    dist = (dx * dx + dy * dy) ** 0.5
    if dist <= 5.0:
        return 0.55
    if dist <= 12.0:
        return 0.25
    if dist <= 20.0:
        return 0.10
    if dist <= 30.0:
        return 0.04
    return 0.01


def _window_xt(passes: list[PassEvent], team_id: int) -> float:
    total = 0.0
    for p in passes:
        if p.team_external_id == team_id and p.completed:
            total += max(0.0, xt_value_at(p.end_x, p.end_y) - xt_value_at(p.start_x, p.start_y))
    return total


def compute_momentum(
    team_external_id: int,
    opponent_external_id: int,
    all_passes: Iterable[PassEvent],
    all_def_actions: Iterable[DefensiveAction],
    all_shots: Iterable[Shot],
    *,
    current_minute: float,
    window_min: float = MOMENTUM_WINDOW_MIN,
) -> EngineResult[MomentumReport]:
    """Canlı momentum + pres kırılma + xG swing."""
    passes = list(all_passes)
    defs = list(all_def_actions)
    shots = list(all_shots)

    win_start = current_minute - window_min
    prev_start = current_minute - 2 * window_min

    def _in(minute: float, lo: float, hi: float) -> bool:
        return lo <= minute < hi

    # Mevcut pencere
    win_passes = [p for p in passes if _in(p.minute, win_start, current_minute)]
    our_xt = _window_xt(win_passes, team_external_id)
    opp_xt = _window_xt(win_passes, opponent_external_id)
    our_shots = sum(1 for s in shots
                    if _in(s.minute, win_start, current_minute)
                    and (s.team_external_id is None
                         or s.team_external_id == team_external_id))
    opp_shots = sum(1 for s in shots
                    if _in(s.minute, win_start, current_minute)
                    and s.team_external_id == opponent_external_id)
    our_pass_n = sum(1 for p in win_passes if p.team_external_id == team_external_id)
    opp_pass_n = sum(1 for p in win_passes if p.team_external_id == opponent_external_id)

    # Momentum score: xT + şut + possession bileşeni, -1..+1 normalize
    xt_diff = our_xt - opp_xt
    shot_diff = our_shots - opp_shots
    poss_diff = (
        (our_pass_n - opp_pass_n) / (our_pass_n + opp_pass_n)
        if (our_pass_n + opp_pass_n) else 0.0
    )
    raw = xt_diff * 2 + shot_diff * 0.3 + poss_diff
    momentum = round(max(-1.0, min(1.0, raw)), 3)
    holder = "us" if momentum > 0.2 else "opponent" if momentum < -0.2 else "balanced"

    # Pres kırılma: bizim defansif aksiyon prev → win düşüşü
    prev_our_def = sum(1 for d in defs
                       if d.team_external_id == team_external_id
                       and _in(d.minute, prev_start, win_start))
    win_our_def = sum(1 for d in defs
                      if d.team_external_id == team_external_id
                      and _in(d.minute, win_start, current_minute))
    press_drop = (
        (prev_our_def - win_our_def) / prev_our_def
        if prev_our_def > 0 else 0.0
    )
    press_breaking = press_drop >= PRESS_DROP_THRESHOLD

    # xG swing: rakibin window xG'si
    our_xg = sum(_shot_xg_proxy(s) for s in shots
                 if _in(s.minute, win_start, current_minute)
                 and (s.team_external_id is None
                      or s.team_external_id == team_external_id))
    opp_xg = sum(_shot_xg_proxy(s) for s in shots
                 if _in(s.minute, win_start, current_minute)
                 and s.team_external_id == opponent_external_id)
    xg_swing = (opp_xg >= XG_SWING_ABS and opp_xg >= our_xg * XG_SWING_RATIO)

    # Alert
    parts: list[str] = []
    if holder == "opponent":
        parts.append("Rakip baskı kuruyor")
    elif holder == "us":
        parts.append("Momentum bizde")
    if press_breaking:
        parts.append(f"PRES KIRILDI (def %{int(press_drop*100)} düştü)")
    if xg_swing:
        parts.append(f"xG swing — rakip {opp_xg:.2f} xG (gol riski)")
    alert = "; ".join(parts) if parts else "Denge korunuyor"

    report = MomentumReport(
        team_external_id=team_external_id,
        opponent_external_id=opponent_external_id,
        current_minute=current_minute,
        window_min=window_min,
        momentum_score=momentum,
        momentum_holder=holder,
        our_window_xt=round(our_xt, 3),
        opp_window_xt=round(opp_xt, 3),
        our_window_shots=our_shots,
        opp_window_shots=opp_shots,
        press_breaking=press_breaking,
        press_drop_pct=round(press_drop, 3),
        xg_swing_alert=xg_swing,
        alert_text=alert,
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="match", subject_id=team_external_id,
        metric="momentum",
        value={
            "momentum_score": momentum, "momentum_holder": holder,
            "press_breaking": press_breaking, "xg_swing_alert": xg_swing,
            "alert_text": alert,
        },
        inputs={
            "current_minute": current_minute, "window_min": window_min,
            "press_drop_threshold": PRESS_DROP_THRESHOLD,
            "opponent_external_id": opponent_external_id,
        },
        formula="momentum = xT_diff×2 + shot_diff×0.3 + poss_diff; press_drop + xG swing flags",
    )
    return EngineResult(value=report, audit=audit)
