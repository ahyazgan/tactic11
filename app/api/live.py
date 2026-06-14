"""Live WebSocket endpoints — canlı maç push.

FastAPI built-in WebSocket; Redis backend gerekmez (tek-process pilot demo).
Production-scale çoklu worker için Redis pub/sub gerekir.

Endpoint: /ws/matches/{match_id}/live?my_team_id=N&interval_seconds=10

Algoritma:
1. Client connect olur
2. Sunucu N saniyede bir tactical-profile + halftime brief snapshot push'lar
3. Client disconnect veya match status FT olduğunda kapanır

Şu an event akışı StatsBomb Open Data static; gerçek canlı feed StatsBomb Pro
veya Opta ile sonradan swap edilir. Bu endpoint protokolü tanımlar.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
from typing import Any

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.api.live_feed_factory import build_live_feed
from app.api.live_provider import build_provider_status
from app.api.replay_feed import ReplayFeed
from app.api.serialize import engine_result_to_dict
from app.core.logging import get_logger
from app.db.session import get_session
from app.engine.field_tilt import compute_field_tilt
from app.engine.live_shape_drift import compute_live_shape_drift
from app.engine.live_sub_recommendation import compute_live_sub_recommendation
from app.engine.match_dominance import compute_match_dominance
from app.engine.ppda import compute_ppda
from app.engine.replay_clock import current_phase

log = get_logger(__name__)

router = APIRouter(prefix="/ws", tags=["live"])

# Tek-process state: aktif WebSocket sayısı (observability)
_ACTIVE_CONNECTIONS: dict[str, int] = {"count": 0}

# Push interval kabul sınırları
MIN_INTERVAL_SECONDS = 5
MAX_INTERVAL_SECONDS = 60

# Maç başlangıcından itibaren simülasyon: "şu an dakika kaç?"
# (gerçek canlı feed varken provider'dan gelecek; şimdi maç süresinden tahmin)
SIMULATION_START_MINUTE = 0.0


def _count_corroborating_signals(snapshot: dict[str, Any]) -> int:
    """Aynı anda 'dolu' kaç kritik sinyal var — güven için teyit sayısı.

    momentum dengesiz (bir tarafa baskı) + en az bir tactical trigger fired +
    spatial alert dolu → 3. Okunur, snapshot anahtarlarından türetilir.
    """
    n = 0
    mom = snapshot.get("momentum") or {}
    if mom.get("holder") not in (None, "balanced"):
        n += 1
    if snapshot.get("tactical_triggers"):  # fired trigger listesi dolu
        n += 1
    spatial = snapshot.get("spatial_control") or {}
    if spatial.get("alerts"):
        n += 1
    return n


# Bağlantı-başına tutulan trend geçmişi üst sınırı (summarize_trend son 5'i alır).
TREND_HISTORY_LIMIT = 8


def _trend_frame(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Bir snapshot'tan trend için minimal skaler özet (hata-toleranslı)."""
    mom = snapshot.get("momentum") or {}
    tilt = snapshot.get("field_tilt") or {}
    dom = snapshot.get("match_dominance") or {}
    primary = (snapshot.get("context") or {}).get("primary") or {}
    return {
        "momentum_score": mom.get("score") if isinstance(mom, dict) else None,
        "field_tilt": tilt.get("team_a_tilt") if isinstance(tilt, dict) else None,
        "dominance": dom.get("dominance_score") if isinstance(dom, dict) else None,
        "primary": primary.get("headline") if isinstance(primary, dict) else None,
    }


