"""Confidence — güven skoru sistemi (Faz 8 #2).

Her öneri "ne kadar güvenilir?" sorusuna sayısal + açıklanabilir cevap verir.
TD/analist "neden?" diye sorar; bu modül cevabı 4 sürücüye dayandırır:

1. sample_size — kaç event/şut/düello destekliyor (az örnek = düşük güven)
2. magnitude — altta yatan metriğin gücü (eşiğe ne kadar net geçmiş)
3. corroboration — kaç bağımsız sinyal aynı yöne işaret ediyor
4. data_quality — sinyal kalite filtresinin (#5) verdiği skor
5. historical_hit_rate — bu tip öneri geçmişte kaç kez doğru çıktı (#4 feedback;
   yoksa nötr 0.5 alınır, güveni ne artırır ne azaltır)

Saf fonksiyon. Ağırlıklı birleşim → 0..1 skor + etiket + sürücü açıklamaları.
"""
from __future__ import annotations

from dataclasses import dataclass, field

ENGINE_NAME = "engine.confidence"
ENGINE_VERSION = "1"

# Yeterli örnek sayılan eşik (bunun üstü sample kapısı tam açık)
SAMPLE_FULL = 12
# Kapı tabanı: veri tamamen yetersizken bile kanıt SIFIRLANMAZ, yarıya iner.
# Sıfırlamak "sinyal yok" demek olurdu; oysa sinyal var, desteği zayıf.
MIN_GATE = 0.5
# Teyit en fazla bu kadar ekler (doygunlukla)
CORROBORATION_BONUS = 0.10
# Geçmiş isabet nötrden (0.5) sapmasıyla en fazla bu kadar oynatır
HISTORY_PULL = 0.10

HIGH_THRESHOLD = 0.66
MED_THRESHOLD = 0.40


