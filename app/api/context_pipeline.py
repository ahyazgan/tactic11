"""Faz 8 bağlam pipeline orkestrasyonu — admin endpoint'leri ile engine arası glue.

live-decision endpoint'inin ürettiği 8 sinyal dict'ini alır, CandidateSignal'e
çevirir, maç-içi hafıza + geçmiş isabet (feedback) + sinyal kalitesini birleştirip
context_engine'i çalıştırır ve tek "şimdi şunu yap" kararını döndürür. Ayrıca her
çağrıda match_snapshots'a bir frame yazar (hafızanın bir sonraki tick'te çalışması için).

Engine'ler saf kalsın diye DB erişimi + dict↔dataclass çevrimi burada yapılır.
"""
from __future__ import annotations

import json as _json
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from app.db import models
from app.engine.context_engine import compute_context
from app.engine.decision_signal import CandidateSignal
from app.engine.match_memory import MemoryFrame, compute_match_memory
from app.sports import football

_URGENCY_BY_LEVEL = {"high": 0.9, "medium": 0.6, "low": 0.35}
# decision_type → context sinyal tipleri (feedback yayılımı)
_HITRATE_SPREAD = {
    "substitution": ("substitution", "risk"),
    "formation_change": ("tactical", "spatial", "matchup"),
    "tactical_instruction": ("tactical", "spatial", "matchup"),
}


def _win_counts(p: list, d: list, s: list, current_minute: float,
                window: float = 15.0) -> dict[str, int]:
    lo = current_minute - window
    return {
        "passes": sum(1 for x in p if lo <= x.minute <= current_minute),
        "defs": sum(1 for x in d if lo <= x.minute <= current_minute),
        "shots": sum(1 for x in s if lo <= x.minute <= current_minute),
    }


