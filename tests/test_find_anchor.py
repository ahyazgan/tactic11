"""find_anchor — başlangıçsız çapa arama ve 180° ikiliği.

Bu fonksiyonun en önemli özelliği bulduğu şey değil, **bulamadığını kabul
etmesi**: saha çizgi modeli 180° dönme altında birebir kendine eşit olduğundan
(bkz. test_pitch_model_is_symmetric) hangi yarıya bakıldığı çizgilerden ASLA
çıkarılamaz. İpucu yoksa sonuç kabul edilmemeli.
"""
from __future__ import annotations

import numpy as np

from app.tracking.calibration import dlt_homography
from app.tracking.homography_fit import (
    anchor_candidates,
    find_anchor,
    mirrored_homography,
    project_to_image,
)
from app.tracking.pitch_model import (
    PITCH_LENGTH_M,
    PITCH_WIDTH_M,
    model_points,
    pitch_corners,
)

W, H = 800, 450
TRUE_CORNERS = np.array(
    [[60.0, 90.0], [740.0, 90.0], [790.0, 400.0], [10.0, 400.0]], dtype=float,
)


def true_homography() -> np.ndarray:
    return dlt_homography(TRUE_CORNERS, pitch_corners())


def dist_map_for(h: np.ndarray) -> np.ndarray:
    mask = np.zeros((H, W), dtype=bool)
    for u, v in project_to_image(h, model_points(0.2)):
        if not (np.isfinite(u) and np.isfinite(v)):
            continue
        ui, vi = int(round(u)), int(round(v))
        if 0 <= ui < W and 0 <= vi < H:
            mask[max(0, vi - 1):vi + 2, max(0, ui - 1):ui + 2] = True
    d = np.where(mask, 0.0, 50.0)
    for _ in range(3):
        for axis in (0, 1):
            for direction in (1, -1):
                d = np.minimum(d, np.roll(d, direction, axis=axis) + 1.0)
    return d


def test_pitch_model_is_exactly_symmetric_under_180_rotation() -> None:
    """Bu turun temel bulgusu — kod bunun üstüne kurulu, testi de olmalı.

    Model kendi 180° dönmesine birebir eşitse, hiçbir algoritma yalnız
    çizgilerden hangi yarıya bakıldığını söyleyemez.
    """
    p = model_points(0.5)
    rotated = np.column_stack([PITCH_LENGTH_M - p[:, 0], PITCH_WIDTH_M - p[:, 1]])
    worst = max(
        float(np.min(np.hypot(p[:, 0] - q[0], p[:, 1] - q[1])))
        for q in rotated[::11]
    )
    assert worst < 1e-9, f"model simetrik değil (en kötü {worst:.6f} m)"


def test_mirror_hypothesis_scores_identically() -> None:
    """Ayna ikizi ÖZDEŞ puan alır — ayırt edilemezliğin doğrudan kanıtı."""
    from app.tracking.homography_fit import score_homography

    h = true_homography()
    dmap = dist_map_for(h)
    s_true = score_homography(h, dmap)[0]
    s_mirror = score_homography(mirrored_homography(h), dmap)[0]
    assert abs(s_true - s_mirror) < 1e-9, (s_true, s_mirror)


def test_never_returns_a_homography_it_did_not_accept() -> None:
    """Temel garanti: kabul edilmeyen sonuçta homografi DÖNMEZ.

    Aracın değeri doğru cevabı bulmasında değil, bulamadığını söylemesinde.
    Ölçüldü — tam saha görünen bir sahnede %90 inlier alan bir öneri 24 m
    yanlış olabiliyor; bu yüzden çıktı insan onayına sunulur, otomatik
    kullanılmaz.
    """
    for hint in (None, true_homography()):
        res = find_anchor(dist_map_for(true_homography()), (W, H), hint_homography=hint)
        assert (res.homography is None) == (not res.accepted)
        assert res.note or res.accepted
        assert res.candidates_scored > 20


def test_offers_both_hypotheses_for_the_operator() -> None:
    """Oturma hesaplanabildiyse 180° ikizi de sunulmalı — operatör seçebilsin."""
    res = find_anchor(dist_map_for(true_homography()), (W, H))
    assert res.fit is not None
    assert res.mirror_homography is not None
    assert not np.allclose(res.fit.homography, res.mirror_homography)