@dataclass(frozen=True)
class ConfidenceScore:
    score: float             # 0..1
    label: str               # "yüksek" | "orta" | "düşük"
    drivers: tuple[str, ...] = field(default_factory=tuple)
    # SAYISAL sürücü kırılımı (0..1, ağırlık uygulanmadan önceki terimler).
    #
    # Neden gerekli: kalibrasyon "sistem fazla güvenli" diyebiliyordu ama HANGİ
    # sürücünün yanılttığını söyleyemiyordu — çünkü kararla birlikte yalnız
    # birleşik skor saklanıyordu (ölçüldü: 74 kararın hepsinde `context_json`
    # boş). Atıf olmadan sinyal kalitesi iyileştirilemez: neyin işe yaradığını
    # bilmeden ağırlık değiştirmek tahmindir.
    #
    # `drivers` insan içindir (metin); bu alan ÖLÇÜM içindir.
    terms: dict[str, float] = field(default_factory=dict)


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def score_confidence(
    *,
    sample_size: int,
    magnitude: float,
    corroboration: int = 0,
    data_quality: float = 1.0,
    historical_hit_rate: float | None = None,
) -> ConfidenceScore:
    """Bir önerinin güven skorunu üret.

    corroboration: bu sinyalle aynı yöne işaret eden DİĞER sinyal sayısı.
    historical_hit_rate: 0..1; None ise nötr (0.5).
    """
    sample_term = _clamp01(sample_size / SAMPLE_FULL)
    mag_term = _clamp01(magnitude)
    # 0 destek → 0, 1 destek → 0.5, 2 → 0.75, 3+ → ~1 (doygunluk)
    corr_term = _clamp01(1.0 - 0.5 ** max(0, corroboration))
    qual_term = _clamp01(data_quality)
    hist_term = 0.5 if historical_hit_rate is None else _clamp01(historical_hit_rate)

    # KANIT = metriğin eşiği ne kadar aştığı. Asıl bilgi budur.
    #
    # KAPILAR: yetersiz veri kanıtı ZAYIFLATIR, yeterli veri BONUS VERMEZ.
    # Eskiden sample ve quality ağırlıklı toplamaya giriyordu ve ikisi de
    # neredeyse hep 1.0 geldiği için skorun %45'i sabit dolguydu; history de
    # hiç dolmadığından 0.5'e sabitti (+%5 daha). Ölçüldü (n=513 gerçek karar):
    # skorun ayrım gücü yoktu ve kararların %87'si TEK bir çeyrek bine
    # düşüyordu — "sistem hep %90 diyor"un kaynağı buydu. Sabit bir terimi
    # toplamaya eklemek bilgi katmaz, yalnız tabanı yükseltir.
    #
    # En zayıf halka belirler: az örnek VE düşük kalite ayrı ayrı cezalandırılıp
    # üst üste binmemeli.
    sample_gate = MIN_GATE + (1.0 - MIN_GATE) * sample_term
    quality_gate = MIN_GATE + (1.0 - MIN_GATE) * qual_term
    gate = min(sample_gate, quality_gate)

    corr_bonus = CORROBORATION_BONUS * corr_term
    # Geçmiş YOKSA hiç oynatma. Eskiden yokluk 0.5 nötr sayılıp yine de
    # ağırlıkla toplanıyordu; "bilmiyorum" ile "tam ortada" aynı şey değil.
    hist_adj = 0.0 if historical_hit_rate is None else HISTORY_PULL * (hist_term - 0.5) * 2.0

    score = round(_clamp01(mag_term * gate + corr_bonus + hist_adj), 3)
    label = ("yüksek" if score >= HIGH_THRESHOLD
             else "orta" if score >= MED_THRESHOLD else "düşük")

    drivers: list[str] = []
    drivers.append(f"{sample_size} örnek destekliyor")
    if mag_term >= 0.66:
        drivers.append("metrik eşiği net geçti")
    elif mag_term <= 0.33:
        drivers.append("metrik eşiğe yakın (zayıf)")
    if corroboration >= 1:
        drivers.append(f"{corroboration} bağımsız sinyal aynı yönde")
    else:
        drivers.append("tek başına sinyal (teyit yok)")
    if qual_term < 0.66:
        drivers.append(f"veri kalitesi düşük ({qual_term:.2f})")
    if historical_hit_rate is not None:
        drivers.append(
            f"bu tip öneri geçmişte %{int(historical_hit_rate*100)} doğru çıktı"
        )

    return ConfidenceScore(
        score=score, label=label, drivers=tuple(drivers),
        terms={
            # Birleşik HAM skor. Kalibrasyon `confidence` alanını olasılıkla
            # değiştirdiği için ham değer başka yerde kalmıyor; atıf analizi
            # "bütün, parçalarından iyi mi?" sorusunu ancak buna bakarak sorar.
            "score": score,
            "sample": round(sample_term, 3),
            "magnitude": round(mag_term, 3),
            "corroboration": round(corr_term, 3),
            "quality": round(qual_term, 3),
            "history": round(hist_term, 3),
            # Kompozisyonun kendi parçaları — skoru yeniden üretebilmek için
            "gate": round(gate, 3),
            "corr_bonus": round(corr_bonus, 4),
            "hist_adj": round(hist_adj, 4),
            # Ham girdiler de saklanır: terimler kırpılmış/dönüştürülmüş
            # olduğu için geriye dönük analizde asıl değer gerekebilir
            # (örn. corroboration 3 ile 9 aynı terime doyuyor).
            "raw_sample_size": float(sample_size),
            "raw_corroboration": float(corroboration),
            # Ölçüldü (n=437): kararların YARISI magnitude 1.0'a kırpılmış
            # geliyor — kırpma ayrım gücünü yok ediyor. Ham değer olmadan
            # "eşiği 2 kat aşan ile 10 kat aşan" ayırt edilemez.
            "raw_magnitude": float(magnitude),
            "has_history": 0.0 if historical_hit_rate is None else 1.0,
        },
    )