def _compute_live_vaep(
    *,
    my_team_id: int,
    opp_team_id: int,
    passes: list[Any],
    carries: list[Any],
    shots: list[Any],
    current_minute: float,
    top_n: int = 5,
    appearances: list[Any] | None = None,
) -> dict[str, Any]:
    """My + opp takım toplam VAEP + top-N my_team oyuncusu (Faz 5 #47).

    Saf orchestrator: engine.vaep.compute_vaep'i takım ve oyuncu için çağırır;
    DB/HTTP bilmez. WebSocket snapshot'ına gömülür ve REST test'lerinde de
    bağımsız çağrılabilir.

    Faz B (kadro farkındalığı): `appearances` (PlayerAppearance listesi) verilirse
    her oyuncunun VAEP/90'ı O OYUNCUNUN gerçek sahada-geçen dakikasına normalize
    edilir (sonradan giren 10 dk'lık oyuncu 75 dk'ya bölünmez). Takım toplamı
    yine `current_minute`'a normalize (her zaman 11 kişi sahada). None →
    eski davranış: minutes_played = current_minute (her oyuncu için aynı).
    """
    from app.engine.vaep.compute import compute_vaep

    minutes_by_player: dict[int, float] = {}
    on_pitch_ids: frozenset[int] = frozenset()
    if appearances is not None:
        from app.engine.live_lineup import resolve_on_pitch
        op = resolve_on_pitch(
            appearances, current_minute, team_external_id=my_team_id,
        )
        minutes_by_player = op.minutes_by_player
        on_pitch_ids = op.player_ids

    try:
        my_team = compute_vaep(
            team_external_id=my_team_id,
            all_passes=passes, all_carries=carries, all_shots=shots,
            minutes_played=current_minute,
        ).value
        opp_team = compute_vaep(
            team_external_id=opp_team_id,
            all_passes=passes, all_carries=carries, all_shots=shots,
            minutes_played=current_minute,
        ).value
    except (ValueError, ZeroDivisionError) as e:
        return {"error": str(e)}

    # Player-level (sadece my_team oyuncuları, pass + carry'den unique pid)
    my_team_player_ids: set[int] = set()
    for p in passes:
        if getattr(p, "team_external_id", None) == my_team_id:
            pid = getattr(p, "player_external_id", None)
            if pid is not None:
                my_team_player_ids.add(int(pid))
    for c in carries:
        if getattr(c, "team_external_id", None) == my_team_id:
            pid = getattr(c, "player_external_id", None)
            if pid is not None:
                my_team_player_ids.add(int(pid))

    player_results: list[dict[str, Any]] = []
    for pid in my_team_player_ids:
        # Faz B: oyuncunun gerçek sahada-geçen dakikası (yoksa current_minute).
        player_minutes = minutes_by_player.get(pid, current_minute)
        try:
            r = compute_vaep(
                player_external_id=pid,
                all_passes=passes, all_carries=carries, all_shots=shots,
                minutes_played=player_minutes,
            ).value
        except (ValueError, ZeroDivisionError):
            continue
        if r.total_actions == 0:
            continue
        player_results.append({
            "player_id": pid,
            "vaep_value": round(r.vaep_value, 4),
            "total_actions": r.total_actions,
            "minutes_played": round(player_minutes, 1),
            # Faz B: appearances yoksa None (bilinmiyor) → frontend rozet göstermez.
            "on_pitch": (pid in on_pitch_ids) if appearances is not None else None,
            "vaep_per_90": (
                round(r.vaep_per_90, 4) if r.vaep_per_90 is not None else None
            ),
        })
    player_results.sort(key=lambda x: x["vaep_value"], reverse=True)

    return {
        "my_team_total": round(my_team.vaep_value, 4),
        "opp_team_total": round(opp_team.vaep_value, 4),
        "my_team_actions": my_team.total_actions,
        "opp_team_actions": opp_team.total_actions,
        "model_version": my_team.model_version,
        "current_minute": current_minute,
        "top_players": player_results[:top_n],
    }


