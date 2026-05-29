"""Context Engine — bağlam motoru / orkestra şefi (Faz 8 #1).

EN KRİTİK katman. Şu ana kadar her engine kendi sonucunu ayrı veriyordu;
kullanıcı ekranda 5 ayrı uyarı görüp hangisine bakacağını bilemiyordu.

Bu motor tüm aktif sinyalleri AYNI ANDA okur ve tek bir karar önceliği üretir:
"67. dk, momentum düşüyor + 8 no kritik eşikte + skor 0-0 → bu üçü aynı anda →
ŞİMDİ değiştir."

Pipeline'ı içeride çalıştırır (tek giriş noktası):
  ham sinyaller → [#5 signal_quality] süz → tema grupla → korroborasyon say
  → [#2 confidence] skorla → [#3 memory] thread'lerle güçlendir → sırala → birleştir

Saf fonksiyon. CandidateSignal listesi + memory thread'leri + bağlam → tek karar.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.audit import AuditRecord, EngineResult
from app.engine.confidence import score_confidence
from app.engine.decision_signal import CandidateSignal, ScoredSignal
from app.engine.signal_quality import compute_signal_quality

ENGINE_NAME = "engine.context_engine"
ENGINE_VERSION = "1"

# Sinyal tipi → kaba tema (çakışan sinyaller aynı temada birleşir)
THEME_BY_TYPE: dict[str, str] = {
    "substitution": "change_personnel",
    "risk": "change_personnel",
    "tactical": "adjust_shape",
    "spatial": "adjust_shape",
    "matchup": "adjust_shape",
    "set_piece": "set_piece",
    "closing": "manage_game",
    "opponent": "manage_game",
}
THEME_LABEL: dict[str, str] = {
    "change_personnel": "oyuncu değişikliği",
    "adjust_shape": "taktiksel ayar",
    "set_piece": "duran top",
    "manage_game": "oyun yönetimi",
}
# Memory thread → tema güçlendirme eşlemesi (kind bazlı)
MEMORY_BOOST = 0.15


@dataclass(frozen=True)
class PrioritizedAction:
    headline: str
    theme: str
    theme_label: str
    urgency: float
    confidence: float
    confidence_label: str
    priority: float
    rationale: str                 # çakışan sinyalleri birleştiren tek cümle
    drivers: tuple[str, ...] = field(default_factory=tuple)
    supporting_keys: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ContextDecision:
    current_minute: float
    one_liner: str                 # "şimdi şunu yap"
    primary: PrioritizedAction | None
    secondary: tuple[PrioritizedAction, ...] = field(default_factory=tuple)
    suppressed: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    memory_threads: tuple[str, ...] = field(default_factory=tuple)


def _theme(sig: CandidateSignal) -> str:
    return THEME_BY_TYPE.get(sig.signal_type, "adjust_shape")


def compute_context(
    signals: list[CandidateSignal],
    *,
    current_minute: float,
    score_state: str = "drawing",
    memory_threads: tuple[str, ...] = (),
    memory_theme_hints: tuple[str, ...] = (),
    historical_hit_rate: dict[str, float] | None = None,
) -> EngineResult[ContextDecision]:
    """Tüm sinyalleri tek karara indirger.

    memory_theme_hints: hafıza katmanının (#3) işaret ettiği temalar; ilgili
    sinyallerin aciliyetini artırır (proaktiflik).
    historical_hit_rate: signal_type → 0..1 geçmiş isabet (feedback #4).
    """
    hit = historical_hit_rate or {}

    # #5 kalite filtresi
    quality = compute_signal_quality(signals, current_minute=current_minute).value
    quality_by_key = {v.key: v for v in (*quality.kept, *quality.suppressed)}
    suppressed = tuple((v.key, v.reason) for v in quality.suppressed)
    kept_keys = {v.key for v in quality.kept}

    fired = [s for s in signals if s.fired and s.key in kept_keys]

    scored: list[ScoredSignal] = []
    for s in fired:
        th = _theme(s)
        qv = quality_by_key[s.key]
        # korroborasyon = aynı anda ateşleyen DİĞER tüm sinyaller. Birden çok
        # bağımsız sinyal aynı dakikada → karar daha güvenilir (kullanıcının
        # "momentum + oyuncu kritik + skor" örneği farklı temalardan gelir).
        corroboration = len(fired) - 1
        conf = score_confidence(
            sample_size=s.sample_size, magnitude=s.magnitude,
            corroboration=corroboration, data_quality=qv.score,
            historical_hit_rate=hit.get(s.signal_type),
        )
        # hafıza güçlendirmesi: bu temaya işaret eden thread varsa aciliyet artar
        urgency = s.urgency
        if th in memory_theme_hints:
            urgency = min(1.0, urgency + MEMORY_BOOST)
        boosted = CandidateSignal(
            key=s.key, signal_type=s.signal_type, headline=s.headline,
            urgency=urgency, fired=True, minute=s.minute,
            sample_size=s.sample_size, magnitude=s.magnitude, detail=s.detail,
        )
        scored.append(ScoredSignal(
            candidate=boosted, quality=qv.score, quality_verdict=qv.verdict,
            quality_reason=qv.reason, confidence=conf.score,
            confidence_label=conf.label, confidence_drivers=conf.drivers,
        ))

    scored.sort(key=lambda s: s.priority, reverse=True)

    if not scored:
        decision = ContextDecision(
            current_minute=current_minute,
            one_liner="Net bir aksiyon yok — mevcut planı koru, izlemeye devam.",
            primary=None, secondary=(), suppressed=suppressed,
            memory_threads=memory_threads,
        )
        return _wrap(decision, current_minute)

    top = scored[0]
    top_theme = _theme(top.candidate)
    # diğer eşzamanlı sinyaller birincil kararı bağlamsal olarak destekler
    others = scored[1:]
    supporting_keys = tuple(s.candidate.key for s in others)

    # birleşik gerekçe: birincil + aynı anda ateşleyen diğer sinyaller
    state_tr = {"leading": "öndesin", "drawing": "berabere",
                "trailing": "gerideysin"}.get(score_state, score_state)
    co_parts = [s.candidate.headline for s in others[:2]]
    if co_parts:
        rationale = (
            f"{current_minute:.0f}. dk, {state_tr} — {top.candidate.headline}; "
            f"aynı anda: {', '.join(co_parts)} → karar net"
        )
    else:
        rationale = (
            f"{current_minute:.0f}. dk, {state_tr} — {top.candidate.headline}"
        )

    primary = PrioritizedAction(
        headline=top.candidate.headline,
        theme=top_theme, theme_label=THEME_LABEL[top_theme],
        urgency=round(top.candidate.urgency, 3),
        confidence=top.confidence, confidence_label=top.confidence_label,
        priority=top.priority, rationale=rationale,
        drivers=top.confidence_drivers, supporting_keys=supporting_keys,
    )

    # ikincil: farklı temadaki sonraki sinyaller (her temadan en güçlü bir tane)
    secondary_actions: list[PrioritizedAction] = []
    seen_themes = {top_theme}
    for s in others:
        th = _theme(s.candidate)
        if th in seen_themes:
            continue
        seen_themes.add(th)
        secondary_actions.append(PrioritizedAction(
            headline=s.candidate.headline, theme=th, theme_label=THEME_LABEL[th],
            urgency=round(s.candidate.urgency, 3), confidence=s.confidence,
            confidence_label=s.confidence_label, priority=s.priority,
            rationale=s.candidate.headline, drivers=s.confidence_drivers,
            supporting_keys=(s.candidate.key,),
        ))

    one_liner = (
        f"ŞİMDİ: {primary.headline} "
        f"(güven: {primary.confidence_label}, öncelik {primary.priority:.2f})"
    )

    decision = ContextDecision(
        current_minute=current_minute,
        one_liner=one_liner,
        primary=primary,
        secondary=tuple(secondary_actions[:3]),
        suppressed=suppressed,
        memory_threads=memory_threads,
    )
    return _wrap(decision, current_minute)


def _wrap(decision: ContextDecision, minute: float) -> EngineResult[ContextDecision]:
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="match", subject_id=0,
        metric="context_decision",
        value={
            "one_liner": decision.one_liner,
            "primary_theme": decision.primary.theme if decision.primary else None,
            "primary_confidence": decision.primary.confidence if decision.primary else None,
            "secondary_count": len(decision.secondary),
            "suppressed_count": len(decision.suppressed),
        },
        inputs={"current_minute": minute},
        formula="quality süz → tema grupla → confidence skorla → memory güçlendir "
                "→ priority sırala → çakışanları tek karara birleştir",
    )
    return EngineResult(value=decision, audit=audit)