def build_candidates(
    out: dict[str, Any], *, current_minute: float, win: dict[str, int],
) -> list[CandidateSignal]:
    """8 engine dict çıktısından normalize sinyaller üret."""
    cands: list[CandidateSignal] = []
    ev = win["passes"] + win["defs"]

    def _is_dict(x: Any) -> bool:
        return isinstance(x, dict) and "error" not in x

    # momentum (tactical)
    m = out.get("momentum")
    if _is_dict(m):
        ms = float(m.get("momentum_score", 0.0))
        pb = bool(m.get("press_breaking"))
        xg = bool(m.get("xg_swing_alert"))
        holder = m.get("momentum_holder", "balanced")
        fired = holder != "balanced" or pb or xg
        urgency = min(1.0, abs(ms) + (0.3 if pb else 0.0) + (0.3 if xg else 0.0))
        cands.append(CandidateSignal(
            key="momentum", signal_type="tactical",
            headline=m.get("alert_text", "Momentum sinyali"),
            urgency=urgency, fired=fired, minute=current_minute,
            sample_size=win["defs"] + win["shots"], magnitude=min(1.0, abs(ms)),
        ))

    # sub_timing (substitution)
    st = out.get("sub_timing")
    if _is_dict(st):
        advices = st.get("advices", []) or []
        now = [a for a in advices if a.get("timing_verdict") == "now"]
        wait10 = [a for a in advices if a.get("timing_verdict") == "wait_10"]
        pkg = st.get("package_recommendation") or []
        fired = bool(now) or bool(pkg)
        urgency = 0.9 if now else (0.6 if wait10 else 0.3)
        mag = max((float(a.get("impact_estimate", 0.0)) for a in advices),
                  default=0.0)
        if now:
            head = f"Şimdi değiştir: {[a.get('player_external_id') for a in now]}"
        else:
            head = st.get("package_rationale", "Değişiklik penceresini izle")
        cands.append(CandidateSignal(
            key="sub_timing", signal_type="substitution", headline=head,
            urgency=urgency, fired=fired, minute=current_minute,
            sample_size=ev, magnitude=min(1.0, mag),
        ))

    # tactical_triggers (tactical)
    tt = out.get("tactical_triggers")
    if _is_dict(tt):
        trigs = [t for t in tt.get("triggers", []) if t.get("fired")]
        if trigs:
            top = trigs[0]
            urg = _URGENCY_BY_LEVEL.get(top.get("urgency", "low"), 0.35)
            cands.append(CandidateSignal(
                key="tactical_triggers", signal_type="tactical",
                headline=top.get("recommendation", "Taktiksel ayar"),
                urgency=urg, fired=True, minute=current_minute,
                sample_size=ev, magnitude=urg,
            ))

    # risk_monitor (risk)
    rm = out.get("risk_monitor")
    if _is_dict(rm):
        cards = rm.get("card_flags", []) or []
        injuries = rm.get("injury_flags", []) or []
        fired = bool(cards or injuries)
        if fired:
            high = any(f.get("severity") == "high" for f in (*cards, *injuries))
            parts = []
            if cards:
                parts.append(f"{len(cards)} kart riski")
            if injuries:
                parts.append(f"{len(injuries)} sakatlık riski")
            cands.append(CandidateSignal(
                key="risk_monitor", signal_type="risk",
                headline="Risk: " + ", ".join(parts),
                urgency=0.85 if high else 0.55, fired=True, minute=current_minute,
                sample_size=len(cards) + len(injuries),
                magnitude=0.9 if high else 0.5,
            ))

    # spatial_control (spatial)
    sc = out.get("spatial_control")
    if _is_dict(sc):
        alerts = sc.get("alerts", []) or []
        fired = bool(alerts)
        if fired:
            cands.append(CandidateSignal(
                key="spatial_control", signal_type="spatial",
                headline=alerts[0], urgency=0.6, fired=True, minute=current_minute,
                sample_size=win["passes"], magnitude=0.6,
            ))

    # live_matchup (matchup)
    lm = out.get("live_matchup")
    if _is_dict(lm):
        alerts = lm.get("alerts", []) or []
        fired = bool(alerts)
        if fired:
            cands.append(CandidateSignal(
                key="live_matchup", signal_type="matchup",
                headline=alerts[0], urgency=0.65, fired=True, minute=current_minute,
                sample_size=win["defs"] + win["passes"], magnitude=0.6,
            ))

    # score_time_matrix (closing)
    stm = out.get("score_time_matrix")
    if _is_dict(stm):
        closing = bool(stm.get("in_closing_phase"))
        posture = stm.get("posture", "balanced")
        fired = closing and posture in ("see_out", "all_out", "chase")
        if fired:
            urg = {"all_out": 0.85, "see_out": 0.7, "chase": 0.7}.get(posture, 0.5)
            cands.append(CandidateSignal(
                key="score_time_matrix", signal_type="closing",
                headline=stm.get("closing_recipe", "Skor-zaman reçetesi"),
                urgency=urg, fired=True, minute=current_minute,
                sample_size=0, magnitude=urg,
            ))

    return cands


def context_only(
    out: dict[str, Any], *, current_minute: float, my_score: int,
    opp_score: int, win: dict[str, int],
    memory_threads: tuple[str, ...] = (),
) -> dict[str, Any]:
    """DB'siz saf bağlam kararı (WebSocket gibi stateless yüzeyler için)."""
    candidates = build_candidates(out, current_minute=current_minute, win=win)
    diff = (my_score or 0) - (opp_score or 0)
    state = "leading" if diff > 0 else "trailing" if diff < 0 else "drawing"
    ctx = compute_context(
        candidates, current_minute=current_minute, score_state=state,
        memory_threads=memory_threads,
    ).value
    return asdict(ctx)


