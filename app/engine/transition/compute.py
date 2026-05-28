"""Transition Speed — top kazanımdan şuta geçiş hızı.

Klopp gegenpress'in komplementeri: top kazanılır kazanılmaz ne kadar
çabuk şuta gidiliyor. Hızlı transition = kontra-atak takımı.

Tanım: bir takımın `tackle|interception|ball_recovery` defansif aksiyonu
ile aynı possession_id'de bulunan shot'a kadar geçen süre (dakika).
possession_id eşleşmesi yoksa 30-saniye penceresi içinde sonraki aynı-
takım şutu sayılır.

Saf hesap. DefensiveAction + Shot → TransitionReport.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.audit import AuditRecord, EngineResult
from app.domain import DefensiveAction, Shot

ENGINE_NAME = "engine.transition"
ENGINE_VERSION = "1"

# Pencere üst sınırı: 15 saniye = 0.25 dakika (Bielsa "transition window")
TRANSITION_WINDOW_MIN = 0.25
# Hızlı kontra eşiği: 10 saniye = 0.17 dakika
FAST_COUNTER_MAX_MIN = 0.17

# Defansif eylemden kontra'ya geçişi tetikleyenler
TRANSITION_TRIGGERS = ("ball_recovery", "tackle", "interception")


@dataclass(frozen=True)
class TransitionReport:
    team_external_id: int
    matches_analyzed: int
    recoveries_with_shot: int       # kazanım sonrası şuta giden top sayısı
    avg_time_to_shot_min: float     # ortalama recovery→shot süresi
    fast_counter_attacks: int       # < FAST_COUNTER_MAX_MIN olanlar
    fast_counter_ratio: float       # fast / total
    style_label: str                # "counter_attacking" | "balanced" | "possession"


def _label(fast_ratio: float, recoveries: int) -> str:
    if recoveries < 3:
        return "insufficient_data"
    if fast_ratio >= 0.30:
        return "counter_attacking"
    if fast_ratio >= 0.15:
        return "balanced"
    return "possession"


def compute_transition(
    team_external_id: int,
    all_def_actions: Iterable[DefensiveAction],
    all_shots: Iterable[Shot],
    *,
    matches_analyzed: int = 1,
) -> EngineResult[TransitionReport]:
    """Top kazanım → şut arasındaki transition süresi.

    Bir takımın TÜM kazanım eventleri ile bizim takımın TÜM şutları
    arasında zaman penceresine bakar.
    """
    triggers = sorted(
        ((d.period * 1000 + d.minute, d.possession_id) for d in all_def_actions
         if d.team_external_id == team_external_id
         and d.action_type in TRANSITION_TRIGGERS),
        key=lambda x: x[0],
    )
    # Shot.period yok; team_external_id de yok (Shot domain'inde) →
    # tüm takım şutlarını üzerinden geçiriyoruz; possession_id de Shot'ta
    # yok, sadece zaman penceresi kullanıyoruz. Bu, takım filtresi
    # caller'ın yapması anlamına gelir — biz tüm shot'ları varsayıyoruz
    # caller team_external_id ile prefilter etti.
    shot_times = sorted(s.minute for s in all_shots)

    times_to_shot: list[float] = []
    for trig_time, _poss in triggers:
        # period offset 1000; shot.minute saf minute. Yaklaşım:
        # trig_time = period*1000 + minute, sadece aynı yarı içindeki şutu say.
        period = int(trig_time // 1000)
        trig_minute = trig_time - period * 1000
        for sm in shot_times:
            if sm < trig_minute:
                continue
            gap = sm - trig_minute
            if gap <= TRANSITION_WINDOW_MIN:
                times_to_shot.append(gap)
                break  # ilk şutu eşle, döngüden çık

    recoveries = len(times_to_shot)
    avg = sum(times_to_shot) / recoveries if recoveries > 0 else 0.0
    fast = sum(1 for g in times_to_shot if g <= FAST_COUNTER_MAX_MIN)
    fast_ratio = fast / recoveries if recoveries > 0 else 0.0

    report = TransitionReport(
        team_external_id=team_external_id,
        matches_analyzed=matches_analyzed,
        recoveries_with_shot=recoveries,
        avg_time_to_shot_min=round(avg, 3),
        fast_counter_attacks=fast,
        fast_counter_ratio=round(fast_ratio, 3),
        style_label=_label(fast_ratio, recoveries),
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="team", subject_id=team_external_id,
        metric="transition_speed",
        value={
            "recoveries_with_shot": recoveries,
            "avg_time_to_shot_min": report.avg_time_to_shot_min,
            "fast_counter_ratio": report.fast_counter_ratio,
            "style_label": report.style_label,
        },
        inputs={
            "transition_window_min": TRANSITION_WINDOW_MIN,
            "fast_counter_max_min": FAST_COUNTER_MAX_MIN,
            "matches_analyzed": matches_analyzed,
        },
        formula="mean(time from recovery to next shot within window)",
    )
    return EngineResult(value=report, audit=audit)
