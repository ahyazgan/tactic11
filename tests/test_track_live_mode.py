"""Canlı hattın kamera kipi kararları — TV yayını desteğinin beyni.

İki karar var ve ikisi de dürüstlük kararı:

1. `plan_mode` — kamera hareketliyse kare başına kalibrasyonu ve kesme sonrası
   yeniden yakalamayı aç. Açılmazsa sabit homografi geçersizdir ve sistem
   kamera hareketini taktik sinyal sanar (ölçüldü: 100 px ≈ 3.6 m, eşikler
   2.5–4 m).

2. `source_after_run` — etiketi TAHMİNE değil GERÇEKLEŞENE göre ver.
   Kalibrasyonun tutacağını varsayıp "tam saha analizi açık" demek,
   tutmadığında avuç dolusu kareden şekil sinyali üretmek demektir.

Kararlar `app/tracking/camera.py`de yaşar, betiklerde değil: canlı hat
(`scripts/track_live.py`) ve çevrimdışı hat (`scripts/track_video.py`) İKİSİ DE
aynı fonksiyonları çağırmalı. Ayrı kopyalar olsaydı aynı görüntüde farklı
etiket üretirler, kareler bir sınıfta yazılıp başka bir sınıfta yorumlanırdı.

cv2 gerekmez: ikisi de saf mantıktır.
"""
from __future__ import annotations

import pytest

from app.tracking.camera import (
    BROADCAST_SOURCE,
    MIN_CALIBRATED_RATIO,
    STATIC_SOURCE,
    plan_mode,
    source_after_run,
)

# --- plan_mode -------------------------------------------------------------- #

def test_static_camera_needs_no_per_frame_work() -> None:
    """Kulüp senaryosu: sabit geniş açı. Tek kalibrasyon geçerli, ek iş yok."""
    m = plan_mode(moving=False, per_frame_mode="auto", reacquire_mode="auto")
    assert m["per_frame"] is False
    assert m["reacquire"] is False
    assert m["source"] == STATIC_SOURCE


def test_broadcast_turns_on_both_defences() -> None:
    """TV yayını: kare başına kalibrasyon VE kesme sonrası yeniden yakalama.

    Yeniden yakalama olmadan ilk kesmede takip kopar ve segmentin kalanındaki
    her kare atılır — yayın için ölümcül.
    """
    m = plan_mode(moving=True, per_frame_mode="auto", reacquire_mode="auto")
    assert m["per_frame"] is True
    assert m["reacquire"] is True
    assert m["source"] == STATIC_SOURCE, "kalibrasyon açıkken konumlar gerçek"


def test_moving_camera_without_calibration_is_ball_centric() -> None:
    """Kalibrasyon elle kapatıldıysa hareketli kamerada konumlara güvenilmez.

    Sistem susmaz ama SINIRINI söyler: kareler top-merkezli sayılır, şekil ve
    bölge analizi kapanır.
    """
    m = plan_mode(moving=True, per_frame_mode="off", reacquire_mode="auto")
    assert m["per_frame"] is False
    assert m["source"] == BROADCAST_SOURCE


def test_explicit_modes_override_the_camera_verdict() -> None:
    """Elle 'on' demek tespitten üstündür — sabit kamerada bile açılır."""
    m = plan_mode(moving=False, per_frame_mode="on", reacquire_mode="on")
    assert m["per_frame"] is True and m["reacquire"] is True

    m = plan_mode(moving=True, per_frame_mode="auto", reacquire_mode="off")
    assert m["per_frame"] is True and m["reacquire"] is False


# --- source_after_run ------------------------------------------------------- #

def test_good_calibration_keeps_the_planned_source() -> None:
    mode = plan_mode(moving=True, per_frame_mode="auto", reacquire_mode="auto")
    source, note = source_after_run(mode, 0.9)
    assert source == STATIC_SOURCE
    assert note == ""


def test_sparse_calibration_downgrades_to_ball_centric() -> None:
    """Az kare kalibre olduysa konumlar GERÇEK ama SEYREK.

    Sorun doğruluk değil: şekil/bölge analizi avuç dolusu kareden hesaplanınca
    gürültülü olur. O yüzden tam saha analizi kapatılır.
    """
    mode = plan_mode(moving=True, per_frame_mode="auto", reacquire_mode="auto")
    source, note = source_after_run(mode, MIN_CALIBRATED_RATIO / 2)
    assert source == BROADCAST_SOURCE
    assert "top-merkezli" in note


def test_downgrade_boundary_is_inclusive() -> None:
    """Eşiğin tam üstü kabul, altı düşürme — sınır belirsiz kalmamalı."""
    mode = plan_mode(moving=True, per_frame_mode="auto", reacquire_mode="auto")
    assert source_after_run(mode, MIN_CALIBRATED_RATIO)[0] == STATIC_SOURCE
    assert source_after_run(mode, MIN_CALIBRATED_RATIO - 0.01)[0] == BROADCAST_SOURCE


def test_static_camera_is_never_downgraded() -> None:
    """Sabit kamerada kare başına kalibrasyon yok; oran da yok, düşürme de."""
    mode = plan_mode(moving=False, per_frame_mode="auto", reacquire_mode="auto")
    assert source_after_run(mode, None) == (STATIC_SOURCE, "")
    assert source_after_run(mode, 0.01) == (STATIC_SOURCE, "")


@pytest.mark.parametrize("ratio", [None, 0.0, 1.0])
def test_missing_or_extreme_ratios_do_not_crash(ratio) -> None:
    mode = plan_mode(moving=True, per_frame_mode="auto", reacquire_mode="auto")
    source, _ = source_after_run(mode, ratio)
    assert source in {STATIC_SOURCE, BROADCAST_SOURCE}
