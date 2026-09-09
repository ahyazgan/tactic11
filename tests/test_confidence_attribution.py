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
