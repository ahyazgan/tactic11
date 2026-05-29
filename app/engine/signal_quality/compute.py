"""Signal Quality — sinyal kalite filtresi (Faz 8 #5).

WebSocket/event-window'dan gelen her sinyal güvenilir değil: yetersiz örnek,
maç başı ısınma penceresi, eksik veri yanlış ateşlemeye yol açar. Bir kez
yanlış alarm → kullanıcı güvenini kaybeder. Bu katman context_engine'den ÖNCE
çalışır; her sinyale kalite skoru + verdict verir, çürükleri eler.

Kurallar (saf, sezgisel — gerçek feed gelince kalibre edilir):
- fired=False → zaten sinyal değil, atla.
- sample_size < tip-eşiği → "suppressed" (insufficient_data).
- current_minute ısınma penceresinde (yarı başı ilk dk) → "degraded" (warmup).
- aksi halde "ok"; kalite skoru örnek doygunluğu × ısınma faktörü.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.audit import AuditRecord, EngineResult
from app.engine.decision_signal import CandidateSignal

ENGINE_NAME = "engine.signal_quality"
ENGINE_VERSION = "1"

# Tip bazlı minimum örnek (altı → süpür)
MIN_SAMPLE_BY_TYPE: dict[str, int] = {
    "substitution": 4,
    "tactical": 3,
    "spatial": 3,
    "matchup": 3,
    "risk": 1,        # payload-fed; örnek azlığı süpürmez
    "closing": 0,     # saf skor-zaman; event gerekmez
    "opponent": 1,
    "set_piece": 0,   # reçete
}
DEFAULT_MIN_SAMPLE = 3
# Isınma: yarı başlangıcından sonraki bu kadar dk içinde event-temelli sinyal şüpheli
WARMUP_MIN = 5.0
SAMPLE_FULL = 12


@dataclass(frozen=True)
class QualityVerdict:
    key: str
    verdict: str             # "ok" | "degraded" | "suppressed"
    score: float             # 0..1
    reason: str


@dataclass(frozen=True)
class SignalQualityReport:
    current_minute: float
    kept: tuple[QualityVerdict, ...] = field(default_factory=tuple)
    suppressed: tuple[QualityVerdict, ...] = field(default_factory=tuple)
    total_in: int = 0
    total_kept: int = 0


def _in_warmup(minute: float) -> bool:
    # Maç başı (0-5) veya ikinci yarı başı (45-50)
    return minute < WARMUP_MIN or (45.0 <= minute < 45.0 + WARMUP_MIN)


def assess_signal(sig: CandidateSignal) -> QualityVerdict:
    """Tek bir sinyalin kalite verdict'i."""
    min_sample = MIN_SAMPLE_BY_TYPE.get(sig.signal_type, DEFAULT_MIN_SAMPLE)
    if min_sample > 0 and sig.sample_size < min_sample:
        return QualityVerdict(
            key=sig.key, verdict="suppressed", score=0.0,
            reason=f"yetersiz örnek ({sig.sample_size}<{min_sample})",
        )
    # örnek doygunluğu
    sample_term = min(1.0, sig.sample_size / SAMPLE_FULL) if min_sample > 0 else 1.0
    if _in_warmup(sig.minute) and min_sample > 0:
        return QualityVerdict(
            key=sig.key, verdict="degraded", score=round(0.5 * sample_term, 3),
            reason=f"ısınma penceresi ({sig.minute:.0f}. dk) — temkinli",
        )
    score = round(max(0.4, sample_term), 3)
    return QualityVerdict(
        key=sig.key, verdict="ok", score=score,
        reason=f"{sig.sample_size} örnek, ısınma dışı",
    )


def compute_signal_quality(
    signals: list[CandidateSignal],
    *,
    current_minute: float,
) -> EngineResult[SignalQualityReport]:
    kept: list[QualityVerdict] = []
    suppressed: list[QualityVerdict] = []
    fired = [s for s in signals if s.fired]
    for sig in fired:
        v = assess_signal(sig)
        if v.verdict == "suppressed":
            suppressed.append(v)
        else:
            kept.append(v)

    report = SignalQualityReport(
        current_minute=current_minute,
        kept=tuple(kept),
        suppressed=tuple(suppressed),
        total_in=len(fired),
        total_kept=len(kept),
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="match", subject_id=0,
        metric="signal_quality",
        value={
            "total_in": len(fired), "total_kept": len(kept),
            "suppressed": [v.key for v in suppressed],
        },
        inputs={"current_minute": current_minute,
                "min_sample_by_type": MIN_SAMPLE_BY_TYPE},
        formula="tip-eşiği örnek + ısınma penceresi → ok/degraded/suppressed",
    )
    return EngineResult(value=report, audit=audit)
