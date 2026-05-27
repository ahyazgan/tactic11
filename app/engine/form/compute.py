"""Form analizi — son N maçtaki sonuçlar, gol farkı, ev/deplasman ayrımı,
clean sheet'ler, momentum.

**v3 → v4:** opsiyonel zaman ağırlığı (`time_decay_rate`). Eski maçlar yeni
maçlardan daha az sayar; `goals_for_per_match` ve `goals_against_per_match`
zaman-ağırlıklı ortalamaya döner. Diğer alanlar (W/D/L, points, ppg, raw
totals) ham sayım kalır — kalite eşikleri (dominant, close) ve momentum
zaten kendi zaman semantiğini taşıyor.

Decay formülü (lineer üs):
    w_i = exp(-rate · days_old_i)

`rate=0` (default) → uniform ağırlık, geriye uyumlu. Tipik rate: 0.0077
(~90 gün half-life), 0.023 (~30 gün), 0.069 (~10 gün). Referans zaman
penceredeki en yeni maçın kickoff'u (deterministik; çağrı anına bağlı değil).

SAF FONKSİYON: girdi `Iterable[MatchLike]`, çıktı `EngineResult[FormReport]`.
DB/API'ye dokunmaz. Maç tamamlandı sayılan statüler `sports/football.py`'den
gelir.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from typing import Literal

from app.audit import AuditRecord, EngineResult
from app.engine._protocols import MatchLike
from app.sports import football

ENGINE_NAME = "engine.form"
ENGINE_VERSION = "4"  # v3 → v4: opsiyonel time_decay_rate (gf/ga per_match)

# Kalite eşikleri — "dominant" / "close" subjektif değil, sayıyla tanımlı.
_DOMINANT_MARGIN = 2  # 2+ gol farkıyla kazandıysa "dominant"
_CLOSE_MARGIN = 1     # 1 gol farkıyla kaybettiyse "close"

# Momentum için "yakın geçmiş" eşiği — son 3 maçın ppg'sini ayrı hesapla.
_RECENT_WINDOW = 3

Outcome = Literal["W", "D", "L"]


@dataclass(frozen=True)
class FormReport:
    matches_played: int
    wins: int
    draws: int
    losses: int
    goals_for: int
    goals_against: int
    goal_diff: int
    points: int
    points_per_game: float
    home_wins: int
    home_draws: int
    home_losses: int
    away_wins: int
    away_draws: int
    away_losses: int
    last_results: list[Outcome]

    # v2 eklemeleri
    clean_sheets: int  # rakipsiz tutulan maç (GA=0)
    goals_for_per_match: float
    goals_against_per_match: float
    recent_ppg: float  # son min(_RECENT_WINDOW, N) maç ppg'si
    momentum: float  # recent_ppg - older_ppg; pozitif=yükseliyor
    current_streak: int  # arda arda son N maç W/L olarak; pozitif=galibiyet
    current_unbeaten: int  # ardarda W veya D sayısı (son maçtan geriye)

    # v3 eklemeleri — galibiyet/mağlubiyet kalitesi sinyalleri
    dominant_wins: int  # >=2 gol farkıyla kazanılan
    close_losses: int   # 1 gol farkıyla kaybedilen
    failed_to_score: int  # GF=0 olan maç sayısı
    scoring_rate: float  # gol attığı maçların oranı (0..1)


def _outcome_for(team_id: int, match: MatchLike) -> Outcome:
    is_home = match.home_team_external_id == team_id
    gf = match.home_score if is_home else match.away_score
    ga = match.away_score if is_home else match.home_score
    assert gf is not None and ga is not None  # finished maçlarda garanti
    if gf > ga:
        return "W"
    if gf < ga:
        return "L"
    return "D"


def _calc_streaks(last_results: list[Outcome]) -> tuple[int, int]:
    """`last_results` yeniden eskiye: ilk eleman son maç.

    current_streak: son maç W ise +ardışık W sayısı, L ise -ardışık L sayısı,
                    D ise 0.
    current_unbeaten: D dahil ardışık "yenilmedi" sayısı.
    """
    if not last_results:
        return 0, 0
    streak = 0
    unbeaten = 0
    first = last_results[0]
    if first == "W":
        for r in last_results:
            if r == "W":
                streak += 1
            else:
                break
    elif first == "L":
        for r in last_results:
            if r == "L":
                streak -= 1
            else:
                break
    # D ise streak=0 (kasıtlı)
    for r in last_results:
        if r != "L":
            unbeaten += 1
        else:
            break
    return streak, unbeaten


def compute_form(
    team_external_id: int,
    matches: Iterable[MatchLike],
    *,
    last_n: int = 5,
    time_decay_rate: float = 0.0,
) -> EngineResult[FormReport]:
    """Bir takımın son N tamamlanmış maçındaki form raporu.

    `time_decay_rate > 0` → `goals_for_per_match` ve `goals_against_per_match`
    zaman-ağırlıklı (exp(-rate · days_old), referans = pencerenin en yeni
    maçı). Diğer alanlar (W/D/L, points, raw totals) ham sayım kalır.
    `rate=0` (default) tamamen geriye uyumlu.
    """
    if last_n <= 0:
        raise ValueError("last_n > 0 olmalı")
    if time_decay_rate < 0:
        raise ValueError("time_decay_rate >= 0 olmalı")

    team_matches = [
        m
        for m in matches
        if m.status in football.FINISHED_STATUSES
        and m.home_score is not None
        and m.away_score is not None
        and team_external_id in (m.home_team_external_id, m.away_team_external_id)
    ]
    team_matches.sort(key=lambda m: m.kickoff, reverse=True)
    window = team_matches[:last_n]

    # Zaman ağırlığı: referans = pencerenin en yeni maçı (deterministik,
    # çağrı anına bağlı değil). Decay yoksa weight=1.0 — eski yola eşdeğer.
    if window and time_decay_rate > 0:
        ref_kickoff = window[0].kickoff
        weights = [
            math.exp(-time_decay_rate * max(0.0, (ref_kickoff - m.kickoff).total_seconds() / 86400))
            for m in window
        ]
    else:
        weights = [1.0] * len(window)

    wins = draws = losses = 0
    home_w = home_d = home_l = 0
    away_w = away_d = away_l = 0
    gf_total = ga_total = 0
    clean_sheets = 0
    dominant_wins = 0
    close_losses = 0
    failed_to_score = 0
    matches_with_goal = 0
    last_results: list[Outcome] = []
    recent_points = 0
    recent_count = 0

    # gf/ga için weighted toplamlar — per_match averages için sum_w'a böleceğiz
    weighted_gf = 0.0
    weighted_ga = 0.0
    sum_w = 0.0

    for idx, m in enumerate(window):
        is_home = m.home_team_external_id == team_external_id
        gf = m.home_score if is_home else m.away_score
        ga = m.away_score if is_home else m.home_score
        assert gf is not None and ga is not None  # filter ile garantili
        gf_total += gf
        ga_total += ga
        w = weights[idx]
        weighted_gf += w * gf
        weighted_ga += w * ga
        sum_w += w
        if ga == 0:
            clean_sheets += 1
        if gf == 0:
            failed_to_score += 1
        else:
            matches_with_goal += 1
        margin = gf - ga

        outcome = _outcome_for(team_external_id, m)
        if outcome == "W" and margin >= _DOMINANT_MARGIN:
            dominant_wins += 1
        elif outcome == "L" and -margin <= _CLOSE_MARGIN:
            close_losses += 1

        last_results.append(outcome)
        pts = 3 if outcome == "W" else (1 if outcome == "D" else 0)
        if idx < _RECENT_WINDOW:
            recent_points += pts
            recent_count += 1

        if outcome == "W":
            wins += 1
            if is_home:
                home_w += 1
            else:
                away_w += 1
        elif outcome == "D":
            draws += 1
            if is_home:
                home_d += 1
            else:
                away_d += 1
        else:
            losses += 1
            if is_home:
                home_l += 1
            else:
                away_l += 1

    played = len(window)
    points = wins * 3 + draws
    ppg = points / played if played else 0.0
    recent_ppg = recent_points / recent_count if recent_count else 0.0

    # older = "recent" dışı kalan kısım; yoksa momentum 0
    older_played = played - recent_count
    older_points = points - recent_points
    older_ppg = older_points / older_played if older_played else recent_ppg
    momentum = recent_ppg - older_ppg

    current_streak, current_unbeaten = _calc_streaks(last_results)

    scoring_rate = matches_with_goal / played if played else 0.0
    # per_match: rate>0 ise zaman-ağırlıklı; rate=0 ise sum_w == played ve
    # weighted toplamlar raw totals'a eşit (geriye uyumlu)
    gf_per_match = weighted_gf / sum_w if sum_w else 0.0
    ga_per_match = weighted_ga / sum_w if sum_w else 0.0
    report = FormReport(
        matches_played=played,
        wins=wins,
        draws=draws,
        losses=losses,
        goals_for=gf_total,
        goals_against=ga_total,
        goal_diff=gf_total - ga_total,
        points=points,
        points_per_game=round(ppg, 3),
        home_wins=home_w,
        home_draws=home_d,
        home_losses=home_l,
        away_wins=away_w,
        away_draws=away_d,
        away_losses=away_l,
        last_results=last_results,
        clean_sheets=clean_sheets,
        goals_for_per_match=round(gf_per_match, 3),
        goals_against_per_match=round(ga_per_match, 3),
        recent_ppg=round(recent_ppg, 3),
        momentum=round(momentum, 3),
        current_streak=current_streak,
        current_unbeaten=current_unbeaten,
        dominant_wins=dominant_wins,
        close_losses=close_losses,
        failed_to_score=failed_to_score,
        scoring_rate=round(scoring_rate, 3),
    )

    decay_formula = (
        " gf_per_match ve ga_per_match Σ(w_i·g_i)/Σ(w_i) zaman-ağırlıklı; "
        f"w_i = exp(-{time_decay_rate}·days_old), referans = pencerenin en yeni maçı."
        if time_decay_rate > 0 else ""
    )
    audit = AuditRecord(
        engine=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        subject_type="team",
        subject_id=team_external_id,
        metric="form_report",
        value=asdict(report),
        inputs={
            "last_n": last_n,
            "recent_window": _RECENT_WINDOW,
            "time_decay_rate": time_decay_rate,
            "considered_match_ids": [m.external_id for m in window],
        },
        formula=(
            f"W=3, D=1, L=0; ppg=points/N; recent_ppg=points of last {_RECENT_WINDOW}/min(N,{_RECENT_WINDOW}); "
            "momentum=recent_ppg-older_ppg; clean_sheet=rakipsiz; "
            "current_streak=son maçtan ardışık W (+) veya L (-), D=0; "
            f"dominant=margin>={_DOMINANT_MARGIN} W; close_loss=margin<={_CLOSE_MARGIN} L; "
            "scoring_rate=gol attığı maç oranı." + decay_formula
        ),
    )
    return EngineResult(value=report, audit=audit)
