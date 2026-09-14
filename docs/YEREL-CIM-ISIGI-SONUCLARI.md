# Çevredeki çim ışığıyla forma rengi düzeltmesi

14 Eylül 2026; başlangıç `1e8e9f2`. **Yerel çim normalizasyonu yeni kontrol
kliplerinde kabul koşullarını geçti ve ortak video/canlı takip hattına bağlandı.**
Doğru atamalar artarken yanlışlar azaldı; atama yapılamayan gözlemler de arttı.
Ölçüm tek maçtandır; farklı maç ve forma renklerinde doğrulanmış başarı değildir.

## Sabitlenmiş deney ve kaynaklar

İlk denemede eski 0/3/6/9 klipleri geliştirme, yeni 2/8 klipleri kontroldü.
Parlak gözlemlerle yalnız mevcut takım atamalarını değiştirmek geliştirmede
102 doğru / 17 yanlış → 106 / 13 verdi. Ancak yeni kontrolde 55 / 10 / 10
(doğru / yanlış / atanamayan) değişmedi. Bu yöntem üretime alınmadı; tekrar
üretim için `benchmark_shadow_reassignment.py` altında tutuldu.
[Dondurulan karar](measurements/kit-reassignment-decision.json) ve
[sonuç](measurements/kit-shadow-reassignment-comparison-2026-09-14.json).

İkinci denemede 2/8 de geliştirmeye alındı. Yeni kontrol **1/7** olarak,
görüntüler açılmadan ayrıldı. Önceki 6/9 ve 2/8 artık bu deneyin kontrolü
değildir. Her klibin 5 ve 20. saniyesine en yakın önbellek karesindeki bütün
kişi kutuları seçildi (4,96 ve 20,00 sn). Seçim tahminlere göre yapılmadı.
Görüntüler tahmin ve GT takım etiketi gösterilmeden Codex tarafından etiketlendi.

- Geliştirme 0/2/3/6/8/9: 222 kutu; 198 mavi/beyaz oyuncu, 18 başka renk,
  6 belirsiz görüntü etiketi.
- Kontrol 1/7: 69 kutu; 66 mavi/beyaz oyuncu, 3 başka renk.
- Tek değerlendirici, aynı maç ve ilişkili kare/takipler kullanıldı. Konumsal
  GT eşleşmesi, oyuncu kimliği veya hakem/kaleci rolü doğruluğu ölçülmedi.

Geliştirmede çim piksellerini seçen yöntem doğru sayısını artırdı; bütün yan
pikselleri kullanan yöntem artırmadı. Aday, parametreler ve kabul koşulları
[kit-local-light-decision.json](measurements/kit-local-light-decision.json)
dosyasına yazıldıktan sonra 1/7 görüntüleri açıldı. Kontrolden sonra eşik,
yöntem, örnek seçimi veya etiket değiştirilmedi.

## Sonuç

| Gözlem sayısı | Geliştirme: ham → çim | Yeni kontrol: ham → çim |
|---|---:|---:|
| Doğru takım ataması | 157 → 160 | 54 → 56 |
| Yanlış takım ataması | 27 → 11 | 7 → 4 |
| Takım atanamayan oyuncu | 14 → 27 | 5 → 6 |
| Başka renkli kişiye takım ataması | 5 → 4 | 0 → 0 |

Kabul şartı aynı örneklerde daha çok doğru atama, artmayan yanlış atama ve
artmayan başka renk atamasıydı; geliştirme ve kontrol geçti. Oyuncu kaybı
gizlenmedi: geliştirmede 13, kontrolde 1 ek gözleme takım atanamadı. Bu küçük,
aynı maç içindeki kazanım genel doğruluk hedefinin tamamlandığı anlamına gelmez.

## Üretim değişikliği

`kit_color`, mevcut gövde rengini kişinin iki yanındaki gövde yüksekliği
bandından ölçülen ışığa göre ölçekler. En az 8 yeşil baskın piksel varsa
yalnız bunlar; yoksa çevredeki bütün pikseller kullanılır. Işık, piksel başına
en büyük RGB kanalının medyanıdır. Ölçek `80 / ışık`, sınırı 0,5–3'tür;
RGB 0–255 aralığında tutulur. Yetersiz/çok karanlık çevrede ham renk korunur.
Görüntü dışındaki kutular ve boş şeritler karşı kenardan piksel okuyamaz.

