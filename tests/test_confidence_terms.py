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

TERIMLER = {"sample", "magnitude", "corroboration", "quality", "history",
            "gate", "corr_bonus", "hist_adj"}


def test_every_weighted_driver_has_a_numeric_term() -> None:
    """Ağırlığı olan her sürücü ölçülebilir olmalı — biri eksikse atıf kör kalır."""
    c = score_confidence(sample_size=6, magnitude=0.5, corroboration=1,
                         data_quality=0.8, historical_hit_rate=0.7)
    assert set(c.terms) >= TERIMLER


def test_terms_reproduce_the_composite_score() -> None:
    """Kırılım gerçekten skoru açıklamalı; süs olmamalı.

    Kompozisyon: kanıt × kapı + teyit bonusu + geçmiş düzeltmesi.
    Terimlerden skor yeniden üretilemiyorsa `terms` başka bir hesabı
    anlatıyordur ve ona bakarak yapılan her çıkarım yanlış olur.
    """
    c = score_confidence(sample_size=6, magnitude=0.5, corroboration=2,
                         data_quality=0.8, historical_hit_rate=0.7)
    t = c.terms
    beklenen = t["magnitude"] * t["gate"] + t["corr_bonus"] + t["hist_adj"]
    assert abs(beklenen - c.score) < 0.002


def test_adequate_data_does_not_inflate_the_score() -> None:
    """ASIL DÜZELTME: yeterli veri BONUS vermez, yetersiz veri CEZA verir.

    Eskiden sample ve quality ağırlıklı toplama giriyordu; ikisi de neredeyse
    hep 1.0 geldiği için skorun %45'i sabit dolguydu. Ölçüldü (n=513): 448
    karar TEK bir çeyrek bine düşüyordu. Artık mükemmel veriyle skor kanıtın
    KENDİSİ kadardır.
    """
    mukemmel = score_confidence(sample_size=99, magnitude=0.30, data_quality=1.0)
    assert abs(mukemmel.score - 0.30) < 0.002, "yeterli veri skoru şişirmemeli"

    zayif = score_confidence(sample_size=1, magnitude=0.30, data_quality=1.0)
    assert zayif.score < mukemmel.score, "az örnek kanıtı zayıflatmalı"

    kotu_veri = score_confidence(sample_size=99, magnitude=0.30, data_quality=0.2)
    assert kotu_veri.score < mukemmel.score, "düşük kalite kanıtı zayıflatmalı"


def test_weakest_link_decides_the_gate() -> None:
    """Az örnek VE düşük kalite üst üste binip kanıtı yok etmemeli."""
    tek_sorun = score_confidence(sample_size=1, magnitude=0.8, data_quality=1.0)
    iki_sorun = score_confidence(sample_size=1, magnitude=0.8, data_quality=0.9)
    assert abs(tek_sorun.score - iki_sorun.score) < 0.01


def test_absent_history_does_not_move_the_score() -> None:
    """"Bilmiyorum" ile "tam ortada" aynı şey değil.

    Eskiden geçmiş yokken 0.5 nötr sayılıp yine de ağırlıkla toplanıyordu.
    """
    yok = score_confidence(sample_size=8, magnitude=0.6)
    orta = score_confidence(sample_size=8, magnitude=0.6, historical_hit_rate=0.5)
    iyi = score_confidence(sample_size=8, magnitude=0.6, historical_hit_rate=0.9)
    assert yok.score == orta.score
    assert iyi.score > yok.score


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
