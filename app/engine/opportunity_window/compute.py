"""Opportunity Window Detector — maç-içi "şimdi hamle yap" momentleri.

TacticalSnapshot serisi (her N dk bir) → çoklu sinyal birleştirilerek
"opportunity window" tespit edilir. TD için somut "şu an risk al / pres
kaldır / sub at" sinyali.

Pencere türleri:
  - opp_fatigued       : rakip yorgun (distance_covered + press düşüş)
  - opp_card_pressure  : rakip kart riskinde (sarı > 2, kırmızı yakın)
  - opp_subs_exhausted : rakip sub hakkı azalmış (≥ 2 kullanmış)
  - momentum_ours      : son 5 dk xG bizim lehimize
  - opp_press_drop     : rakip pres yüksekliği bariz düştü
  - opp_disorganized   : rakip ardışık 2+ snapshot sinyali

Her pencere için: type, minute_open, confidence (0..1), why, recommended_action,
decay_after_minutes (kapanma tahmini).

Pure compute. Snapshot listesi tek girdi.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from app.audit import AuditRecord, EngineResult

ENGINE_NAME = "engine.opportunity_window"
ENGINE_VERSION = "1"

# Eşikler (tek noktadan tunable)
FATIGUE_DISTANCE_DROP = 0.12      # rakip distance_covered_normalized drop
PRESS_DROP_THRESHOLD = 0.20       # rakip press_intensity drop (0..1)
MOMENTUM_XG_GAP = 0.20            # son 5 dk our_xg - opp_xg
YELLOW_PRESSURE_COUNT = 2         # rakip yellow ≥ 2
SUB_EXHAUSTED_COUNT = 3           # rakip 3+ sub kullanmış (5'ten)
WINDOW_DEFAULT_DECAY = 10.0       # dk


@dataclass(frozen=True)
class TacticalSnapshot:
    """Bir andaki taktiksel durum (anlık ölçüm)."""
    minute: float
    our_press_intensity: float = 0.5         # 0..1
    opp_press_intensity: float = 0.5
    opp_distance_covered: float = 0.7        # normalize 0..1 (1=fresh)
    opp_sub_count_used: int = 0              # 0..5
    opp_yellow_count: int = 0
    opp_red_imminent: bool = False
    our_xg_recent_5min: float = 0.0
    opp_xg_recent_5min: float = 0.0


@dataclass(frozen=True)
class OpportunityWindow:
    type: str
    minute_open: float
    confidence: float                        # 0..1
    why: str                                 # TR
    recommended_action: str                  # TR
    decay_after_minutes: float = WINDOW_DEFAULT_DECAY


@dataclass(frozen=True)
class OpportunityWindowReport:
    snapshot_count: int
    windows: tuple[OpportunityWindow, ...]
    summary: str
    notes: tuple[str, ...] = field(default_factory=tuple)


def _check_fatigue(prev: TacticalSnapshot, cur: TacticalSnapshot) -> OpportunityWindow | None:
    drop = prev.opp_distance_covered - cur.opp_distance_covered
    if drop < FATIGUE_DISTANCE_DROP:
        return None
    confidence = min(1.0, drop / (FATIGUE_DISTANCE_DROP * 2.5))
    return OpportunityWindow(
        type="opp_fatigued",
        minute_open=cur.minute,
        confidence=round(confidence, 2),
        why=f"Rakip mesafe normalize {prev.opp_distance_covered:.2f}→{cur.opp_distance_covered:.2f} (-{drop:.2f}) — yorgunluk",
        recommended_action="Tempo'yu artır + hızlı kanat geçişleri; pres'i bir kademe yükselt",
        decay_after_minutes=8.0,
    )


def _check_press_drop(prev: TacticalSnapshot, cur: TacticalSnapshot) -> OpportunityWindow | None:
    drop = prev.opp_press_intensity - cur.opp_press_intensity
    if drop < PRESS_DROP_THRESHOLD:
        return None
    confidence = min(1.0, drop / (PRESS_DROP_THRESHOLD * 2.0))
    return OpportunityWindow(
        type="opp_press_drop",
        minute_open=cur.minute,
        confidence=round(confidence, 2),
        why=f"Rakip pres yoğunluğu {prev.opp_press_intensity:.2f}→{cur.opp_press_intensity:.2f} — düşük block'a çekildi",
        recommended_action="Kontrolü al, geniş ortalar; cut-back için iç koşular hazır",
        decay_after_minutes=10.0,
    )


def _check_momentum(cur: TacticalSnapshot) -> OpportunityWindow | None:
    gap = cur.our_xg_recent_5min - cur.opp_xg_recent_5min
    if gap < MOMENTUM_XG_GAP:
        return None
    confidence = min(1.0, gap / (MOMENTUM_XG_GAP * 2.0))
    return OpportunityWindow(
        type="momentum_ours",
        minute_open=cur.minute,
        confidence=round(confidence, 2),
        why=f"Son 5 dk xG farkı +{gap:.2f} (bizim {cur.our_xg_recent_5min:.2f} vs rakip {cur.opp_xg_recent_5min:.2f})",
        recommended_action="Bu dalgayı uzat — taze atak oyuncusu hazırla, set-piece routine devrede",
        decay_after_minutes=7.0,
    )


def _check_card_pressure(cur: TacticalSnapshot) -> OpportunityWindow | None:
    if cur.opp_yellow_count < YELLOW_PRESSURE_COUNT and not cur.opp_red_imminent:
        return None
    confidence = 0.9 if cur.opp_red_imminent else min(0.85, 0.5 + 0.1 * cur.opp_yellow_count)
    why = (
        f"Rakipte {cur.opp_yellow_count} sarı"
        + (" + kırmızı imminent" if cur.opp_red_imminent else "")
    )
    return OpportunityWindow(
        type="opp_card_pressure",
        minute_open=cur.minute,
        confidence=round(confidence, 2),
        why=why,
        recommended_action="Sarı alan oyuncuyu hedefle — dribble + 1v1 koşu; provoke etmeden temasa zorla",
        decay_after_minutes=15.0,
    )


def _check_subs_exhausted(cur: TacticalSnapshot) -> OpportunityWindow | None:
    if cur.opp_sub_count_used < SUB_EXHAUSTED_COUNT:
        return None
    confidence = min(1.0, 0.6 + 0.1 * (cur.opp_sub_count_used - SUB_EXHAUSTED_COUNT + 1))
    return OpportunityWindow(
        type="opp_subs_exhausted",
        minute_open=cur.minute,
        confidence=round(confidence, 2),
        why=f"Rakip {cur.opp_sub_count_used} sub kullandı — taze oyuncu kapasitesi azaldı",
        recommended_action="Bizim taze sub'larımız tempo'yu sürdürsün; oyuncu rotasyonu lehimize",
        decay_after_minutes=20.0,
    )


def _check_disorganized(snapshots: list[TacticalSnapshot]) -> OpportunityWindow | None:
    """Ardışık 2+ snapshot'ta fatigue+press_drop birleşimi → dağılma."""
    if len(snapshots) < 3:
        return None
    last3 = snapshots[-3:]
    fatigue_count = 0
    press_drop_count = 0
    for i in range(1, 3):
        if last3[i - 1].opp_distance_covered - last3[i].opp_distance_covered >= FATIGUE_DISTANCE_DROP / 2:
            fatigue_count += 1
        if last3[i - 1].opp_press_intensity - last3[i].opp_press_intensity >= PRESS_DROP_THRESHOLD / 2:
            press_drop_count += 1
    if fatigue_count >= 2 and press_drop_count >= 2:
        return OpportunityWindow(
            type="opp_disorganized",
            minute_open=last3[-1].minute,
            confidence=0.85,
            why="Ardışık 2+ snapshot fatigue + press drop — rakip dağılıyor",
            recommended_action="Final phase: 3 taze hücum oyuncusu, full court press, set-piece bekle",
            decay_after_minutes=12.0,
        )
    return None


