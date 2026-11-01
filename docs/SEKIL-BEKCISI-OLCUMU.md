# Şekil bekçisi ölçümleri: gürültü tabanı ve eşikler (2026-11-02)

`engine.shape_watch` (PR #326/#330) savunan takımın blok derinliği, genişliği, hat
aralığı ve boyunu dakikalık medyanla izler ve 6/6/4/6 m eşiklerle uyarı üretir.
Eşikler sezgiseldi; bu belge ölçüm gürültüsünü referansa karşı verir. Yöntem:
aynı `sample_frame` hesabı takip karelerine ve GSR'den kurulan karelere (kaleci
GSR'den, yön GSR kalecilerinden, her iki takım her karede) uygulanır; hata =
|takip − referans|, bekçinin birimi olan **1 dakikalık medyan** üzerinden
(`scripts/soccertrack_v2/eval_shape_watch.py`, `docs/measurements/shape-watch-noise.json`).
Gündüz ve üçüncü saha referansı saha işaretlerine göre düzeltilmiş GSR; gece ham GSR
(düzeltilemedi, `gsr-corrected-telestration.json`).

Hücre: dakikalık medyan hatasının **medyanı / p90'ı** (m). Karar en kötü 10 dakikalık
pencereye göre (4 segmentlik ayrık pencere yalnız gösterge; p90 için çok az dakika):
p90 ≤ eşik → güvenilir; medyan ≤ eşik/2 → sınırda; değilse güvenilmez.

| Ölçüm | Gündüz 132877 (düzeltilmiş GSR) | Başka stadyum 132831 (düzeltilmiş GSR) | Gece 117092 (ham GSR) | 132831 ayrık 4 segment | Karar |
|---|---|---|---|---|---|
| Blok derinliği (eşik 6 m) | 0.8 / 2.5 | 0.9 / 5.6 | 2.1 / 6.5 | 4.6 / 12.5 | sınırda |
| Genişlik, en–en (eşik 6 m) | 5.8 / 10.9 | 2.4 / 9.7 | 5.2 / 12.9 | 3.6 / 8.7 | güvenilmez |
| Hat aralığı (eşik 4 m) | 0.6 / 1.4 | 1.6 / 3.4 | 2.0 / 4.7 | 1.8 / 3.2 | güvenilmez |
| Boy, en ileri oyuncu (eşik 6 m) | 1.3 / 3.8 | 10.6 / 21.4 | 2.6 / 6.2 | 10.8 / 18.9 | güvenilmez |
| Genişlik, uçtan 1 kırpılmış | 3.2 / 10.2 | 4.6 / 8.6 | 5.5 / 8.1 | 4.5 / 7.2 |  |
| Genişlik, %10–90 aralığı | 3.9 / 7.9 | 4.5 / 7.6 | 3.5 / 7.1 | 4.0 / 6.2 |  |
| Boy, p90 derinlik − geri hat | 1.0 / 4.5 | 2.3 / 6.8 | 2.2 / 8.5 | 2.3 / 7.9 |  |

## Okuma

- **Blok derinliği** ve **hat aralığı**: gündüzde gürültü eşiklerin çok altında (0,8 ve
  0,6 m); gecede ve yeni sahada p90 eşiğe değiyor (6,5 ve 4,7 m) → karar "sınırda".
  Bekçi tek dakikaya değil 5 dakikalık medyan farkına baktığı için pratikte kullanılabilir,
  ama gece uyarılarının bir kısmı ölçüm hatası olabilir.
- **Genişlik (en–en)**: gürültü 2,4–5,8 m medyan, 8,7–12,9 m p90 — 6 m eşik gürültünün
  içinde; uyarıların yarısı ölçüm hatası olur. Uçları kırpan tanımlar (%10–90 aralığı)
  p90'ı 6–8 m'ye indiriyor ama medyan 3,5–4,6 m kalıyor: genişlik için eşik en az 8 m
  ve %10–90 tanımı önerilir; yine de en zayıf ölçüm.
- **Boy (en ileri oyuncu)**: 132877'de iyi (1,3 m) ama 132831'de 10,6–10,8 m — tek bir
  hayalet/kenar tespiti en ileri oyuncu sayılıyor. p90 derinlik tanımıyla gürültü
  2.3 / 8.5 m. Mevcut tanımla 6 m eşik yeni sahada güvenilmez.
- Kapsama: takipte şekil hesaplanabilen kare payı %87–100 (gece en düşük).

## Diğer oturum için somut öneri

1. `width` → %10–90 yüzdelik aralığı, eşik 8 m; `length` → p90 derinlik − geri hat.
2. `block_depth` 6 m ve `line_gap` 4 m kalsın.
3. Bu değişiklikler yapılırsa aynı araçla yeniden ölçülür; değişiklik uyarı sayısını
   düşürür, bu yüzden "normalden sapma" tespiti için 25+5 dakikalık pencere korunmalı.

Sınırlar: üç maç, 10'ar dakika (+4 ayrık segment); şekil hataları sahiplik hatasını
içermez (iki tarafta da aynı takım aynı karede); referansın kendi hatası gündüzde
≈1 m, gecede bilinmiyor.
