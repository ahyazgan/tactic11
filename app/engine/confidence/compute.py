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

# Yeterli örnek sayılan eşik (bunun üstü sample skoru 1.0)
SAMPLE_FULL = 12
# Ağırlıklar (toplam 1.0)
W_SAMPLE = 0.25
W_MAGNITUDE = 0.25
W_CORROBORATION = 0.20
W_QUALITY = 0.20
W_HISTORY = 0.10

HIGH_THRESHOLD = 0.66
MED_THRESHOLD = 0.40


@dataclass(frozen=True)
class ConfidenceScore:
    score: float             # 0..1
    label: str               # "yüksek" | "orta" | "düşük"
    drivers: tuple[str, ...] = field(default_factory=tuple)


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

    raw = (
        W_SAMPLE * sample_term
        + W_MAGNITUDE * mag_term
        + W_CORROBORATION * corr_term
        + W_QUALITY * qual_term
        + W_HISTORY * hist_term
    )
    score = round(_clamp01(raw), 3)
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

    return ConfidenceScore(score=score, label=label, drivers=tuple(drivers))
