"""app/tracking/camera.py — kamera sabit mi, çeviriyor mu, yayın mı?

Neden kritik: takip hattı TEK ve SABİT bir homografi kullanır. Kamera çevirince
oyuncular sahada kaymış görünür (ölçüldü: 100 px ≈ 3.6 m) ve sinyal eşikleri
2.5–4 m olduğu için **kamera hareketi tek başına sahte taktik sinyal üretir**.
Bu modül videoyu işlemeden önce bunu yakalayıp karelere doğru kaynak etiketini
koyar; etiket motorlara kadar gidip şekil/bölge analizini kapatır.

cv2 yalnız venv-cv'de olduğu için burada saf karar mantığı test edilir
(`classify_pairs` / `summarise`); `analyze_video` onların ince sarmalayıcısı.
"""
from __future__ import annotations

from app.tracking.camera import (
    BROADCAST_SOURCE,
    STATIC_SOURCE,
    classify_pair,
    classify_pairs,
    summarise,
)


def test_streaming_and_batch_classification_agree() -> None:
    """Canlı hat ile çevrimdışı analiz AYNI kesme tanımını kullanmalı.

    `CutDetector` (kare kare, hattın içinde) ve `classify_pairs` (video önceden
    taranırken) ikisi de `classify_pair`e iner. Ayrı eşik kopyaları olsaydı biri
    kesme dediğine öbürü çevirme der, davranış videoya göre sessizce değişirdi.
    """
    cases = [(0.3, 0.9, 0.02), (25.0, 0.55, 0.6), (40.0, 0.02, 0.8), (1.0, 0.3, 0.1)]
    motions, responses, hists = (list(c) for c in zip(*cases, strict=True))
    assert classify_pairs(motions, responses, hists) == [
        classify_pair(m, r, h) for m, r, h in cases
    ]


def test_static_camera_pairs_are_static() -> None:
    n = 20
    labels = classify_pairs([0.3] * n, [0.9] * n, [0.02] * n)
    assert set(labels) == {"static"}


def test_fast_pan_is_movement_not_a_cut() -> None:
    """Hızlı çevirme histogramı çok değiştirir ama kayması TUTARLIDIR.

    Bu ayrım olmadan her hızlı pan kesme sanılır ve yayın tespiti bozulur.
    """
    labels = classify_pairs([25.0] * 10, [0.55] * 10, [0.6] * 10)
    assert set(labels) == {"moving"}, labels


def test_cut_is_big_content_change_without_coherent_shift() -> None:
    labels = classify_pairs([40.0], [0.02], [0.8])
    assert labels == ["cut"]


def test_static_camera_verdict_keeps_full_analysis_open() -> None:
    n = 40
    v = summarise(classify_pairs([0.4] * n, [0.95] * n, [0.01] * n),
                  [0.4] * n, sample_fps=4.0)
    assert v.kind == "static" and v.continuous is True
    assert v.source_name == STATIC_SOURCE
    assert v.cuts == 0 and v.moving_fraction == 0.0
    assert "tam analiz açık" in v.note


def test_broadcast_verdict_closes_full_pitch_analysis() -> None:
    """TV yayını: sık kesme + kamera hareketi → top-merkezli sayılmalı."""
    motions, responses, hists = [], [], []
    for i in range(40):
        cut = i % 8 == 0                    # ~her 2 saniyede bir kesme
        motions.append(50.0 if cut else 18.0)
        responses.append(0.02 if cut else 0.5)
        hists.append(0.9 if cut else 0.25)
    v = summarise(classify_pairs(motions, responses, hists), motions, sample_fps=4.0)
    assert v.kind == "broadcast" and v.continuous is False
    assert v.source_name == BROADCAST_SOURCE
    assert v.cuts == 5 and v.cuts_per_minute > 3.0
    assert "TOP-MERKEZLİ" in v.note and "şekil/bölge analizi kapalı" in v.note


def test_panning_single_shot_also_closes_full_pitch_analysis() -> None:
    """Kesme yok ama kamera sürekli çeviriyor: sabit homografi yine geçersiz."""
    n = 40
    v = summarise(classify_pairs([15.0] * n, [0.6] * n, [0.2] * n),
                  [15.0] * n, sample_fps=4.0)
    assert v.kind == "panning" and v.continuous is False
    assert v.source_name == BROADCAST_SOURCE
    assert v.cuts == 0
    assert "kare başına kalibrasyon" in v.note


def test_unknown_camera_falls_back_to_restricted_mode() -> None:
    """Analiz yapılamazsa güvenli taraf: kısıtlı mod, tam analiz açılmaz."""
    v = summarise([], [], sample_fps=4.0)
    assert v.kind == "unknown" and v.continuous is False
    assert v.source_name == BROADCAST_SOURCE
    assert "güvenli tarafta" in v.note


def test_occasional_wobble_still_counts_as_static() -> None:
    """Rüzgârda hafif titreyen sabit kamera yayın sayılmamalı."""
    motions = [0.5] * 36 + [4.0] * 4        # %10 hareket
    v = summarise(classify_pairs(motions, [0.9] * 40, [0.05] * 40),
                  motions, sample_fps=4.0)
    assert v.kind == "static" and v.continuous is True
