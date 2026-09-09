"""Görüntüden saha çizgisi çıkarma + kare başına kalibrasyon takibi (venv-cv).

`homography_fit` homografiyi çizgilere oturtur ama "çizgi nerede" bilgisini
görüntüden almak gerekir. Burası o kısım:

1. **Çim maskesi** — HSV'de yeşil aralık. Tribün, skorboard, oyuncu formaları
   ve reklam panoları böylece elenir; sahanın dışındaki beyazlar çizgi sanılmaz.
2. **Beyaz çizgi pikselleri** — çim içinde kalan, komşularından belirgin parlak
   olan ince yapılar. Oyuncuların beyaz formaları da parlaktır; morfolojik
   açma (ince yapı filtresi) çizgileri bırakıp gövdeleri atar.
3. **Mesafe dönüşümü** — her piksel için en yakın çizgi pikseline uzaklık.
   `homography_fit.score_homography` bunu okur.

`PerFrameCalibrator` bunları bir arada tutar: her karede önceki homografiden
başlayıp iyileştirir. Kamera bir karede az oynadığı için başlangıç hep yakındır;
uzaklaşırsa (kesme, ani zoom) oturma başarısız olur ve kare **kalibre edilmemiş**
sayılır — konum üretilmez. Sessizce kaymış homografiyle konum üretmek, sahte
taktik sinyal demektir (bkz. app/tracking/camera.py).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.tracking.calibration import PitchCalibration
from app.tracking.homography_fit import (
    DEFAULT_TOLERANCE_PX,
    FitResult,
    corners_from_homography,
    homography_from_corners,
    refine_homography,
)

# Çim rengi (HSV). Saha aydınlatması/çim tonu değişir; gerekirse ayarlanmalı.
GRASS_HSV_LOW = (30, 40, 40)
GRASS_HSV_HIGH = (90, 255, 255)
# Çizgi kalınlığı bu değerden ince yapılar çizgi sayılır (piksel, 720p ölçeğinde)
LINE_THICKNESS_PX = 9
WHITE_MIN_VALUE = 140          # çizgi pikseli en az bu parlaklıkta olmalı
MIN_LINE_PIXELS = 400          # bu kadar çizgi pikseli yoksa kalibrasyon denenmez


@dataclass(frozen=True)
class LineExtraction:
    mask: np.ndarray           # bool, çizgi pikselleri
    dist_map: np.ndarray       # float32, en yakın çizgiye uzaklık (px)
    line_pixels: int
    grass_ratio: float         # karenin ne kadarı çim (saha görüyor muyuz?)


def extract_lines(bgr: np.ndarray) -> LineExtraction:
    """Kareden beyaz saha çizgilerini çıkar + mesafe haritası üret."""
    import cv2

    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    grass = cv2.inRange(hsv, np.array(GRASS_HSV_LOW), np.array(GRASS_HSV_HIGH))
    # Çim maskesindeki delikleri (oyuncular, çizgiler) kapat → saha bölgesi
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (25, 25))
    pitch_region = cv2.morphologyEx(grass, cv2.MORPH_CLOSE, kernel)
    grass_ratio = float((pitch_region > 0).mean())

    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    # İnce yapı filtresi: açma (opening) kalın nesneleri bırakır; farkı almak
    # ince olanları (çizgileri) verir. Oyuncu gövdeleri kalındır, elenir.
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (LINE_THICKNESS_PX, LINE_THICKNESS_PX))
    opened = cv2.morphologyEx(gray, cv2.MORPH_OPEN, k)
    thin = cv2.subtract(gray, opened)
    _, lines = cv2.threshold(thin, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    lines = cv2.bitwise_and(lines, lines, mask=pitch_region)
    lines[gray < WHITE_MIN_VALUE] = 0

    mask = lines > 0
    # Mesafe dönüşümü çizgi OLMAYAN pikseller için hesaplanır
    dist = cv2.distanceTransform((~mask).astype(np.uint8), cv2.DIST_L2, 3)
    return LineExtraction(
        mask=mask, dist_map=dist, line_pixels=int(mask.sum()), grass_ratio=grass_ratio,
    )


def calibration_from_homography(
    h_img_to_pitch: np.ndarray, image_size: tuple[int, int],
    *, pitch_length_m: float = 105.0, pitch_width_m: float = 68.0,
) -> PitchCalibration:
    """Homografiden `PitchCalibration` üret (dört köşe eşlemesi olarak).

    Dört tam eşleşmeden DLT aynı homografiyi geri verir, yani bu kayıpsızdır.
    Böylece hattın geri kalanı (saha-içi kontrolü, görünür alan, hız hesabı)
    hiç değişmeden kare başına homografiyle çalışabilir.
    """
    from app.tracking.homography_fit import corners_from_homography
    from app.tracking.pitch_model import pitch_corners

    corners_px = corners_from_homography(h_img_to_pitch)
    return PitchCalibration.from_dict({
        "image_size": list(image_size),
        "pitch_length_m": pitch_length_m,
        "pitch_width_m": pitch_width_m,
        "points": [
            {"image": [float(u), float(v)], "pitch": [float(x), float(y)]}
            for (u, v), (x, y) in zip(corners_px, pitch_corners(), strict=True)
        ],
    })


@dataclass
class FrameCalibration:
    """Bir karenin kalibrasyon sonucu."""

    calibration: PitchCalibration | None    # None → kare kalibre edilemedi
    fit: FitResult | None
    reason: str = ""

    @property
    def ok(self) -> bool:
        return self.calibration is not None


class PerFrameCalibrator:
    """Kamera hareket ettikçe homografiyi kare kare takip eder.

    İki durumlu bir makine:

    - **TAKİPTE** — önceki karenin homografisinden başlanır (kamera bir karede az
      oynar). Kabul için hem oturma kalitesi hem de FİZİK gerekir: sabit bir
      görüntü noktasının saha karşılığı bir karede `MAX_PITCH_JUMP_M`'den fazla
      oynayamaz.
    - **KAYIP** — kesme, replay, yakın çekim. Süreklilik referansı yoktur.
      Varsayılanda kare üretilmez ve dışarıdan çapa beklenir. `allow_reacquire`
      açıksa arama **çapadan** yapılır (kaymış son homografiden DEĞİL) ve yüksek
      inlier istenir; TV yayınında ana kamera kesmeden sonra benzer görüntüye
      döndüğü için bu pratikte işe yarar.

    Neden bu kadar sıkı — iki ayrı sebep, ikisi de ölçüldü:

    1. Sahanın paralel çizgileri benzer olduğu için homografi yanlış çizgiye
       kilitlenebilir. Böyle oturmalar %55 inlier alıyor, doğrulardan biri %58 —
       **skor tek başına ayırmıyor**. Ayıran şey fizik: yanlış çözüm bir karede
       36 m sıçrıyor, ki imkânsızdır (süreklilik kapısı).
    2. **Saha çizgi modeli 180° dönme altında birebir kendine eşit** (sayısal
       olarak doğrulandı: fark 0.0000 m). Yani hangi yarıya bakıldığı yalnız
       çizgilerden ASLA çıkarılamaz; her çözümün özdeş puanlı bir ikizi vardır.
       Serbest aramayla bulunan %94 inlier'lık bir çapa 47 m yanlıştı. Çapadan
       arama bu ikiliği kapatır, çünkü çapa hangi yarı olduğunu sabitler.

    Ölçülen doğruluk (sentetik pan+zoom, gerçek 4K klipten üretilmiş, saha
    gerçeği bilinen): sabit homografi ~21 m hata verirken kare başına
    kalibrasyon her karede 0.09 m, her 3. karede 0.19 m; her 5. karede takip
    kopuyor ve sistem üretmeyi reddediyor (çöp üretmiyor).
    """

    SEARCH_STEPS_PX = (12.0, 40.0, 110.0)
    MAX_PITCH_JUMP_M = 5.0
    REACQUIRE_MIN_INLIER = 0.85
    # Tahmini başlangıç ancak BELİRGİN daha iyiyse kullanılır. Eşit skorlarda
    # tahmini seçmek yavaş kaymaya yol açıyordu (ölçüldü: 0.09 m → 2.81 m).
    PREDICTION_MARGIN = 1.02
    # Tahmin yalnız kamera GERÇEKTEN hareket ettiyse devreye girer. Ölçüldü:
    #   her kare işlenirken   → tahminsiz 0.09 m, tahminle 2.81 m
    #   her 3. kare işlenirken → tahminsiz %4 kalibre, tahminle 0.11 m
    # Küçük hareketlerde tahmin zarar, büyüklerinde şart.
    # Ölçü SAHA METRESİ cinsindendir: köşeler kadraj dışında olduğu için piksel
    # cinsinden köşe hareketi kaldıraçla büyür ve gerçek hareketi temsil etmez.
    PREDICT_MIN_MOTION_M = 0.3
    _PROBE_UV = ((0.5, 0.5), (0.25, 0.5), (0.75, 0.5))

    def __init__(self, anchor: PitchCalibration, *, image_size: tuple[int, int] | None = None,
                 allow_reacquire: bool = False, tolerance_px: float | None = None):
        # Tolerans PİKSEL cinsindendir, yani çözünürlüğe bağlıdır. Görüntü
        # küçültülerek işleniyorsa aynı sayı sahada daha büyük bir alana denk
        # gelir ve oturma gevşer (ölçüldü: yarı çözünürlükte sabit toleransla
        # hata 0.10 m → 3.95 m). Verilmezse görüntü genişliğinden ölçeklenir.
        self._tolerance_px = tolerance_px
        self._reacquire_allowed = allow_reacquire
        self._anchor = anchor
        self._h = anchor.homography
        self._image_size = image_size or tuple(anchor.image_size)
        self._last_corners: np.ndarray | None = None
        self._prev_corners: np.ndarray | None = None
        self._pending: np.ndarray | None = None   # doğrulama bekleyen aday (KAYIP)
        self._last_jump_m = 0.0                   # son karede kameranın saha hareketi
        self._misses = 0
        if self._tolerance_px is None:
            self._tolerance_px = DEFAULT_TOLERANCE_PX * (self._image_size[0] / 1280.0)
        self.frames_seen = 0
        self.frames_calibrated = 0
        self.frames_rejected = 0

    @property
    def tracking(self) -> bool:
        """Süreklilik referansımız var mı? Çapa da bir referanstır (ilk kare)."""
        return self._misses == 0

    @property
    def calibrated_ratio(self) -> float:
        return round(self.frames_calibrated / self.frames_seen, 3) if self.frames_seen else 0.0

    def _jump_m(self, h_a: np.ndarray, h_b: np.ndarray) -> float | None:
        """Sabit görüntü noktalarının iki homografi arasındaki saha farkı (m)."""
        w, h = self._image_size
        worst = 0.0
        for fx, fy in self._PROBE_UV:
            p = np.array([fx * w, fy * h, 1.0])
            a, b = h_a @ p, h_b @ p
            if abs(a[2]) < 1e-9 or abs(b[2]) < 1e-9:
                return None
            worst = max(worst, float(np.hypot(*(a[:2] / a[2] - b[:2] / b[2]))))
        return worst

    def _predicted_homography(self) -> np.ndarray | None:
        """Sabit hız modeliyle bir sonraki karenin tahmini (yeterince hareket varsa)."""
        if self._last_corners is None or self._prev_corners is None:
            return None
        if self._last_jump_m < self.PREDICT_MIN_MOTION_M:
            return None             # kamera yavaş — tahmine gerek yok
        return homography_from_corners(
            self._last_corners + (self._last_corners - self._prev_corners),
        )

    def _best_fit(self, dist_map: np.ndarray, step: float) -> FitResult:
        """Hem son homografiden hem TAHMİNDEN oturt, iyi olanı seç.

        Tahmini doğrudan başlangıç yapmak (taahhüt) hata biriktiriyordu: kamera
        düzgün hızlanıp yavaşladığı için doğrusal tahmin dönüş noktalarında
        sistematik olarak aşıyor, iyileştirme tam geri çekmiyor ve sapma her
        karede büyüyor (ölçüldü: 0.03 m → 3.65 m). Tahmini ADAY yapıp kararı
        skora bırakmak bu yanlılığı kaldırır.
        """
        fit = refine_homography(self._h, dist_map, step_px=step,
                                tolerance_px=self._tolerance_px)
        if fit.accepted and fit.inlier_ratio >= 0.9:
            return fit              # zaten çok iyi — ikinci aramaya gerek yok
        h_pred = self._predicted_homography()
        if h_pred is None:
            return fit
        alt = refine_homography(h_pred, dist_map, step_px=step,
                                tolerance_px=self._tolerance_px)
        return alt if alt.score > fit.score * self.PREDICTION_MARGIN else fit

    def _miss(self, fit: FitResult | None, reason: str) -> FrameCalibration:
        self.frames_rejected += 1
        self._misses += 1
        return FrameCalibration(None, fit, reason)

    def _accept(self, fit: FitResult, *, jump_m: float | None = None) -> FrameCalibration:
        self._last_jump_m = jump_m if jump_m is not None else 0.0
        self._misses = 0
        self._pending = None
        self._h = fit.homography
        self._prev_corners = self._last_corners
        self._last_corners = corners_from_homography(fit.homography)
        self.frames_calibrated += 1
        return FrameCalibration(
            calibration_from_homography(fit.homography, self._image_size), fit,
        )

    def process(self, bgr: np.ndarray) -> FrameCalibration:
        """Kareyi işle (cv2 ile çizgi çıkarımı + karar)."""
        ext = extract_lines(bgr)
        return self.process_lines(
            ext.dist_map, line_pixels=ext.line_pixels, grass_ratio=ext.grass_ratio,
        )

    def process_lines(
        self, dist_map: np.ndarray, *, line_pixels: int, grass_ratio: float = 1.0,
    ) -> FrameCalibration:
        """Çizgi haritası verilmişken karar ver — cv2 gerektirmez.

        `process` bunun cv2'lü sarmalayıcısıdır. Güvenlik-kritik karar mantığı
        (sıçrama reddi, kayıp durumu) burada olduğu için testler bunu doğrudan
        çağırır.
        """
        self.frames_seen += 1
        if line_pixels < MIN_LINE_PIXELS:
            return self._miss(None,
                              f"saha çizgisi bulunamadı ({line_pixels} piksel, çim %"
                              f"{grass_ratio * 100:.0f}) — yakın çekim/replay olabilir")

        was_tracking = self.tracking
        step = self.SEARCH_STEPS_PX[min(self._misses, len(self.SEARCH_STEPS_PX) - 1)]
        if was_tracking:
            fit = self._best_fit(dist_map, step)
        else:
            # Kayıpken kaymış son homografiden değil, ÇAPADAN ara: çapa hem
            # 180° ikiliğini sabitler hem de sürüklenmiş bir başlangıcın
            # yanlış çizgiye kilitlenmesini engeller.
            fit = refine_homography(self._anchor.homography, dist_map, step_px=step,
                                    tolerance_px=self._tolerance_px)
        if not fit.accepted:
            self._pending = None
            return self._miss(fit, fit.note)

        if was_tracking:
            jump = self._jump_m(fit.homography, self._h)
            if jump is not None and jump > self.MAX_PITCH_JUMP_M:
                return self._miss(
                    fit,
                    f"kalibrasyon bir karede {jump:.0f} m sıçradı (inlier "
                    f"%{fit.inlier_ratio * 100:.0f}) — yanlış çizgiye kilitlenmiş, atlandı",
                )
            return self._accept(fit, jump_m=jump)

        # KAYIP: süreklilik desteği yok.
        #
        # SERBEST arama YAPILMAZ. Saha çizgi modeli 180° dönme altında birebir
        # kendine eşit olduğundan (sayısal olarak doğrulandı: fark 0.0000 m) her
        # çözümün özdeş puanlı bir ikizi vardır; çizgilerden hangi yarıya
        # bakıldığı ASLA çıkarılamaz. Ölçüldü: serbest aramayla bulunan %94
        # inlier'lık bir çapa 47 m yanlıştı.
        #
        # Bunun yerine ÇAPADAN geniş arama yapılır: TV yayınında ana kamera
        # kesmeden sonra benzer görüntüye döner, çapa da hangi yarı olduğunu
        # sabitler — ikilik böylece kapanır. Kabul çıtası yüksektir çünkü
        # süreklilik desteği yoktur.
        if not self._reacquire_allowed:
            return self._miss(
                fit,
                f"takip kayboldu (inlier %{fit.inlier_ratio * 100:.0f}) — yeniden "
                f"çapa gerekiyor; otomatik yakalama doğrulanamadığı için kapalı",
            )
        if fit.inlier_ratio < self.REACQUIRE_MIN_INLIER:
            return self._miss(
                fit,
                f"yeniden yakalama için oturma zayıf (inlier "
                f"%{fit.inlier_ratio * 100:.0f} < %{self.REACQUIRE_MIN_INLIER * 100:.0f})",
            )
        return self._accept(fit)

    def reset_to_anchor(self) -> None:
        """Kesme sonrası: çapaya dön (kayan homografiyle devam etme)."""
        self._h = self._anchor.homography
        self._last_corners = self._prev_corners = self._pending = None
        self._misses = 0
