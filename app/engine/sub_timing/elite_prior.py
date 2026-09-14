"""Elit değişiklik ZAMANLAMA önseli — "bu durumda antrenör 12 dk içinde değiştirir mi?"

## Kaynak ve ölçüm (2026-09-14 yeniden fit)

StatsBomb açık verisi, YEDİ küme / 16559 tik (`scripts/fit_timing_prior.py`):
Barcelona 3-hak (54 maç) ve 5-hak (46), La Liga 2015/16 (100), Premier League
2015/16 (100), Indian Super League 2021/22 (100), FA WSL 2023/24 (100),
Euro 2024 (51). Erkek/kadın, kulüp/milli, 3-hak/5-hak karışık — kasten.
Tik ızgarası her 5 dk (10..85); hedef: takım sonraki 12 dk içinde TAKTİK
değişiklik yaptı mı. Hücre = (dakika bandı, skor durumu, yapılan değişiklik ≤ 3);
Laplace düzeltmeli oran.

**HAK-BİTMİŞ TİKLER FİT'E GİRMEZ** (1073 tik elendi). Hak bittiğinde değişiklik
imkânsızdır ve bu bilgi tabloda değil KAPIDA durur (`subs_allowed`). Elenince
"3 kullanılmış" hücresi her rejimde aynı şeyi anlatır — *3 yaptı ve hakkı var* —
ve ancak bu sayede 3-hak ile 5-hak verisi aynı havuza konabilir.

Önceki tablo tek kulübün 100 maçındandı (3200 tik) ve rejim karışımını hücreye
gömüyordu. Leave-one-out F1 (her küme KENDİSİ hariç ötekilerden fit edilen
tabloyla ölçüldü):

  küme                          eski    yeni
  Barcelona 3-hak              0.761   0.758
  Barcelona 5-hak              0.701   0.718
  La Liga 2015/16              0.751   0.759
  Premier League 2015/16       0.698   0.699
  Indian Super League 21/22    0.653   0.703
  FA WSL 2023/24               0.656   0.696
  Euro 2024                    0.659   0.735
  ORTALAMA                     0.697   0.724
  EN KÖTÜ                      0.653   0.696

Yedi küme de 5-hak dünyasında ya da dışında; yeni tablo hiçbirinde belirgin
kötüleşmiyor, üç yeni kümede 0.04-0.08 kazanıyor.

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

## Değişiklik hakkı: doğal deney ve HAK-BİTTİ KAPISI (2026-09-14)

Külliyat kural değişimini içeriyor: La Liga 2020-06-11'de 5 hakla yeniden
başladı. Tarihe göre ayrılınca (54 maç 3-hak, 46 maç 5-hak; 3-hak döneminde
takımların %0'ı 4+ değişiklik yaptı, 5-hak döneminde %80'i) "3 kullanılmış"
hücresinin İKİ ZIT gerçeği harmanladığı görülüyor:

  kullanılmış 3 → P(12 dk içinde değişiklik):  3-hak dönemi 0.000 (n=169)
                                               5-hak dönemi 0.672 (n=125)

Tablo bu karışımdan fit edildiği için ikisine de yanlış cevap veriyor ve 5-hak
döneminde yakalama 0.898'den 0.753'e düşüyor.

Çözüm ÖĞRENİLEN değil MANTIKSAL: hak bittiyse olasılık 0'dır. Kapı yalnız
yanlış pozitif siler, yakalamaya dokunamaz (hak bitmişken değişiklik imkânsız
olduğundan oradaki her bayrak zaten yanlıştı). Ölçüldü — dört kümede de F1
artıyor, hiçbirinde düşmüyor, yakalama sabit:

  küme              kapısız → kapılı F1   yakalama
  3-hak Barça          0.749 → 0.761      0.898 (sabit)
  5-hak Barça          0.697 → 0.701      0.753 (sabit)
  La Liga 2015/16      0.741 → 0.751      0.900 (sabit)
  Premier League 15/16 0.693 → 0.698      0.884 (sabit)

Tablonun KENDİSİ hâlâ karışımdan geliyor. Kapı+yeniden fit ölçüldü ve 5-hak
döneminde 0.746'ya çıkıyor (kapısız fit 0.719); yeniden fit EDİLMEDİ çünkü
5-hak örneği yalnız 46 maç. Hangi veriyle fit edileceği ayrı bir karardır.
docs/KARNE-DEGISIKLIK-HAKKI.md.
"""
from __future__ import annotations

MINUTE_BANDS: tuple[float, ...] = (45.0, 60.0, 70.0, 80.0)
MAX_SUBS_CELL = 3
# Karar eşiği. 2026-09-14 taraması (7 küme, leave-one-out ortalama F1):
# 0.25→0.725  0.30→0.725  0.35→0.724  0.40→0.727  0.45→0.721  0.50→0.712.
# 0.25-0.40 arası DÜZ PLATO (fark 0.003 = gürültü). Argmax (0.40) SEÇİLMEDİ:
# düz bölgede en yüksek ortalamayı seçmek gürültüye uymaktır ve 0.40'ın en kötü
# kümesi daha kötü (0.689 vs 0.696). 0.35 korundu; böylece önce/sonra farkı
# yalnız TABLOYA atfedilebiliyor.
SUB_WINDOW_THRESHOLD = 0.35
UNKNOWN_CELL = 0.5
# Maç başına değişiklik hakkı. 2022'den beri IFAB kuralı 5; tablo 3-hak ve 5-hak
# maçlarının karışımından geldiği için hak sayısı DIŞARIDAN verilmelidir.
DEFAULT_SUBS_ALLOWED = 5

