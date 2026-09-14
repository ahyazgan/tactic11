# Gündüz maçı: dış doğrulama ve varsayılan düzeltmesi

Sonraki geliştirme: [saha dışı takip filtresi ve önizleme düzeltmesi](OYUNCU-SUZGECI-SONUCLARI.md).
Aşağıdaki ilk gündüz ölçümü değişmeden korunur.

14 Eylül 2026. SoccerTrack v2 **117093**, birinci yarı, üç adet 30 saniyelik
gündüz klibi işlendi. Daha aydınlık görüntü, önceki gece düzeltmesinin başka
maça taşınamadığını ortaya çıkardı. **Yerel çim normalizasyonu artık varsayılan
kapalı; ham gövde rengi kullanılıyor.** Kümeleme/eşikler bu kontrolle ayarlanmadı.

## Kaynak ve kamera

Video: [SoccerTrack v2 resmî proje](https://atomscott.github.io/SoccerTrack-v2/),
[117093 ilk yarı](https://drive.google.com/file/d/1gPoN2h2SxEjWORK6FwKTEsCuKPylar53/view).
Atıf: Atom Scott ve diğerleri, SoccerTrack v2 (2025),
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
Paylaşılan görseller bu kayıttan kırpılmış veya kutu/işaret eklenmiş türevlerdir.

- Kaynak **4096×1080, 25 fps**, sabit panoramik kamera. Parlaklık değiştirilmedi.
- 600, 690, 780, 870. saniyeler sonuçlardan önce seçildi; yerel segmentler
  0/3/6/9. 0/3/6 alındı. Dördüncü indirmede Drive kotası doldu; 9 yerine başka
  klip seçilmedi. Etiketler açılmadan kaydedilen bu kısıt nedeniyle kontrolün
  planlanan üç klibinden ikisi mevcut.
- [Plan](GUNDUZ-MACI-PLANI.md), [kaynak ve video SHA-256](measurements/daylight-117093-source.json).
- Bu maçın [65 resmî saha işareti](https://drive.google.com/file/d/1k5hl4jVzlgB4AN-lSs35VpPW7elz4cha/view)
  ile [ayrı TPS kalibrasyonu](../data/tracking/calibrations/soccertrack_v2_117093_landmarks.json)
  oluşturuldu. Kaynak işaret SHA-256 kalibrasyon metadata'sında tutulur.
  [Görüntü üzerindeki işaretler](measurements/daylight-117093-landmarks.jpg)
  incelendi. Bir işareti dışarıda bırakarak hesaplanan ortalama hata **1,432 m**;
  bu oyuncu/top konum doğruluğu değildir. Gece kalibrasyonu kullanılmadı.

## Sabit karşılaştırma

Dedektör RF-DETR mixed small, dört görüntü parçası; takip ayarları değişmedi.
25 fps kaynakta mevcut örnekleme 12,5 fps üretti: klip başına 375, toplam 1.125
örnek kare. Ham gözlemdeki aynı kutular tekrar okunarak iki renk yöntemi
karşılaştırıldı; uygun takiplerin bütün ham renk geçmişleri birebir doğrulandı.

Her klibin 4,96 ve 20,00 saniyelerinde **bütün tespit kutuları** tahminler
gösterilmeden etiketlendi: toplam 172 kutu. Segment 0 yalnız anonim takım
numarasını mavi/beyaz ada eşlemek için kullanıldı; 3/6 dış kontroldü.

| Örnek grubu | Mavi/beyaz | Başka renk kişi | Kişi olmayan | Belirsiz |
|---|---:|---:|---:|---:|
| Eşleme 0 | 36 | 9 | 9 | 4 |
| Kontrol 3/6 | 74 | 18 | 17 | 5 |

[Etiketler](measurements/daylight-117093-labels.json) ve kör inceleme görselleri:
[0](measurements/daylight-117093-review-0.jpg),
[3](measurements/daylight-117093-review-3.jpg),
[6](measurements/daylight-117093-review-6.jpg).
Tek Codex değerlendiricisi kullanıldı; bağımsız ikinci inceleme yok.
Kareler/takipler ilişkili. Bu ölçüm tespit edilmiş kutulardaki forma atamasıdır;
tespit duyarlılığı, oyuncu kimliği veya olay doğruluğu değildir.

| Sonuç | Eşleme: ham → çim | Kontrol: ham → çim |
|---|---:|---:|
| Doğru takım | 33 → 18 | **53 → 16** |
| Yanlış takım | 3 → 11 | **13 → 54** |
| Takım atanamayan oyuncu | 0 → 7 | 8 → 4 |
| Başka renkli kişiye atama | 5 → 4 | 12 → 10 |
| Kişi olmayan kutuya atama | 9 → 7 | 17 → 10 |

Ham yöntemin kontroldeki doğru oranı **53/74 = %71,6**. Normalizasyonun
dış kontrolü başarısız: azalan sahte atamalar, forma atamasındaki bozulmayı
telafi etmiyor. Klip bazında ham doğru/yanlış/atanamayan: 3'te 38/2/1,
6'da 15/11/7. Yalnız iyi görünen 3. klip sonuç olarak seçilmedi.
[Tam karşılaştırma](measurements/daylight-117093-comparison.json) bütün etiketli
tahminleri, renk paletlerini, takip atamalarını ve kaynak hash'lerini içerir.

### Neden sadece numara değişimi değil?

Normalizasyon, ilk eşleme klibinde 18 beyaz ve 11 mavi kutuyu aynı takım 0'a
atadı; diğer 7 maviye takım veremedi. Takım 1'e atanan etiketli kutuların
7'si kişi değildi, biri başka renkli kişiydi. İki RGB merkezi ayrık olmasına
rağmen iki gerçek formayı temsil etmedi. Segment 0'daki çoğunluk eşlemesi
bu yüzden mavi=1 seçti. Kontrolde eşlemeyi ters çevirerek skor düzeltilmedi.
Bu tablo, kümeler ile ilk renk çapasının anlamsal olarak bozulduğunu gösterir;
görünür kutu örnekleri bunun saha yazılarıyla ilişkili olduğuna işaret eder.

Her iki yöntemin üç klipteki atamaları ayrıca gerçek `process_video` hattından
geçirildi; canlı özetin 0,1 RGB yuvarlamalı çapasına kadar ölçümle aynıydı.
[Üretim yolu doğrulaması](measurements/daylight-117093-production-verification.json).
Dedektör bu doğrulamada yeniden çalıştırılmadı; dondurulmuş gözlemler kullanıldı.

## Uygulanan değişiklik ve sınırlar

`PipelineConfig.normalize_kit_light` ve `kit_color` varsayılanları kapatıldı.
Önbellek CLI'sı da ham renk kullanır; eski `--raw-kit-colors` komutu geçerlidir.
Deneysel yöntem `normalize_kit_light=True` veya `--normalize-kit-light` ile
açıkça seçilebilir. Yeniden renk çıkarma deneyi normalizasyonu açıkça çağırır;
eski gece ölçümü tekrar üretilebilir.

Bu bir genel doğruluk kazanımı iddiası değil, dış doğrulamada başarısız
varsayılanın geri alınmasıdır. Önceki gece kontrolünde ham 54/7/5,
normalizasyon 56/4/6 vermişti; ham varsayılana dönüş o yerel kazanımdan
vazgeçer. Otomatik gece/gündüz seçici bu küçük veriyle eklenmedi. Artık görülen
117093 kontrolü, gelecekteki ayarlamalar için yeni kör kontrol sayılamaz.

Kalan belirgin sorun: saha yazıları, kenardaki ekipman ve bazı yinelenen/kenar
tespitleri oyuncu sayısını şişiriyor. Ham yöntemde kontrolün 750 örnek karesinin
725'inde en az bir takıma 11'den fazla kutu atanıyor. Örneklenen saha dışı
yazı/ekipman kutuları mevcut 2 m saha marjının içinde kalıyor. Bu marj veya
dedektör eşikleri burada değiştirilmedi; bunlar sonraki ayrı geliştirme ve
görülmemiş kontrol gerektiren sorunlar. Güvenilir oyuncu/olay analizi tamamlanmadı.

## Takip çıktısı ve tekrar üretim

Ham yöntemle üç klibin JSON çıktısı üretildi; klip başına 125 dışa aktarılan
kare, fiilî **4,167 fps**. Kaynağın 600/690/780 saniye başlangıçları korunur;
0/1 takım numaraları anonimdir, kulüp kimliği değildir. Top bulunan çıktı
karesi 84/122/21; çıkarılan tahmini pas 3/8/0, tahmini savunma olayı 0/0/0.
**Olaylar görüntüden doğrulanmadı; sıfır, gerçek maçta olay olmadığı demek değildir.**
[Çıktı özeti](measurements/daylight-117093-tracking-summary.json).

İlk kontrol klibinin 30 saniyelik önizlemesi yerelde
`data/tracking/bench/daylight_117093/tracking_raw/daylight-tracking.mp4`:
H.264, 2048×540, 12,5 fps, 375 kare. Kutu yeşil=anonim takım 0 (mavi forma),
kırmızı=takım 1 (beyaz forma), sarı=atanamayan; bunlar tahmindir.
[Önizleme karesi](measurements/daylight-117093-tracking-preview.jpg).
Ham videolar ve büyük önbellekler repoya eklenmedi, canlı veritabanına yazılmadı.

Yerel kaynak klipler ve önbellekler mevcutken, yeni çıktı yollarıyla:

```powershell
.\venv-cv\Scripts\python.exe -m scripts.soccertrack_v2.cache_observations --source data/tracking/bench/daylight_117093/source --segments 0 3 6 --calibration data/tracking/calibrations/soccertrack_v2_117093_landmarks.json --out data/tracking/bench/daylight_repeat_raw
.\venv-cv\Scripts\python.exe -m scripts.soccertrack_v2.cache_local_kit_light --cache data/tracking/bench/daylight_117093/raw --segments 0 3 6 --out data/tracking/bench/daylight_repeat_colors
.\venv\Scripts\python.exe -m scripts.soccertrack_v2.benchmark_daylight_kits --cache data/tracking/bench/daylight_repeat_colors --labels docs/measurements/daylight-117093-labels.json --source-manifest docs/measurements/daylight-117093-source.json --out data/tracking/bench/daylight_repeat_comparison.json
.\venv-cv\Scripts\python.exe -m scripts.soccertrack_v2.export_daylight_tracking --report data/tracking/bench/daylight_repeat_comparison.json --out data/tracking/bench/daylight_repeat_tracking --preview
```

İlk komut dedektörü tekrar çalıştırır; sonraki üç komut etiketlerin bağlı olduğu
korunmuş ham önbellekten ölçümü tekrarlar. Farklı dedektör koşusu eski kutu
etiketlerine sessizce bağlanmaz. Kaynak/kutu/hash değişimleri ve mevcut çıktı
üzerine yazma reddedilir. `--preview` OpenCV MP4 üretir; gösterilen H.264 kopya
ffmpeg ile CRF 18, yuv420p, faststart kullanılarak dönüştürüldü.

29 ilgili regresyon geçti; varsayılan/açık renk seçimi, gerçek toplama hattı,
kontrol etiketlerinin eşlemeye karışmaması, eksik/değişmiş kaynak kutuları ve
çıktı zamanları testli. Ruff temiz; mypy 503 kaynak dosyasında temiz.
İzole SQLite ile tam yerel paket: **2.594 geçti, 1 atlandı**. Birleşik son PR
commit'inin tam CI kontrolleri ayrıca takip edilir.
