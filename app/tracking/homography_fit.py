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
from app.tracking.pitch_model import (
    PITCH_LENGTH_M,
    PITCH_WIDTH_M,
    model_points,
    pitch_corners,
)

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


_PITCH_CORNERS = pitch_corners()


def homography_from_corners(corners_px: np.ndarray) -> np.ndarray | None:
    """Görüntüdeki 4 köşeden homografi (görüntü → saha) — hızlı kapalı form.

    `corners_from_homography` ile çift oluşturur: biri homografiden köşeleri,
    diğeri köşelerden homografiyi verir. İkisi de kalibrasyon takibinin
    parametreleştirmesidir, bu yüzden ikisi de açık API'dir.

    Tam 4 eşleşmede homografi tek türlü belirlidir; genel DLT'nin (Hartley
    normalizasyonu + SVD) gerekmediği yer burasıdır. h33=1 alınıp 8 bilinmeyenli
    doğrusal sistem çözülür. Arama sırasında bu fonksiyon yüz kez çağrıldığı için
    fark büyük: ölçüldü, SVD yolu iyileştirmenin 97 ms'sinin 60 ms'sini yiyordu.

    Genel `dlt_homography` ile aynı sonucu verir (4 nokta için test edilir);
    tekil/dejenere yapılandırmada None döner.
    """
    src = np.asarray(corners_px, dtype=float)
    dst = _PITCH_CORNERS
    a = np.zeros((8, 8), dtype=float)
    b = np.empty(8, dtype=float)
    for i in range(4):
        x, y = src[i]
        u, v = dst[i]
        a[2 * i] = (x, y, 1.0, 0.0, 0.0, 0.0, -u * x, -u * y)
        a[2 * i + 1] = (0.0, 0.0, 0.0, x, y, 1.0, -v * x, -v * y)
        b[2 * i], b[2 * i + 1] = u, v
    try:
        h = np.linalg.solve(a, b)
    except np.linalg.LinAlgError:
        return None
    if not np.all(np.isfinite(h)):
        return None
    return np.array([[h[0], h[1], h[2]], [h[3], h[4], h[5]], [h[6], h[7], 1.0]])


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
    step_m: float = 1.5,   # arama sırasında model noktası aralığı (m)
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
            h_trial = homography_from_corners(trial)
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


# --- Sıfırdan çapa arama (kesme sonrası) ----------------------------------- #
#
# `refine_homography` yakınsak bir başlangıç ister. Kesmeden sonra öyle bir
# başlangıç yoktur: kamera bambaşka bir yere bakıyordur. O yüzden çapa MUTLAK
# aranır — makul kamera duruşlarından bir aday kümesi üretilip hepsi denenir.
#
# Buradaki asıl tehlike, yerel iyileştirmede görülenin aynısıdır: sahanın
# paralel çizgileri birbirine benzediği için BİRDEN FAZLA duruş iyi puan
# alabilir. Ölçüldü — yanlış kilitlenmeler %55 inlier alıyordu, doğrulardan
# biri %58. Bu yüzden burada tek bir eşik yetmez; **net kazanan** şartı vardır:
# en iyi aday, kendisinden GEOMETRİK OLARAK FARKLI en iyi rakibini belirgin
# farkla geçmelidir. Geçemiyorsa sahne belirsizdir ve çapa üretilmez.

