"""Güven kalibrasyonu — kanıt skorunu gerçek olasılığa eşleme.

Neden var: `score_confidence` bir OLASILIK değil, kanıt gücü üretir. Gerçek
veride ölçüldü — sistem ortalama %84 diyor, gerçekleşme %58. Mevcut geri
besleme etkisizdi: `historical_hit_rate` beş terimden biri, ağırlığı 0.10 ve
nötr 0.5'e göre tartılıyor, yani skoru en fazla ±0.05 oynatabiliyor.
"""
from __future__ import annotations

from app.engine.confidence.calibration import (
    MIN_SAMPLES,
    CalibrationMap,
    fit_calibration,
)


def _samples(pairs: list[tuple[float, int, int]]) -> list[tuple[float, bool]]:
    """(skor, isabet, toplam) → tekil örneklere aç."""
    out: list[tuple[float, bool]] = []
    for score, hits, total in pairs:
        out += [(score, True)] * hits + [(score, False)] * (total - hits)
    return out


def test_refuses_to_calibrate_on_thin_history() -> None:
    """Az veriden kalibrasyon uydurmak, kalibrasyonsuzluktan kötüdür."""
    cmap = fit_calibration(_samples([(0.9, 3, 5)]))
    assert not cmap.fitted
    assert cmap.samples == 5
    assert "yetersiz" in cmap.note
    # Eşleme yokken ham skor korunmalı
    assert cmap.apply(0.9) == 0.9
    assert cmap.apply(0.2) == 0.2


def test_corrects_systematic_overconfidence() -> None:
    """Asıl vaka: sistem %90 diyor, gerçekte %58 tutuyor → skor aşağı çekilmeli.

    Gerçek ölçümden alınan dağılım (n=41): kararların çoğu 0.8-1.0 bandında ve
    o bantta gerçekleşme %58.
    """
    cmap = fit_calibration(_samples([
        (0.35, 1, 1),
        (0.55, 4, 5),
        (0.72, 0, 2),
        (0.90, 19, 33),
    ]))
    assert cmap.fitted, cmap.note
    assert cmap.samples == 41
    high = cmap.apply(0.90)
    assert high < 0.75, f"fazla güven düzeltilmedi: {high}"
    assert high > 0.40, f"aşırı düzeltildi: {high}"


def test_enforces_monotonicity() -> None:
    """Daha çok kanıt, daha DÜŞÜK olasılığa eşlenmemeli.

    Gerçek veride ihlal görüldü: %60-80 bininde n=2 ile gerçekleşme %0 iken
    %80-100 bininde %58. Ham haliyle bırakılırsa "kanıt arttıkça güven düşer"
    gibi saçma bir eşleme çıkar.
    """
    cmap = fit_calibration(_samples([
        (0.15, 2, 8),
        (0.40, 6, 10),
        (0.65, 0, 4),      # ihlal: aşağı düşüyor
        (0.90, 14, 20),
    ]))
    assert cmap.fitted
    probs = [b.probability for b in cmap.bins]
    assert probs == sorted(probs), probs


def test_shrinks_noisy_small_bins_toward_base_rate() -> None:
    """Tek örnekli bin %100 demez — taban orana çekilir."""
    cmap = fit_calibration(_samples([
        (0.10, 0, 10), (0.35, 5, 10), (0.60, 5, 10), (0.90, 1, 1),
    ]))
    assert cmap.fitted
    top = cmap.bins[-1]
    assert top.raw_rate == 1.0          # ham oran %100
    assert top.probability < 0.95, top  # ama olasılık çekilmiş


def test_underconfidence_is_also_corrected() -> None:
    """Kalibrasyon tek yönlü değil: fazla temkinli sistem yukarı çekilmeli."""
    cmap = fit_calibration(_samples([
        (0.20, 6, 10), (0.30, 8, 10), (0.40, 9, 10), (0.45, 9, 10),
    ]))
    assert cmap.fitted
    assert cmap.apply(0.30) > 0.45, "düşük skor yukarı kalibre edilmedi"


def test_empty_history_is_safe() -> None:
    cmap = fit_calibration([])
    assert not cmap.fitted and cmap.samples == 0
    assert cmap.apply(0.7) == 0.7


def test_map_is_serialisable_and_explains_itself() -> None:
    """Arayüz/denetim için: eşleme kendini anlatmalı."""
    cmap = fit_calibration(_samples([(0.3, 2, 10), (0.6, 6, 10), (0.9, 9, 12)]))
    assert isinstance(cmap, CalibrationMap)
    assert cmap.samples >= MIN_SAMPLES
    assert "kalibre edildi" in cmap.note
    assert all(0.0 <= b.probability <= 1.0 for b in cmap.bins)
    assert sum(b.n for b in cmap.bins) == cmap.samples


# --- yön tespiti: sessiz başarısızlığı görünür kıl ------------------------- #

def test_increasing_relationship_is_reported_as_such() -> None:
    """Kanıt gerçekten öngörüyorsa eşleme bunu söylemeli."""
    cmap = fit_calibration(_samples([(0.2, 2, 12), (0.5, 6, 12), (0.9, 11, 12)]))
    assert cmap.direction == "artan"
    assert cmap.auc > 0.5
    assert cmap.discriminates


def test_inverted_relationship_is_flagged_loudly() -> None:
    """ASIL KUSUR: PAVA artan monotonluğu ZORLUYOR.

    İlişki azalansa tüm binler taban orana çöker ve sonuç "kalibre edildi"
    gibi görünürdü — sessiz başarısızlık. Ölçüldü (n=518, gerçek veri): kanıt
    skoru AUC 0.43, yani sonuçla ters ilişkili; eski kod bunu gizliyordu.

    Beklenen davranış: eşleme yine taban oranı döndürür (dürüst cevap) AMA
    bunu AÇIKÇA söyler ve düzeltilmesi gerekenin kanıt skoru olduğunu belirtir.
    """
    cmap = fit_calibration(_samples([(0.2, 11, 12), (0.5, 6, 12), (0.9, 2, 12)]))
    assert cmap.direction == "azalan"
    assert cmap.auc < 0.5
    assert "TERS" in cmap.note
    assert "düzeltilmesi" in cmap.note
    # Monotonluk zorlandığı için ayrım kalmıyor — bu kabul edilebilir, ama
    # "kalibre edildi" deyip susmak kabul edilemez.
    assert not cmap.discriminates


def test_unrelated_evidence_says_so_instead_of_pretending() -> None:
    """Kanıt sonucu öngörmüyorsa eşleme taban oranı döndürdüğünü söylemeli."""
    cmap = fit_calibration(_samples([(0.2, 6, 12), (0.5, 6, 12), (0.9, 6, 12)]))
    assert cmap.direction == "ilişkisiz"
    assert "öngörmüyor" in cmap.note
    assert not cmap.discriminates
    assert abs(cmap.apply(0.9) - cmap.base_rate) < 0.05


def test_discriminates_is_false_without_a_fit() -> None:
    """Eşleme kurulmadıysa 'ayırt ediyor' iddiası edilemez."""
    cmap = fit_calibration(_samples([(0.9, 3, 5)]))
    assert not cmap.fitted
    assert not cmap.discriminates
