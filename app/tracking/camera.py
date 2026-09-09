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

# Kare başına kalibrasyon açıkken, karelerin bu oranından AZI kalibre olduysa
# konumlar gerçek ama ÇOK SEYREK demektir: şekil/bölge analizi az sayıda kareden
# hesaplanır ve gürültülü olur. O yüzden kareler top-merkezli sayılır.
# NOT: Gerçek yayın görüntüsüyle ayarlanmalıdır; şu an sezgiseldir.
MIN_CALIBRATED_RATIO = 0.35

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
    return [
        classify_pair(motion, response, hist)
        for motion, response, hist in zip(motions_px, responses, hist_dists, strict=True)
    ]


def plan_mode(*, moving: bool, per_frame_mode: str, reacquire_mode: str) -> dict:
    """Kamera hükmünden ne açılacağına karar ver — saf mantık, cv2 gerekmez.

    `moving`: kamera hareketli/yayın mı. Modlar "auto" | "on" | "off".

    Kaynak etiketi PLANLANAN değerdir: kare başına kalibrasyon açıksa konumlar
    gerçek saha konumu olacağı varsayılır. Bu varsayım işlem sonrası
    `source_after_run` ile GERÇEKLEŞENE göre düzeltilir.

    Canlı hat (`scripts/track_live.py`) ve çevrimdışı hat
    (`scripts/track_video.py`) İKİSİ DE bunu kullanır: aynı görüntüde farklı
    karar vermeleri, karelerin bir sınıfta yazılıp başka bir sınıfta
    yorumlanmasına yol açar.
    """
    per_frame = per_frame_mode == "on" or (per_frame_mode == "auto" and moving)
    reacquire = reacquire_mode == "on" or (reacquire_mode == "auto" and moving)
    return {
        "moving": moving,
        "per_frame": per_frame,
        "reacquire": reacquire,
        "source": STATIC_SOURCE if (per_frame or not moving) else BROADCAST_SOURCE,
    }


def source_after_run(mode: dict, calibrated_ratio: float | None) -> tuple[str, str]:
    """İşlem sonrası kaynak etiketi + (varsa) düşürme gerekçesi.

    Etiketi TAHMİNE göre değil GERÇEKLEŞENE göre vermek için. Kalibrasyonun
    tutacağını baştan varsayıp "tam saha analizi açık" demek, tutmadığında avuç
    dolusu kareden şekil sinyali üretmek demektir. Kalibre olan kareler yine
    gerçek konum taşır — sorun doğruluk değil, SEYREKLİK.
    """
    if not mode["per_frame"] or calibrated_ratio is None:
        return str(mode["source"]), ""
    if calibrated_ratio >= MIN_CALIBRATED_RATIO:
        return str(mode["source"]), ""
    return BROADCAST_SOURCE, (
        f"kalibre oran %{calibrated_ratio * 100:.0f} < "
        f"%{MIN_CALIBRATED_RATIO * 100:.0f} — kareler top-merkezli sayıldı"
    )


def classify_pair(motion: float, response: float, hist: float) -> str:
    """Tek kare çifti için etiket — `classify_pairs`in akış hali.

    Eşikler tek yerde kalsın diye ikisi de bunu çağırır; canlı hat ile
    çevrimdışı analiz aynı kesme tanımını kullanmalı, yoksa biri kesme dediğine
    öbürü çevirme der ve davranış videoya göre değişir.
    """
    if hist >= CUT_HIST_MIN and response < CUT_RESPONSE_MAX:
        return "cut"
    if abs(motion) > STATIC_MOTION_PX:
        return "moving"
    return "static"


class CutDetector:
    """Kare kare kesme tespiti — takip hattının içinde kullanılır (venv-cv).

    `analyze_video` videoyu ÖNCEDEN tarar ve tek bir hüküm verir; bu sınıf ise
    kareler geldikçe çalışır, çünkü kalibrasyon kesmeyi **olduğu anda** bilmek
    zorundadır: kesmeden sonra homografi süreklilik referansını kaybeder.

    Kareler `analyze_video` ile AYNI ölçekte (320x180) karşılaştırılır; eşikler
    (`STATIC_MOTION_PX` vb.) o ölçekte piksel cinsinden tanımlı, farklı
    boyutta ölçüp aynı eşiği uygulamak sessizce yanlış olur.
    """

    SCALE = (320, 180)

    def __init__(self) -> None:
        self._prev_gray = None
        self._prev_hist = None
        self.cuts = 0
        self.frames = 0
        # Son karenin ölçümleri. Tekrar süzgeci (replay.ReplayFilter) aynı
        # büyüklüklere ihtiyaç duyuyor; faz korelasyonunu ikinci kez hesaplamak
        # yerine buradan okur.
        self.last_gray = None        # (180, 320) float32 gri kare
        self.last_motion = 0.0       # kareler arası global kayma (px, bu ölçekte)

    def update(self, bgr) -> str:
        """Bir kare al, önceki kareye göre etiketi döndür.

        İlk karede referans yoktur → "unknown" (kesme SAYILMAZ; ilk kareyi
        kesme saymak her segmentin başında takibi gereksiz yere düşürürdü).
        """
        import cv2
        import numpy as np

        small = cv2.resize(bgr, self.SCALE, interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).astype(np.float32)
        hist = cv2.calcHist([small], [0, 1, 2], None, [8, 8, 8], [0, 256] * 3)
        cv2.normalize(hist, hist)
        label = "unknown"
        motion = 0.0
        if self._prev_gray is not None and self._prev_hist is not None:
            (dx, dy), response = cv2.phaseCorrelate(self._prev_gray, gray)
            motion = float((dx ** 2 + dy ** 2) ** 0.5)
            corr = float(cv2.compareHist(self._prev_hist, hist, cv2.HISTCMP_CORREL))
            label = classify_pair(motion, float(response), max(0.0, 1.0 - corr))
            self.frames += 1
            if label == "cut":
                self.cuts += 1
        self._prev_gray, self._prev_hist = gray, hist
        self.last_gray, self.last_motion = gray, motion
        return label


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
