"""Pressing Trigger — top kaybından sonra geri-kazanım süresi.

Klopp-Bielsa gegenpress kavramı: takım topu kaybeder kaybetmez X saniye
içinde top tekrar kazanılmaya çalışılır (6-saniye kuralı).

Tanım: bir takımın `ball_recovery|tackle|interception` ile sonuçlanan
top-kazanım eventlerinin, son rakip-defansif-aksiyondan (yani son top
kaybından) sonra geçen ortalama süresi (dakika cinsinden).

Düşük süre (~6-10 sn → 0.10-0.17 dk) = yoğun gegenpress.
Yüksek süre = top kaybedince geri çekilen savunma.

Saf hesap; minute-based zaman çözünürlüğü ile yaklaşık.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.audit import AuditRecord, EngineResult
from app.domain import DefensiveAction, PassEvent

ENGINE_NAME = "engine.pressing_trigger"
ENGINE_VERSION = "1"

# 6-saniye kuralı = 0.10 dakika; ortalama bu değerin altında ise "high press"
HIGH_PRESS_THRESHOLD_MIN = 0.15  # 9 saniye

# Recovery sayılan aksiyon tipleri
RECOVERY_ACTIONS = ("ball_recovery", "tackle", "interception")


@dataclass(frozen=True)
class PressingTriggerReport:
    team_external_id: int
    matches_analyzed: int
    recoveries: int                 # toplam top-kazanım sayısı
    avg_recovery_time_min: float    # rakip son aksiyonundan ortalama süre
    fast_recoveries: int            # < HIGH_PRESS_THRESHOLD süresinde olanlar
    fast_recovery_ratio: float      # fast / total
    style_label: str                # "gegenpress" | "mid_press" | "low_block"


def _label(avg_min: float) -> str:
    if avg_min <= HIGH_PRESS_THRESHOLD_MIN:
        return "gegenpress"
    if avg_min <= 0.40:  # 24 saniye
        return "mid_press"
    return "low_block"


def compute_pressing_trigger(
    team_external_id: int,
    all_passes: Iterable[PassEvent],
    all_def_actions: Iterable[DefensiveAction],
    *,
    matches_analyzed: int = 1,
) -> EngineResult[PressingTriggerReport]:
    """Top kazanım sonrası gegenpress tetikleme süresi.

    Algoritma: zaman sırasıyla tüm eventleri taradık. Bizim takımdan rakibe
    geçiş anlarını (top kaybı = rakip ball_recovery/interception veya
    bizim pasımız başarısız) tespit et; sonraki bizim kazanımımıza kadar
    geçen süreyi ölç.
    """
    passes = list(all_passes)
    defs = list(all_def_actions)

    # Sırala: önce period, sonra minute
    events: list[tuple[float, str, int, bool]] = []
    # (sort_time, kind, team_id, is_loss_or_recovery_flag)
    for p in passes:
        t = p.period * 1000 + p.minute  # period offsets
        events.append((t, "pass", p.team_external_id, p.completed))
    for d in defs:
        t = d.period * 1000 + d.minute
        events.append((t, "def", d.team_external_id, d.action_type in RECOVERY_ACTIONS))
    events.sort(key=lambda e: e[0])

    recovery_gaps: list[float] = []
    last_loss_time: float | None = None

    for t, kind, team, flag in events:
        if team == team_external_id:
            # Top bizde — eğer kazanım eventi ise ve önceki kayıp varsa gap ölç
            if kind == "def" and flag and last_loss_time is not None:
                gap = t - last_loss_time
                # Aynı yarı içinde kazanım (period offset farklıysa atla)
                if 0.0 <= gap <= 5.0:  # 5 dk üst sınır (çok uzaksa kazanım sayma)
                    recovery_gaps.append(gap)
                last_loss_time = None
            elif kind == "pass" and not flag:
                # Kendi pasımız başarısız → top kaybı
                last_loss_time = t
        else:
            # Rakibin eventi — eğer ilk rakip eventi ise loss timing zaten dolu
            # Rakip kazanım gibi davranan event (def + recovery) bizden top alındı demek
            if kind == "def" and flag:
                last_loss_time = t

    recoveries = len(recovery_gaps)
    avg = sum(recovery_gaps) / recoveries if recoveries > 0 else 0.0
    fast = sum(1 for g in recovery_gaps if g < HIGH_PRESS_THRESHOLD_MIN)
    fast_ratio = fast / recoveries if recoveries > 0 else 0.0

    report = PressingTriggerReport(
        team_external_id=team_external_id,
        matches_analyzed=matches_analyzed,
        recoveries=recoveries,
        avg_recovery_time_min=round(avg, 3),
        fast_recoveries=fast,
        fast_recovery_ratio=round(fast_ratio, 3),
        style_label=_label(avg) if recoveries > 0 else "insufficient_data",
    )
    audit = AuditRecord(
        engine=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        subject_type="team",
        subject_id=team_external_id,
        metric="pressing_trigger",
        value={
            "recoveries": recoveries,
            "avg_recovery_time_min": report.avg_recovery_time_min,
            "fast_recovery_ratio": report.fast_recovery_ratio,
            "style_label": report.style_label,
        },
        inputs={
            "high_press_threshold_min": HIGH_PRESS_THRESHOLD_MIN,
            "matches_analyzed": matches_analyzed,
        },
        formula="mean(recovery_time after own ball-loss); label by avg vs threshold",
    )
    return EngineResult(value=report, audit=audit)