def test_mirroring_twice_returns_the_original() -> None:
    """180° dönme kendi tersidir — ikizin ikizi başlangıçtır."""
    h = true_homography()
    back = mirrored_homography(mirrored_homography(h))
    assert np.allclose(h, back)


def test_camera_looking_at_the_centre_has_a_nearby_twin() -> None:
    """Uyarı niteliğinde: 180° dönmenin sabit noktası saha merkezidir.

    Kamera orta yuvarlağa bakıyorsa iki hipotez birbirine ÇOK yakın düşer —
    yani oradan alınan bir öneri yanlış olsa bile az saparken, kanatlara bakan
    bir kamerada aynı hata sahanın öbür ucuna taşır. Operatör önizlemesi bu
    yüzden önemlidir.
    """
    probe = np.array([52.5, 34.0])   # saha merkezi
    h = true_homography()
    m = mirrored_homography(h)
    inv_h, inv_m = np.linalg.inv(h), np.linalg.inv(m)
    p = np.array([probe[0], probe[1], 1.0])
    a, b = inv_h @ p, inv_m @ p
    a, b = a[:2] / a[2], b[:2] / b[2]
    assert float(np.hypot(*(a - b))) < 1e-6


def test_hint_picks_the_nearer_of_the_two_hypotheses() -> None:
    """İpucu verilip kabul edildiyse, dönen hipotez ipucuna YAKIN olandır.

    (Hangi hipotezin gerçekte doğru olduğunu araç bilemez — bunu ipucu belirler.)
    """
    h_true = true_homography()
    dmap = dist_map_for(h_true)
    accepted = [
        find_anchor(dmap, (W, H), hint_homography=h)
        for h in (h_true, mirrored_homography(h_true))
    ]
    probe = np.array([W / 2, H / 2, 1.0])

    def to_pitch(h):
        q = h @ probe
        return q[:2] / q[2]

    for res, hint in zip(accepted, (h_true, mirrored_homography(h_true)), strict=True):
        if not res.accepted:
            continue          # kalite kapısı reddetmiş olabilir; o da geçerli
        assert res.mirror_homography is not None
        d_chosen = float(np.hypot(*(to_pitch(res.homography) - to_pitch(hint))))
        d_other = float(np.hypot(*(to_pitch(res.mirror_homography) - to_pitch(hint))))
        assert d_chosen <= d_other


# --- TV kuralı: yayın sahnesi (kadraj = saha dilimi) ----------------------- #

def _probe_m(h_a: np.ndarray, h_b: np.ndarray, u: float, v: float) -> float:
    p = np.array([u, v, 1.0])
    a, b = h_a @ p, h_b @ p
    return float(np.hypot(*(a[:2] / a[2] - b[:2] / b[2])))


def test_camera_side_rule_accepts_a_broadcast_scene_and_lands_on_truth() -> None:
    """TV kuralı ile ipucusuz KABUL — ve doğru yere.

    Sahne yayın kamerası gibi kurulu: kadraj sahanın 60 m'lik orta dilimi,
    görüntünün altı yakın taç (y=68), aday duruşlardan 9 px kaymış. Kabul
    edilen çözüm gerçeğin 1 m içinde olmalı; uzlaşım yönelimi (alt = y>34)
    korunmalı. Bu test kabul YOLUNU sentetik sahnede ilk kez kilitler —
    önceki sahneler sahayı kadrajın içine koyduğu için aday uzayı dışındaydı.
    """
    from tests.pitch_scenes import dist_map_for as scene_map
    from tests.pitch_scenes import view_homography

    h_true = view_homography(W, H, centre_m=52.5, view_len_m=60.0, taper=0.82,
                             offset_px=(9.0, -6.0))
    res = find_anchor(scene_map(h_true, W, H), (W, H), assume_camera_side=True)
    assert res.accepted, res.note
    assert res.homography is not None and "TV kuralı" in res.note
    q = res.homography @ np.array([W / 2, H - 1.0, 1.0])
    assert (q[:2] / q[2])[1] > PITCH_WIDTH_M / 2, "görüntünün altı yakın taç (y>34) olmalı"
    worst = max(_probe_m(res.homography, h_true, u, v)
                for u, v in ((W / 2, H / 2), (W * 0.25, H * 0.6), (W * 0.75, H * 0.4)))
    assert worst < 1.0, f"çapa gerçeğin {worst:.2f} m uzağında"
    # İkiz yine sunulur: karşı açı olasılığı operatöre görünür kalsın
    assert res.mirror_homography is not None
    assert np.allclose(res.mirror_homography, mirrored_homography(res.homography))


