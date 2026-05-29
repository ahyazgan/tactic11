"""Match Memory — maç-içi hafıza katmanı (Faz 8 #3).

Sistem "o anı" görüyor ama geçmişi unutuyor. Bu katman maç boyunca biriken
snapshot dizisini (frame'ler) okuyup zaman-bağlantıları kurar:

- Momentum dönüşleri: "momentum 58'de bize döndü, 66'da rakibe geçti".
- Sürekli trend: "sol kanat 55'ten beri verimsizleşiyor".
- Rakip değişimi: "rakip 55'te formasyon değiştirdi".
- BAĞLANTI (asıl değer): rakip değişimi + ardından bizim bir kanadın düşüşü
  zaman olarak çakışıyorsa → "rakip 55'te değişti, o andan beri sol kanat düştü".

Bu bağlantı kurulmadan 75. dakikada doğru sub önerisi zor. Hafıza ekleyince
sistem proaktif olur.

Saf fonksiyon. Frame listesi (kronolojik) → aktif "thread"ler.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.audit import AuditRecord, EngineResult

ENGINE_NAME = "engine.match_memory"
ENGINE_VERSION = "1"

# Kanat düşüşü: baz değere göre bu oran kadar düşüş + en az bu kadar frame sürmüş
FLANK_DROP_RATIO = 0.40
FLANK_MIN_FRAMES = 2
# Bağlantı penceresi: rakip değişiminden sonra bu kadar dk içinde başlayan düşüş ilişkili
LINK_WINDOW_MIN = 8.0
FLANKS = ("left", "center", "right")


@dataclass(frozen=True)
class MemoryFrame:
    """Tek bir tick'te kaydedilen hafıza karesi."""

    minute: float
    momentum_score: float = 0.0
    opponent_formation: str | None = None
    # kanat verimliliği (xT veya benzeri) — {"left":.., "center":.., "right":..}
    flank_xt: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class MemoryThread:
    kind: str                # "momentum_flip" | "flank_decline" | "opponent_change" | "linked"
    since_minute: float
    text: str
    linked_minute: float | None = None


@dataclass(frozen=True)
class MatchMemoryReport:
    current_minute: float
    frames_seen: int
    threads: tuple[MemoryThread, ...] = field(default_factory=tuple)
    last_momentum_flip_minute: float | None = None


def _opponent_changes(frames: list[MemoryFrame]) -> list[tuple[float, str, str]]:
    """(minute, from_formation, to_formation) listesi."""
    changes: list[tuple[float, str, str]] = []
    last: str | None = None
    for f in frames:
        if f.opponent_formation is None:
            continue
        if last is not None and f.opponent_formation != last:
            changes.append((f.minute, last, f.opponent_formation))
        last = f.opponent_formation
    return changes


def _flank_decline(frames: list[MemoryFrame], flank: str) -> tuple[float, float, float] | None:
    """Bir kanatta sürekli düşüş varsa (since_minute, baseline, current) döner."""
    series: list[tuple[float, float]] = []
    for f in frames:
        v = f.flank_xt.get(flank)
        if v is not None:
            series.append((f.minute, float(v)))
    if len(series) < FLANK_MIN_FRAMES + 1:
        return None
    # En yüksek noktadan bu yana düşüyor mu
    peak_idx = max(range(len(series)), key=lambda i: series[i][1])
    if peak_idx >= len(series) - FLANK_MIN_FRAMES:
        return None  # tepe çok yeni, sürekli düşüş yok
    baseline = series[peak_idx][1]
    current = series[-1][1]
    if baseline <= 0:
        return None
    drop = (baseline - current) / baseline
    # tepeden sonra genel olarak düşmüş + son değer tepeden belirgin düşük
    if drop >= FLANK_DROP_RATIO and current < baseline:
        return (series[peak_idx][0], baseline, current)
    return None


def compute_match_memory(
    history: list[MemoryFrame],
    *,
    current_minute: float,
) -> EngineResult[MatchMemoryReport]:
    frames = sorted(history, key=lambda f: f.minute)
    threads: list[MemoryThread] = []

    # Momentum dönüşleri
    last_flip: float | None = None
    prev_sign = 0
    for f in frames:
        sign = 1 if f.momentum_score > 0.2 else -1 if f.momentum_score < -0.2 else 0
        if sign != 0 and prev_sign != 0 and sign != prev_sign:
            last_flip = f.minute
        if sign != 0:
            prev_sign = sign
    if last_flip is not None:
        holder = "bize" if prev_sign > 0 else "rakibe"
        threads.append(MemoryThread(
            kind="momentum_flip", since_minute=last_flip,
            text=f"momentum {last_flip:.0f}. dk'da {holder} döndü",
        ))

    # Rakip formasyon değişimleri
    changes = _opponent_changes(frames)
    for minute, frm, to in changes:
        threads.append(MemoryThread(
            kind="opponent_change", since_minute=minute,
            text=f"rakip {minute:.0f}. dk'da {frm}→{to} geçti",
        ))

    # Kanat düşüşleri + bağlantı
    for flank in FLANKS:
        decline = _flank_decline(frames, flank)
        if decline is None:
            continue
        since, baseline, current = decline
        side = {"left": "sol", "center": "merkez", "right": "sağ"}[flank]
        # Bu düşüş bir rakip değişimini takip ediyor mu?
        linked_minute: float | None = None
        for minute, _frm, _to in changes:
            if minute <= since <= minute + LINK_WINDOW_MIN:
                linked_minute = minute
                break
        if linked_minute is not None:
            threads.append(MemoryThread(
                kind="linked", since_minute=since, linked_minute=linked_minute,
                text=(f"rakip {linked_minute:.0f}. dk'da değişti, o andan beri "
                      f"{side} kanadımız düştü (xT {baseline:.2f}→{current:.2f})"),
            ))
        else:
            threads.append(MemoryThread(
                kind="flank_decline", since_minute=since,
                text=(f"{side} kanat {since:.0f}'ten beri verimsizleşiyor "
                      f"(xT {baseline:.2f}→{current:.2f})"),
            ))

    report = MatchMemoryReport(
        current_minute=current_minute,
        frames_seen=len(frames),
        threads=tuple(threads),
        last_momentum_flip_minute=last_flip,
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="match", subject_id=0,
        metric="match_memory",
        value={
            "frames_seen": len(frames),
            "threads": [t.kind for t in threads],
            "last_momentum_flip": last_flip,
        },
        inputs={"current_minute": current_minute,
                "flank_drop_ratio": FLANK_DROP_RATIO,
                "link_window_min": LINK_WINDOW_MIN},
        formula="frame dizisi → momentum flip + kanat düşüş + rakip değişim + bağlantı",
    )
    return EngineResult(value=report, audit=audit)