def _compute_live_snapshot(
    feed: ReplayFeed, match_id: int, my_team_id: int, current_minute: float,
) -> dict[str, Any]:
    """Tek-snapshot: events şu ana kadar olanlar + canlı engine'ler."""
    home_id = feed.home_team_id
    away_id = feed.away_team_id
    opp_id = away_id if my_team_id == home_id else home_id

    # Sadece şu ana kadar olan event'ler (feed dilimler)
    evw = feed.window(current_minute)
    passes_so_far = evw.passes
    carries_so_far = evw.carries
    defs_so_far = evw.defensive_actions
    shots_so_far = evw.shots

    if not passes_so_far:
        return {
            "match_id": match_id, "current_minute": current_minute,
            "events_so_far": 0,
            "note": "Henüz event yok",
            "mode": feed.mode(),
            "provider": build_provider_status(source=feed.mode()),
        }

    # As-of-minute koşan skor (final-skor sızıntısı yerine). Bu local'ler aşağıda
    # 5 tüketiciye akar: sub_recommendation, sub_timing, tactical_trigger,
    # score_time_matrix, context_only — hepsi doğru oyun durumuyla beslenir.
    home_sc, away_sc = feed.running_score(current_minute)
    my_score = home_sc if my_team_id == home_id else away_sc
    opp_score = away_sc if my_team_id == home_id else home_sc

    # Faz B: kadro/sub farkındalığı. appearances yoksa (None) eski davranış —
    # eligible=None (tüm aktörler), VAEP current_minute'a normalize.
    appearances = feed.appearances()
    eligible_ids: set[int] | None = None
    if appearances is not None:
        from app.engine.live_lineup import resolve_on_pitch
        eligible_ids = set(
            resolve_on_pitch(
                appearances, current_minute, team_external_id=my_team_id,
            ).player_ids
        )

    snapshot: dict[str, Any] = {
        "match_id": match_id,
        "my_team_id": my_team_id,
        "opponent_id": opp_id,
        "current_minute": current_minute,
        "events_so_far": (len(passes_so_far) + len(carries_so_far)
                          + len(defs_so_far) + len(shots_so_far)),
        "score": f"{home_sc}-{away_sc}",
        "mode": feed.mode(),
        "provider": build_provider_status(source=feed.mode()),
        "phase": current_phase(current_minute),
    }
    try:
        ppda = compute_ppda(my_team_id, passes_so_far, defs_so_far)
        snapshot["ppda"] = engine_result_to_dict(ppda)["value"]
        tilt = compute_field_tilt(my_team_id, opp_id, passes_so_far)
        snapshot["field_tilt"] = engine_result_to_dict(tilt)["value"]
        from app.data.loaders import shots_by_team
        my_shots_so_far = shots_by_team(shots_so_far, my_team_id)
        opp_shots_so_far = shots_by_team(shots_so_far, opp_id)
        dom = compute_match_dominance(
            team_external_id=my_team_id, opponent_team_external_id=opp_id,
            team_shots=my_shots_so_far, opponent_shots=opp_shots_so_far,
            all_passes=passes_so_far, team_carries=carries_so_far,
            opponent_carries=carries_so_far,
        )
        snapshot["match_dominance"] = engine_result_to_dict(dom)["value"]
        # Live decisions (gerçek "live" özellikler) — skor yukarıda as-of hesaplandı
        sub_rec = compute_live_sub_recommendation(
            my_team_id, passes_so_far, defs_so_far,
            current_minute=current_minute, my_score=my_score,
            opponent_score=opp_score, eligible_player_ids=eligible_ids,
        )
        snapshot["live_sub_recommendation"] = engine_result_to_dict(sub_rec)["value"]
        shape = compute_live_shape_drift(
            opp_id, passes_so_far, current_minute=current_minute,
        )
        snapshot["opponent_shape_drift"] = engine_result_to_dict(shape)["value"]

        # Faz 6: maç-içi karar mekanizması
        from app.engine.momentum_tracker import compute_momentum
        from app.engine.sub_timing import compute_sub_timing
        mom = compute_momentum(
            my_team_id, opp_id, passes_so_far, defs_so_far, shots_so_far,
            current_minute=current_minute,
        ).value
        snapshot["momentum"] = {
            "score": mom.momentum_score, "holder": mom.momentum_holder,
            "press_breaking": mom.press_breaking,
            "xg_swing_alert": mom.xg_swing_alert,
            "alert_text": mom.alert_text,
        }
        timing = compute_sub_timing(
            my_team_id, passes_so_far, defs_so_far,
            current_minute=current_minute, my_score=my_score,
            opponent_score=opp_score,
        ).value
        snapshot["sub_timing"] = {
            "package": list(timing.package_recommendation),
            "rationale": timing.package_rationale,
            "advices": [
                {"player_id": a.player_external_id, "verdict": a.timing_verdict,
                 "impact": a.impact_estimate}
                for a in timing.advices[:3]
            ],
        }
        from app.engine.live_tactical_trigger import (
            compute_live_tactical_trigger,
        )
        trig = compute_live_tactical_trigger(
            my_team_id, current_minute=current_minute,
            my_score=my_score, opponent_score=opp_score,
            momentum_score=mom.momentum_score,
        ).value
        snapshot["tactical_triggers"] = [
            {"type": t.trigger_type, "urgency": t.urgency,
             "recommendation": t.recommendation}
            for t in trig.triggers if t.fired
        ]

        # Faz 7: mekânsal kontrol + bireysel eşleşme + skor-zaman reçetesi
        from app.engine.live_matchup import compute_live_matchup
        from app.engine.score_time_matrix import compute_score_time_matrix
        from app.engine.spatial_control import compute_spatial_control
        spat = compute_spatial_control(
            my_team_id, opp_id, passes_so_far, defs_so_far,
            current_minute=current_minute,
        ).value
        snapshot["spatial_control"] = {
            "gap_between_lines": spat.gap_between_lines,
            "superiority_flank": spat.superiority_flank,
            "shape_state": spat.shape_state,
            "alerts": list(spat.alerts),
        }
        match_up = compute_live_matchup(
            my_team_id, opp_id, passes_so_far, defs_so_far,
            current_minute=current_minute,
        ).value
        snapshot["live_matchup"] = {
            "struggling_defender": (
                match_up.struggling_defender.player_external_id
                if match_up.struggling_defender else None
            ),
            "hot_opponent": (
                match_up.hot_opponent.player_external_id
                if match_up.hot_opponent else None
            ),
            "alerts": list(match_up.alerts),
        }
        stm = compute_score_time_matrix(
            my_team_id, current_minute=current_minute,
            my_score=my_score, opponent_score=opp_score,
        ).value
        snapshot["score_time_matrix"] = {
            "score_state": stm.score_state,
            "posture": stm.posture,
            "closing_recipe": stm.closing_recipe,
            "alerts": list(stm.alerts),
        }

        # K kategorisi: kapanış reçetesi + risk/getiri eşiği (momentum'la zenginleştirilmiş)
        from app.engine.closing_strategy import compute_closing_strategy
        cs = compute_closing_strategy(
            my_team_id, current_minute=current_minute,
            my_score=my_score, opponent_score=opp_score,
            momentum_score=mom.momentum_score,
        ).value
        snapshot["closing_strategy"] = {
            "score_state": cs.score_state,
            "closing_phase": cs.closing_phase,
            "urgency_level": cs.urgency_level,
            "key_message": cs.key_message,
            "recipe": {
                "tempo": cs.recipe.tempo,
                "positioning": cs.recipe.positioning,
                "sub_priority": cs.recipe.sub_priority,
                "set_pieces": cs.recipe.set_pieces,
                "extra_note": cs.recipe.extra_note,
            },
            "risk_reward": {
                "take_risk": cs.risk_reward.take_risk,
                "rationale": cs.risk_reward.rationale,
                "threshold_breached": cs.risk_reward.threshold_breached,
            },
        }

        # Faz 6 #10-12: kart/sakatlık/zaman riski. player_states zaten hesaplanan
        # sub-önerisinin fatigue_score'undan beslenir (ek maliyet yok). Kart verisi
        # (sarı/düello) henüz ingest edilmiyor → şimdilik sakatlık+zaman aktif.
        from app.engine.live_risk_monitor import compute_live_risk_monitor
        _sub_recs = snapshot["live_sub_recommendation"].get("recommendations", [])
        _player_states = [
            {"player_id": r.get("player_external_id"),
             "fatigue": r.get("fatigue_score", 0.0)}
            for r in _sub_recs if r.get("player_external_id") is not None
        ]
        risk = compute_live_risk_monitor(
            my_team_id, _player_states, current_minute=current_minute,
            my_score=my_score, opponent_score=opp_score,
        ).value
        snapshot["live_risk_monitor"] = {
            "score_state": risk.score_state,
            "time_management": risk.time_management,
            "total_flags": risk.total_flags,
            "card_flags": [
                {"player_external_id": f.player_external_id, "risk_type": f.risk_type,
                 "severity": f.severity, "message": f.message}
                for f in risk.card_flags
            ],
            "injury_flags": [
                {"player_external_id": f.player_external_id, "risk_type": f.risk_type,
                 "severity": f.severity, "message": f.message}
                for f in risk.injury_flags
            ],
        }

        # Faz 5 #47: VAEP canlı momentum (player-level streaming)
        # Faz B: appearances varsa oyuncu-başına gerçek dakikaya normalize.
        snapshot["vaep"] = _compute_live_vaep(
            my_team_id=my_team_id, opp_team_id=opp_id,
            passes=passes_so_far, carries=carries_so_far, shots=shots_so_far,
            current_minute=current_minute, appearances=appearances,
        )

        # Faz 8: bağlam motoru (orkestra şefi) — tek "şimdi şunu yap" başlığı
        from app.api.context_pipeline import context_only
        lo = current_minute - 15.0
        win = {
            "passes": sum(1 for x in passes_so_far if lo <= x.minute <= current_minute),
            "defs": sum(1 for x in defs_so_far if lo <= x.minute <= current_minute),
            "shots": sum(1 for x in shots_so_far if lo <= x.minute <= current_minute),
        }
        out_like = {
            "momentum": {
                "momentum_score": mom.momentum_score,
                "momentum_holder": mom.momentum_holder,
                "press_breaking": mom.press_breaking,
                "xg_swing_alert": mom.xg_swing_alert,
                "alert_text": mom.alert_text,
            },
            "sub_timing": {
                "package_recommendation": list(timing.package_recommendation),
                "package_rationale": timing.package_rationale,
                "advices": [
                    {"player_external_id": a.player_external_id,
                     "timing_verdict": a.timing_verdict,
                     "impact_estimate": a.impact_estimate}
                    for a in timing.advices
                ],
            },
            "tactical_triggers": {
                "triggers": [
                    {"trigger_type": t.trigger_type, "fired": t.fired,
                     "recommendation": t.recommendation, "urgency": t.urgency}
                    for t in trig.triggers
                ],
            },
            "spatial_control": {
                "alerts": list(spat.alerts),
                "flank_balance": [
                    {"flank": fb.flank, "our_count": fb.our_count}
                    for fb in spat.flank_balance
                ],
            },
            "live_matchup": {"alerts": list(match_up.alerts)},
            "score_time_matrix": {
                "in_closing_phase": stm.in_closing_phase,
                "posture": stm.posture, "closing_recipe": stm.closing_recipe,
            },
        }
        ctx = context_only(
            out_like, current_minute=current_minute,
            my_score=my_score, opp_score=opp_score, win=win,
        )
        snapshot["context"] = {
            "one_liner": ctx.get("one_liner"),
            "primary": ctx.get("primary"),
            "secondary": ctx.get("secondary", []),
        }

        # Veri kalitesi: event akışının güvenilirliği (dropout/seyrek/bayat feed).
        # Önce hesaplanır ki güven skoru gerçek feed kalitesini kullanabilsin.
        from app.engine.data_quality import EventStamp, compute_data_quality
        _stamps = (
            [EventStamp(p.minute, "pass") for p in passes_so_far]
            + [EventStamp(d.minute, "defensive_action") for d in defs_so_far]
            + [EventStamp(s.minute, "shot") for s in shots_so_far]
            + [EventStamp(c.minute, "carry") for c in carries_so_far]
        )
        dq = compute_data_quality(_stamps, current_minute=current_minute)
        snapshot["data_quality"] = {
            "score": dq.quality_score, "status": dq.status,
            "density_per_min": dq.density_per_min,
            "largest_gap_min": dq.largest_gap_min,
            "freshness_min": dq.freshness_min,
            "missing_types": list(dq.missing_types),
            "flags": list(dq.flags),
        }

        # Canlı güven: en kritik 3 sinyale veri-yeterliliği skoru ekle. Gerçek
        # veri-kalite skoru (dropout/bayat dahil) güvene beslenir; erken/seyrek/
        # bozuk feed → "düşük" (sahte kesinlik üretmez).
        from app.engine.live_confidence import live_signal_confidence
        corroboration = _count_corroborating_signals(snapshot)

        def _conf(cs) -> dict[str, Any]:
            return {"score": cs.score, "label": cs.label, "drivers": list(cs.drivers)}

        ctx_conf = live_signal_confidence(
            events_so_far=snapshot["events_so_far"],
            current_minute=current_minute, corroborating_signals=corroboration,
            data_quality=dq.quality_score,
        )
        snapshot["confidence"] = {
            "context": _conf(ctx_conf),
            "live_sub_recommendation": _conf(ctx_conf),
            "momentum": _conf(ctx_conf),
        }
        # Güven düşükse one_liner'ı KORU, ayrı bir saha-güvenliği notu ekle.
        if ctx_conf.label == "düşük":
            snapshot["context"]["confidence_note"] = (
                "sinyal zayıf — teyit bekle"
            )
    except (ValueError, ZeroDivisionError, KeyError, TypeError) as e:
        snapshot["error"] = str(e)
    return snapshot