def test_camera_side_rule_is_a_convention_not_an_inference() -> None:
    """Aynı sahnenin 180° ikizi verildiğinde sonuç yine 'alt = y 68' çıkar.

    Yani kural sahneden bir şey ÖĞRENMEZ; çerçeveyi tanımlar. Karşı açıdan
    çekilmiş bir görüntüde konumlar aynalanır — belgelenen sınır budur.
    """
    from tests.pitch_scenes import dist_map_for as scene_map
    from tests.pitch_scenes import view_homography

    h_true = view_homography(W, H, offset_px=(9.0, -6.0))
    h_reverse = mirrored_homography(h_true)          # karşı açı: alt = y 0
    res = find_anchor(scene_map(h_reverse, W, H), (W, H), assume_camera_side=True)
    assert res.accepted, res.note
    assert res.homography is not None and res.mirror_homography is not None
    q = res.homography @ np.array([W / 2, H - 1.0, 1.0])
    assert (q[:2] / q[2])[1] > PITCH_WIDTH_M / 2
    # Gerçek (karşı açı) çözüm ikizde duruyor
    assert _probe_m(res.mirror_homography, h_reverse, W / 2, H / 2) < 1.0


def test_coverage_catches_a_pose_that_explains_only_part_of_the_scene() -> None:
    """Kapsama kapısı — gerçek karede görülen kusurun sentetik hâli.

    Ölçüldü (pan_zoom kare 300): modelin çoğunu kadraj dışına atıp yalnız orta
    çizgiyi oturtan duruş %97 inlier aldı ve 27 m yanlıştı; kadrajdaki orta
    yuvarlak ve ceza yayı hiç açıklanmıyordu. inlier "model → çizgi" bakar,
    kapsama "çizgi → model": görünen çizgilerin payı. Gerçek duruş ~1.0
    kapsama alırken, kadrajın yalnız bir şeridini açıklayan duruş eşiğin
    altında kalmalı.
    """
    from app.tracking.homography_fit import ANCHOR_MIN_COVERAGE, line_coverage
    from tests.pitch_scenes import dist_map_for as scene_map
    from tests.pitch_scenes import view_homography

    h_true = view_homography(W, H, offset_px=(9.0, -6.0))
    mask = scene_map(h_true, W, H) <= 0.5
    assert line_coverage(h_true, mask) > 0.95
    # Modeli 3 kat büyütüp kaydır: kadraja yalnız orta çizgi + bir taç düşer
    squeezed = view_homography(W, H, centre_m=52.5, view_len_m=20.0, taper=1.0,
                               offset_px=(0.0, -H * 1.2), scale=3.0)
    cov = line_coverage(squeezed, mask)
    assert cov < ANCHOR_MIN_COVERAGE, cov


def test_camera_side_rule_is_off_by_default() -> None:
    """Varsayılan davranış değişmedi: ipucu yoksa kabul yok — kalite iyi olsa da."""
    from tests.pitch_scenes import dist_map_for as scene_map
    from tests.pitch_scenes import view_homography

    h_true = view_homography(W, H, offset_px=(9.0, -6.0))
    res = find_anchor(scene_map(h_true, W, H), (W, H))
    assert not res.accepted and res.homography is None
    assert "180°" in res.note


def test_blank_scene_produces_no_anchor() -> None:
    """Çizgi yoksa çapa da yok — uydurma homografi üretilmemeli."""
    blank = np.full((H, W), 50.0, dtype=float)
    res = find_anchor(blank, (W, H))
    assert not res.accepted and res.homography is None


def test_candidates_cover_the_pitch() -> None:
    """Aday üretimi sahanın her yerine bakan duruşları içermeli."""
    cands = anchor_candidates((W, H))
    assert len(cands) > 30
    centres = []
    for h in cands:
        q = h @ np.array([W / 2, H / 2, 1.0])
        centres.append((q[:2] / q[2])[0])
    centres = np.array(centres)
    assert centres.min() < 30.0 and centres.max() > 75.0, (centres.min(), centres.max())
