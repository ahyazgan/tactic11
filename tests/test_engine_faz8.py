"""Faz 8 bağlam katmanı — confidence / signal_quality / match_memory / context_engine."""
from __future__ import annotations

from app.engine.confidence import score_confidence
from app.engine.context_engine import compute_context
from app.engine.decision_signal import CandidateSignal
from app.engine.match_memory import MemoryFrame, compute_match_memory
from app.engine.signal_quality import assess_signal, compute_signal_quality


def _sig(key, stype, urgency=0.7, fired=True, sample=8, mag=0.7,
         minute=70.0, headline="öneri") -> CandidateSignal:
    return CandidateSignal(
        key=key, signal_type=stype, headline=headline, urgency=urgency,
        fired=fired, minute=minute, sample_size=sample, magnitude=mag,
    )


# --------------------------------------------------------------------------- #
# #2 confidence
# --------------------------------------------------------------------------- #


def test_confidence_high_when_strong_evidence():
    c = score_confidence(sample_size=12, magnitude=0.9, corroboration=3,
                         data_quality=1.0)
    assert c.label == "yüksek"
    assert c.score >= 0.66


def test_confidence_low_when_thin_evidence():
    c = score_confidence(sample_size=1, magnitude=0.1, corroboration=0,
                         data_quality=0.4)
    assert c.label == "düşük"
    assert c.score < 0.40


def test_confidence_history_drives_explanation():
    c = score_confidence(sample_size=8, magnitude=0.6, corroboration=1,
                         data_quality=0.8, historical_hit_rate=0.75)
    assert any("doğru çıktı" in d for d in c.drivers)


# --------------------------------------------------------------------------- #
# #5 signal_quality
# --------------------------------------------------------------------------- #


def test_quality_suppresses_thin_substitution():
    v = assess_signal(_sig("sub", "substitution", sample=2))
    assert v.verdict == "suppressed"


def test_quality_ok_with_enough_sample():
    v = assess_signal(_sig("tac", "tactical", sample=6, minute=70))
    assert v.verdict == "ok"


def test_quality_degraded_in_warmup():
    v = assess_signal(_sig("tac", "tactical", sample=6, minute=2))
    assert v.verdict == "degraded"


def test_quality_closing_never_suppressed():
    v = assess_signal(_sig("close", "closing", sample=0, minute=88))
    assert v.verdict == "ok"


def test_compute_signal_quality_splits_kept_suppressed():
    sigs = [_sig("a", "tactical", sample=6), _sig("b", "substitution", sample=1)]
    r = compute_signal_quality(sigs, current_minute=70).value
    assert r.total_kept == 1
    assert any(v.key == "b" for v in r.suppressed)


# --------------------------------------------------------------------------- #
# #3 match_memory
# --------------------------------------------------------------------------- #


def test_memory_detects_momentum_flip():
    frames = [
        MemoryFrame(minute=50, momentum_score=-0.5),
        MemoryFrame(minute=55, momentum_score=-0.5),
        MemoryFrame(minute=60, momentum_score=0.5),
    ]
    r = compute_match_memory(frames, current_minute=62).value
    assert r.last_momentum_flip_minute == 60
    assert any(t.kind == "momentum_flip" for t in r.threads)


def test_memory_flank_decline():
    frames = [
        MemoryFrame(minute=50, flank_xt={"left": 1.0}),
        MemoryFrame(minute=55, flank_xt={"left": 0.8}),
        MemoryFrame(minute=60, flank_xt={"left": 0.5}),
        MemoryFrame(minute=65, flank_xt={"left": 0.4}),
    ]
    r = compute_match_memory(frames, current_minute=66).value
    assert any(t.kind == "flank_decline" for t in r.threads)


def test_memory_links_opponent_change_to_decline():
    frames = [
        MemoryFrame(minute=50, opponent_formation="442", flank_xt={"left": 0.6}),
        MemoryFrame(minute=52, opponent_formation="433", flank_xt={"left": 0.7}),
        MemoryFrame(minute=55, opponent_formation="433", flank_xt={"left": 1.0}),
        MemoryFrame(minute=60, opponent_formation="433", flank_xt={"left": 0.5}),
        MemoryFrame(minute=65, opponent_formation="433", flank_xt={"left": 0.3}),
    ]
    r = compute_match_memory(frames, current_minute=66).value
    assert any(t.kind == "linked" for t in r.threads)


# --------------------------------------------------------------------------- #
# #1 context_engine (orkestra şefi)
# --------------------------------------------------------------------------- #


def test_context_picks_single_primary():
    sigs = [
        _sig("momentum", "tactical", urgency=0.7, headline="momentum düşüyor"),
        _sig("sub_timing", "substitution", urgency=0.9, headline="şimdi değiştir"),
        _sig("score_time_matrix", "closing", urgency=0.6, sample=0,
             headline="oyunu böl"),
    ]
    d = compute_context(sigs, current_minute=67, score_state="drawing").value
    assert d.primary is not None
    assert d.one_liner.startswith("ŞİMDİ")
    # en yüksek urgency × güven → sub_timing primary olmalı
    assert d.primary.headline == "şimdi değiştir"
    # diğer eşzamanlı sinyaller destekleyici
    assert len(d.primary.supporting_keys) >= 1


def test_context_rationale_fuses_cooccurring():
    sigs = [
        _sig("sub_timing", "substitution", urgency=0.9, headline="8 no değiştir"),
        _sig("momentum", "tactical", urgency=0.7, headline="momentum düşüyor"),
    ]
    d = compute_context(sigs, current_minute=67, score_state="drawing").value
    assert "aynı anda" in d.primary.rationale


def test_context_suppresses_low_quality():
    sigs = [
        _sig("good", "tactical", sample=8, headline="iyi sinyal"),
        _sig("thin", "substitution", sample=1, headline="zayıf sinyal"),
    ]
    d = compute_context(sigs, current_minute=70).value
    assert any(k == "thin" for k, _ in d.suppressed)


def test_context_empty_when_nothing_fires():
    sigs = [_sig("m", "tactical", fired=False)]
    d = compute_context(sigs, current_minute=70).value
    assert d.primary is None
    assert "Net bir aksiyon yok" in d.one_liner


def test_context_memory_threads_passed_through():
    sigs = [_sig("m", "tactical", headline="ayar yap")]
    d = compute_context(
        sigs, current_minute=70,
        memory_threads=("rakip 55'te değişti, sol kanat düştü",),
    ).value
    assert d.memory_threads
