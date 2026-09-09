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
from typing import Any, TypeGuard

from sqlalchemy import select

from app.db import models
from app.engine.context_engine import compute_context
from app.engine.decision_signal import CandidateSignal
from app.engine.match_memory import MemoryFrame, compute_match_memory
from app.sports import football

_URGENCY_BY_LEVEL = {"high": 0.9, "medium": 0.6, "low": 0.35}
# decision_type → context sinyal tipleri (feedback yayılımı)
# decision_type → hangi sinyal tiplerine geçmiş isabet olarak yayılacağı.
#
# "tactical" ANAHTARI ŞART: API'nin kabul ettiği kanonik tip
# "tactical_instruction" ama veritabanındaki kararların ezici çoğunluğu
# "tactical" olarak yazılmış. Ölçüldü (2026-09-09): ölçülmüş 293 kararın
# 280'i (%96) "tactical" tipinde ve bu anahtar burada YOKTU — yani geri
# besleme döngüsü sessizce ölüydü, `historical_hit_rate` hiç dolmuyordu
# (sürücü karnesinde `has_history` her kararda 0.000 çıktı).
_TACTICAL_TYPES = ("tactical", "spatial", "matchup", "momentum_us", "momentum_opp")
# Sinyal tipine özel geçmiş isabet oranı için gereken en az ölçülmüş karar.
# Altında kaba (decision_type) oran korunur: n=2'lik bir tip %0 ya da %100 der
# ve güveni uçurur.
MIN_SIGNAL_TYPE_SAMPLES = 12

_HITRATE_SPREAD = {
    "substitution": ("substitution", "risk"),
    "formation_change": _TACTICAL_TYPES,
    "tactical_instruction": _TACTICAL_TYPES,
    "tactical": _TACTICAL_TYPES,
}


def _win_counts(p: list, d: list, s: list, current_minute: float,
                window: float = 15.0) -> dict[str, int]:
    lo = current_minute - window
    return {
        "passes": sum(1 for x in p if lo <= x.minute <= current_minute),
        "defs": sum(1 for x in d if lo <= x.minute <= current_minute),
        "shots": sum(1 for x in s if lo <= x.minute <= current_minute),
    }


def _soft_saturate(x: float, *, half: float = 1.0) -> float:
    """Sınırsız bir büyüklüğü [0,1)'e SIRALAMAYI KORUYARAK sıkıştır.

    `min(1.0, x)` sert kırpması "eşiği biraz aşan" ile "eşiği katbekat aşan"ı
    aynı sayıya indiriyordu. Ölçüldü (n=437): kararların %64'ü magnitude
    1.00'da toplanmıştı ve o grubun olumsuz sonuç oranı iki katıydı — yani
    ayırt edecek bilgi tam da kırpmada yok oluyordu.

    x/(x+half): x=0 → 0, x=half → 0.5, x=2·half → 0.667, x→∞ → 1.
    Monotondur; büyük değerler birbirinden ayrılabilir kalır.
    """
    x = max(0.0, x)
    return x / (x + half) if half > 0 else 0.0