def compute_opportunity_windows(
    snapshots: Iterable[TacticalSnapshot],
) -> EngineResult[OpportunityWindowReport]:
    """Snapshot dizisinden opportunity window'lar tespit et."""
    slist = sorted(list(snapshots), key=lambda s: s.minute)
    windows: list[OpportunityWindow] = []
    notes: list[str] = []

    if len(slist) == 0:
        return _empty_result(len(slist))

    # Tek-snapshot kontroller (her snapshot'ta)
    for cur in slist:
        w = _check_momentum(cur)
        if w:
            windows.append(w)
        w = _check_card_pressure(cur)
        if w:
            windows.append(w)
        w = _check_subs_exhausted(cur)
        if w:
            windows.append(w)

    # Çift-snapshot kontroller (ardışık fark)
    for prev, cur in zip(slist, slist[1:], strict=False):
        w = _check_fatigue(prev, cur)
        if w:
            windows.append(w)
        w = _check_press_drop(prev, cur)
        if w:
            windows.append(w)

    # Üç-snapshot meta kontrol
    w = _check_disorganized(slist)
    if w:
        windows.append(w)

    # Aynı tip & yakın dakikada duplicate'leri ele
    deduped = _dedupe(windows)
    deduped.sort(key=lambda x: (-x.confidence, x.minute_open))

    if not deduped:
        summary = f"{len(slist)} snapshot — açık bir opportunity penceresi yok"
    else:
        top = deduped[0]
        summary = (
            f"{len(deduped)} pencere; en güçlü: {top.type} "
            f"({top.minute_open:.0f}. dk, conf {top.confidence:.2f})"
        )
        notes.append(top.recommended_action)

    report = OpportunityWindowReport(
        snapshot_count=len(slist),
        windows=tuple(deduped),
        summary=summary,
        notes=tuple(notes),
    )
    audit = AuditRecord(
        engine=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        subject_type="match",
        subject_id=0,
        metric="opportunity_window",
        value={
            "snapshot_count": len(slist),
            "window_count": len(deduped),
            "types": sorted({w.type for w in deduped}),
            "top_confidence": deduped[0].confidence if deduped else 0.0,
        },
        inputs={
            "thresholds": {
                "fatigue_distance_drop": FATIGUE_DISTANCE_DROP,
                "press_drop_threshold": PRESS_DROP_THRESHOLD,
                "momentum_xg_gap": MOMENTUM_XG_GAP,
                "yellow_pressure_count": YELLOW_PRESSURE_COUNT,
                "sub_exhausted_count": SUB_EXHAUSTED_COUNT,
            },
        },
        formula=(
            "Tek-snapshot (momentum, card, subs) + çift-snapshot (fatigue, "
            "press_drop) + üç-snapshot (disorganized) kombo; eşik geçen pencere"
        ),
    )
    return EngineResult(value=report, audit=audit)


