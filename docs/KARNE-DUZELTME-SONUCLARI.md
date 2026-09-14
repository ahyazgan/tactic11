# Karne inceleme düzeltmeleri — 14 Eylül 2026

İki hata giderildi ve özgün 100 maç / 514 tik üzerinde yeniden ölçüldü.
Canlı öneri motorunda filtre etkinleştirilmedi.

## Düzeltmeler

- Eğitimde %15 bayrak bütçesini karşılayan aday yoksa eşikler `None` olur;
  ilk adayın sessizce seçilmesi kaldırıldı. Model bu durumda bayrak vermez.
- Kontrol yarısında yeterli bayrak yoksa yüksek kaldırma başarı sayılmaz.
  Bütçe kontrolü yuvarlanmış gösterim oranıyla değil gerçek sayılarla yapılır.
- Kullanılan değişiklik sayısında aynı dakikadaki ayrı oyuncular korunur.
  Hamle zamanlarını ölçen eski cetvellerin tekilleştirmesi korunur.
- Yetersiz ölçümde permütasyon p değeri `null` olur; sonlu denemelerde
  `(yakalama + 1) / (deneme + 1)` kullanılır. Sıfır olasılık iddiası yoktur.

Eski kod 40'ar tiklik iki yarıda yalnız 1'er bayrakla **seçici** diyordu.
Regresyon testi artık bu örnekte **yetersiz veri** döndüğünü doğruluyor.
Ayrıca boş eğitim, %15'e yuvarlanan ama eşik altındaki 150/1003 oranı,
kontrol yarısında az bayrak ve çift değişiklik test edildi.

## Aynı veriyle karşılaştırma

Ham olaylar `statsbomb/open-data` deposunun
`4b73468fc5b0f1950f9f66fada70ad3a4f9327cb` sürümünden alındı.
Kaynak veritabanı salt okunur açılarak yerel bir SQLite kopyası üretildi.
101 yerel maç kimliğinin 100'ü açık kaynakta bulundu; bulunmayan yerel
`20260914` kaydı değerlendirmeye girmedi.

Eski toplayıcı (`e0237df`) ile yeniden üretilen girdinin SHA-256'sı:
`5cf345a22f5e74e00b58c70e81a83ea32e1ac0bdc46a8f1f8cd4cab7ea999e73`.
Bu değer özgün raporla **birebir aynı**. Yeni toplayıcı 65 tikte kullanılan
oyuncu değişikliği sayısını düzeltti. Yeni girdi SHA-256'sı:
`4be72ff3bd6a1592f151cb218fd2a334a2d9629888ddfc1618a252fe1e3a4f56`.

| Kapılı öneri, A / B | Önce | Düzeltme sonrası |
|---|---|---|
| Bayrak sayısı | 47 / 53 | 51 / 52 |
| Bayrak oranı | 0,178 / 0,212 | 0,193 / 0,208 |
| İsabet | 0,362 / 0,377 | 0,314 / 0,327 |
| Kaldırma | 1,645 / 1,848 | 1,427 / 1,603 |
| Yakalama | 0,293 / 0,392 | 0,276 / 0,333 |
| Öğrenilen önsel eşiği | 0,30 / 0,30 | 0,30 / 0,30 |
| Öğrenilen destek eşiği | 2 / 2 | 2 / 1 |

İki yarı da 1,25 kaldırma eşiğini geçti; eski başarı büyüklüğü korunmadı.
400 permütasyonda gerçek isabeti yakalama sayısı 16 / 1; düzeltilmiş
p değerleri 0,04239 / 0,00499. Bu tik düzeyinde keşifsel bir sınavdır;
maç içi bağımlılığı modelleyen bağımsız doğrulama sayılmaz.

Hedef hâlâ StatsBomb Tactical Shift etiketidir; gerçek diziliş ihtiyacına
zayıf vekildir. Tek takımın aynı külliyatında tekrar ölçüm, başka maçlarda
genelleme kanıtı değildir. Yakalama düşüklüğü nedeniyle canlı filtreyi
etkinleştirme kararı bu düzeltmenin kapsamı dışındadır.

Sayısal çıktı: [v2 ölçümü](measurements/karne-sekil-seciciligi-2026-09-14-v2.json).

## Yeniden çalıştırma ve kontroller

Ham olaylar ve SQLite kopyası gitignore kapsamındaki
`data/tracking/bench/karne-review-20260914/` klasöründedir; depoya eklenmez.
Komutlar repo kökünden:

```powershell
$env:DATABASE_URL = 'sqlite:///./data/tracking/bench/karne-review-20260914/snapshot.db'
.\venv\Scripts\python.exe -m scripts.measure_shape_selectivity --tenant t-default --team 217 --events-dir data/tracking/bench/karne-review-20260914/events --out docs/measurements/karne-sekil-seciciligi-2026-09-14-v2.json
.\venv\Scripts\python.exe -m scripts.coach_iq --tenant t-default --team 217 --events-dir data/tracking/bench/karne-review-20260914/events
```

- Yeni regresyonlarla hedefli testler: 43 geçti.
- Birleşik tam pytest: 2519 geçti, 1 atlandı; 15 uyarı.
- Ruff temiz; mypy 489 kaynak dosyasında temiz.
- `coach_iq` komutu aynı veride tamamlandı: bayrak 51/52, kaldırma 1,43/1,60,
  destek eşiği 2/1; bağımsız ölçüm komutunun çıktısıyla eşleşiyor.