@router.websocket("/matches/{match_id}/live")
async def matches_live(
    websocket: WebSocket,
    match_id: int,
    my_team_id: int = Query(...),
    interval_seconds: int = Query(default=10),
    max_minute: float = Query(default=90.0,
        description="Opsiyonel sert tavan; replay normalde son-event'te biter"),
    speed: float = Query(default=5.0,
        description="Her interval'da ilerleyen match-dakikası (replay hızı)"),
    tenant_id: str = Query(default="t-default"),
    session: Session = Depends(get_session),
) -> None:
    """WebSocket: her N saniyede tactical snapshot push.

    Replay modu: event-zaman güdümlü saat; replay gerçek son-event dakikasında
    biter (düz 90 değil). `speed` wall-time→match-time eşler.
    """
    interval = max(MIN_INTERVAL_SECONDS, min(MAX_INTERVAL_SECONDS, interval_seconds))
    await websocket.accept()
    _ACTIVE_CONNECTIONS["count"] += 1
    log.info(
        "ws connect match=%d team=%d interval=%ds tenant=%s",
        match_id, my_team_id, interval, tenant_id,
    )
    session.info["tenant_id"] = tenant_id
    start_wall = time.monotonic()
    # Bağlantı-başına trend state (global DEĞİL) — son N snapshot özeti.
    from app.engine.live_alerts import compute_live_alerts
    from app.engine.live_confidence import summarize_trend
    from app.engine.replay_clock import ClockConfig, advance_minute
    from app.notifications import build_default_notifier, dispatch_live_alerts
    trend_history: list[dict[str, Any]] = []
    # Kritik uyarı telefona (Telegram/WhatsApp/e-posta) — yalnızca gerçek kanal
    # yapılandırılmışsa. Bağlantı-başına dedup: aynı uyarı tekrar push edilmez.
    _notifier = build_default_notifier()
    _push_critical = bool(_notifier.active_channel_names())
    _alert_sent: set[str] = set()
    try:
        # Feed'i bağlantı başında BİR kez kur (event'ler bir kez yüklenir).
        # Fabrika config'ten kaynağı seçer; bugün replay, gerçek sağlayıcı
        # bağlanınca aynı WS döngüsü değişmeden onu kullanır.
        try:
            feed: ReplayFeed = build_live_feed(session, match_id)
        except ValueError as e:
            await websocket.send_text(json.dumps({"error": str(e)}))
            return
        last_event_minute = feed.last_event_minute()
        clock_cfg = ClockConfig(speed=speed, start_minute=SIMULATION_START_MINUTE)
        while True:
            elapsed_wall = time.monotonic() - start_wall
            current_minute, ended = advance_minute(
                elapsed_wall=elapsed_wall, interval=interval,
                last_event_minute=last_event_minute, config=clock_cfg,
            )
            # max_minute opsiyonel sert tavan (test geri-uyumu)
            if current_minute >= max_minute:
                current_minute = max_minute
                ended = True
            snapshot = _compute_live_snapshot(
                feed, match_id, my_team_id, current_minute,
            )
            # Zamansal trend: snapshot'tan küçük bir özet biriktir, yön türet.
            trend_history.append(_trend_frame(snapshot))
            del trend_history[:-TREND_HISTORY_LIMIT]
            snapshot["trend"] = summarize_trend(trend_history)
            # Proaktif uyarılar (J): trend + veri kalitesinden eşik-aşımı uyarısı.
            _alerts = compute_live_alerts(
                current_minute=current_minute,
                momentum_trend=snapshot.get("trend"),
                data_quality_status=(snapshot.get("data_quality") or {}).get("status"),
            )
            snapshot["live_alerts"] = {
                "total": _alerts.total, "critical": _alerts.critical,
                "warning": _alerts.warning, "info": _alerts.info,
                "alerts": [
                    {"type": a.alert_type, "severity": a.severity,
                     "message": a.message, "dedup_key": a.dedup_key,
                     "player_id": a.player_external_id}
                    for a in _alerts.alerts
                ],
            }
            await websocket.send_text(json.dumps(snapshot, default=str))
            # Kritik uyarıyı telefona it (event-loop'u bloklamadan, WS'i bozmadan).
            if _push_critical and _alerts.critical:
                with contextlib.suppress(Exception):
                    await asyncio.to_thread(
                        dispatch_live_alerts, _alerts, _notifier,
                        min_severity="critical", already_sent=_alert_sent,
                    )
            if ended:
                await websocket.send_text(json.dumps({
                    "type": "match_ended", "current_minute": current_minute,
                }))
                break
            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.sleep(interval)
    except WebSocketDisconnect:
        log.info("ws disconnect match=%d team=%d", match_id, my_team_id)
    finally:
        _ACTIVE_CONNECTIONS["count"] -= 1


@router.get("/active-connections")
def active_connections() -> dict[str, int]:
    """Şu an kaç WebSocket bağlı (observability)."""
    return _ACTIVE_CONNECTIONS.copy()
