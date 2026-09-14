"""Elit değişiklik ZAMANLAMA önseli — "bu durumda antrenör 12 dk içinde değiştirir mi?"

## Kaynak ve ölçüm (2026-09-12)

StatsBomb açık verisi, La Liga 2018-21, Barcelona'nın 100 maçı, İKİ takımın
antrenörleri (elit lig; n=3200 tik). Tik ızgarası her 5 dk (10..85);
hedef: takım sonraki 12 dk içinde TAKTİK değişiklik yaptı mı. Hücre =
(dakika bandı, o anki skor durumu, o ana kadar yapılan değişiklik ≤ 3);
Laplace düzeltmeli oran (`engine.coach_benchmark.fit_timing_prior`).

Ayrık yarı testi: önsel F1 0.711 vs saat-kuralı (dk ≥ 55) F1 0.682 — saatle
aynı bantta. Yani ZAMANLAMA büyük ölçüde saatin ve kalan hakkın işidir; önsel
motoru saatle eşitler, saati geçmez. Motorun yorgunluk projeksiyonu tek başına
F1 0.49 idi (elit antrenörle uyum boyutu, `scripts/coach_iq.py`).

Bantlar: [0,45) [45,60) [60,70) [70,80) [80,∞) → 0..4. Değişiklik sayısı 3+
tek hücrede (2018-21'de hak 3'tü; 5-hak kuralıyla yeniden fit gerekir).
Görülmemiş hücre → 0.5 (bilinmiyor). Yeniden fit edilirse tablo VE bu not güncellenir.

## Bağımsız doğrulama (2026-09-14)

Tablo ve eşik DONDURULMUŞ hâliyle, külliyatla kesişmeyen 100'er maça uygulandı
(`scripts/validate_timing_prior.py`). Saat kuralına kasten avantaj verildi:
eşiği ölçülen kümede en iyi olacak şekilde seçildi.

  küme                    önsel F1   saat F1   fark     hüküm
  La Liga 2015/16            0.741     0.686  +0.055   saati geçiyor
  Premier League 2015/16     0.693     0.681  +0.012   saatle aynı

İkisinde de küme içi tavana oturuyor (0.744/0.740 ve 0.699/0.747). Karnedeki
"saatle aynı" hükmü MOTOR TİKLERİNDE (28/40/55/66/78) ölçülür; o dağılım saati
kayırıyor. Bu ölçüm önselin fit edildiği 5 dk ızgarada. İkisi farklı soruları
ölçüyor, ikisi de raporlanır. docs/KARNE-ZAMANLAMA-BAGIMSIZ.md.

Görülmemiş hücre payı bağımsız kümelerde %0.1-0.3 — tablo durum uzayını
neredeyse tamamen kaplıyor. "Görülmemişte sus" varyantı ölçüldü, sonuç
değişmedi; bu yüzden `UNKNOWN_CELL` 0.5 bırakıldı (şekil kapısında oran
%10-12 olduğu için orada 0.0'a çekilmişti).
"""
from __future__ import annotations

MINUTE_BANDS: tuple[float, ...] = (45.0, 60.0, 70.0, 80.0)
MAX_SUBS_CELL = 3
# Karar eşiği. 5 dk ızgarada eğitim-optimal 0.4 idi; panelin konuştuğu külliyat
# tiklerinde (28/40/55/66/78) ayrık yarı seçimi 0.25-0.35 platosunu verdi
# (F1 0.75, 0.4'te 0.71; saat-kuralı 0.74). Yeniden fit edilirse yeniden ölçülür.
SUB_WINDOW_THRESHOLD = 0.35
UNKNOWN_CELL = 0.5

ELITE_SUB_WINDOW_PRIOR: dict[tuple[int, str, int], float] = {
    (0, "drawing", 0): 0.046,
    (0, "drawing", 1): 0.129,
    (0, "leading", 0): 0.093,
    (0, "leading", 1): 0.150,
    (0, "trailing", 0): 0.163,
    (0, "trailing", 1): 0.529,
    (1, "drawing", 0): 0.450,
    (1, "drawing", 1): 0.278,
    (1, "drawing", 2): 0.167,
    (1, "leading", 0): 0.359,
    (1, "leading", 1): 0.411,
    (1, "leading", 2): 0.375,
    (1, "trailing", 0): 0.609,
    (1, "trailing", 1): 0.477,
    (1, "trailing", 2): 0.441,
    (1, "trailing", 3): 0.522,
    (2, "drawing", 0): 0.735,
    (2, "drawing", 1): 0.667,
    (2, "drawing", 2): 0.531,
    (2, "drawing", 3): 0.636,
    (2, "leading", 0): 0.857,
    (2, "leading", 1): 0.800,
    (2, "leading", 2): 0.769,
    (2, "leading", 3): 0.700,
    (2, "trailing", 0): 0.923,
    (2, "trailing", 1): 0.721,
    (2, "trailing", 2): 0.609,
    (2, "trailing", 3): 0.433,
    (3, "drawing", 0): 0.833,
    (3, "drawing", 1): 0.811,
    (3, "drawing", 2): 0.684,
    (3, "drawing", 3): 0.486,
    (3, "leading", 0): 0.909,
    (3, "leading", 1): 0.850,
    (3, "leading", 2): 0.894,
    (3, "leading", 3): 0.500,
    (3, "trailing", 0): 0.833,
    (3, "trailing", 1): 0.885,
    (3, "trailing", 2): 0.865,
    (3, "trailing", 3): 0.343,
    (4, "drawing", 0): 0.667,
    (4, "drawing", 1): 0.778,
    (4, "drawing", 2): 0.808,
    (4, "drawing", 3): 0.212,
    (4, "leading", 1): 0.929,
    (4, "leading", 2): 0.776,
    (4, "leading", 3): 0.167,
    (4, "trailing", 1): 0.857,
    (4, "trailing", 2): 0.875,
    (4, "trailing", 3): 0.112,
}


def elite_sub_window_probability(minute: float, score_state: str, subs_used: int) -> float:
    """P(elit antrenör bu durumda 12 dk içinde değiştirir). score_state: leading/drawing/trailing."""
    band = sum(1 for edge in MINUTE_BANDS if minute >= edge)
    return ELITE_SUB_WINDOW_PRIOR.get((band, score_state, min(max(0, subs_used), MAX_SUBS_CELL)),
                                      UNKNOWN_CELL)
