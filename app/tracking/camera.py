"""Kamera davranışı tespiti — görüntü sabit mi, çeviriyor mu, yayın mı?

## Neden gerekli

Takip hattı **tek ve sabit** bir homografi kullanır: kalibrasyon bir kez yapılır,
her karede aynı matrisle piksel → saha metresi çevrilir. Bu yalnız kamera hiç
oynamıyorsa doğrudur. Kamera çevirdiğinde oyuncular sahada YER DEĞİŞTİRMİŞ gibi
görünür — ölçüldü (4K, gerçek kalibrasyon):

    kamera  30 px kayarsa → oyuncu sahada 1.1 m kayar
    kamera 100 px kayarsa → oyuncu sahada 3.6 m kayar

`engine.tracking_signals` eşikleri 2.5–4 m'dir. Yani **kamera hareketi tek başına
sahte taktik sinyal üretir**: "geri hat 4 m yükseldi" der, oysa hat yerinde
durmuştur, kamera kaymıştır. Yayın kamerası saniyede yüzlerce piksel çevirir.

Bu modül videoyu işlemeden ÖNCE kameranın nasıl davrandığına bakar ve karelere
doğru `source` etiketini koyar. Etiket motorlara kadar gider: `video_tracking`
(sabit kamera) sürekli takip sayılır ve tüm şekil/bölge analizleri açılır;
`broadcast_tracking` ise top-merkezli kabul edilir — StatsBomb 360 freeze
frame'lerle aynı sınıf — ve yalnız topa göreli sinyaller üretilir.

## Nasıl ayırt eder

İki ardışık örnek kare arasında:
- **faz korelasyonu** global kaymayı ve onun tutarlılığını (response) verir.
  Yüksek response + belirgin kayma = çevirme (pan/tilt/zoom).
- **histogram uzaklığı** içeriğin ne kadar değiştiğini verir.
  Büyük değişim + DÜŞÜK response = kesme (farklı kamera/çekim), çünkü kesmede
  tutarlı bir kayma yoktur.

Bu ayrım önemlidir: hızlı bir çevirme de histogramı çok değiştirir, ama kayması
tutarlıdır; kesmede tutarlılık yoktur.

## Sınır

Eşikler sezgiseldir ve gerçek yayın görüntüsüyle ayarlanmalıdır. Modülün amacı
kesin sınıflandırma değil, **sistemin sabit kamera varsayımıyla yayın görüntüsüne
kendinden emin çöp üretmesini engellemektir**. Şüphede kalırsa yayın (kısıtlı)
tarafa düşer — yanlış sinyal üretmektense az sinyal üretmek yeğdir.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

STATIC_SOURCE = "video_tracking"
BROADCAST_SOURCE = "broadcast_tracking"

# --- eşikler (gerçek yayın görüntüsüyle ayarlanmalı) ------------------------ #
CUT_RESPONSE_MAX = 0.08     # faz korelasyonu güveni bunun altındaysa tutarsız
CUT_HIST_MIN = 0.45         # histogram uzaklığı bunun üstündeyse içerik değişti
STATIC_MOTION_PX = 2.0      # örnek kare başına bu kadar kayma "sabit" sayılır
BROADCAST_CUTS_PER_MIN = 3.0
BROADCAST_MOVING_FRACTION = 0.35


@dataclass(frozen=True)
class CameraVerdict:
    kind: str               # static | panning | broadcast | unknown
    source_name: str        # karelere yazılacak kaynak etiketi
    frames_compared: int
    cuts: int
    cuts_per_minute: float
    moving_fraction: float
    mean_motion_px: float
    max_motion_px: float
    continuous: bool = True
    note: str = ""


def classify_pairs(
    motions_px: list[float], responses: list[float], hist_dists: list[float],
) -> list[str]:
    """Ardışık kare çiftlerini etiketle: cut | moving | static.

    Kesme = içerik çok değişti AMA tutarlı bir kayma yok. Çevirme = kayma var ve
    tutarlı. Bu ayrım olmadan hızlı çevirmeler kesme sanılır.
    """
    out: list[str] = []
    for motion, response, hist in zip(motions_px, responses, hist_dists, strict=True):
        if hist >= CUT_HIST_MIN and response < CUT_RESPONSE_MAX:
            out.append("cut")
        elif abs(motion) > STATIC_MOTION_PX:
            out.append("moving")
        else:
            out.append("static")
    return out


def summarise(labels: list[str], motions_px: list[float], *, sample_fps: float) -> CameraVerdict:
    """Etiketlerden kamera hükmü + karelere yazılacak kaynak adı."""
    n = len(labels)
    if n == 0:
        return CameraVerdict(
            kind="unknown", source_name=BROADCAST_SOURCE, frames_compared=0, cuts=0,
            cuts_per_minute=0.0, moving_fraction=0.0, mean_motion_px=0.0,
            max_motion_px=0.0, continuous=False,
            note="kamera analizi yapılamadı — güvenli tarafta kalınıp top-merkezli sayıldı",
        )
    cuts = sum(1 for lbl in labels if lbl == "cut")
    moving = sum(1 for lbl in labels if lbl == "moving")
    seconds = n / max(sample_fps, 1e-6)
    cuts_per_min = round(cuts / max(seconds / 60.0, 1e-6), 2)
    moving_fraction = round(moving / n, 3)
    abs_motions = [abs(m) for m in motions_px] or [0.0]
    mean_motion = round(sum(abs_motions) / len(abs_motions), 2)
    max_motion = round(max(abs_motions), 2)

    if cuts_per_min >= BROADCAST_CUTS_PER_MIN or (cuts > 0 and moving_fraction >= BROADCAST_MOVING_FRACTION):
        kind, continuous = "broadcast", False
        note = (f"yayın görüntüsü: dakikada {cuts_per_min:.1f} kesme, karelerin "
                f"%{moving_fraction * 100:.0f}'inde kamera hareketi. Sabit homografi "
                f"geçersiz → kareler TOP-MERKEZLİ sayıldı; şekil/bölge analizi kapalı, "
                f"yalnız topa göreli sinyaller üretilir.")
    elif moving_fraction >= BROADCAST_MOVING_FRACTION:
        kind, continuous = "panning", False
        note = (f"kamera çeviriyor (karelerin %{moving_fraction * 100:.0f}'i, ortalama "
                f"{mean_motion:.1f} px). Kalibrasyon tek ve sabit olduğu için konumlar "
                f"kayar → top-merkezli sayıldı. Tam saha analizi için kare başına "
                f"kalibrasyon (saha çizgisi tespiti) gerekir.")
    else:
        kind, continuous = "static", True
        note = (f"kamera sabit (ortalama {mean_motion:.1f} px, en fazla {max_motion:.1f} px)"
                f" — sabit homografi geçerli, tam analiz açık.")
    return CameraVerdict(
        kind=kind, source_name=STATIC_SOURCE if continuous else BROADCAST_SOURCE,
        frames_compared=n, cuts=cuts, cuts_per_minute=cuts_per_min,
        moving_fraction=moving_fraction, mean_motion_px=mean_motion,
        max_motion_px=max_motion, continuous=continuous, note=note,
    )


def analyze_video(
    path: str | Path, *, sample_fps: float = 4.0, max_seconds: float | None = 60.0,
) -> CameraVerdict:
    """Videonun ilk `max_seconds` saniyesine bakıp kamera hükmü ver (venv-cv).

    Tüm videoyu taramaya gerek yok: kamera davranışı bir yayında baştan bellidir.
    """
    import cv2
    import numpy as np

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return summarise([], [], sample_fps=sample_fps)
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    step = max(1, int(round(src_fps / max(sample_fps, 0.1))))
    limit = int(src_fps * max_seconds) if max_seconds else None

    motions: list[float] = []
    responses: list[float] = []
    hists: list[float] = []
    prev_gray = None
    prev_hist = None
    idx = 0
    while True:
        ok, frame = cap.read()
        if not ok or (limit is not None and idx > limit):
            break
        if idx % step:
            idx += 1
            continue
        idx += 1
        small = cv2.resize(frame, (320, 180), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).astype(np.float32)
        hist = cv2.calcHist([small], [0, 1, 2], None, [8, 8, 8], [0, 256] * 3)
        cv2.normalize(hist, hist)
        if prev_gray is not None and prev_hist is not None:
            (dx, dy), response = cv2.phaseCorrelate(prev_gray, gray)
            motions.append(float((dx ** 2 + dy ** 2) ** 0.5))
            responses.append(float(response))
            # correlation 1.0 = aynı → uzaklık 0
            corr = float(cv2.compareHist(prev_hist, hist, cv2.HISTCMP_CORREL))
            hists.append(max(0.0, 1.0 - corr))
        prev_gray, prev_hist = gray, hist
    cap.release()
    return summarise(classify_pairs(motions, responses, hists), motions, sample_fps=sample_fps)
