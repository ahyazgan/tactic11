"""Güven kalibrasyonu — kanıt skorunu GERÇEK olasılığa eşle.

## Sorun

`score_confidence` bir olasılık değil, **kanıt gücü** üretir: örneklem + metrik
büyüklüğü + teyit + veri kalitesi + geçmişin ağırlıklı toplamı. "Elimde ne kadar
bilgi var" sorusunun cevabı. Ama arayüzde ve karar kalitesi ölçümünde bu sayı
"bu karar tutar" olasılığı gibi okunuyor. İkisi aynı şey değil.

Ölçüldü (12 gerçek maç, 41 karar): sistem ortalama **%84** diyor, gerçekleşme
**%58**. Yani sistematik olarak fazla güvenli.

Geri besleme zaten vardı ama işe yaramıyordu: `historical_hit_rate` beş terimden
biri ve ağırlığı **0.10**; üstelik nötr 0.5'e göre tartılıyor. Geçmiş "%58"
dese bile skoru en fazla ±0.05 oynatabiliyor. Döngü kuruluydu ama **etkisizdi**.

## Çözüm

Kanıt skorunu bırak, üstüne bir **eşleme** koy: takımın kendi geçmişinde "şu
kanıt seviyesinde verilen kararların yüzde kaçı tuttu" diye bak ve skoru o
orana çevir. Klasik olasılık kalibrasyonu.

- **Binleme + küçültme (shrinkage):** her bin için `(isabet + k·taban) / (n + k)`.
  Küçük örneklemde bin oranı gürültülüdür; taban orana doğru çekilir (k=5).
- **Monotonluk (PAVA):** daha çok kanıt, daha düşük olasılığa eşlenmemeli.
  Gerçek veride bu ihlal görüldü (%60-80 bininde n=2 ile %0). İhlal eden komşu
  binler havuzlanır — izotonik regresyonun standart çözümü.
- **Yetersiz veriyle çalışmaz:** `MIN_SAMPLES` altında eşleme kurulmaz ve ham
  skor olduğu gibi döner. Az veriden kalibrasyon uydurmak, kalibrasyonsuzluktan
  kötüdür.

Saf hesap: DB/HTTP bilmez, `Sequence[(skor, sonuç)]` alır.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

# Bu sayının altında eşleme kurulmaz — ham skor korunur
MIN_SAMPLES = 20
# Bin oranı taban orana bu ağırlıkla çekilir (Laplace benzeri küçültme)
SHRINK = 5.0
DEFAULT_BINS = 4


@dataclass(frozen=True)
class CalibrationBin:
    lower: float
    upper: float
    n: int
    raw_rate: float        # binin ham gerçekleşme oranı
    probability: float     # küçültme + monotonluk sonrası


@dataclass(frozen=True)
class CalibrationMap:
    """Kanıt skoru → olasılık eşlemesi (takıma özgü, geçmişten öğrenilmiş)."""

    bins: tuple[CalibrationBin, ...]
    base_rate: float
    samples: int
    fitted: bool           # False → eşleme yok, ham skor kullanılmalı
    note: str = ""

    def apply(self, raw_score: float) -> float:
        """Ham kanıt skorunu kalibre olasılığa çevir (eşleme yoksa aynen döner)."""
        if not self.fitted:
            return raw_score
        for b in self.bins:
            if b.lower <= raw_score < b.upper:
                return b.probability
        return self.bins[-1].probability if self.bins else raw_score


def _pava(values: list[float], weights: list[int]) -> list[float]:
    """İzotonik regresyon (Pool Adjacent Violators) — azalan komşuları havuzla.

    Küçük örneklemde bin oranları gürültüden dolayı azalabilir; monotonluk
    fiziksel beklentidir (daha çok kanıt → daha düşük olasılık olmamalı).
    """
    out = list(values)
    wts = [float(w) for w in weights]
    i = 0
    while i < len(out) - 1:
        if out[i] <= out[i + 1] + 1e-12:
            i += 1
            continue
        # İhlal: iki bini ağırlıklı ortalamada birleştir, geriye doğru kontrol et
        total_w = wts[i] + wts[i + 1]
        merged = (out[i] * wts[i] + out[i + 1] * wts[i + 1]) / max(total_w, 1e-9)
        out[i] = out[i + 1] = merged
        wts[i] = wts[i + 1] = total_w / 2.0
        i = max(i - 1, 0)
    return out


def fit_calibration(
    samples: Sequence[tuple[float, bool]],
    *,
    bin_count: int = DEFAULT_BINS,
    min_samples: int = MIN_SAMPLES,
    shrink: float = SHRINK,
) -> CalibrationMap:
    """Geçmiş (kanıt skoru, sonuç) çiftlerinden eşleme kur.

    `samples`: (0..1 skor, karar olumlu çıktı mı) çiftleri.
    """
    usable = [(float(s), bool(ok)) for s, ok in samples if 0.0 <= s <= 1.0]
    n = len(usable)
    if n < min_samples:
        return CalibrationMap(
            bins=(), base_rate=0.0, samples=n, fitted=False,
            note=(f"kalibrasyon için yetersiz geçmiş ({n} < {min_samples}) — "
                  f"ham kanıt skoru kullanılıyor"),
        )
    base = sum(1 for _s, ok in usable if ok) / n

    edges = [i / bin_count for i in range(bin_count + 1)]
    edges[-1] = 1.0 + 1e-9        # üst sınır dahil
    raw_rates: list[float] = []
    counts: list[int] = []
    for lo, hi in zip(edges[:-1], edges[1:], strict=True):
        inside = [ok for s, ok in usable if lo <= s < hi]
        counts.append(len(inside))
        raw_rates.append(sum(1 for ok in inside if ok) / len(inside) if inside else base)

    # Küçültme: az örnekli bin taban orana yaklaşır
    shrunk = [
        (rate * cnt + shrink * base) / (cnt + shrink)
        for rate, cnt in zip(raw_rates, counts, strict=True)
    ]
    monotone = _pava(shrunk, [max(c, 1) for c in counts])

    bins = tuple(
        CalibrationBin(
            lower=round(lo, 4), upper=round(min(hi, 1.0), 4), n=cnt,
            raw_rate=round(rate, 4), probability=round(min(max(p, 0.0), 1.0), 4),
        )
        for lo, hi, cnt, rate, p in zip(
            edges[:-1], edges[1:], counts, raw_rates, monotone, strict=True,
        )
    )
    return CalibrationMap(
        bins=bins, base_rate=round(base, 4), samples=n, fitted=True,
        note=(f"{n} geçmiş karardan kalibre edildi (taban oran "
              f"%{base * 100:.0f})"),
    )
