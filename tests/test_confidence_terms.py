"""Güven skorunun SAYISAL sürücü kırılımı kararla birlikte saklanabilmeli.

Neden ayrı bir test dosyası: bu alan kozmetik değil, **ölçüm altyapısı**.
Kalibrasyon "sistem fazla güvenli (%84 diyor, %58 tutuyor)" diyebiliyordu ama
hangi sürücünün yanılttığını söyleyemiyordu — çünkü kararla yalnız birleşik
skor saklanıyordu (ölçüldü: 74 kararın hepsinde `context_json` boştu). Atıf
olmadan ağırlık değiştirmek tahmindir.

`drivers` insan içindir (metin), `terms` ölçüm içindir (sayı). İkisi
karıştırılırsa analiz yapılamaz.
"""
from __future__ import annotations

from app.engine.confidence import score_confidence
from app.engine.confidence.compute import (
    W_CORROBORATION,
    W_HISTORY,
    W_MAGNITUDE,
    W_QUALITY,
    W_SAMPLE,
)

TERIMLER = {"sample", "magnitude", "corroboration", "quality", "history"}


def test_every_weighted_driver_has_a_numeric_term() -> None:
    """Ağırlığı olan her sürücü ölçülebilir olmalı — biri eksikse atıf kör kalır."""
    c = score_confidence(sample_size=6, magnitude=0.5, corroboration=1,
                         data_quality=0.8, historical_hit_rate=0.7)
    assert set(c.terms) >= TERIMLER


def test_terms_reproduce_the_composite_score() -> None:
    """Kırılım gerçekten skoru açıklamalı; süs olmamalı.

    Ağırlıklı toplam skora eşit değilse `terms` başka bir hesabı anlatıyordur
    ve ona bakarak yapılan her çıkarım yanlış olur.
    """
    c = score_confidence(sample_size=6, magnitude=0.5, corroboration=2,
                         data_quality=0.8, historical_hit_rate=0.7)
    t = c.terms
    beklenen = (
        W_SAMPLE * t["sample"] + W_MAGNITUDE * t["magnitude"]
        + W_CORROBORATION * t["corroboration"] + W_QUALITY * t["quality"]
        + W_HISTORY * t["history"]
    )
    assert abs(beklenen - c.score) < 0.002


def test_raw_inputs_survive_saturation() -> None:
    """Doygunluğa giren girdiler HAM haliyle de saklanmalı.

    corroboration 3 ile 9 arasında terim neredeyse hiç değişmiyor (1-0.5^n
    doygunluğu: 0.875 → 0.998) ama girdi ÜÇ KAT. Geriye dönük analizde ikisini
    ayırt edememek "daha çok teyit daha mı iyi?" sorusunu cevapsız bırakırdı.
    Aynı şekilde sample_size 12'de terim tavana vuruyor (SAMPLE_FULL).
    """
    az = score_confidence(sample_size=99, magnitude=0.5, corroboration=3)
    cok = score_confidence(sample_size=99, magnitude=0.5, corroboration=9)
    assert abs(az.terms["corroboration"] - cok.terms["corroboration"]) < 0.13
    assert az.terms["raw_corroboration"] == 3.0
    assert cok.terms["raw_corroboration"] == 9.0

    # sample terimi tavanda ama ham değer korunuyor
    assert az.terms["sample"] == 1.0
    assert az.terms["raw_sample_size"] == 99.0


def test_composite_score_is_kept_for_comparison() -> None:
    """Ham birleşik skor da terimlerde durmalı.

    Kalibrasyon `confidence` alanını olasılıkla EZİYOR; ham değer başka yerde
    kalmıyor. "Bütün, parçalarından iyi mi?" sorusu ancak buna bakarak sorulur.
    """
    c = score_confidence(sample_size=6, magnitude=0.5)
    assert c.terms["score"] == c.score


def test_missing_history_is_marked_not_silently_neutral() -> None:
    """Geçmiş yoksa 0.5 nötr alınıyor — bu bir VERİ EKSİĞİ, ölçümde görünmeli.

    0.5 hem "geçmiş yok" hem "geçmiş tam ortada" anlamına gelebilir; ikisini
    ayırmayan bir kayıt, history sürücüsünün analizini bozar.
    """
    yok = score_confidence(sample_size=6, magnitude=0.5)
    var = score_confidence(sample_size=6, magnitude=0.5, historical_hit_rate=0.5)
    assert yok.terms["history"] == var.terms["history"] == 0.5
    assert yok.terms["has_history"] == 0.0
    assert var.terms["has_history"] == 1.0


def test_prose_drivers_still_exist_for_humans() -> None:
    """Sayısal kırılım metin açıklamanın YERİNE geçmez; ikisi de gerekir."""
    c = score_confidence(sample_size=3, magnitude=0.2, corroboration=0)
    assert c.drivers and any("örnek destekliyor" in d for d in c.drivers)
    assert c.terms