# Aday duruşlar: kadrajda sahanın ne kadarı var, nerede, ne kadar perspektifle
ANCHOR_VIEW_LENGTHS_M = (30.0, 45.0, 60.0, 105.0)
ANCHOR_PERSPECTIVE = (1.0, 0.82, 0.66)   # üst kenarın alt kenara oranı
ANCHOR_CENTRE_STEP_M = 10.0
# Kadraj sahanın GENİŞLİĞİNİN ne kadarını görüyor ve nerede: (genişlik m,
# üst kenarın saha y'si). Eski adaylar hep tam genişliği (0..68) varsayıyordu;
# ölçüldü (pan_zoom bench, 50 kare): gerçek kadraj genişliğin yarısını
# görürken hiçbir aday ulaşamıyor, kabul %2 kalıyordu. Yakın taç altta (TV ana
# kamera) ve ortalanmış (üstten/orta zoom) dilimler eklendi.
ANCHOR_VIEW_BANDS_M: tuple[tuple[float, float], ...] = (
    (68.0, 0.0),           # tam genişlik
    (45.0, 23.0),          # yakın taç altta, uzak taç dışarıda
    (45.0, 11.5),          # ortalanmış
    (30.0, 38.0),          # yakın taç altta, dar
    (30.0, 19.0),          # ortalanmış, dar
)
# Kaba elemeden sonra kaç aday iyileştirilecek (iyileştirme pahalı)
ANCHOR_REFINE_TOP_N = 8
# Kabul için: neredeyse kusursuz oturma + rakibine belirgin üstünlük.
# Eşik yüksek çünkü saha ORTA ÇİZGİYE GÖRE SİMETRİKTİR: bir ceza sahası
# görüntüsü diğerinin aynısıdır. Tek kareden bu ikilik çözülemez. Ölçüldü —
# %79 inlier alan bir çapa 51 m yanlıştı. Bu yüzden yalnız sahne
# TARTIŞMASIZ okunduğunda çapa üretilir; değilse net bir kare beklenir.
ANCHOR_MIN_INLIER = 0.90
ANCHOR_WIN_MARGIN = 1.25
# Çapa için ayırt edici yapı (ceza sahası / orta yuvarlak) görünmeli: yalnız
# paralel taç çizgileri kameranın nerede olduğunu belirlemez.
ANCHOR_MIN_LANDMARK_POINTS = 25
ANCHOR_MIN_LANDMARK_INLIER = 0.70
# İki çözüm bu kadar metre ayrıysa "farklı duruş" sayılır (rakip kabul edilir)
ANCHOR_DISTINCT_M = 8.0
# KAPSAMA kapısı — inlier ve skor "model → çizgi" bakar (kesinlik): modelin
# kadraja düşen noktaları çizgi üstünde mi? Bu tek başına yetmiyor. Ölçüldü
# (gerçek üstten çekim, pan_zoom kare 300): modelin neredeyse tamamını kadraj
# DIŞINA atıp yalnız orta çizgiyi orta çizgiye oturtan bir duruş %97 inlier
# aldı ve 27 m yanlıştı — kadrajdaki orta yuvarlak ve ceza yayı hiç
# açıklanmıyordu. Kapsama tersini sorar ("çizgi → model", duyarlılık):
# görüntüdeki çizgi piksellerinin ne kadarı modelin bir çizgisine yakın?
ANCHOR_MIN_COVERAGE = 0.60
# SAHA ÇİZGİ MODELİ 180° DÖNME ALTINDA BİREBİR KENDİNE EŞLENİR.
# Sayısal olarak doğrulandı: döndürülmüş model noktalarının orijinale uzaklığı
# ortalama ve en fazla 0.0000 m. Yani her homografinin bir "ayna ikizi" vardır
# ve ikisi ÖZDEŞ puan alır (ölçüldü: oran her karede tam 1.00).
#
# Sonuç: **hangi yarıya bakıldığı yalnız saha çizgilerinden ASLA çıkarılamaz.**
# Bu bir uygulama eksiği değil, geometrinin sınırıdır. Ayrımı ancak dışarıdan
# bir bilgi yapar: kaleler, tribün/reklam panoları, çim deseni, ya da kesme
# öncesi bilinen homografi. Bu yüzden `find_anchor` iki hipotezi de döndürür ve
# ipucu verilmedikçe KABUL ETMEZ. (Ölçüldü: ipucusuz kabul edilen bir çapa %94
# inlier'a rağmen 47 m yanlıştı.)
#
# TV KURALI (`assume_camera_side`): ikilik bir UZLAŞIMLA da kapanabilir. Yayın
# rejisinde tüm canlı kameralar sahanın AYNI tarafındadır (180° kuralı — karşı
# açı yalnız tekrarda kullanılır). Adaylar görüntünün ALTINI yakın taç çizgisine
# (y = 68) eşler ve iyileştirme yerel olduğu için bu yönelim korunur; o hâlde
# "yakın taç = y 68, görüntünün solu = küçük x" demek dünya çerçevesini
# kameranın tarafına göre TANIMLAMAK demektir — bir tahmin değil, bir tanım.
# Aynı taraftaki her kamera için tutarlıdır; hücum yönü bu çerçeve içinde
# veriden çıkarılır (bkz. space_map). Kural bozulursa (canlı karşı açı) o
# çekimin konumları aynalanır — bilinen sınır, docstring'de yazılı.


