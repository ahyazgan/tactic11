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


def auc_score(pos: list[float], neg: list[float]) -> float:
    """Mann-Whitney U → AUC. Beraberlikler 0.5 sayılır.

    Küçük n için kütüphaneye gerek yok; O(n·m) yeterli ve şeffaf.

    Kalibrasyon da bunu kullanır (`calibration.fit_calibration`): eşleme
    kurmadan ÖNCE ilişkinin yönünü bilmek gerekiyor, yoksa izotonik regresyon
    azalan ilişkiyi sessizce taban orana çökertiyor.
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
    auc = auc_score(positives, negatives)

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


def attribute_stratified(
    samples: list[tuple[float, bool, float]], driver: str = "sürücü", *,
    strata: int = 4,
) -> DriverAttribution:
    """KARIŞTIRICIYI kontrol ederek ayrım gücü — katmanlı AUC.

    ## Neden gerekli

    Karar etkisi cetveli `sonraki pencere - önceki pencere` farkıdır. Bu ölçü
    **ortalamaya dönüş** taşır: iyi giderken verilen kararlar sistematik olarak
    cezalandırılır, kötü giderken verilenler ödüllendirilir. Ölçüldü (n=502,
    gerçek maçlar) — eğimler ZIT işaretli:

        momentum_us  (biz baskın)  : -0.126
        momentum_opp (rakip baskın): +0.030

    Aynı sürücü, duruma göre zıt yönde "çalışıyor" görünüyor. Bu sürücünün
    kalitesi değil, cetvelin yanlılığı. Ham AUC bu ikisini ayıramaz.

    ## Yöntem

    Örnekler karıştırıcıya (`confound`, örn. karar öncesi xG farkı) göre eşit
    büyüklükte katmanlara bölünür; AUC her katman İÇİNDE hesaplanır ve katman
    büyüklüğüne göre ağırlıklı ortalanır. Katman içinde karıştırıcı hemen hemen
    sabit olduğu için geriye sürücünün kendi katkısı kalır.

    `samples`: (sürücü değeri, olumlu mu, karıştırıcı değeri) üçlüleri.
    """
    kullanilir = [s for s in samples if s[1] is not None]
    if len(kullanilir) < MIN_SAMPLES:
        return attribute_driver(driver, [v for v, ok, _ in kullanilir if ok],
                                [v for v, ok, _ in kullanilir if not ok])

    sirali = sorted(kullanilir, key=lambda s: s[2])
    boyut = max(1, len(sirali) // max(1, strata))
    toplam_agirlik = 0.0
    toplam_auc = 0.0
    n_pos = n_neg = 0
    poslar: list[float] = []
    neglar: list[float] = []
    for i in range(0, len(sirali), boyut):
        katman = sirali[i:i + boyut]
        p = [v for v, ok, _ in katman if ok]
        n = [v for v, ok, _ in katman if not ok]
        n_pos += len(p)
        n_neg += len(n)
        poslar += p
        neglar += n
        if not p or not n:
            continue                       # tek sınıflı katman AUC vermez
        agirlik = float(len(p) * len(n))   # kıyaslanabilir çift sayısı
        toplam_auc += auc_score(p, n) * agirlik
        toplam_agirlik += agirlik

    if toplam_agirlik == 0.0:
        # Her katman tek sınıflı: karıştırıcı sonucu neredeyse TAMAMEN
        # belirliyor, geriye sürücüye ait ayrılabilir bilgi kalmıyor. Ham
        # hükme sessizce düşmek yanıltıcı olurdu — ham ölçüm sürücüyü suçlu
        # gösterir, oysa söylenebilecek tek dürüst şey "ayıramıyorum".
        ham = attribute_driver(driver, poslar, neglar)
        return DriverAttribution(
            driver=driver, auc=0.5, lift=ham.lift,
            mean_positive=ham.mean_positive, mean_negative=ham.mean_negative,
            n_pos=n_pos, n_neg=n_neg, verdict="ayrıştırılamıyor",
            note=(f"karıştırıcı sonucu tek başına belirliyor; her katman tek "
                  f"sınıflı kaldı — sürücünün kendi katkısı ÖLÇÜLEMEZ "
                  f"(kontrolsüz ölçüm {ham.auc:.2f} diyordu)"),
        )

    auc = toplam_auc / toplam_agirlik
    ham = attribute_driver(driver, poslar, neglar)
    if auc >= 0.5 + NOISE_BAND:
        verdict, ek = "ayırıyor", "terim yüksekken sonuç daha sık olumlu"
    elif auc <= 0.5 - NOISE_BAND:
        verdict, ek = "TERS", "terim yüksekken sonuç daha sık OLUMSUZ"
    else:
        verdict, ek = "ayırmıyor", "sürücü sonucu öngörmüyor"
    return DriverAttribution(
        driver=driver, auc=round(auc, 3), lift=ham.lift,
        mean_positive=ham.mean_positive, mean_negative=ham.mean_negative,
        n_pos=n_pos, n_neg=n_neg, verdict=verdict,
        note=(f"{ek} (katmanlı AUC {auc:.2f}; karıştırıcı kontrol edilmeden "
              f"{ham.auc:.2f} görünüyordu)"),
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
