"""Kare başına kalibrasyon: homografiyi görüntüdeki saha çizgilerine oturt.

## Sorun

Takip hattı tek ve sabit bir homografi kullanır. Yayın kamerası çevirdiğinde bu
homografi geçersizleşir ve oyuncular sahada kaymış görünür (100 px ≈ 3.6 m —
sinyal eşikleri 2.5–4 m, yani sahte taktik sinyal üretir). Çözüm: homografiyi
her karede yeniden bulmak.

## Yaklaşım — sıfırdan değil, iyileştirerek

Sıfırdan homografi çıkarmak (çizgileri tespit et → modele eşleştir → çöz) kırılgan
ve karmaşıktır. Bunun yerine **yakınsak bir başlangıçtan iyileştiririz**: önceki
karenin (ya da elle yapılmış kalibrasyonun) homografisi bu karede de yaklaşık
doğrudur; kamera bir karede çok az oynar. Modelin çizgilerini o homografiyle
görüntüye izdüşürüp gerçek çizgi piksellerine ne kadar oturduğuna bakar, oturana
kadar homografiyi küçük adımlarla kaydırırız.

## Parametreleme — neden 4 köşe

Homografinin 8 serbestliğini doğrudan optimize etmek kararsızdır (matris
elemanları farklı ölçeklerde, küçük değişim büyük bozulma). Onun yerine sahanın
dört köşesinin GÖRÜNTÜDEKİ konumunu oynatırız; her denemede DLT ile homografi
yeniden çözülür. Sekiz sayı yine sekiz serbestlik verir ama hepsi piksel
biriminde ve geometrik olarak anlamlıdır — adım büyüklüğü sezgisel kalır.
Köşeler kadraj dışında olabilir; parametre olarak sorun değildir.

## Skor

Modelin her noktası görüntüye izdüşürülür; kadraj içindekiler için en yakın çizgi
pikseline uzaklık (mesafe dönüşümü haritasından) okunur ve `1/(1+d/tol)` ile
yumuşak bir puana çevrilir. Toplam puan, kadraj içinde kalan nokta sayısına
bölünür — böylece "az nokta görünüyor ama hepsi oturuyor" ile "çok nokta
görünüyor ve oturuyor" adil kıyaslanır. Ayrı olarak `inlier_ratio` (tol içinde
kalan nokta oranı) raporlanır; asıl güven ölçüsü odur.

DİKKAT — bu bir güven ölçüsüdür, garanti değil: yayında sahanın küçük bir kısmı
görünürken birkaç çizgi birden fazla modele oturabilir (örneğin yalnız bir taç
çizgisi ve orta yuvarlağın parçası görünüyorsa homografi kayabilir). Bu yüzden
`fit_quality` eşiğin altındaysa kare kalibre EDİLMEMİŞ sayılmalı ve konum
üretilmemelidir; sessizce yanlış konum üretmektense kare atlanmalıdır.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.tracking.calibration import dlt_homography
from app.tracking.pitch_model import model_points, pitch_corners

# Model noktası bu kadar piksel içinde çizgi bulursa "oturmuş" sayılır
DEFAULT_TOLERANCE_PX = 6.0
# Kalibrasyonun kabul edilmesi için gereken en düşük inlier oranı
MIN_INLIER_RATIO = 0.45
# Skorun anlamlı olması için kadraj içinde kalması gereken en az model noktası
MIN_VISIBLE_POINTS = 40


@dataclass(frozen=True)
class FitResult:
    homography: np.ndarray      # görüntü → saha (calibration.py ile aynı yön)
    score: float                # 0..1 yumuşak oturma puanı
    inlier_ratio: float         # tolerans içinde kalan model noktası oranı
    visible_points: int
    iterations: int
    accepted: bool
    note: str = ""


def project_to_image(h_img_to_pitch: np.ndarray, pts_m: np.ndarray) -> np.ndarray:
    """Saha metrelerini görüntü pikseline çevir (homografinin tersiyle)."""
    h_inv = np.linalg.inv(h_img_to_pitch)
    ones = np.ones((len(pts_m), 1), dtype=float)
    hom = np.hstack([pts_m, ones]) @ h_inv.T
    w = hom[:, 2:3]
    # Kameranın arkasına düşen / ufuk üstündeki noktalar: w ~ 0 → geçersiz
    safe = np.where(np.abs(w) < 1e-9, np.nan, w)
    return hom[:, :2] / safe


def score_homography(
    h_img_to_pitch: np.ndarray,
    dist_map: np.ndarray,
    *,
    pts_m: np.ndarray | None = None,
    tolerance_px: float = DEFAULT_TOLERANCE_PX,
) -> tuple[float, float, int]:
    """(skor, inlier_oranı, görünür_nokta) — model çizgileri gerçek çizgilere oturuyor mu.

    `dist_map`: her piksel için en yakın çizgi pikseline uzaklık (mesafe dönüşümü).
    """
    pts = model_points() if pts_m is None else pts_m
    h_img = dist_map.shape[0]
    w_img = dist_map.shape[1]
    uv = project_to_image(h_img_to_pitch, pts)
    u, v = uv[:, 0], uv[:, 1]
    inside = (
        np.isfinite(u) & np.isfinite(v)
        & (u >= 0) & (u < w_img) & (v >= 0) & (v < h_img)
    )
    n = int(inside.sum())
    if n == 0:
        return 0.0, 0.0, 0
    d = dist_map[v[inside].astype(int), u[inside].astype(int)]
    soft = 1.0 / (1.0 + d / max(tolerance_px, 1e-6))
    return float(soft.mean()), float((d <= tolerance_px).mean()), n


def _homography_from_corners(corners_px: np.ndarray) -> np.ndarray | None:
    """Görüntüdeki 4 köşeden homografi (görüntü → saha)."""
    try:
        return dlt_homography(corners_px, pitch_corners())
    except (ValueError, np.linalg.LinAlgError):
        return None


def corners_from_homography(h_img_to_pitch: np.ndarray) -> np.ndarray:
    """Homografinin ima ettiği görüntüdeki saha köşeleri (parametre başlangıcı)."""
    return project_to_image(h_img_to_pitch, pitch_corners())


def refine_homography(
    h_start: np.ndarray,
    dist_map: np.ndarray,
    *,
    tolerance_px: float = DEFAULT_TOLERANCE_PX,
    step_px: float = 12.0,
    min_step_px: float = 0.5,
    max_iterations: int = 4000,
    step_m: float = 1.0,
) -> FitResult:
    """`h_start`'tan başlayıp homografiyi çizgilere oturt (yön aramalı iniş).

    Denenen hamleler gerçek kamera hareketlerine karşılık gelir; sırası önemlidir:

    1. **Öteleme** — dört köşeyi birlikte kaydır (kamera çevirmesi/pan)
    2. **Ölçek** — köşeleri merkeze göre büyüt/küçült (zoom)
    3. **Tek köşe** — perspektif/eğim için ince ayar

    Yalnız 3. hamleyle (klasik koordinat inişi) aranırsa arama takılır: kamera
    kayması dört köşeyi BİRLİKTE kaydırır, tek köşeyi oynatmak homografiyi
    çarpıtır ve puanı yeterince artırmaz. Ölçüldü: yalnız tek-köşe hamlesiyle
    25 px'lik bir kayma %82 inlier'da, zoom ise %60'ta takılıyordu.

    İyileştirmeyen tur sonunda adım yarılanır. Türev gerektirmez, deterministiktir.
    """
    pts_m = model_points(step_m)
    corners = corners_from_homography(h_start)
    if not np.all(np.isfinite(corners)):
        return FitResult(h_start, 0.0, 0.0, 0, 0, False,
                         "başlangıç homografisi geçersiz (köşeler sonsuz)")
    best_h = h_start
    best_score, best_inlier, best_visible = score_homography(
        h_start, dist_map, pts_m=pts_m, tolerance_px=tolerance_px,
    )

    def _moves(step: float):
        """Bu adım büyüklüğü için denenecek köşe düzenlemeleri."""
        for dx, dy in ((step, 0.0), (-step, 0.0), (0.0, step), (0.0, -step)):
            yield lambda c, dx=dx, dy=dy: c + np.array([dx, dy])
        for factor in (1.0 + step / 200.0, 1.0 - step / 200.0):
            def _scale(c, f=factor):
                mid = c.mean(axis=0)
                return mid + (c - mid) * f
            yield _scale
        for i in range(4):
            for axis in (0, 1):
                for delta in (step, -step):
                    def _one(c, i=i, axis=axis, delta=delta):
                        out = c.copy()
                        out[i, axis] += delta
                        return out
                    yield _one

    step = step_px
    iterations = 0
    while step >= min_step_px and iterations < max_iterations:
        # EN İYİ hamleyi seç, ilk iyileşmeyi değil. İlk-iyileşme sırayı
        # önemli kılar ve aramayı ötelemeye saplar (ölçüldü: pan %82 → %59).
        candidate = None
        for move in _moves(step):
            trial = move(corners)
            h_trial = _homography_from_corners(trial)
            if h_trial is None:
                continue
            s, inl, vis = score_homography(
                h_trial, dist_map, pts_m=pts_m, tolerance_px=tolerance_px,
            )
            iterations += 1
            if s > best_score and (candidate is None or s > candidate[0]):
                candidate = (s, inl, vis, h_trial, trial)
        if candidate is None:
            step /= 2.0
        else:
            best_score, best_inlier, best_visible, best_h, corners = candidate
    enough = best_visible >= MIN_VISIBLE_POINTS
    accepted = enough and best_inlier >= MIN_INLIER_RATIO
    if accepted:
        note = ""
    elif not enough:
        note = (f"kadrajda yalnız {best_visible} model noktası — kalibrasyon "
                f"doğrulanamaz, kare atlanmalı")
    else:
        note = (f"çizgi oturması zayıf (inlier %{best_inlier * 100:.0f} < "
                f"%{MIN_INLIER_RATIO * 100:.0f}) — kare atlanmalı")
    return FitResult(
        homography=best_h, score=round(best_score, 4),
        inlier_ratio=round(best_inlier, 4), visible_points=best_visible,
        iterations=iterations, accepted=accepted, note=note,
    )
