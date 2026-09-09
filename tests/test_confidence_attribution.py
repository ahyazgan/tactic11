"""Sürücü atıfı — güvenin hangi bileşeni sonucu gerçekten ayırıyor?

Kalibrasyon "sistem fazla güvenli" diyebiliyor ama NEDEN diyemiyor. Bu modül
her sürücü için tek soruyu sorar: terim yüksekken sonuç daha mı sık olumlu?

En kritik davranış: **ters çalışan sürücüyü yakalamak**. Güveni yanlış yönde
artıran bir bileşen, hiç katkı vermeyen bir bileşenden daha zararlıdır — ve
birleşik skora bakarak görünmez.
"""
from __future__ import annotations

from app.engine.confidence.attribution import (
    MIN_SAMPLES,
    attribute,
    attribute_driver,
    attribute_stratified,
)


def _pairs(pos: list[float], neg: list[float], key: str = "x"):
    return ([({key: v}, True) for v in pos] + [({key: v}, False) for v in neg])


def test_perfectly_separating_driver_scores_auc_one() -> None:
    d = attribute_driver("x", [0.9] * 10, [0.1] * 10)
    assert d.auc == 1.0
    assert d.verdict == "ayırıyor"
    assert d.lift > 0


def test_reversed_driver_is_flagged_not_just_weak() -> None:
    """TERS sürücü, katkısız sürücüden AYRI raporlanmalı.

    Güveni yanlış yönde artıran bileşen zararlıdır: sistem tam da yanılacağı
    yerde daha çok güvenir. "ayırmıyor" demek bunu gizlerdi.
    """
    d = attribute_driver("x", [0.1] * 10, [0.9] * 10)
    assert d.auc == 0.0
    assert d.verdict == "TERS"
    assert "YANLIŞ yönde" in d.note


def test_noise_is_called_noise() -> None:
    """Karışık dağılım 'ayırıyor' sayılmamalı — gürültü bandı var."""
    d = attribute_driver("x", [0.4, 0.6] * 8, [0.4, 0.6] * 8)
    assert abs(d.auc - 0.5) < 0.06
    assert d.verdict == "ayırmıyor"


def test_thin_evidence_refuses_to_judge() -> None:
    """Az örnekle sürücü hakkında hüküm verilmez."""
    d = attribute_driver("x", [0.9, 0.8], [0.1])
    assert d.verdict == "yetersiz veri"
    assert str(MIN_SAMPLES) in d.note


def test_single_class_refuses_to_judge() -> None:
    """Hiç olumsuz sonuç yoksa ayrım gücü tanımsızdır."""
    d = attribute_driver("x", [0.5] * 30, [])
    assert d.verdict == "yetersiz veri"


def test_report_ranks_by_distance_from_chance() -> None:
    """En bilgilendirici sürücü (ister lehte ister TERS) başa gelmeli."""
    samples = []
    for v_ok, v_ters, ok in [(0.9, 0.1, True)] * 10 + [(0.5, 0.9, False)] * 10:
        samples.append(({"iyi": v_ok, "ters": v_ters, "sabit": 0.7}, ok))
    r = attribute(samples)
    assert r.drivers[0].driver in {"iyi", "ters"}
    assert r.drivers[-1].driver == "sabit", "sabit terim en sona düşmeli"


def test_report_headline_names_the_harmful_driver() -> None:
    samples = [({"ters": 0.1}, True)] * 10 + [({"ters": 0.9}, False)] * 10
    r = attribute(samples)
    assert r.harmful and r.harmful[0].driver == "ters"
    assert "TERS" in r.headline


def test_report_says_so_when_nothing_discriminates() -> None:
    """Bulgu 'hiçbiri ayırmıyor' ise sistem bunu AÇIKÇA söylemeli."""
    samples = _pairs([0.5] * 12, [0.5] * 12)
    r = attribute(samples)
    assert not r.useful and not r.harmful
    assert "gürültüden ibaret" in r.headline


