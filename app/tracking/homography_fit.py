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
            pitch_quad = np.array([[x0, 0.0], [x1, 0.0], [x1, 68.0], [x0, 68.0]])
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
) -> AnchorResult:
    """Başlangıç homografisi olmadan çapa bul (kesme sonrası).

    Adaylar kabaca puanlanır (ucuz), en iyi birkaçı iyileştirilir (pahalı), sonra
    net kazanan aranır. Kazanan yoksa çapa üretilmez.

    **180° ikiliği:** saha çizgi modeli kendi 180° dönmesine birebir eşit
    olduğundan her çözümün özdeş puanlı bir ikizi vardır. `hint_homography`
    verilmezse hangisinin doğru olduğu bilinemez ve sonuç KABUL EDİLMEZ; iki
    hipotez de döndürülür. İpucu tipik olarak kesmeden önceki son geçerli
    homografidir (kamera aynı yarıya dönüyorsa ikilik çözülür).
    """
    pts_m = model_points(1.0)
    cands = anchor_candidates(image_size)
    scored = []
    for h in cands:
        s, inl, vis = score_homography(h, dist_map, pts_m=pts_m, tolerance_px=tolerance_px)
        if vis >= MIN_VISIBLE_POINTS:
            scored.append((s, inl, h))
    if not scored:
        return AnchorResult(None, None, len(cands), 0.0, False,
                            "hiçbir aday kadrajda yeterli saha göremedi")
    scored.sort(key=lambda t: t[0], reverse=True)

    refined: list[FitResult] = []
    for _s, _inl, h in scored[:ANCHOR_REFINE_TOP_N]:
        refined.append(refine_homography(h, dist_map, tolerance_px=tolerance_px, step_px=30.0))
    refined.sort(key=lambda f: f.score, reverse=True)
    best = refined[0]

    # Rakip: en iyiden GEOMETRİK OLARAK farklı en yüksek puanlı çözüm
    runner_up = 0.0
    probes = np.array([[image_size[0] / 2, image_size[1] / 2, 1.0],
                       [image_size[0] * 0.25, image_size[1] * 0.6, 1.0],
                       [image_size[0] * 0.75, image_size[1] * 0.6, 1.0]])

    def _pitch(h: np.ndarray) -> np.ndarray:
        q = probes @ h.T
        return q[:, :2] / q[:, 2:3]

    best_pts = _pitch(best.homography)
    for f in refined[1:]:
        if float(np.abs(_pitch(f.homography) - best_pts).max()) >= ANCHOR_DISTINCT_M:
            runner_up = f.score
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
    if runner_up > 0.0 and best.score < runner_up * ANCHOR_WIN_MARGIN:
        return AnchorResult(
            None, best, len(cands), runner_up, False,
            f"sahne belirsiz: en iyi aday ({best.score:.3f}) farklı bir duruşu "
            f"({runner_up:.3f}) belirgin geçemedi — çapa üretilmedi",
           mirror_homography=mirrored_homography(best.homography),
        )
    mirror = mirrored_homography(best.homography)
    if hint_homography is None:
        return AnchorResult(
            None, best, len(cands), runner_up, False,
            "180° ikilik çözülemedi: saha çizgileri hangi yarıya bakıldığını "
            "belirlemez (model tam simetrik). Kesme öncesi homografi ya da "
            "operatör bilgisi gerekiyor.",
            mirror_homography=mirror,
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
                        mirror_homography=mirror)
