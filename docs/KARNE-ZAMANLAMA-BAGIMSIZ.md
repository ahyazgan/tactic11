# Zamanlama önseli: bağımsız doğrulama — 14 Eylül 2026

Canlı motorda veriden türetilmiş **üç** donmuş tablo vardı. Bu çalışmayla
üçünün de bağımsız maçlarda sınanması tamamlandı:

| Tablo | Nerede | Sonuç |
|---|---|---|
| Şekil kapısının durum önseli | karne ölçüm katmanı | taşındı (kaldırma 2,01 / 2,21) |
| `ELITE_OFF_PRIOR` — kim çıkar | canlı motor | tek kulübe özgüydü → yeniden fit edildi |
| `ELITE_SUB_WINDOW_PRIOR` — ne zaman | canlı motor | **bu rapor** |

Zamanlama önseli panelde `sub_timing` sinyalini yakıyor: koça "şimdi değişiklik
penceresi" diyen şey bu. Kaynağı Barcelona'nın 100 maçındaki **iki takımın**
antrenörleri, 3200 ızgara tiki. Hiç dışarıda sınanmamıştı.

**Sonuç: taşınıyor, ve karnenin eski hükmünü düzeltiyor.** La Liga 2015/16'da
saati açık farkla geçiyor, Premier League 2015/16'da saatle aynı. İki kümede de
küme içi tavana oturuyor.

Ölçüm:
[La Liga 2015/16](measurements/karne-zamanlama-bagimsiz-laliga-2015-16.json) ·
[Premier League 2015/16](measurements/karne-zamanlama-bagimsiz-premier-league-2015-16.json).
Sabit kamera / takip dosyalarına dokunulmadı.

## Sonuçlar

Her küme: 100 bağımsız maç, 3200 ızgara tiki (10–85 dk arası her 5 dk, iki takım),
12 dakikalık pencere, külliyatla kesişim 0.

### La Liga 2015/16 (taban oranı 0,323)

| Kural | Bayrak | İsabet | Kaldırma | Yakalama | F1 |
|---|---:|---:|---:|---:|---:|
| Hep-evet | 1,00 | 0,323 | 1,00 | 1,00 | 0,488 |
| **Donmuş tablo + donmuş eşik** | 0,46 | 0,629 | **1,95** | 0,90 | **0,741** |
| Saat kuralı (≥50 dk, en iyi eşik) | 0,50 | 0,564 | 1,75 | 0,87 | 0,686 |
| Küme içi tavan A / B | 0,38 / 0,43 | 0,682 / 0,653 | 2,14 / 1,99 | 0,82 / 0,85 | 0,744 / 0,740 |

Hüküm: **saati geçiyor** (+0,055, deponun gürültü bandı ±0,05).

### Premier League 2015/16 (taban oranı 0,307)

| Kural | Bayrak | İsabet | Kaldırma | Yakalama | F1 |
|---|---:|---:|---:|---:|---:|
| Hep-evet | 1,00 | 0,307 | 1,00 | 1,00 | 0,469 |
| **Donmuş tablo + donmuş eşik** | 0,48 | 0,570 | 1,86 | 0,88 | 0,693 |
| Saat kuralı (≥55 dk, en iyi eşik) | 0,44 | 0,579 | 1,89 | 0,83 | 0,681 |
| Küme içi tavan A / B | 0,40 / 0,34 | 0,609 / 0,726 | 2,05 / 2,30 | 0,82 / 0,77 | 0,699 / 0,747 |

Hüküm: **saatle aynı** (+0,012, bandın içinde).

Saat kuralına kasten avantaj verildi: eşiği ölçülen kümede **en iyi** olacak
şekilde seçildi. Gerçek bir saat kuralı eşiğini önceden sabitlemek zorunda
kalırdı; yani buradaki saat, sahadaki saatten iyidir.

## Karnenin eski hükmü neden farklıydı