RECALL_SAMPLES = 200


def _line_samples(dist_map: np.ndarray, n: int = RECALL_SAMPLES) -> np.ndarray | None:
    """Çizgi piksellerinden eşit aralıklı, DETERMİNİSTİK örneklem (u, v)."""
    ys, xs = np.nonzero(dist_map <= 0.5)
    if len(xs) == 0:
        return None
    stride = max(1, len(xs) // n)
    return np.column_stack([xs[::stride], ys[::stride]]).astype(float)


def _recall(h_img_to_pitch: np.ndarray, samples: np.ndarray, pts_m: np.ndarray,
            tolerance_px: float) -> float:
    """Çizgi örneklerinin ne kadarı bir model noktasına `tolerance_px` içinde?

    `line_coverage`nin ucuz, örneklemli hâli — aday sıralaması için (yüzlerce
    aday). Kesin ölçüm kabul kapısında raster ile yapılır.
    """
    uv = project_to_image(h_img_to_pitch, pts_m)
    uv = uv[np.isfinite(uv).all(axis=1)]
    lo = samples.min(axis=0) - tolerance_px
    hi = samples.max(axis=0) + tolerance_px
    uv = uv[(uv >= lo).all(axis=1) & (uv <= hi).all(axis=1)]
    if len(uv) == 0:
        return 0.0
    d2 = ((samples[:, None, :] - uv[None, :, :]) ** 2).sum(axis=-1).min(axis=1)
    return float((d2 <= tolerance_px * tolerance_px).mean())


def line_coverage(
    h_img_to_pitch: np.ndarray, line_mask: np.ndarray, *,
    tolerance_px: float = DEFAULT_TOLERANCE_PX, step_m: float = 0.1,
) -> float:
    """Görüntüdeki çizgi piksellerinin modelle AÇIKLANAN payı (0..1).

    Model çizgileri sık örneklenip görüntüye izdüşürülür, `tolerance_px` kadar
    genişletilir; çizgi maskesinin bu örtüye düşen oranı döner. Kadrajda model
    noktası yoksa 0.
    """
    h_px, w_px = line_mask.shape
    total = int(line_mask.sum())
    if total == 0:
        return 0.0
    r = max(1, int(round(tolerance_px)))
    # Kadraj kenarındaki çizgiler (yakın taç çoğu zaman görüntünün altında)
    # model noktası kenarın hemen dışına düşünce de açıklanmış sayılmalı:
    # raster tolerans kadar payla kurulur, genişletilir, sonra kırpılır.
    pts = project_to_image(h_img_to_pitch, model_points(step_m))
    pts = pts[np.isfinite(pts).all(axis=1)]
    inside = ((pts[:, 0] >= -r) & (pts[:, 0] < w_px + r)
              & (pts[:, 1] >= -r) & (pts[:, 1] < h_px + r))
    pts = pts[inside]
    if len(pts) == 0:
        return 0.0
    raster = np.zeros((h_px + 2 * r, w_px + 2 * r), dtype=bool)
    raster[(pts[:, 1] + r).astype(int), (pts[:, 0] + r).astype(int)] = True
    grown = raster
    for _ in range(r):
        g = grown.copy()
        g[1:, :] |= grown[:-1, :]
        g[:-1, :] |= grown[1:, :]
        g[:, 1:] |= grown[:, :-1]
        g[:, :-1] |= grown[:, 1:]
        grown = g
    grown = grown[r:r + h_px, r:r + w_px]
    return float((line_mask & grown).sum() / total)


def mirrored_homography(h_img_to_pitch: np.ndarray) -> np.ndarray:
    """Sahayı 180° döndüren eşdeğer hipotez: (x, y) → (105-x, 68-y)."""
    r = np.array([[-1.0, 0.0, PITCH_LENGTH_M],
                  [0.0, -1.0, PITCH_WIDTH_M],
                  [0.0, 0.0, 1.0]])
    return r @ h_img_to_pitch


@dataclass(frozen=True)
class AnchorResult:
    """Çapa arama sonucu.

    Garantiler:
    - `accepted` False ise `homography` None'dır ve `note` sebebi söyler.
      Hiçbir koşulda uydurma homografi DÖNMEZ.
    - Bir oturma hesaplanabildiyse `fit` doludur ve `mirror_homography` onun
      180° ikizidir — operatöre iki seçenek sunulabilsin diye.

    NOT: bu bir ÖNERİ aracıdır, otomatik kalibrasyon değil. Ölçüldü — tam saha
    görünen bir sahnede %90 inlier alan bir öneri 24 m yanlış olabiliyor. Öneri
    mutlaka insan tarafından (önizleme görüntüsüyle) doğrulanmalıdır; bkz.
    scripts/propose_calibration.py.
    """

    homography: np.ndarray | None
    fit: FitResult | None
    candidates_scored: int
    runner_up_score: float
    accepted: bool
    note: str
    # Eşit geçerli 180° ikiz çözüm. İpucu olmadan hangisinin doğru olduğu
    # bilinemez (saha modeli tam simetrik); ikisi de burada döner.
    mirror_homography: np.ndarray | None = None
    # Kadrajdaki çizgi piksellerinin modelle açıklanan payı (kapsama kapısı)
    coverage: float = 0.0


def _view_quad(width_px: float, height_px: float, taper: float) -> np.ndarray:
    """Kadrajın saha üzerindeki izdüşümü için görüntü dörtgeni (yamuk).

    Yandan bakan kamerada uzak taç çizgisi kısa görünür; `taper` üst kenarın
    alt kenara oranıdır (1.0 = tepeden bakış).
    """
    cx = width_px / 2.0
    half_top = width_px / 2.0 * taper
    return np.array([
        [cx - half_top, 0.0], [cx + half_top, 0.0],
        [width_px, height_px], [0.0, height_px],
    ], dtype=float)


def anchor_candidates(image_size: tuple[int, int]) -> list[np.ndarray]:
    """Makul kamera duruşlarından homografi adayları üret (görüntü → saha)."""
    w, h = float(image_size[0]), float(image_size[1])
    out: list[np.ndarray] = []
    for view_len in ANCHOR_VIEW_LENGTHS_M:
        centres = np.arange(view_len / 2.0, 105.0 - view_len / 2.0 + 1e-6,
                            ANCHOR_CENTRE_STEP_M)
        if len(centres) == 0:
            centres = np.array([52.5])
        for cx_m in centres:
            x0, x1 = cx_m - view_len / 2.0, cx_m + view_len / 2.0
            for band_w, y_top in ANCHOR_VIEW_BANDS_M:
                # Dar dilimler yalnız yakın çekimlerde anlamlı: 105 m uzunluk
                # görürken 30 m genişlik görmek fiziksel değil.
                if band_w < 68.0 and view_len > 2.0 * band_w:
                    continue
                y0, y1 = y_top, y_top + band_w
                pitch_quad = np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]])
                for taper in ANCHOR_PERSPECTIVE:
                    try:
                        out.append(dlt_homography(_view_quad(w, h, taper), pitch_quad))
                    except (ValueError, np.linalg.LinAlgError):
                        continue
    return out


