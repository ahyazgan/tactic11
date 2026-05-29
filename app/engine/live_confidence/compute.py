"""Live Confidence + Trend — canlı snapshot için güven ve zamansal yön (saf).

İki saf yardımcı:
1. `live_signal_confidence` — bir canlı sinyalin ne kadar güvenilir olduğunu
   maç ilerlemesi + event yoğunluğu + teyit eden sinyal sayısına göre skorlar.
   Çekirdek `engine.confidence.score_confidence` kullanılır (yeniden yazılmaz).
2. `summarize_trend` — son N snapshot özetinden momentum yönü, tilt/dominance
   trendi ve "primary" istikrarını çıkarır (saha-içi "momentum 3'tür bize karşı").

Saf: DB/HTTP/state yok. Snapshot geçmişini TUTAN yapı çağıran (live.py WS
handler) tarafındadır; buraya yalnız liste geçilir.

Kalibrasyon notu — `score_confidence`'ın sample_size terimi SAMPLE_FULL=12'de
doygunlaşır; canlı maçta event sayısı ilk dakikalarda bile 12'yi geçer, yani
sample boyutu canlı ayrımı yapmaz. Bu yüzden veri-yeterliliğini ayrıca
`data_quality` (event yoğunluğu) ve `magnitude` (maç ilerleme × yoğunluk) ile
besliyoruz; böylece "erken dakika / az event → düşük" gerçekten elde edilir.
"""
from __future__ import annotations

from app.engine.confidence import ConfidenceScore, score_confidence

ENGINE_NAME = "engine.live_confidence"
ENGINE_VERSION = "1"

# Maç olgunluğu: ~60. dakikaya kadar oyun yeterince açılır; bu noktadan sonra
# sinyaller tam güç. (90 yerine 60: ikinci yarı ortasında zaten olgun sayılır.)
MATURE_MINUTE = 60.0
# Veri yoğunluğu: ~300 event istikrarlı bir canlı okuma için yeterli yoğunluk
# (bir yarı tipik 400-600 event; 300 sağlam bir alt eşik).
DENSE_EVENTS = 300
# Trend penceresi + minimum frame (altında "warming_up").
TREND_WINDOW = 5
TREND_MIN_FRAMES = 3
# Momentum yön bandı: |delta| bunun altıysa "dengeli".
MOMENTUM_FLAT_EPS = 0.08
# Tilt/dominance trend bandı.
SERIES_FLAT_EPS = 0.05


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def live_signal_confidence(
    *,
    events_so_far: int,
    current_minute: float,
    corroborating_signals: int = 0,
    data_quality: float | None = None,
) -> ConfidenceScore:
    """Canlı bir sinyalin güven skoru.

    - magnitude = maç ilerleme × veri kalitesi (min): erken dakika VEYA zayıf
      veri → düşük; ikisi de yüksekse → yüksek.
    - data_quality: `engine.data_quality.compute_data_quality(...).quality_score`
      verilirse onu kullan (dropout/bayat/eksik-tip de içerir, salt yoğunluktan
      zengin); verilmezse salt yoğunluk proxy'sine (events/DENSE_EVENTS) düş.
    - corroboration = aynı yönü işaret eden diğer sinyal sayısı.
    """
    minute_term = _clamp01(current_minute / MATURE_MINUTE)
    density_term = _clamp01(events_so_far / DENSE_EVENTS)
    quality = _clamp01(data_quality) if data_quality is not None else density_term
    magnitude = round(min(minute_term, density_term, quality), 3)
    return score_confidence(
        sample_size=events_so_far,
        magnitude=magnitude,
        corroboration=corroborating_signals,
        data_quality=round(quality, 3),
    )


def _direction(delta: float, eps: float) -> str:
    if delta > eps:
        return "artan"
    if delta < -eps:
        return "azalan"
    return "sabit"


def _sustained(values: list[float], eps: float) -> int:
    """Sondan başlayarak son değerle aynı yönde (işaret) kaç frame sürüyor."""
    if not values:
        return 0
    last = values[-1]
    sign = 1 if last > eps else -1 if last < -eps else 0
    if sign == 0:
        return 0
    count = 0
    for v in reversed(values):
        v_sign = 1 if v > eps else -1 if v < -eps else 0
        if v_sign == sign:
            count += 1
        else:
            break
    return count


def summarize_trend(history: list[dict]) -> dict:
    """Snapshot özet listesinden (eski→yeni) trend çıkar.

    Beklenen frame anahtarları (hepsi opsiyonel): momentum_score, field_tilt,
    dominance, primary. Yetersiz geçmişte {"status": "warming_up"} döner.
    """
    frames = history[-TREND_WINDOW:]
    if len(frames) < TREND_MIN_FRAMES:
        return {"status": "warming_up", "frames": len(frames)}

    out: dict = {"status": "ok", "window": len(frames)}

    # Momentum yönü + süreklilik
    moms = [f["momentum_score"] for f in frames
            if f.get("momentum_score") is not None]
    if len(moms) >= 2:
        delta = round(moms[-1] - moms[0], 3)
        if delta > MOMENTUM_FLAT_EPS:
            direction = "bize doğru"
        elif delta < -MOMENTUM_FLAT_EPS:
            direction = "rakibe doğru"
        else:
            direction = "dengeli"
        out["momentum"] = {
            "direction": direction,
            "delta": delta,
            "sustained_snapshots": _sustained(moms, MOMENTUM_FLAT_EPS),
        }

    # field_tilt / dominance trendi (varsa)
    for key in ("field_tilt", "dominance"):
        vals = [f[key] for f in frames if f.get(key) is not None]
        if len(vals) >= 2:
            out[key] = _direction(vals[-1] - vals[0], SERIES_FLAT_EPS)

    # Primary istikrarı: sondan kaç frame aynı öneri tekrar ediyor
    primaries = [f.get("primary") for f in frames]
    latest = primaries[-1]
    repeats = 0
    if latest is not None:
        for p in reversed(primaries):
            if p == latest:
                repeats += 1
            else:
                break
    out["stability"] = {
        "primary": latest,
        "repeats": repeats,
        "stable": repeats >= TREND_MIN_FRAMES,
    }
    return out