Karne bugüne kadar "zamanlama saatle aynı" diyordu (önsel F1 0,704 vs saat
0,738). O ölçüm **motorun tik dakikalarında** yapılıyor: 28, 40, 55, 66, 78 —
yalnız beş dakika, ve dördü ikinci yarıda. Bu dağılım saat kuralını kayırıyor,
çünkü saat zaten "geç ise evet" demekten ibaret ve tiklerin çoğu geç.

Bu ölçüm önselin fit edildiği ızgarada (5 dakikada bir, 10'dan 85'e) yapılıyor —
maçın tamamını eşit ağırlıkla tarayan daha adil bir sınav. Orada önsel saatin
üstüne çıkıyor ya da eşitleniyor.

İkisi çelişmiyor, farklı soruları ölçüyorlar: karnedeki satır *"motorun konuştuğu
anlarda"* geçerli, buradaki *"maçın herhangi bir anında"*. İkisi de doğru; hangi
iddiayı savunacağımız hangi soruyu sorduğumuza bağlı.

## Görülmemiş hücre sorunu burada YOK

Şekil kapısında tablonun hiç görmediği hücreler tiklerin %10–12'siydi ve oraya
kaldırılan bayraklar tam 1,00 kaldırma veriyordu (sıfır bilgi) — bu yüzden şekil
kapısı artık orada susuyor.

Zamanlama tablosunda görülmemiş hücre payı **%0,1–0,3**. Tablo durum uzayını
neredeyse tamamen kaplıyor. "Görülmemişte sus" varyantı ölçüldü ve sonuç
değişmedi (F1 0,741 → 0,741 ve 0,693 → 0,691). Bu yüzden `UNKNOWN_CELL = 0.5`
olduğu gibi bırakıldı; değiştirmek için sebep yok.

## Ölçüm sınırları

- **Değişiklik hakkı sınanmadı.** Tablo 3 hakkın geçerli olduğu sezonlardan
  geliyor ve hücrenin bir ekseni "o ana kadar yapılan değişiklik". Bağımsız
  kümeler de 2015/16, yani yine 3 hak. Tablonun kendi doküstringindeki "5-hak
  kuralıyla yeniden fit gerekir" uyarısı **hâlâ geçerli** — bu ölçüm onu
  karşılamıyor.
- **Hedef vekil değil ama dar.** "Antrenör 12 dk içinde taktik değişiklik yaptı
  mı" gerçek bir olay, ama "iyi bir değişiklik miydi" sorusuna cevap vermez.
  Bütün bu ölçüm taklit kalitesidir, karar kalitesi değil.
- **Izgara ≠ motor tiki.** Yukarıda anlatıldı: iki dağılım iki farklı hüküm
  veriyor ve ikisi de raporlanmalı.
- **İki lig, bir dönem.** Her iki bağımsız küme de 2015/16 ve Avrupa'nın beş
  büyük liginden. Başka rekabet düzeyi sınanmadı.

## Tekrar üretim

```powershell
.\venv\Scripts\python.exe -m scripts.validate_timing_prior --corpus-dir C:\sb --independent-dir C:\sb-laliga1516 --label "La Liga 2015/16" --out docs/measurements/karne-zamanlama-bagimsiz-laliga-2015-16.json
.\venv\Scripts\python.exe -m scripts.validate_timing_prior --corpus-dir C:\sb --independent-dir C:\sb-pl1516 --label "Premier League 2015/16" --out docs/measurements/karne-zamanlama-bagimsiz-premier-league-2015-16.json
```

Script kesişimi kendisi denetler ve kesişim varsa durur. Izgara tablosunun
SHA-256'sı ölçüm JSON'larında.

Kontroller: **2555 test geçti, 1 atlandı**; ruff temiz; mypy 497 kaynak
dosyasında temiz. Külliyat veritabanına ve ham maç dosyalarına yazılmadı.
