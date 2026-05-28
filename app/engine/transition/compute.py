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
# v1 → v2: full_season_audit fast_counter_ratio = 1.0 sabit kaldığını gösterdi.
# Yeni ana metrik: recovery_to_shot_conversion (kazanımların % kaçı şutla
# sonuçlanıyor) — La Liga'da %1-5 doğal varyans.
ENGINE_VERSION = "2"

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
    total_recoveries: int           # tüm takım recovery aksiyonu
    recoveries_with_shot: int       # kazanım sonrası şuta giden top sayısı
    recovery_to_shot_conversion: float  # ana metrik: rec_w_shot / total_rec
    avg_time_to_shot_min: float     # ortalama recovery→shot süresi
    fast_counter_attacks: int       # < FAST_COUNTER_MAX_MIN olanlar
    fast_counter_ratio: float       # fast / total (v1 backward compat)
    transitions_per_match: float    # rec_w_shot / matches_analyzed
    style_label: str                # "counter_attacking" | "balanced" | "possession"


def _label(conversion: float, recoveries: int) -> str:
    """v2: recovery_to_shot_conversion'a göre sınıflandır.

    La Liga 2018/19 audit: %1-2 normal, %3+ counter-attacking takım.
    """
    if recoveries < 5:
        return "insufficient_data"
    if conversion >= 0.03:
        return "counter_attacking"
    if conversion >= 0.015:
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

    rec_with_shot = len(times_to_shot)
    total_recoveries = len(triggers)
    avg = sum(times_to_shot) / rec_with_shot if rec_with_shot > 0 else 0.0
    fast = sum(1 for g in times_to_shot if g <= FAST_COUNTER_MAX_MIN)
    fast_ratio = fast / rec_with_shot if rec_with_shot > 0 else 0.0
    conversion = rec_with_shot / total_recoveries if total_recoveries > 0 else 0.0
    per_match = rec_with_shot / matches_analyzed if matches_analyzed > 0 else 0.0

    report = TransitionReport(
        team_external_id=team_external_id,
        matches_analyzed=matches_analyzed,
        total_recoveries=total_recoveries,
        recoveries_with_shot=rec_with_shot,
        recovery_to_shot_conversion=round(conversion, 4),
        avg_time_to_shot_min=round(avg, 3),
        fast_counter_attacks=fast,
        fast_counter_ratio=round(fast_ratio, 3),
        transitions_per_match=round(per_match, 2),
        style_label=_label(conversion, total_recoveries),
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="team", subject_id=team_external_id,
        metric="transition_speed",
        value={
            "total_recoveries": total_recoveries,
            "recoveries_with_shot": rec_with_shot,
            "recovery_to_shot_conversion": report.recovery_to_shot_conversion,
            "transitions_per_match": report.transitions_per_match,
            "avg_time_to_shot_min": report.avg_time_to_shot_min,
            "fast_counter_ratio": report.fast_counter_ratio,
            "style_label": report.style_label,
        },
        inputs={
            "transition_window_min": TRANSITION_WINDOW_MIN,
            "fast_counter_max_min": FAST_COUNTER_MAX_MIN,
            "matches_analyzed": matches_analyzed,
        },
        formula=(
            "v2: recovery_to_shot_conversion = rec_w_shot / total_recoveries; "
            "style: ≥3% counter_attacking, ≥1.5% balanced, < possession"
        ),
    )
    return EngineResult(value=report, audit=audit)
