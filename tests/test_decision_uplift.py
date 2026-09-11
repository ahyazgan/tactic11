"""engine.decision_uplift — uygulanan vs uygulanmayan öneri kıyası.

Külliyat bulgusu (502 karar): kararlar uygulanmadığı için "sonra ne oldu" ile
"öneri yüzünden ne oldu" ayrılamıyor. Bu motor karşı-olguyu (`applied=False`)
kullanır. Testler üç şeyi kilitler:

1. Bir kol boşsa hüküm VERİLMEZ — sayı uydurulmaz.
2. Ortalamaya dönüş karıştırıcısı katmanlamayla düşer: koç öneriyi hep kötü
   giderken uyguluyorsa ham kıyas uygulanan kolu haksız yere öne çıkarır.
3. Hüküm eşikleri (`MIN_EFFECT`, `MIN_SAMPLES`) sabit ve tekrarlanabilir.
"""
from __future__ import annotations

from app.engine.confidence.attribution import MIN_SAMPLES
from app.engine.decision_uplift import (
    MIN_EFFECT,
    UpliftSample,
    compute_decision_uplift,
)


def _s(applied: bool | None, positive: bool, *, pre: float = 0.0,
       xg: float = 0.0) -> UpliftSample:
    return UpliftSample(applied=applied, positive=positive, xg_delta=xg, pre=pre)


def _arm(applied: bool, n: int, pos: int, *, pre: float) -> list[UpliftSample]:
    """`n` örnek, `pos` tanesi olumlu — tek katman (`pre`) içinde."""
    return [_s(applied, i < pos, pre=pre) for i in range(n)]


# --- kol boşsa hüküm yok ---------------------------------------------------- #

def test_no_counterfactual_gives_no_verdict() -> None:
    """Külliyatın hâli: hepsi işaretsiz ya da uygulanmış → kıyas YOK."""
    samples = _arm(True, 20, 10, pre=0.0) + [_s(None, True)] * 3
    u = compute_decision_uplift(1, samples).value
    assert u.verdict == "karşı-olgu yok"
    assert u.applied.n == 20 and u.not_applied.n == 0 and u.unknown == 3
    assert u.stratified_hit_rate_diff is None
    assert u.raw_hit_rate_diff is None
    assert "Uygulamadım" in u.note


def test_no_applied_arm_gives_no_verdict() -> None:
    u = compute_decision_uplift(1, _arm(False, 16, 8, pre=0.0)).value
    assert u.verdict == "uygulanan yok"
    assert u.applied.n == 0 and u.not_applied.n == 16


def test_thin_data_reports_numbers_but_no_verdict() -> None:
    samples = _arm(True, 5, 5, pre=0.0) + _arm(False, 5, 0, pre=0.0)
    assert len(samples) < MIN_SAMPLES
    u = compute_decision_uplift(1, samples).value
    assert u.verdict == "yetersiz veri"
    # Sayılar yine de raporlanır — yön göstergesi olarak
    assert u.applied.hit_rate == 1.0 and u.not_applied.hit_rate == 0.0
    assert u.raw_hit_rate_diff == 1.0


# --- gerçek etki ------------------------------------------------------------ #

def _four_strata(applied_pos: int, not_pos: int) -> list[UpliftSample]:
    """4 katman × (4 uygulanan + 4 uygulanmayan); katman içi isabetler sabit."""
    out: list[UpliftSample] = []
    for k in range(4):
        out += _arm(True, 4, applied_pos, pre=k * 0.1)
        out += _arm(False, 4, not_pos, pre=k * 0.1)
    return out


def test_uplift_when_applied_wins_inside_every_stratum() -> None:
    u = compute_decision_uplift(1, _four_strata(applied_pos=3, not_pos=1)).value
    assert u.verdict == "uplift"
    assert u.stratified_hit_rate_diff == 0.5
    assert u.raw_hit_rate_diff == 0.5
    assert len(u.strata) == 4
    assert all(s.hit_rate_diff == 0.5 for s in u.strata)