def _load_frames(session, match_id: int, team_id: int,
                 current_minute: float) -> list[MemoryFrame]:
    rows = session.execute(
        select(models.MatchSnapshot).where(
            models.MatchSnapshot.sport == football.SPORT_NAME,
            models.MatchSnapshot.match_external_id == match_id,
            models.MatchSnapshot.team_external_id == team_id,
            models.MatchSnapshot.minute <= current_minute,
        ).order_by(models.MatchSnapshot.minute)
    ).scalars().all()
    frames: list[MemoryFrame] = []
    for r in rows:
        flank_xt: dict[str, float] = {}
        if r.frame_json:
            try:
                flank_xt = (_json.loads(r.frame_json) or {}).get("flank_xt", {})
            except (ValueError, TypeError):
                flank_xt = {}
        frames.append(MemoryFrame(
            minute=r.minute, momentum_score=r.momentum_score or 0.0,
            opponent_formation=r.opponent_formation, flank_xt=flank_xt,
        ))
    return frames


def _hit_rate(session, team_id: int) -> dict[str, float]:
    """decision outcome'larından signal_type → geçmiş isabet oranı."""
    rows = session.execute(
        select(models.Decision).where(
            models.Decision.sport == football.SPORT_NAME,
            models.Decision.team_external_id == team_id,
            models.Decision.outcome.in_(("positive", "negative")),
        )
    ).scalars().all()
    by_type: dict[str, list[int]] = {}
    for r in rows:
        by_type.setdefault(r.decision_type, []).append(
            1 if r.outcome == "positive" else 0
        )
    out: dict[str, float] = {}
    for dtype, results in by_type.items():
        if not results:
            continue
        rate = sum(results) / len(results)
        for sig_type in _HITRATE_SPREAD.get(dtype, ()):  # noqa: B007
            out[sig_type] = rate
    return out


def _record_snapshot(session, match, team_id: int, current_minute: float,
                     out: dict[str, Any]) -> None:
    flank_xt: dict[str, float] = {}
    sc = out.get("spatial_control")
    if isinstance(sc, dict):
        for fb in sc.get("flank_balance", []) or []:
            flank_xt[fb.get("flank", "?")] = float(fb.get("our_count", 0))
    mom = out.get("momentum")
    ms = float(mom.get("momentum_score", 0.0)) if isinstance(mom, dict) else None
    period = 1 if current_minute < 45 else 2
    session.add(models.MatchSnapshot(
        sport=football.SPORT_NAME,
        match_external_id=match.external_id,
        team_external_id=team_id,
        minute=current_minute, period=period,
        momentum_score=ms, opponent_formation=None,
        frame_json=_json.dumps({"flank_xt": flank_xt}),
        created_at=datetime.now(UTC),
    ))
    session.commit()


def run_context_pipeline(
    session, match, my_team_id: int, current_minute: float,
    out: dict[str, Any], p: list, d: list, s: list,
    *, my_score: int, opp_score: int,
) -> dict[str, Any]:
    """Tüm pipeline: kalite → güven → hafıza → bağlam motoru → tek karar.

    Hata-toleranslı: herhangi bir adım patlarsa endpoint'i bozmaz."""
    try:
        win = _win_counts(p, d, s, current_minute)
        candidates = build_candidates(out, current_minute=current_minute, win=win)

        frames = _load_frames(session, match.external_id, my_team_id,
                              current_minute)
        memory = compute_match_memory(frames, current_minute=current_minute).value
        memory_threads = tuple(t.text for t in memory.threads)
        # hafıza herhangi bir thread ürettiyse şekil/personel temalarını güçlendir
        hints: tuple[str, ...] = (
            ("adjust_shape", "change_personnel") if memory.threads else ()
        )
        hit = _hit_rate(session, my_team_id)

        diff = (my_score or 0) - (opp_score or 0)
        state = "leading" if diff > 0 else "trailing" if diff < 0 else "drawing"

        ctx = compute_context(
            candidates, current_minute=current_minute, score_state=state,
            memory_threads=memory_threads, memory_theme_hints=hints,
            historical_hit_rate=hit or None,
        ).value

        _record_snapshot(session, match, my_team_id, current_minute, out)

        return {"context": asdict(ctx), "match_memory": asdict(memory)}
    except (ValueError, ZeroDivisionError, KeyError, TypeError, AttributeError) as e:
        return {"context": {"error": str(e)[:120]}}
