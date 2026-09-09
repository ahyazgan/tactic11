"""Replay (tekrar) tespiti — canlı maç zaman çizgisini bozan kareleri ayıkla.

## Sorun

TV yayınında tekrarlar canlı akışın arasına girer. Bir kare tekrar görüntüsüne
aitse, canlı dakikayla kaydedilirse:

- 68. dakikadaki bir atak 71. dakikaya yazılır (zaman çizgisi bozulur)
- aynı olay iki kez sayılır (şut/pas istatistiği şişer)
- karar etkisi ölçümü yanlış pencereyi kıyaslar

## Kapsam — neyin zaten çözüldüğü

Farklı kamera açısından gelen tekrarlar **zaten** ayıklanıyor: kalibrasyon
takibi kopuyor, kare "kalibre edilmemiş" sayılıyor ve konum üretilmiyor
(bkz. `pitch_lines.PerFrameCalibrator`). Kalan gerçek boşluk **ana kameradan
gelen AĞIR ÇEKİM tekrar**: aynı açı olduğu için sorunsuz kalibre olur ve canlı
dakikayla kaydedilir. Bu modülün hedefi odur.

## İki bağımsız işaret

1. **Ağır çekim** — tekrarlar yavaşlatılır. Kareler arası global hareket, canlı
   oyunun kendi ortalamasına göre belirgin düşer. Mutlak eşik KULLANILMAZ:
   "yavaş" kameraya, maça ve sahneye göre değişir; ölçüt canlı akışın kendi
   medyanına oranıdır.

2. **Skorboard kayboldu** — yayıncıların çoğu tekrar sırasında skor/logo
   bindirmesini gizler. Nerede olduğunu bilmemize gerek yok: canlı oyunda
   zamanla DEĞİŞMEYEN pikseller bindirmedir (kendi kendini kalibre eder).
   O bölge birden değişmeye başlarsa bindirme kalkmıştır.

İkisi bağımsız olduğu için birlikte çok daha güvenilir: yavaş bir pozisyon
(oyun durdu) tek başına tekrar sanılmaz; skorboard duruyorsa canlıdır.

## Dürüstlük

Şüphede kalırsa **canlı** sayar. Yanlışlıkla canlı kareyi atmak veri kaybıdır;
yanlışlıkla tekrarı canlı saymak zaman çizgisini bozar — ama tekrar tespiti
sezgiseldir ve gerçek yayın görüntüsüyle ayarlanmadan agresif davranmamalıdır.
Bu yüzden karar İKİ işaretten en az birinin GÜÇLÜ olmasını ister ve eşikler
`ReplayThresholds` ile dışarıdan ayarlanabilir.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median

# Canlı medyanın bu oranının altındaki hareket "ağır çekim" adayı
SLOW_MOTION_RATIO = 0.45
# Bindirme bölgesi bu oranda değiştiyse "skorboard kalktı"
OVERLAY_CHANGE_RATIO = 0.35
# Canlı medyanı hesaplamak için gereken en az örnek
MIN_BASELINE_SAMPLES = 12


@dataclass(frozen=True)
class ReplayThresholds:
    slow_motion_ratio: float = SLOW_MOTION_RATIO
    overlay_change_ratio: float = OVERLAY_CHANGE_RATIO
    min_baseline: int = MIN_BASELINE_SAMPLES


@dataclass(frozen=True)
class ReplayVerdict:
    is_replay: bool
    slow_motion: bool
    overlay_gone: bool
    motion_ratio: float          # kare hareketi / canlı medyan
    overlay_change: float        # bindirme bölgesindeki değişim oranı
    reason: str


def live_motion_baseline(motions: list[float], *, thresholds: ReplayThresholds | None = None) -> float | None:
    """Canlı oyunun tipik kare-arası hareketi (medyan).

    Ortalama değil medyan: tek bir hızlı çevirme ortalamayı yukarı çeker ve
    sonraki her kare "yavaş" görünür.
    """
    t = thresholds or ReplayThresholds()
    usable = [m for m in motions if m >= 0.0]
    if len(usable) < t.min_baseline:
        return None
    return float(median(usable))


def classify_frame(
    *,
    motion: float,
    baseline: float | None,
    overlay_change: float | None,
    thresholds: ReplayThresholds | None = None,
) -> ReplayVerdict:
    """Tek kare için tekrar hükmü.

    `baseline` None ise (yeterli canlı örnek yok) ağır çekim işareti
    kullanılmaz — referans olmadan "yavaş" tanımsızdır.
    `overlay_change` None ise bindirme işareti kullanılmaz (bindirme bulunamadı).
    """
    t = thresholds or ReplayThresholds()
    ratio = (motion / baseline) if baseline and baseline > 1e-9 else float("nan")
    slow = bool(baseline and baseline > 1e-9 and ratio < t.slow_motion_ratio)
    gone = bool(overlay_change is not None and overlay_change > t.overlay_change_ratio)

    if slow and gone:
        reason = (f"tekrar: hareket canlı medyanın %{ratio * 100:.0f}'i ve "
                  f"skorboard bindirmesi kalkmış")
    elif gone:
        reason = "tekrar: skorboard bindirmesi kalkmış"
    elif slow:
        reason = (f"yavaş kare (canlı medyanın %{ratio * 100:.0f}'i) ama skorboard "
                  f"yerinde — oyun durmuş olabilir, canlı sayıldı")
    else:
        reason = ""
    # Bindirme işareti tek başına yeterli; ağır çekim TEK BAŞINA yeterli DEĞİL
    # (oyun durunca da hareket düşer). Şüphede canlı sayılır.
    return ReplayVerdict(
        is_replay=gone, slow_motion=slow, overlay_gone=gone,
        motion_ratio=round(ratio, 3) if ratio == ratio else 0.0,
        overlay_change=round(overlay_change or 0.0, 3), reason=reason,
    )


def find_overlay_mask(frame_stack, *, relative_ratio: float = 0.1,
                      absolute_floor: float = 0.05):
    """Canlı karelerden değişmeyen bölgeyi (skorboard/logo) bul — venv-cv.

    `frame_stack`: (N, H, W) gri kareler. Zamanla varyansı düşük olan pikseller
    bindirmedir; saha/oyuncu bölgesi sürekli değişir ve elenir.

    Eşik GÖRELİDİR: sahnenin kendi varyans medyanının `relative_ratio` katı.
    Mutlak eşik kameradan kameraya taşınmıyor — ölçüldü: durgun bir drone
    klibinde tüm karenin varyans medyanı 1.5 iken sabit eşik 2.0 karenin
    %65'ini "bindirme" sanıyordu. Sıkıştırma gürültüsü de sahneye göre değişir.
    """
    import numpy as np

    stack = np.asarray(frame_stack, dtype=np.float32)
    if stack.ndim != 3 or stack.shape[0] < MIN_BASELINE_SAMPLES:
        return None
    var = stack.var(axis=0)
    scene = float(np.median(var))
    threshold = max(absolute_floor, scene * relative_ratio)
    mask = var < threshold
    # Çok küçük bir bölge güvenilir bindirme değildir (gürültü olabilir)
    if mask.mean() < 0.005 or mask.mean() > 0.6:
        return None
    return mask


def overlay_change_ratio(frame_gray, reference_gray, mask, *, tol: float = 12.0) -> float | None:
    """Bindirme bölgesi referanstan ne kadar saptı (0..1) — venv-cv."""
    import numpy as np

    if mask is None:
        return None
    diff = np.abs(np.asarray(frame_gray, dtype=np.float32)
                  - np.asarray(reference_gray, dtype=np.float32))
    changed = (diff[mask] > tol)
    return float(changed.mean()) if changed.size else None