def test_reverse_effect_is_named_ters() -> None:
    u = compute_decision_uplift(1, _four_strata(applied_pos=1, not_pos=3)).value
    assert u.verdict == "TERS"
    assert u.stratified_hit_rate_diff == -0.5


def test_small_difference_is_no_difference() -> None:
    """Eşik altı fark 'uplift' diye satılmaz."""
    samples: list[UpliftSample] = []
    for pre in (-0.1, 0.1):
        samples += _arm(True, 20, 11, pre=pre)     # %55
        samples += _arm(False, 20, 10, pre=pre)    # %50
    u = compute_decision_uplift(1, samples, strata=2).value
    assert u.stratified_hit_rate_diff == 0.05
    assert abs(u.stratified_hit_rate_diff) < MIN_EFFECT
    assert u.verdict == "fark yok"


# --- karıştırıcı: ortalamaya dönüş ------------------------------------------ #

def test_mean_reversion_confound_is_removed_by_stratification() -> None:
    """ASIL KORUMA.

    Koç öneriyi çoğunlukla KÖTÜ giderken uyguluyor; kötü giderken cetvel
    (`sonraki − önceki`) zaten sık olumlu döner. Katman İÇİNDE iki kol eşit
    (%75 / %25); ham kıyas yine de uygulanan kola +25 puan yazar. Katmanlı
    fark sıfır olmalı, hüküm 'fark yok'.
    """
    samples: list[UpliftSample] = []
    # kötü gidiş (pre < 0): iki kol da %75, uygulanan kol kalabalık
    samples += _arm(True, 12, 9, pre=-0.1)
    samples += _arm(False, 4, 3, pre=-0.1)
    # iyi gidiş (pre > 0): iki kol da %25, uygulanmayan kol kalabalık
    samples += _arm(True, 4, 1, pre=0.1)
    samples += _arm(False, 12, 3, pre=0.1)

    u = compute_decision_uplift(1, samples, strata=2).value
    assert u.raw_hit_rate_diff == 0.25          # yanıltıcı ham "uplift"
    assert u.stratified_hit_rate_diff == 0.0    # karıştırıcı düşünce yok
    assert u.verdict == "fark yok"
    assert all(s.hit_rate_diff == 0.0 for s in u.strata)


def test_single_arm_strata_cannot_be_resolved() -> None:
    """Koç yalnız kötü giderken uyguluyor, iyi giderken HİÇ uygulamıyor.

    Katmanlar tek kollu kalır; ham fark (+50 puan) tamamen karıştırıcıdır.
    Dürüst cevap 'ayrıştırılamıyor' — ham farka düşülmez.
    """
    samples = _arm(True, 8, 6, pre=-0.1) + _arm(False, 8, 2, pre=0.1)
    u = compute_decision_uplift(1, samples, strata=2).value
    assert u.raw_hit_rate_diff == 0.5
    assert u.stratified_hit_rate_diff is None
    assert u.verdict == "ayrıştırılamıyor"
    assert "yanıltıcı" in u.note


# --- sözleşme --------------------------------------------------------------- #

def test_xg_delta_difference_is_reported_per_arm() -> None:
    samples = ([_s(True, True, pre=0.0, xg=0.02)] * 8
               + [_s(False, False, pre=0.0, xg=-0.01)] * 8)
    u = compute_decision_uplift(1, samples).value
    assert u.applied.mean_xg_delta == 0.02
    assert u.not_applied.mean_xg_delta == -0.01
    assert u.raw_xg_delta_diff == 0.03


def test_audit_is_reproducible() -> None:
    res = compute_decision_uplift(217, _four_strata(3, 1))
    assert res.audit.engine == "engine.decision_uplift"
    assert res.audit.inputs["marked"] == 32 and res.audit.inputs["unknown"] == 0
    assert "Gözlemsel" in res.audit.formula
    assert res.value == compute_decision_uplift(217, _four_strata(3, 1)).value