def build_candidates(
    out: dict[str, Any], *, current_minute: float, win: dict[str, int],
) -> list[CandidateSignal]:
    """8 engine dict çıktısından normalize sinyaller üret."""
    cands: list[CandidateSignal] = []
    ev = win["passes"] + win["defs"]

    def _is_dict(x: object) -> TypeGuard[dict[str, Any]]:
        return isinstance(x, dict) and "error" not in x

    # momentum — YÖNE GÖRE AYRI SİNYAL TİPİ
    #
    # Eskiden tek tip ("tactical") ve `magnitude=min(1.0, abs(ms))` idi. İki
    # ayrı kusur vardı, ikisi de gerçek veriyle ölçüldü (n=437):
    #
    # 1. `abs()` YÖNÜ SİLİYORDU. "Momentum bizde" ile "Rakip baskı kuruyor"
    #    aynı magnitude'ü ve aynı güveni alıyordu — oysa sonuçları taban
    #    tabana zıt:
    #        biz baskın  (n=314): %21 olumlu, %39 olumsuz, xG farkı -0.011
    #        rakip baskın (n= 75): %44 olumlu, %5  olumsuz, xG farkı +0.037
    #    Ayrı tip verilince geçmiş isabet oranı (`historical_hit_rate`) ikisini
    #    ayrı öğrenebiliyor. Zıt durumlar zıt tavsiye ister; tek kovaya
    #    koymak öğrenmeyi imkânsız kılıyordu.
    #
    # 2. SERT KIRPMA doygunluk yaratıyordu: kararların %64'ü magnitude 1.00'da
    #    toplanıyordu ve o grubun olumsuz oranı iki katıydı. Artık kırpılmamış
    #    `momentum_raw` yumuşak doyumla (x/(1+x)) sıkıştırılıyor: 1.2 ile 5.0
    #    artık farklı değerler alıyor, sıralama korunuyor.
    m = out.get("momentum")
    if _is_dict(m):
        ms = float(m.get("momentum_score", 0.0))
        raw_ms = float(m.get("momentum_raw", ms))
        pb = bool(m.get("press_breaking"))
        xg = bool(m.get("xg_swing_alert"))
        holder = m.get("momentum_holder", "balanced")
        fired = holder != "balanced" or pb or xg
        urgency = min(1.0, abs(ms) + (0.3 if pb else 0.0) + (0.3 if xg else 0.0))
        cands.append(CandidateSignal(
            key="momentum",
            signal_type=("momentum_us" if holder == "us"
                         else "momentum_opp" if holder == "opponent"
                         else "tactical"),
            headline=m.get("alert_text", "Momentum sinyali"),
            urgency=urgency, fired=fired, minute=current_minute,
            sample_size=win["defs"] + win["shots"],
            magnitude=_soft_saturate(abs(raw_ms)),
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

    # closing_strategy (closing — K kategorisi reçete + risk eşiği)
    cs = out.get("closing_strategy")
    if _is_dict(cs):
        urgency_level = cs.get("urgency_level", "low")
        risk = cs.get("risk_reward", {}) or {}
        take_risk = bool(risk.get("take_risk"))
        # fire koşulu: urgency yüksek/kritik VEYA risk eşiği fırlamış
        fired = urgency_level in ("high", "critical") or take_risk
        if fired:
            urg = {"critical": 0.95, "high": 0.8,
                   "moderate": 0.55, "low": 0.3}.get(urgency_level, 0.5)
            recipe = cs.get("recipe", {}) or {}
            headline = (
                cs.get("key_message")
                or f"Kapanış: tempo={recipe.get('tempo', '?')}, "
                   f"ikame={recipe.get('sub_priority', '?')}"
            )
            # sample_size = skor+dakika her zaman tam bilinir → tam destek (12)
            cands.append(CandidateSignal(
                key="closing_strategy", signal_type="closing",
                headline=headline, urgency=urg, fired=True,
                minute=current_minute, sample_size=12, magnitude=urg,
            ))

    # foul_pressure (friction — I.1 ritim kırma + hakem kart eşiği)
    fp = out.get("foul_pressure")
    if _is_dict(fp):
        opp_tactical = bool(fp.get("tactical_fouling_alert"))
        our_high = bool(fp.get("our_high_foul_alert"))
        ref_pressure = fp.get("referee_card_pressure", "low")
        flags = fp.get("player_flags", []) or []
        critical_flag = any(f.get("risk_level") == "critical" for f in flags)
        fired = opp_tactical or our_high or critical_flag or ref_pressure == "high"
        if fired:
            urg = 0.85 if critical_flag else (
                0.7 if ref_pressure == "high" else (
                    0.65 if opp_tactical else 0.55))
            cands.append(CandidateSignal(
                key="foul_pressure", signal_type="friction",
                headline=fp.get("tactical_advice", "Faul ritmi anormal"),
                urgency=urg, fired=True, minute=current_minute,
                sample_size=int(fp.get("our_fouls_window", 0))
                            + int(fp.get("opp_fouls_window", 0)),
                magnitude=urg,
            ))

    # hot_hand (hot_hand — G.2 sıcak el)
    hh = out.get("hot_hand")
    if _is_dict(hh):
        is_hot = bool(hh.get("hot_streak"))
        if is_hot:
            cands.append(CandidateSignal(
                key="hot_hand", signal_type="hot_hand",
                headline=hh.get("tactical_advice", "Sıcak el — şut açıklarını zorla"),
                urgency=0.7, fired=True, minute=current_minute,
                sample_size=int(hh.get("shots_window", 0)),
                magnitude=min(1.0, float(hh.get("shot_volume_ratio", 0)) / 2.0),
            ))

    # set_piece_opportunity (set_piece — H.1)
    spo = out.get("set_piece_opportunity")
    if _is_dict(spo):
        high_freq = bool(spo.get("high_frequency"))
        low_conv = bool(spo.get("low_conversion"))
        fired = high_freq
        if fired:
            cands.append(CandidateSignal(
                key="set_piece_opportunity", signal_type="set_piece_opportunity",
                headline=spo.get("tactical_advice", "Standart top sıcak"),
                urgency=0.75 if low_conv else 0.55, fired=True,
                minute=current_minute,
                sample_size=int(spo.get("total_set_pieces", 0)),
                magnitude=0.8 if low_conv else 0.5,
            ))

    # referee_tendency (referee — J.1)
    rt = out.get("referee_tendency")
    if _is_dict(rt):
        sev = rt.get("severity", "unknown")
        fired = sev in ("strict", "lenient")
        if fired:
            cands.append(CandidateSignal(
                key="referee_tendency", signal_type="referee",
                headline=rt.get("tactical_advice", f"Hakem {sev}"),
                urgency=0.55 if sev == "strict" else 0.35,
                fired=True, minute=current_minute,
                sample_size=int(rt.get("matches_analyzed", 0)),
                magnitude=abs(float(rt.get("severity_score", 1.0)) - 1.0),
            ))

    # star_feed (feed — G.3 yıldız beslemesi)
    sf = out.get("star_feed")
    if _is_dict(sf):
        state = sf.get("involvement_state", "balanced")
        action = sf.get("suggested_action", "OK")
        fired = state in ("starved", "well-fed")
        if fired:
            urg = {"starved": 0.75, "well-fed": 0.55}.get(state, 0.4)
            cands.append(CandidateSignal(
                key="star_feed", signal_type="feed",
                headline=sf.get("tactical_advice", "Yıldız beslemesi anormal"),
                urgency=urg, fired=True, minute=current_minute,
                sample_size=int(sf.get("team_passes_window", 0)),
                magnitude=urg,
                detail={"suggested_action": action,
                        "pass_share_pct": sf.get("pass_share_pct", 0.0)},
            ))

    # tracking_signals (spatial) — pozisyon verisi (video / 360) varsa
    ts = out.get("tracking_signals")
    if _is_dict(ts):
        frames = int(ts.get("frames_used", 0) or 0)
        for f in (ts.get("findings") or [])[:2]:   # en acil iki bulgu
            if not isinstance(f, dict):
                continue
            cands.append(CandidateSignal(
                key=f"tracking:{f.get('key', 'signal')}", signal_type="spatial",
                headline=str(f.get("headline", "Pozisyon sinyali")),
                urgency=float(f.get("urgency", 0.5)), fired=True, minute=current_minute,
                # kare sayısı = kanıt; sample_size event sayısıyla aynı ölçekte olsun
                sample_size=frames, magnitude=float(f.get("magnitude", 0.0)),
                detail={"source": "tracking", **(f.get("detail") or {})},
            ))

    # space_map (spatial) — "nerede boşluk var": bölgesel üstünlük, hat boşluğu,
    # zayıf kanat. tracking_signals DEĞİŞİMİ söyler, bu YERİ söyler; ikisi
    # birbirini tamamladığı için ayrı sinyal olarak girer.
    sm = out.get("space_map")
    if _is_dict(sm):
        frames = int(sm.get("frames_used", 0) or 0)
        for f in (sm.get("findings") or [])[:2]:
            if not isinstance(f, dict):
                continue
            cands.append(CandidateSignal(
                key=f"space:{f.get('key', 'zone')}", signal_type="spatial",
                headline=str(f.get("headline", "Bölge sinyali")),
                urgency=float(f.get("urgency", 0.5)), fired=True, minute=current_minute,
                sample_size=frames, magnitude=float(f.get("magnitude", 0.0)),
                detail={"source": "space_map", **(f.get("detail") or {})},
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


def _apply_calibration(ctx, cmap):
    """Karardaki güven değerlerini kalibre olasılıkla değiştir.

    Eşleme kurulmadıysa (yetersiz geçmiş) karar aynen döner. Etiket
    (yüksek/orta/düşük) da yeni değere göre yeniden hesaplanır — aksi halde
    "yüksek" yazıp %55 gösteren bir kart çıkardı.
    """
    import dataclasses

    from app.engine.confidence.compute import HIGH_THRESHOLD, MED_THRESHOLD

    if not cmap.fitted:
        return ctx

    def _label(v: float) -> str:
        return "yüksek" if v >= HIGH_THRESHOLD else "orta" if v >= MED_THRESHOLD else "düşük"

    # Eşleme ayırt etmiyorsa (tüm binler aynı olasılığa çökmüş) her karara AYNI
    # sayı verilir. O sayıyı "bu kararın güveni" diye sunmak sahte kesinliktir:
    # gerçekte söylenen "bu takımın taban oranı". Ölçüldü (n=518): kanıt skoru
    # sonuçla TERS ilişkili olduğu için izotonik regresyon her şeyi çökertiyor.
    if cmap.discriminates:
        not_metni = f"kalibre edildi ({cmap.samples} karar, yön: {cmap.direction})"
    else:
        not_metni = (
            f"kanıt seviyesi sonucu AYIRT ETMİYOR ({cmap.samples} karar, "
            f"AUC {cmap.auc:.2f}); gösterilen değer bu takımın taban oranı "
            f"(%{cmap.base_rate * 100:.0f}), karara özel bir olasılık değil"
        )

    def _fix(action):
        if action is None:
            return None
        p = round(cmap.apply(action.confidence), 3)
        return dataclasses.replace(
            action, confidence=p, confidence_label=_label(p),
            evidence=action.confidence, calibration_note=not_metni,
        )

    return dataclasses.replace(
        ctx,
        primary=_fix(ctx.primary),
        secondary=tuple(_fix(a) for a in ctx.secondary),
    )


def _confidence_calibration(session, team_id: int):
    """Takımın geçmişinden kanıt skoru → olasılık eşlemesi kur.

    `score_confidence` bir olasılık değil KANIT GÜCÜ üretir; arayüzde ise
    "bu karar tutar" olasılığı gibi okunuyor. Ölçüldü: sistem ortalama %84
    diyor, gerçekleşme %58. Mevcut `historical_hit_rate` terimi bunu
    düzeltemiyor — beş terimden biri, ağırlığı 0.10, nötr 0.5'e göre tartılıyor,
    yani skoru en fazla ±0.05 oynatabiliyor.

    Burada geçmişteki (kaydedilmiş güven, ölçülmüş sonuç) çiftlerinden eşleme
    kurulur. Yetersiz geçmişte eşleme kurulmaz ve ham skor korunur.
    """
    from app.engine.confidence.calibration import fit_calibration

    rows = session.execute(
        select(models.Decision.confidence, models.Decision.outcome).where(
            models.Decision.sport == football.SPORT_NAME,
            models.Decision.team_external_id == team_id,
            models.Decision.recommended.is_(True),
            models.Decision.confidence.is_not(None),
            models.Decision.outcome.in_(("positive", "negative")),
        )
    ).all()
    return fit_calibration([(float(c), o == "positive") for c, o in rows])


def _hit_rate(
    session, team_id: int, *,
    score_state: str | None = None,
) -> dict[str, float]:
    """decision outcome'larından signal_type → geçmiş isabet oranı.

    score_state verilirse aynı durumdaki kararlara filtreler (örn. "trailing"
    + "tactical_instruction" → 'Geride 0-1 80. dk tempo yükselt' tipi
    kararların oranı). context_json'da score_state alanı varsa kullanılır.
    """
    rows = session.execute(
        select(models.Decision).where(
            models.Decision.sport == football.SPORT_NAME,
            models.Decision.team_external_id == team_id,
            models.Decision.outcome.in_(("positive", "negative")),
        )
    ).scalars().all()
    by_type: dict[str, list[int]] = {}          # decision_type → sonuçlar (kaba)
    by_signal: dict[str, list[int]] = {}        # signal_type → sonuçlar (ince)
    for r in rows:
        ctx: dict = {}
        if r.context_json:
            try:
                loaded = _json.loads(r.context_json)
                ctx = loaded if isinstance(loaded, dict) else {}
            except (ValueError, TypeError):
                ctx = {}
        if score_state is not None and ctx.get("score_state") != score_state:
            continue
        ok = 1 if r.outcome == "positive" else 0
        by_type.setdefault(r.decision_type, []).append(ok)
        # Kararla birlikte SİNYAL TİPİ saklandıysa ince kırılım da birikir.
        sig = ctx.get("signal_type")
        if isinstance(sig, str) and sig:
            by_signal.setdefault(sig, []).append(ok)

    # Önce kaba oran: decision_type'ın oranı ilgili tüm sinyal tiplerine yayılır.
    out: dict[str, float] = {}
    for dtype, results in by_type.items():
        if not results:
            continue
        rate = sum(results) / len(results)
        for sig_type in _HITRATE_SPREAD.get(dtype, ()):
            out[sig_type] = rate

    # Sonra İNCE oran kaba oranı EZER — yeterli örnek varsa.
    #
    # Neden gerekli: kaba yayma tek bir oranı "tactical, spatial, matchup,
    # momentum_us, momentum_opp"un HEPSİNE veriyordu. Oysa ölçüldü (n=437):
    # momentum_opp %44 tutuyor, momentum_us %21. Tek kovaya koymak bu farkı
    # öğrenilemez kılıyor — sistem zıt iki durumu aynı güvenle sunuyordu.
    #
    # Az örnekte ince orana geçilmez: n=2'lik bir tip %0 ya da %100 der ve
    # güveni uçurur. Eşiğin altında kaba oran korunur.
    for sig_type, results in by_signal.items():
        if len(results) >= MIN_SIGNAL_TYPE_SAMPLES:
            out[sig_type] = sum(results) / len(results)
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
        diff = (my_score or 0) - (opp_score or 0)
        state = "leading" if diff > 0 else "trailing" if diff < 0 else "drawing"
        # State-filtered hit_rate: aynı durumdaki kararlar üzerinden
        # ("trailing-tactical" → sadece geride iken verilen taktik kararlar)
        hit = _hit_rate(session, my_team_id, score_state=state)
        if not hit:
            # Fallback: state filtresi yetersizse (veri az) tüm tarihçeye düş
            hit = _hit_rate(session, my_team_id)

        ctx = compute_context(
            candidates, current_minute=current_minute, score_state=state,
            memory_threads=memory_threads, memory_theme_hints=hints,
            historical_hit_rate=hit or None,
        ).value

        # Kanıt skorunu takımın kendi geçmişinden öğrenilen OLASILIĞA çevir.
        # Ham skor "ne kadar bilgim var"ı ölçer; koça ve kalibrasyon ucuna
        # sunulan sayı "bu karar tutar mı" olmalı.
        cmap = _confidence_calibration(session, my_team_id)
        ctx = _apply_calibration(ctx, cmap)

        _record_snapshot(session, match, my_team_id, current_minute, out)

        return {"context": asdict(ctx), "match_memory": asdict(memory)}
    except (ValueError, ZeroDivisionError, KeyError, TypeError, AttributeError) as e:
        return {"context": {"error": str(e)[:120]}}