def _dedupe(windows: list[OpportunityWindow]) -> list[OpportunityWindow]:
    """Aynı tipte yakın dakika (< 6 dk) pencereleri birleştir, en yüksek conf kalır."""
    by_type: dict[str, list[OpportunityWindow]] = {}
    for w in windows:
        by_type.setdefault(w.type, []).append(w)
    out: list[OpportunityWindow] = []
    for group in by_type.values():
        group.sort(key=lambda x: x.minute_open)
        kept: list[OpportunityWindow] = []
        for w in group:
            if kept and w.minute_open - kept[-1].minute_open < 6.0:
                # En yüksek conf'u koru
                if w.confidence > kept[-1].confidence:
                    kept[-1] = w
                continue
            kept.append(w)
        out.extend(kept)
    return out


def _empty_result(n: int) -> EngineResult[OpportunityWindowReport]:
    report = OpportunityWindowReport(
        snapshot_count=n,
        windows=(),
        summary="Snapshot yok — opportunity tespiti yapılamadı",
        notes=("En az 1 snapshot gerek",),
    )
    return EngineResult(
        value=report,
        audit=AuditRecord(
            engine=ENGINE_NAME,
            engine_version=ENGINE_VERSION,
            subject_type="match",
            subject_id=0,
            metric="opportunity_window",
            value={"snapshot_count": n, "window_count": 0, "types": [], "top_confidence": 0.0},
            inputs={},
            formula="insufficient",
        ),
    )