`TeamAssigner` kümeleme, aykırılık ve renk çapasını sıralama kuralları aynı
kaldı. `PipelineConfig.normalize_kit_light` varsayılan açık; ham karşılaştırma
için `False` seçilebilir. Gözlem önbelleği CLI'sında `--raw-kit-colors` bunu
sağlar. Top adayları önbelleği de ana hatla aynı renk fonksiyonunu kullanır.
Özet, renk yöntemini `local_grass_v1` veya `raw_rgb_v1` olarak kaydeder.
Bir canlı işçide tüm segmentler aynı renk yöntemini kullanır; çapa bu yöntemle
ölçülen ilk ayırt edilebilir paletten kurulur.

## Tekrar üretim ve doğrulama

Üretim fonksiyonuyla aynı 8 klibin bütün kutuları tekrar işlendi. **54.103 renk
gözlemi** dondurulan deneyle birebir eşleşti. Yeniden çıkarılan ham gözlemler de
kaynak önbelleğin bütün uygun takip gözlemleriyle aynıydı. Canlı özetteki 0,1 RGB
yuvarlamasıyla tekrar edilen atamalar ve bütün etiketli sonuçlar değişmedi.

- [Dondurulan karşılaştırma](measurements/kit-local-light-comparison-2026-09-14.json):
  yöntemlerin bütün etiketli tahminleri, örnek sayıları, kabul sonuçları ve hash'ler.
- [Üretim tekrar doğrulaması](measurements/kit-local-light-production-verification.json):
  gözlem eşitliği, canlı çapa kontrolü ve kaynak/önbellek SHA-256 kayıtları.
- Yeni etiketler: [2/8](measurements/kit-shadow-new-control-labels.json),
  [1/7](measurements/kit-local-light-control-labels.json).
- Kör inceleme görüntüleri: [1](measurements/kit-retry-segment-1.jpg),
  [2](measurements/kit-retry-segment-2.jpg), [7](measurements/kit-retry-segment-7.jpg),
  [8](measurements/kit-retry-segment-8.jpg). Önceki 0/3/6/9 etiketleri korunur.

Yerel videolar ve ham önbellekler mevcutken, yeni çıktı yollarıyla:

```powershell
.\venv-cv\Scripts\python.exe -m scripts.soccertrack_v2.cache_local_kit_light --cache data/tracking/bench/signal_quality_v1 data/tracking/bench/kit_v2_control_raw data/tracking/bench/kit_local_light_control_raw --segments 0 1 2 3 6 7 8 9 --out data/tracking/bench/kit_light_repeat
.\venv\Scripts\python.exe -m scripts.soccertrack_v2.benchmark_local_kit_light --cache data/tracking/bench/kit_light_repeat --labels docs/measurements/kit-fixed-development-labels.json docs/measurements/kit-fixed-control-labels.json docs/measurements/kit-shadow-new-control-labels.json docs/measurements/kit-local-light-control-labels.json --out data/tracking/bench/kit_light_repeat_result.json
```

Normalleştirilmiş kaynak önbelleğini tekrar normalleştirme, değişen ham gözlem,
etiket/kaynak hash uyuşmazlığı ve mevcut çıktının üzerine yazma reddedilir.
80 ilgili test geçti; ruff temiz, mypy 498 kaynak dosyasında temiz. Testler
ışık değişimi, komşu beyaz pikseller, görüntü sınırları, karanlık/boş çevre,
kazanç sınırları, gerçek toplama hattında config geçişi, ham gözlem eşitliği,
kontrol etiketlerinin tahmin/eşlemeye karışmaması ve canlı çapanın korunmasını kapsar.
İzole SQLite ile tam yerel paket: **2.569 geçti, 1 atlandı**. Birleşik son PR
commit'inde Docker, migration, lint/tip ve tam test kontrolleri ayrıca izlenir.
