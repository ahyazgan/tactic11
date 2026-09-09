"""Bir kareden saha kalibrasyonu ÖNER — operatörün onayı için (venv-cv).

Elle kalibrasyon dört saha işaretine tıklamayı gerektirir. Bu script o işi
hızlandırır: kareden saha çizgilerini çıkarır, makul kamera duruşları arasında
arama yapar ve en iyi oturan homografiyi önerir.

## 180° ikiliği — neden iki öneri çıkar

Saha çizgi modeli 180° dönme altında BİREBİR kendine eşittir (sayısal olarak
doğrulandı: fark 0.0000 m). Yani her çözümün özdeş puanlı bir ikizi vardır ve
kameranın hangi yarıya baktığı **yalnız çizgilerden çıkarılamaz** — bu bir
uygulama eksiği değil, geometrinin sınırıdır. Bu yüzden script iki hipotezi de
üretir ve seçimi operatöre bırakır; sahayı gören insan bunu bir bakışta bilir.

`--expect-left` / `--expect-right` verilirse seçim otomatik yapılır: kameranın
sahanın hangi yarısına baktığını siz söylersiniz, ikilik kapanır.

Kullanım:
    venv-cv\\Scripts\\python.exe -m scripts.propose_calibration \\
        --video mac.mp4 --at-seconds 30 --out data/tracking/calibrations/saha.json

    # Önizleme görüntüsüyle (çizgiler + önerilen model üst üste):
    ... --preview onizleme.png

Çıktı `PitchCalibration` JSON'udur; `track_video --calibration` doğrudan okur.
"""
from __future__ import annotations

import argparse
import sys

import numpy as np

from app.tracking.homography_fit import find_anchor
from app.tracking.pitch_lines import calibration_from_homography, extract_lines
from app.tracking.pitch_model import model_points


def _describe(h: np.ndarray, width: int, height: int) -> str:
    """Kameranın sahanın neresine baktığını insan diliyle anlat."""
    q = h @ np.array([width / 2.0, height / 2.0, 1.0])
    x, y = q[:2] / q[2]
    half = "sol yarı" if x < 52.5 else "sağ yarı"
    third = "savunma" if x < 35 else ("orta saha" if x < 70 else "hücum")
    return f"kadraj merkezi saha ({x:.0f} m, {y:.0f} m) — {half}, {third} bölgesi"


def _write_preview(bgr, h: np.ndarray, path: str) -> None:
    """Önerilen modeli kareye çiz — operatör bir bakışta doğrular."""
    import cv2

    from app.tracking.homography_fit import project_to_image

    img = bgr.copy()
    for u, v in project_to_image(h, model_points(0.5)):
        if np.isfinite(u) and np.isfinite(v):
            ui, vi = int(u), int(v)
            if 0 <= ui < img.shape[1] and 0 <= vi < img.shape[0]:
                cv2.circle(img, (ui, vi), 2, (0, 0, 255), -1)
    cv2.imwrite(path, img)


def main() -> int:
    import cv2

    p = argparse.ArgumentParser(description="Kareden saha kalibrasyonu öner")
    p.add_argument("--video", required=True)
    p.add_argument("--at-seconds", type=float, default=0.0,
                   help="Hangi andaki kare kullanılsın (sahanın çok göründüğü bir an seç)")
    p.add_argument("--out", default=None, help="Kabul edilirse kalibrasyon JSON yolu")
    p.add_argument("--preview", default=None, help="Önerilen modeli çizip PNG kaydet")
    side = p.add_mutually_exclusive_group()
    side.add_argument("--expect-left", action="store_true",
                      help="Kamera sahanın SOL yarısına bakıyor (180° ikiliğini kapatır)")
    side.add_argument("--expect-right", action="store_true",
                      help="Kamera sahanın SAĞ yarısına bakıyor")
    args = p.parse_args()

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        print(f"video açılamadı: {args.video}")
        return 2
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(args.at_seconds * fps))
    ok, frame = cap.read()
    cap.release()
    if not ok:
        print(f"{args.at_seconds:.1f}. saniyede kare okunamadı")
        return 2
    h_img, w_img = frame.shape[:2]

    ext = extract_lines(frame)
    print(f"kare {w_img}x{h_img} · çizgi pikseli {ext.line_pixels} · çim %{ext.grass_ratio * 100:.0f}")

    # Beklenen yarı verildiyse ipucu homografisi üret: o yarının ortasına bakan
    # kaba bir duruş, iki hipotezden doğru olanı seçmeye yeter.
    hint = None
    if args.expect_left or args.expect_right:
        from app.tracking.calibration import dlt_homography

        cx = 26.0 if args.expect_left else 79.0
        quad = np.array([[cx - 22, 0.0], [cx + 22, 0.0], [cx + 22, 68.0], [cx - 22, 68.0]])
        img_quad = np.array([[0.0, 0.0], [w_img, 0.0], [w_img, h_img], [0.0, h_img]])
        hint = dlt_homography(img_quad, quad)

    res = find_anchor(ext.dist_map, (w_img, h_img), hint_homography=hint)
    if res.fit is None:
        print(f"öneri üretilemedi: {res.note}")
        return 1

    print(f"\n{res.candidates_scored} aday denendi · en iyi oturma: "
          f"inlier %{res.fit.inlier_ratio * 100:.0f} · skor {res.fit.score:.3f}")

    if not res.accepted:
        print(f"\nOTOMATİK SEÇİM YAPILMADI: {res.note}\n")
        print("İki eşit geçerli hipotez var (saha 180° simetrik). Kameranın hangi")
        print("yarıya baktığını siz biliyorsunuz — şu seçeneklerden birini ekleyip")
        print("tekrar çalıştırın:\n")
        print(f"  A) --expect-left   → {_describe(res.fit.homography, w_img, h_img)}")
        if res.mirror_homography is not None:
            print(f"  B) --expect-right  → {_describe(res.mirror_homography, w_img, h_img)}")
        if args.preview:
            _write_preview(frame, res.fit.homography, args.preview)
            print(f"\nA seçeneğinin önizlemesi: {args.preview}")
        return 1

    print(f"\nÖNERİ: {_describe(res.homography, w_img, h_img)}")
    calib = calibration_from_homography(res.homography, (w_img, h_img))
    print(f"geri-izdüşüm hatası: {calib.reprojection_error_m:.3f} m")
    if args.preview:
        _write_preview(frame, res.homography, args.preview)
        print(f"önizleme: {args.preview} — model çizgileri gerçek çizgilere oturuyor mu, bakın")
    if args.out:
        calib.save(args.out)
        print(f"yazıldı: {args.out}")
    else:
        print("(--out verilmedi, kaydedilmedi)")
    # Ayna hipotezi yine de bildirilir: operatör önizlemede yanlış görürse
    # diğerini seçebilsin.
    if res.mirror_homography is not None:
        print(f"\nalternatif (180° ikiz): {_describe(res.mirror_homography, w_img, h_img)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
