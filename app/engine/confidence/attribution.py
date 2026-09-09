"""Sürücü atıfı — güvenin HANGİ bileşeni sonucu gerçekten ayırıyor?

## Neden

Kalibrasyon (`calibration.py`) "sistem fazla güvenli: %84 diyor, %58 tutuyor"
diyebiliyor ama **neden** diyemiyor. İzotonik regresyon tüm binleri taban orana
çöktürdüğünde öğrendiğimiz tek şey "birleşik skor ayırt etmiyor" oluyor; hangi
sürücünün yanılttığı görünmüyor. Ağırlıkları buna bakmadan değiştirmek tahmindir.

Bu modül her sürücü için tek soruyu sorar: **bu terim yüksekken sonuç daha mı
sık olumlu?** Cevap üç sayıyla verilir:

- `auc` — ayrım gücü (0.5 = hiç ayırmıyor, 1.0 = kusursuz, <0.5 = TERS yönde).
  Mann-Whitney U'nun olasılık yorumu: rastgele bir olumlu ile rastgele bir
  olumsuz seçildiğinde, olumlunun terimi büyük olma olasılığı.
- `lift` — olumlularda ortalama terim eksi olumsuzlarda ortalama terim.
- `n_pos` / `n_neg` — kaç örnekle söylüyoruz.

## Neden AUC (korelasyon değil)

Sonuç ikili (tuttu/tutmadı), terimler kırpılmış ve doygun. Pearson korelasyonu
bu ölçekte yanıltıcı; AUC sıralamaya bakar, ölçek dönüşümlerinden etkilenmez.

## Dürüstlük

Az örnekle güçlü iddia edilmez: `MIN_SAMPLES` altında `verdict` "yetersiz veri"
olur. AUC'nin 0.5'ten farkı örneklem hatasıyla açıklanabiliyorsa "ayırmıyor"
denir — eşik `NOISE_BAND`, kaba bir kural olduğu ve gerçek veriyle
ayarlanacağı için sabit tutulur.

Saf fonksiyon; DB/IO yok.
"""
from __future__ import annotations

from dataclasses import dataclass

ENGINE_NAME = "engine.confidence.attribution"
ENGINE_VERSION = "1"

# Bu sayının altında sürücü hakkında hüküm verilmez
MIN_SAMPLES = 15
# AUC'nin 0.5'ten bu kadar uzaklığı "gürültü" sayılır
NOISE_BAND = 0.06


@dataclass(frozen=True)
class DriverAttribution:
    driver: str
    auc: float               # 0..1; 0.5 = ayırmıyor
    lift: float              # olumlu ort. - olumsuz ort.
    mean_positive: float
    mean_negative: float
    n_pos: int
    n_neg: int
    verdict: str             # "ayırıyor" | "TERS" | "ayırmıyor" | "yetersiz veri"
    note: str = ""


def _auc(pos: list[float], neg: list[float]) -> float:
    """Mann-Whitney U → AUC. Beraberlikler 0.5 sayılır.

    Küçük n için kütüphaneye gerek yok; O(n·m) yeterli ve şeffaf.
    """
    if not pos or not neg:
        return 0.5
    wins = 0.0
    for p in pos:
        for n in neg:
            if p > n:
                wins += 1.0
            elif p == n:
                wins += 0.5
    return wins / (len(pos) * len(neg))


def attribute_driver(
    driver: str, positives: list[float], negatives: list[float],
) -> DriverAttribution:
    """Tek sürücü için ayrım gücü hükmü."""
    n_pos, n_neg = len(positives), len(negatives)
    mp = sum(positives) / n_pos if n_pos else 0.0
    mn = sum(negatives) / n_neg if n_neg else 0.0
    auc = _auc(positives, negatives)

    if n_pos + n_neg < MIN_SAMPLES or n_pos == 0 or n_neg == 0:
        verdict = "yetersiz veri"
        note = (f"n={n_pos + n_neg} (olumlu {n_pos} / olumsuz {n_neg}) — "
                f"hüküm için en az {MIN_SAMPLES} ve her iki sınıftan örnek gerekir")
    elif auc >= 0.5 + NOISE_BAND:
        verdict = "ayırıyor"
        note = (f"terim yüksekken sonuç daha sık olumlu "
                f"(AUC {auc:.2f}, fark {mp - mn:+.3f})")
    elif auc <= 0.5 - NOISE_BAND:
        verdict = "TERS"
        note = (f"terim yüksekken sonuç daha sık OLUMSUZ (AUC {auc:.2f}) — "
                f"bu sürücü güveni YANLIŞ yönde artırıyor")
    else:
        verdict = "ayırmıyor"
        note = (f"AUC {auc:.2f} ≈ 0.5; bu sürücü sonucu öngörmüyor, "
                f"güvene katkısı gürültü")

    return DriverAttribution(
        driver=driver, auc=round(auc, 3), lift=round(mp - mn, 4),
        mean_positive=round(mp, 4), mean_negative=round(mn, 4),
        n_pos=n_pos, n_neg=n_neg, verdict=verdict, note=note,
    )


@dataclass(frozen=True)
class AttributionReport:
    drivers: tuple[DriverAttribution, ...]
    n_decisions: int
    headline: str

    @property
    def useful(self) -> tuple[DriverAttribution, ...]:
        return tuple(d for d in self.drivers if d.verdict == "ayırıyor")

    @property
    def harmful(self) -> tuple[DriverAttribution, ...]:
        return tuple(d for d in self.drivers if d.verdict == "TERS")


def attribute(samples: list[tuple[dict[str, float], bool]]) -> AttributionReport:
    """Ölçülmüş kararlardan sürücü karnesi.

    `samples`: (terimler, olumlu_mu) çiftleri. Terim adları birleştirilir;
    bir örnekte olmayan terim O ÖRNEK İÇİN atlanır (sıfır sayılmaz — eksik
    veriyi sıfır saymak sürücüyü haksız yere aşağı çeker).
    """
    keys: list[str] = []
    for terms, _ in samples:
        for k in terms:
            if k not in keys:
                keys.append(k)

    out: list[DriverAttribution] = []
    for k in keys:
        pos = [t[k] for t, ok in samples if ok and k in t]
        neg = [t[k] for t, ok in samples if not ok and k in t]
        out.append(attribute_driver(k, pos, neg))

    out.sort(key=lambda d: abs(d.auc - 0.5), reverse=True)
    useful = [d for d in out if d.verdict == "ayırıyor"]
    harmful = [d for d in out if d.verdict == "TERS"]

    if not samples:
        headline = "ölçülmüş karar yok"
    elif harmful:
        headline = (f"{len(harmful)} sürücü TERS yönde çalışıyor: "
                    f"{', '.join(d.driver for d in harmful)}")
    elif useful:
        headline = (f"sonucu ayıran sürücü(ler): "
                    f"{', '.join(d.driver for d in useful)}")
    else:
        headline = ("hiçbir sürücü sonucu ayırmıyor — güven skoru şu an "
                    "gürültüden ibaret")

    return AttributionReport(
        drivers=tuple(out), n_decisions=len(samples), headline=headline,
    )
