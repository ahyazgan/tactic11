"""Live Substitution Recommendation — maç esnasında oyuncu değişikliği önerisi.

Tanım: maçın belirli bir dakikasında, takımın event akışından + skor durumundan
+ oyuncu fatigue sinyallerinden ranked sub recommendation üret.

Skorlama:
- fatigue_score (50% ağırlık)
- pass_completion_recent (20%) — son 10 dk pas tamamlama
- score_state_pressure (15%) — geride gidiyorsak hücum oyuncusu sub'ı daha urgent
- minute (15%) — geç dakikada her sub'ın aciliyeti artar

Çıktı: top 3 sub önerisi + neden + confidence.

Pure-compute. PassEvent + DefensiveAction + current_minute + score_state input.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from app.audit import AuditRecord, EngineResult
from app.domain import DefensiveAction, PassEvent
from app.engine.fatigue_signal import compute_fatigue_signal

ENGINE_NAME = "engine.live_sub_recommendation"
ENGINE_VERSION = "1"

ScoreState = Literal["winning", "drawing", "losing"]

# Window: "son 10 dk" yaklaşımı
RECENT_WINDOW_MIN = 10.0
# Sub urgency thresholds
HIGH_URGENCY_SCORE = 0.55
MEDIUM_URGENCY_SCORE = 0.30


@dataclass(frozen=True)
class SubRecommendation:
    player_external_id: int
    urgency_score: float          # 0..1
    urgency_label: str            # "high" | "medium" | "low"
    reasons: tuple[str, ...]      # human-readable Türkçe nedenler
    fatigue_score: float
    recent_pass_completion: float


@dataclass(frozen=True)
class LiveSubReport:
    team_external_id: int
    current_minute: float
    score_state: str
    recommendations: tuple[SubRecommendation, ...]  # top 3 (ranked)


def _score_state_weight(state: str, position_hint: str | None = None) -> float:
    """Skor durumuna göre acilik çarpanı. Position hint varsa hücum/savunma
    oyuncusuna farklı ağırlık (basit: geride → hücum, önde → savunma)."""
    if state == "losing":
        return 1.15  # toplam aciliyet artar
    if state == "winning":
        return 0.90
    return 1.0


def _score_state_from_score(my_score: int, opp_score: int) -> str:
    if my_score > opp_score:
        return "winning"
    if my_score < opp_score:
        return "losing"
    return "drawing"


def _recent_pass_completion(
    passes: list[PassEvent], minute_window_start: float,
) -> float:
    recent = [p for p in passes if p.minute >= minute_window_start]
    if not recent:
        return 0.0
    return sum(1 for p in recent if p.completed) / len(recent)


def _minute_urgency(minute: float) -> float:
    """Maç ilerledikçe sub aciliyeti artar (linear scaling 0-90).

    60. dk = 0.65, 75. dk = 0.85, 85. dk = 0.95.
    """
    return min(1.0, max(0.0, minute / 90.0))


def compute_live_sub_recommendation(
    team_external_id: int,
    all_passes: Iterable[PassEvent],
    all_def_actions: Iterable[DefensiveAction],
    *,
    current_minute: float,
    my_score: int = 0,
    opponent_score: int = 0,
    eligible_player_ids: Iterable[int] | None = None,
) -> EngineResult[LiveSubReport]:
    """Canlı maçta sub önerisi.

    Algoritma:
    1. Takımdaki tüm oyuncu ID'lerini event'lerden çıkar
    2. Her oyuncu için: fatigue_score (0-now window), recent_pass_completion
    3. Composite urgency = 0.50 × fatigue + 0.20 × (1 - recent_comp) +
       0.15 × score_pressure + 0.15 × minute_progression
    4. Score state çarpanı uygulanır
    5. Top 3 ranked döner

    `eligible_player_ids` verilirse (Faz B — kadro farkındalığı), yalnızca o
    kümedeki (= şu an SAHADA olan) oyuncular değerlendirilir. Aksi halde çoktan
    çıkmış bir oyuncu, event'leri pencerede hâlâ görüldüğü için yanlışlıkla
    önerilebilir. None → eski davranış (tüm event-aktörleri).
    """
    passes_list = list(all_passes)
    defs_list = list(all_def_actions)
    score_state = _score_state_from_score(my_score, opponent_score)
    eligible = set(eligible_player_ids) if eligible_player_ids is not None else None

    # Takım oyuncuları (eligible verilmişse sahadakilerle sınırla)
    my_player_ids: set[int] = set()
    for p in passes_list:
        if p.team_external_id == team_external_id:
            my_player_ids.add(p.player_external_id)
    for d in defs_list:
        if d.team_external_id == team_external_id:
            my_player_ids.add(d.player_external_id)
    if eligible is not None:
        my_player_ids &= eligible

    minute_urgency = _minute_urgency(current_minute)
    score_pressure = 1.0 if score_state == "losing" else (
        0.5 if score_state == "drawing" else 0.2
    )
    recent_window_start = max(0.0, current_minute - RECENT_WINDOW_MIN)
    ss_weight = _score_state_weight(score_state)

    candidates: list[SubRecommendation] = []
    for pid in my_player_ids:
        # Fatigue: 0 to current_minute window
        # FatigueSignal: early/late within (0, current_minute)
        # early_end = current_minute - 15, late_start = current_minute - 15
        early_end = max(15.0, current_minute - 15.0)
        late_start = early_end
        fatigue = compute_fatigue_signal(
            pid, passes_list, defs_list,
            early_end=early_end, late_start=late_start,
            minutes_window=(0.0, current_minute),
        ).value
        if fatigue.early_actions + fatigue.late_actions < 5:
            continue
        recent_comp = _recent_pass_completion(
            [p for p in passes_list if p.player_external_id == pid],
            recent_window_start,
        )
        urgency = (
            0.50 * fatigue.fatigue_score
            + 0.20 * (1.0 - recent_comp if recent_comp > 0 else 0.5)
            + 0.15 * score_pressure
            + 0.15 * minute_urgency
        ) * ss_weight
        urgency = round(min(1.0, max(0.0, urgency)), 3)
        label = (
            "high" if urgency >= HIGH_URGENCY_SCORE
            else "medium" if urgency >= MEDIUM_URGENCY_SCORE
            else "low"
        )
        reasons = _build_reasons(
            fatigue=fatigue.fatigue_score,
            recent_comp=recent_comp,
            score_state=score_state,
            current_minute=current_minute,
        )
        candidates.append(SubRecommendation(
            player_external_id=pid,
            urgency_score=urgency,
            urgency_label=label,
            reasons=reasons,
            fatigue_score=fatigue.fatigue_score,
            recent_pass_completion=round(recent_comp, 3),
        ))

    candidates.sort(key=lambda c: -c.urgency_score)
    top_3 = tuple(candidates[:3])

    report = LiveSubReport(
        team_external_id=team_external_id,
        current_minute=current_minute,
        score_state=score_state,
        recommendations=top_3,
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="team", subject_id=team_external_id,
        metric="live_sub_recommendation",
        value={
            "current_minute": current_minute,
            "score_state": score_state,
            "top_recommendations": [
                {
                    "player_id": r.player_external_id,
                    "urgency": r.urgency_score,
                    "label": r.urgency_label,
                } for r in top_3
            ],
        },
        inputs={
            "recent_window_min": RECENT_WINDOW_MIN,
            "high_urgency": HIGH_URGENCY_SCORE,
            "medium_urgency": MEDIUM_URGENCY_SCORE,
        },
        formula="0.50*fatigue + 0.20*(1-recent_comp) + 0.15*score_press + 0.15*minute_prog",
    )
    return EngineResult(value=report, audit=audit)


def _build_reasons(
    *, fatigue: float, recent_comp: float,
    score_state: str, current_minute: float,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if fatigue >= 0.50:
        reasons.append(f"Yüksek yorgunluk sinyali (skor {fatigue:.2f})")
    elif fatigue >= 0.30:
        reasons.append(f"Belirgin yorgunluk (skor {fatigue:.2f})")
    if recent_comp > 0 and recent_comp < 0.65:
        reasons.append(
            f"Son 10 dk pas tamamlama %{int(recent_comp * 100)} — düşük",
        )
    if score_state == "losing" and current_minute >= 60:
        reasons.append("Geride gidiyoruz; hücum oyuncusu değişikliği düşünülmeli")
    if current_minute >= 75:
        reasons.append("Maçın son 1/4'üne girildi; energy gradient kritik")
    if not reasons:
        reasons.append("Mevcut performans normal; geç dakika önlem")
    return tuple(reasons)