def test_missing_term_is_skipped_not_zeroed() -> None:
    """Eksik terim sıfır sayılırsa sürücü haksız yere aşağı çekilir."""
    samples = [({"a": 0.9}, True)] * 10 + [({"a": 0.1}, False)] * 10
    samples += [({"b": 0.5}, True)] * 2          # 'a' yok
    r = attribute(samples)
    a = next(d for d in r.drivers if d.driver == "a")
    assert a.n_pos == 10 and a.n_neg == 10
    assert a.auc == 1.0


def test_empty_input_is_honest() -> None:
    r = attribute([])
    assert r.n_decisions == 0
    assert r.headline == "ölçülmüş karar yok"


# --- katmanlı ölçüm: karıştırıcıyı kontrol et ------------------------------ #

def test_stratified_auc_removes_a_pure_confound() -> None:
    """ASIL KUSUR: cetvel ortalamaya dönüş taşıyor.

    Kurgu: sürücünün sonuçla HİÇ ilişkisi yok; sonucu belirleyen tamamen
    karıştırıcı. Ama sürücü ile karıştırıcı ilişkili olduğu için HAM AUC
    sürücüyü suçlu gösterir. Katmanlı ölçüm bunu temizlemeli.
    """
    samples = []
    for i in range(80):
        conf = i / 80.0                       # karıştırıcı
        # Sonucu AĞIRLIKLI olarak karıştırıcı belirler (%75), sürücünün
        # kendi katkısı YOK. Tam belirlenim kurmuyoruz: o zaman katmanlar tek
        # sınıflı kalır ve ölçülecek bir şey kalmaz (ayrı test).
        ok = (conf < 0.5) if (i % 4) else (conf >= 0.5)
        samples.append((conf, ok, conf))      # sürücü = karıştırıcının kopyası
    ham = attribute_driver("x", [v for v, o, _ in samples if o],
                           [v for v, o, _ in samples if not o])
    kat = attribute_stratified(samples, "x")
    assert ham.verdict == "TERS", "kurgu gereği ham ölçüm suçlu göstermeli"
    assert kat.verdict in {"ayırmıyor", "ayrıştırılamıyor"}, kat.note
    assert kat.auc > ham.auc, "katmanlama yanlılığı azaltmalı"


def test_perfect_confound_says_it_cannot_separate() -> None:
    """Karıştırıcı sonucu TAM belirliyorsa dürüst cevap "ayıramıyorum"dur.

    Ham hükme sessizce düşmek sürücüyü haksız yere suçlu gösterirdi.
    """
    samples = [(i / 60.0, i / 60.0 < 0.5, i / 60.0) for i in range(60)]
    kat = attribute_stratified(samples, "x")
    assert kat.verdict == "ayrıştırılamıyor"
    assert kat.auc == 0.5
    assert "ÖLÇÜLEMEZ" in kat.note


def test_stratified_keeps_a_real_effect() -> None:
    """Gerçek etki katmanlama SONRASI da görünmeli — yoksa yöntem körleştirir."""
    samples = []
    for i in range(80):
        # Karıştırıcı, sürücüden BAĞIMSIZ olmalı: her katmanda iki sınıf da
        # bulunsun. (i // 2) kullanınca ardışık çift/tek aynı katmana düşer.
        conf = (i // 2 % 5) / 5.0
        gercek = 0.9 if i % 2 == 0 else 0.1   # sürücü sonucu GERÇEKTEN belirliyor
        samples.append((gercek, i % 2 == 0, conf))
    kat = attribute_stratified(samples, "x")
    assert kat.verdict == "ayırıyor"
    assert kat.auc > 0.9


def test_stratified_falls_back_on_thin_data() -> None:
    """Az örnekte katmanlama gürültü üretir; ham ölçüme düşülür."""
    samples = [(0.9, True, 0.1), (0.1, False, 0.9)]
    kat = attribute_stratified(samples, "x")
    assert kat.verdict == "yetersiz veri"