ELITE_SUB_WINDOW_PRIOR: dict[tuple[int, str, int], float] = {
    (0, "drawing", 0): 0.047,   # 200/4317
    (0, "drawing", 1): 0.128,   # 23/186
    (0, "drawing", 2): 0.333,   # 0/1
    (0, "leading", 0): 0.071,   # 109/1542
    (0, "leading", 1): 0.094,   # 5/62
    (0, "leading", 2): 0.333,   # 0/1
    (0, "trailing", 0): 0.164,   # 251/1539
    (0, "trailing", 1): 0.311,   # 18/59
    (0, "trailing", 2): 0.111,   # 0/7
    (1, "drawing", 0): 0.369,   # 340/921
    (1, "drawing", 1): 0.325,   # 85/263
    (1, "drawing", 2): 0.300,   # 20/68
    (1, "drawing", 3): 0.333,   # 1/4
    (1, "leading", 0): 0.336,   # 245/730
    (1, "leading", 1): 0.364,   # 95/262
    (1, "leading", 2): 0.267,   # 7/28
    (1, "leading", 3): 0.143,   # 0/5
    (1, "trailing", 0): 0.543,   # 272/501
    (1, "trailing", 1): 0.457,   # 146/320
    (1, "trailing", 2): 0.291,   # 43/149
    (1, "trailing", 3): 0.386,   # 21/55
    (2, "drawing", 0): 0.755,   # 196/259
    (2, "drawing", 1): 0.693,   # 166/239
    (2, "drawing", 2): 0.512,   # 62/121
    (2, "drawing", 3): 0.487,   # 18/37
    (2, "leading", 0): 0.808,   # 285/352
    (2, "leading", 1): 0.743,   # 184/247
    (2, "leading", 2): 0.570,   # 76/133
    (2, "leading", 3): 0.400,   # 15/38
    (2, "trailing", 0): 0.881,   # 155/175
    (2, "trailing", 1): 0.803,   # 186/231
    (2, "trailing", 2): 0.612,   # 136/222
    (2, "trailing", 3): 0.500,   # 61/122
    (3, "drawing", 0): 0.908,   # 58/63
    (3, "drawing", 1): 0.811,   # 141/173
    (3, "drawing", 2): 0.701,   # 149/212
    (3, "drawing", 3): 0.642,   # 78/121
    (3, "leading", 0): 0.941,   # 94/99
    (3, "leading", 1): 0.855,   # 206/240
    (3, "leading", 2): 0.768,   # 228/296
    (3, "leading", 3): 0.652,   # 87/133
    (3, "trailing", 0): 0.921,   # 34/36
    (3, "trailing", 1): 0.891,   # 113/126
    (3, "trailing", 2): 0.814,   # 227/278
    (3, "trailing", 3): 0.692,   # 145/209
    (4, "drawing", 0): 0.875,   # 6/6
    (4, "drawing", 1): 0.851,   # 56/65
    (4, "drawing", 2): 0.736,   # 144/195
    (4, "drawing", 3): 0.525,   # 83/158
    (4, "leading", 0): 0.833,   # 9/10
    (4, "leading", 1): 0.906,   # 76/83
    (4, "leading", 2): 0.824,   # 196/237
    (4, "leading", 3): 0.568,   # 132/232
    (4, "trailing", 0): 0.750,   # 2/2
    (4, "trailing", 1): 0.700,   # 20/28
    (4, "trailing", 2): 0.732,   # 103/140
    (4, "trailing", 3): 0.547,   # 121/221
}


def elite_sub_window_probability(
    minute: float, score_state: str, subs_used: int, *, subs_allowed: int = DEFAULT_SUBS_ALLOWED,
) -> float:
    """P(elit antrenör bu durumda 12 dk içinde değiştirir). score_state: leading/drawing/trailing.

    Hak bittiyse olasılık ÖĞRENİLMEZ, 0'dır: değişiklik kural gereği imkânsız.
    Tablo 3-hak ve 5-hak maçlarının KARIŞIMINDAN fit edildiği için "3 kullanılmış"
    hücresi iki zıt durumu harmanlar (bkz. yukarıdaki ölçüm günlüğü); bu kapı o
    harmanın yarısını mantıkla keser.
    """
    if subs_used >= subs_allowed:
        return 0.0
    band = sum(1 for edge in MINUTE_BANDS if minute >= edge)
    return ELITE_SUB_WINDOW_PRIOR.get((band, score_state, min(max(0, subs_used), MAX_SUBS_CELL)),
                                      UNKNOWN_CELL)