def find_anchor(
    dist_map: np.ndarray,
    image_size: tuple[int, int],
    *,
    tolerance_px: float = DEFAULT_TOLERANCE_PX,
    hint_homography: np.ndarray | None = None,
    assume_camera_side: bool = False,
) -> AnchorResult:
    """Başlangıç homografisi olmadan çapa bul (kesme sonrası / çapasız başlangıç).

    Adaylar kabaca puanlanır (ucuz), en iyi birkaçı iyileştirilir (pahalı), sonra
    net kazanan aranır. Kazanan yoksa çapa üretilmez.

    **180° ikiliği:** saha çizgi modeli kendi 180° dönmesine birebir eşit
    olduğundan her çözümün özdeş puanlı bir ikizi vardır. `hint_homography`
    verilmezse hangisinin doğru olduğu bilinemez ve sonuç KABUL EDİLMEZ; iki
    hipotez de döndürülür. İpucu tipik olarak kesmeden önceki son geçerli
    homografidir (kamera aynı yarıya dönüyorsa ikilik çözülür).

    **`assume_camera_side` (TV kuralı):** ipucu yokken ikiliği uzlaşımla kapat —
    görüntünün altı yakın taç çizgisi (y = 68), görüntünün solu küçük x. Yayının
    tüm canlı kameraları aynı taraftaysa (rejinin 180° kuralı) bu çerçeve
    maç boyunca tutarlıdır. Canlı karşı açıda o çekimin konumları aynalanır;
    bu bilinen sınırdır ve kalite kapıları (inlier, ayırt edici yapı, net
    kazanan) bunu YAKALAMAZ — geometri aynı puanı verir.
    """
    pts_m = model_points(1.0)
    cands = anchor_candidates(image_size)
    samples = _line_samples(dist_map)
    if samples is None:
        return AnchorResult(None, None, len(cands), 0.0, False,
                            "kadrajda çizgi pikseli yok")
    recall_tol = 2.0 * tolerance_px

    # Sıralama ölçüsü KESİNLİK × DUYARLILIK. `score` yalnız "model → çizgi"
    # bakar ve modelin çoğunu kadraj dışına atıp kalan birkaç noktayı bir
    # çizgiye oturtan duruşları öne çıkarır (ölçüldü: 303 adayla sentetik
    # sahnede gerçek duruş ilk 8'e giremedi, 16 m yanlış aday kazandı; gerçek
    # karede %97 inlier'lı çözüm 27 m yanlıştı). `_recall` tersini sorar:
    # görüntüdeki çizgi piksellerinin ne kadarı bir model noktasına yakın?
    def _key(h: np.ndarray, s: float) -> float:
        return s * _recall(h, samples, pts_m, recall_tol)

    scored = []
    for h in cands:
        s, inl, vis = score_homography(h, dist_map, pts_m=pts_m, tolerance_px=tolerance_px)
        if vis >= MIN_VISIBLE_POINTS:
            scored.append((_key(h, s), inl, h))
    if not scored:
        return AnchorResult(None, None, len(cands), 0.0, False,
                            "hiçbir aday kadrajda yeterli saha göremedi")
    scored.sort(key=lambda t: t[0], reverse=True)

    # İyileştirme pahalı; aday sayısı büyüdükçe iyileştirilen pay da büyür,
    # yoksa kaba sıralamanın hatası son sözü söyler.
    top_n = max(ANCHOR_REFINE_TOP_N, len(scored) // 12)
    refined: list[tuple[float, FitResult]] = []
    for _s, _inl, h in scored[:top_n]:
        f = refine_homography(h, dist_map, tolerance_px=tolerance_px, step_px=30.0)
        refined.append((_key(f.homography, f.score), f))
    refined.sort(key=lambda t: t[0], reverse=True)
    best_key, best = refined[0]

    # Rakip: en iyiden GEOMETRİK OLARAK farklı en yüksek puanlı çözüm
    runner_up = 0.0
    probes = np.array([[image_size[0] / 2, image_size[1] / 2, 1.0],
                       [image_size[0] * 0.25, image_size[1] * 0.6, 1.0],
                       [image_size[0] * 0.75, image_size[1] * 0.6, 1.0]])

    def _pitch(h: np.ndarray) -> np.ndarray:
        q = probes @ h.T
        return q[:, :2] / q[:, 2:3]

    best_pts = _pitch(best.homography)
    for key, f in refined[1:]:
        if float(np.abs(_pitch(f.homography) - best_pts).max()) >= ANCHOR_DISTINCT_M:
            runner_up = key
            break

    lm_pts = model_points(1.0, "landmark")
    _lm_score, lm_inlier, lm_visible = score_homography(
        best.homography, dist_map, pts_m=lm_pts, tolerance_px=tolerance_px,
    )
    if lm_visible < ANCHOR_MIN_LANDMARK_POINTS:
        return AnchorResult(
            None, best, len(cands), runner_up, False,
            f"kadrajda ayırt edici yapı yok (ceza sahası/orta yuvarlak: "
            f"{lm_visible} nokta) — yalnız paralel çizgiyle çapa kurulamaz",
           mirror_homography=mirrored_homography(best.homography),
        )
    if lm_inlier < ANCHOR_MIN_LANDMARK_INLIER:
        return AnchorResult(
            None, best, len(cands), runner_up, False,
            f"ayırt edici yapılar oturmadı (inlier %{lm_inlier * 100:.0f}) — "
            f"çapa üretilmedi",
           mirror_homography=mirrored_homography(best.homography),
        )
    if best.inlier_ratio < ANCHOR_MIN_INLIER:
        return AnchorResult(
            None, best, len(cands), runner_up, False,
            f"çapa oturması zayıf (inlier %{best.inlier_ratio * 100:.0f} < "
            f"%{ANCHOR_MIN_INLIER * 100:.0f}) — çapa üretilmedi",
           mirror_homography=mirrored_homography(best.homography),
        )
    if runner_up > 0.0 and best_key < runner_up * ANCHOR_WIN_MARGIN:
        return AnchorResult(
            None, best, len(cands), runner_up, False,
            f"sahne belirsiz: en iyi aday ({best_key:.3f}) farklı bir duruşu "
            f"({runner_up:.3f}) belirgin geçemedi — çapa üretilmedi",
           mirror_homography=mirrored_homography(best.homography),
        )
    # Kapsama: kadrajdaki çizgilerin çoğu bu duruşla açıklanıyor mu? Mesafe
    # haritasında 0 olan pikseller çizgidir. Tolerans oturmanınkinin İKİ KATI:
    # kapı "yapı hiç açıklanmıyor"u (27 m) yakalamak için, birkaç piksellik
    # oturma kusurunu cezalandırmak için değil — ölçüldü, 0.24 m doğru bir
    # çözüm yakın taçta 10 px kayıkken oturma toleransıyla %57 kapsama alıyordu.
    coverage = line_coverage(best.homography, dist_map <= 0.5,
                             tolerance_px=2.0 * tolerance_px)
    if coverage < ANCHOR_MIN_COVERAGE:
        return AnchorResult(
            None, best, len(cands), runner_up, False,
            f"kadrajdaki çizgilerin yalnız %{coverage * 100:.0f}'i modelle açıklanıyor "
            f"(< %{ANCHOR_MIN_COVERAGE * 100:.0f}) — görünen yapının çoğu bu duruşa "
            f"uymuyor, çapa üretilmedi",
            mirror_homography=mirrored_homography(best.homography), coverage=coverage,
        )
    mirror = mirrored_homography(best.homography)
    if hint_homography is None:
        if assume_camera_side:
            # Adaylar görüntünün altını y=68'e eşler; yerel iyileştirme yönelimi
            # değiştiremez → `best` uzlaşımın kendisidir, ikizi karşı taraf.
            return AnchorResult(
                best.homography, best, len(cands), runner_up, True,
                "TV kuralı ile kabul: yakın taç çizgisi y=68 varsayıldı "
                "(kameralar aynı tarafta); karşı açıda konumlar aynalanır",
                mirror_homography=mirror, coverage=coverage,
            )
        return AnchorResult(
            None, best, len(cands), runner_up, False,
            "180° ikilik çözülemedi: saha çizgileri hangi yarıya bakıldığını "
            "belirlemez (model tam simetrik). Kesme öncesi homografi ya da "
            "operatör bilgisi gerekiyor.",
            mirror_homography=mirror, coverage=coverage,
        )
    # İpucuna yakın olan hipotez seçilir
    probe = np.array([[image_size[0] / 2, image_size[1] / 2, 1.0]])

    def _p(h: np.ndarray) -> np.ndarray:
        q = probe @ h.T
        return q[:, :2] / q[:, 2:3]

    ref = _p(hint_homography)
    d_best = float(np.hypot(*(_p(best.homography) - ref)[0]))
    d_mirror = float(np.hypot(*(_p(mirror) - ref)[0]))
    chosen = best.homography if d_best <= d_mirror else mirror
    return AnchorResult(chosen, best, len(cands), runner_up, True, "",
                        mirror_homography=mirror, coverage=coverage)
