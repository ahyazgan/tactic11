# Gölgede forma rengi: doğrudan görüntü testi

14 Eylül 2026. **Alternatif yöntem kontrol kapısını geçmedi; üretim varsayılanı
değiştirilmedi.** Önceki PR #239 tüm kontroller geçince `81cfca2` ile birleştirildi.
PR oluşturma, kontrolleri takip etme ve yeşil son commit'i birleştirme yetkisi
kullanıcının isteğiyle `AGENTS.md` içine kalıcı olarak kaydedildi.

## Test seti

Geometrik GT eşlemesi kullanılmadı. Her segmentin 5 ve 20. saniyesine en yakın
önbellek karesindeki **bütün kişi kutuları** alındı; zaman eşitliğinde erken
kare seçildi (4,96 ve 20,00 sn). Seçim, tahminler veya hata listesiyle yapılmadı.
Kutu numarası ve zaman görünen inceleme görüntülerinde tahmin/GT etiketi yoktu.

- Geliştirme 0/3: 61 kutu; 49 mavi/beyaz oyuncu, 6 başka renk, 6 belirsiz.
- Kontrol 6/9: 81 kutu; 74 mavi/beyaz oyuncu, 7 başka renk.
- Başka renk, örneğin kırmızı/sarı/siyah giyimdir; kişinin hakem, kaleci veya
  kenar görevlisi olduğu ayrıca iddia edilmez. Bu sınıf için takım atanma sayısı
  ayrı izlenir. Örtüşme veya yetersiz detayda belirsiz etiketi kullanıldı.

142 kutu Codex tarafından görüntüden etiketlendi. Tek değerlendirici vardır;
bağımsız hakemli etiketler değildir. Kareler ve takipler ilişkilidir, iki bölüm
aynı maçtandır. Bu test farklı maç, ışık, forma veya oyuncu kimliğine genellenemez.

## Dondurulan deney

Mevcut yöntem her takibin renk gözlemlerinin medyanını kullanır. Alternatif,
en büyük RGB kanalına göre en parlak `max(2, ceil(N/4))` gözlemi seçip onların
medyanını mevcut kümeleme/ret sistemine verir. Renk kümelemesi, kısa takip
elemesi, çapa ve aykırılık eşikleri değiştirilmedi. Deney yalnız `scripts/`
altındadır; `TeamAssigner` ve canlı takip koduna bağlanmadı.

Geliştirme sonucu alındıktan sonra aday ve kabul şartı
[kit-temporal-decision.json](measurements/kit-temporal-decision.json) dosyasına
yazıldı. Daha sonra kontrol görüntüleri etiketlendi. Kontrol sonucundan sonra
parametre, örnek seçimi veya etiket değiştirilmedi.

## Sonuç

| Doğrudan forma etiketleri | Geliştirme: mevcut → aday | Kontrol: mevcut → aday |
|---|---:|---:|
| Doğru takım ataması | 36 → 41 | 66 → 65 |
| Yanlış takım ataması | 10 → 8 | 7 → 5 |
| Takımı belirsiz oyuncu | 3 → 0 | 1 → 4 |
| Başka renkli kişiye takım ataması | 1 → 1 | 3 → 3 |

Geliştirmede gözlenen gölgeli beyaz oyuncu (segment 3, takip 9), her iki
inceleme karesinde mavi yerine beyaz takıma geçti. Ancak kontrolde segment 9'un
16 ve 21 numaralı takiplerine ait dört doğru beyaz forma gözlemi belirsizleşti.
Diğer kazanımlar bu kaybı doğru sayısı açısından telafi etmedi.

Kabul şartı: aynı etiketli nüfusta doğru atamalar artmalı, yanlışlar ve başka
renklilere atamalar artmamalı. Geliştirme geçti, kontrol geçmedi. Daha düşük
yanlış sayısını, doğru oyuncu kaybını gizleyerek başarı olarak sunmuyoruz.
Eski %81,11 konumsal GT uyumuyla bu doğrudan görüntü sayıları karşılaştırılmaz.

## Tekrar üretim ve test

- [Geliştirme etiketleri](measurements/kit-fixed-development-labels.json),
  [kontrol etiketleri](measurements/kit-fixed-control-labels.json): kaynak
  video/önbellek SHA-256, kare/track/bbox, etiket ve belirsizlik notu.
- Kör inceleme görüntüleri: [0](measurements/kit-fixed-segment-0.jpg),
  [3](measurements/kit-fixed-segment-3.jpg), [6](measurements/kit-fixed-segment-6.jpg),
  [9](measurements/kit-fixed-segment-9.jpg).
- [Karşılaştırma](measurements/kit-temporal-comparison-2026-09-14.json):
  her kutunun iki tahmini, etiket/önbellek hash'leri ve otomatik kabul kararı.

```powershell
.\venv-cv\Scripts\python.exe -m scripts.soccertrack_v2.prepare_kit_review --cache data/tracking/bench/signal_quality_v1 --segments 0 3 --out data/tracking/bench/kit_review_repeat
.\venv\Scripts\python.exe -m scripts.soccertrack_v2.benchmark_kit_colors --cache data/tracking/bench/signal_quality_v1 --labels docs/measurements/kit-fixed-development-labels.json --out data/tracking/bench/kit_dev_repeat.json --development-only
.\venv\Scripts\python.exe -m scripts.soccertrack_v2.benchmark_kit_colors --cache data/tracking/bench/signal_quality_v1 --labels docs/measurements/kit-fixed-development-labels.json docs/measurements/kit-fixed-control-labels.json --out data/tracking/bench/kit_all_repeat.json
```

İlgili **58 test geçti**, ruff temiz, mypy 495 kaynak dosyasında temiz.
Testler zaman seçimi/tüm kutuların korunması, parlak gözlem seçimi, belirsizlerin
doğru sayılmaması, kontrol etiketleri değişince tahmin/eşlemenin sabit kalması ve
doğru kaybı/artan yanlış/farklı nüfusta kabul verilmemesini kapsar.
Tam proje ve Docker/migration kontrolleri PR'ın son commit'inde izlenir.
