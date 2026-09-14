# Saha dışı takipleri ayırma ve güvenilir önizleme

14 Eylül 2026; başlangıç `66b5502`. **117093 gündüz kamera profilinde saha
dışı takip filtresi etkinleştirildi. Genel varsayılan yapılmadı:** yeni gece
kontrolünde başka renkli kişiye bir ek takım ataması kabul koşulunu bozdu.
Önizlemede örnekleme/zaman ve panoramik saha çizimi de düzeltildi.

## Sorun ve uygulama

Mevcut metre filtresi saha çevresinde 2 m pay bırakıyordu. Saha yazıları,
kenardaki ekipman ve bazı kişiler bu pay içinde kalarak oyuncu takibi ve forma
renk kümelerini etkiliyordu. Yalnız kutu güven puanını artırmak gerçek oyuncu
kaybını da artırabilir; bu deneyde dedektör/renk eşikleri değiştirilmedi.

`person_filter.py`, kalibrasyonun gerçek sınır işaretlerinden görüntü poligonu
kurar. Dört köşe bilinmeli; eğri TPS kameralarda kenar başına en az üç işaret
bulunmalı. Kendini kesen/eksik sınır kullanılmaz. Kutu alt orta noktası saha
içinde veya max(1 px, görüntü yüksekliğinin %0,2'si) yakınındaysa saha kanıtıdır.
**Aynı süreklilikte en az iki saha gözlemi olan takip tümüyle korunur.** Böylece
duran, eğilen veya kısa süre çizgi dışına çıkan oyuncu sırf bu nedenle silinmez.
Süreklilik kesilince aynı takip numarası eski kanıtı devralmaz.

Kanıtsız takipler klibin sonunda, takım kümeleri kurulmadan önce çıkarılır.
ByteTrack kutuları/kimlikleri değiştirilmez; elenen takiplerin renkleri mevcut
uygun-kimlik kuralı sayesinde kümeye katılmaz. Silinen takip/kutu sayısı,
kimlikleri, uygulama/atlama nedeni ve tolerans `calibration_stats.person_filter`
içinde raporlanır. Bu, kişi sınıflandırıcısı veya gerçek oyuncu kimliği değildir.
Hareketli kalibrasyonda ve tam sınır bilinmediğinde mevcut filtre korunur.

## Deney ve kontrolün ayrılması

[Plan](OYUNCU-SUZGECI-PLANI.md) ve [dondurulan karar](measurements/perimeter-decision.json).
Filtre kodunun LF satır sonlarına göre SHA-256 değeri kontrol komutunda doğrulanır. Karardan sonra filtre
eşikleri veya etiketler skora göre değiştirilmedi.

- Geliştirme: önceki gündüz 172 kutu ve gece 291 kutu. Eski kontroller artık
  geliştirme verisidir. Gündüz 26 kişi olmayan kutunun 25'i elendi; 110 forma
  kutusu korundu, doğru/yanlış/atanamayan **86/16/8 → 100/10/0**.
- Gece geliştirme önbelleklerindeki 500 noktalı kalibrasyon tam, doğrudan
  işaretlenmiş çevre içermiyor; filtre uygulanmadı. **211/34/19 değişmedi**.
  Bu sonuç yalnız geriye uyum kontrolüdür, etkin filtrenin gece başarısı değildir.
- Yeni gündüz kontrolü: aynı üç klibin daha önce etiketlenmeyen 10 ve 24,96 sn
  karelerinde bütün 170 kutu. **Aynı klip ve ilişkili takipler**; bağımsız maç
  doğrulaması değildir.
- Yeni gece kontrolü: yereldeki 117092 ilk yarıdan önceden seçilen 1200 ve
  1500. saniyelerde başlayan 30 sn'lik iki yeni klip. 4,96/20 sn'de bütün 78
  kutu etiketlendi. Yeni zaman aralıkları, fakat aynı bilinen gece maçı.
  Burada ayrı 65 saha işaretli kalibrasyon kullanıldı; filtre etkin çalıştı.
- Bütün kontrol etiketleri iki yöntemin tahminleri gösterilmeden tek Codex
  değerlendiricisiyle tamamlandı. Bağımsız ikinci inceleme yok. Mavi/beyaz renk
  etiketi kulüp, oyuncu kimliği veya hakem/kaleci rolü doğrulaması değildir.

Takım 0/1 adları her maçın eski segment 0 etiketlerinden eşlendi; kontrol
etiketleri renk çapasını veya takım adını seçmedi. Eksik/kopya etiket, atlanan
kutu, değişmiş kaynak/hash ve önceden filtrelenmiş girdi ölçümde reddedilir.

## Kontrol sonuçları

| Ölçüt | Gündüz: eski → filtre | Gece: eski → filtre |
|---|---:|---:|
| Mavi/beyaz kutu | 108 | 67 |
| Doğru takım | **83 → 95** | 50 → 51 |
| Yanlış takım | **17 → 12** | 12 → 12 |
| Atanamayan forma | 8 → 1 | 5 → 4 |
| Silinen mavi/beyaz kutu | **0 → 0** | **0 → 0** |
| Başka renkli kişiye takım ataması | 22 → 8 | **3 → 4** |
| Kalan kişi olmayan kutu | **25 → 0** | 0 → 0 |
| Kişi olmayan kutuya takım ataması | 25 → 0 | 0 → 0 |

Gündüz doğru oranı **83/108 (%76,9) → 95/108 (%88,0)**. Kabul koşulları geçti.
Bu oran, tespit edilen ve etiketlenebilen forma kutularına aittir; dedektörün
kaçırdığı oyuncuları kapsamaz. Gece başka renge atama arttığı için **genel
geçiş reddedildi**; küçük doğru sayısı artışı başarısızlığı gizlemez.

Kliplerin bütün örnek karelerinde en az bir takıma 11'den fazla kutu atama:
gündüz **1.085/1.125 → 692/1.125**. Yeni gece klipleri **75/750 → 79/750**.
Bu sayılar tespit kutularıdır, benzersiz gerçek oyuncu sayısı değildir. Fazla
sayım hâlâ yüksek; aynı kişiye birden çok kutu, renk karışması ve benzer renk
giyen diğer kişiler çözülmüş sayılmaz. Gece sonucu bunun ek bir karşı örneğidir.

## Dağıtım kararı

`PipelineConfig.filter_off_pitch_tracks=None`, yalnız kalibrasyon metadata'sında
doğrulanmış `person_filter_profile` varsa açar. Bu profil **yalnız 117093 saha
kalibrasyonuna** eklendi. Görüntüye bakıp otomatik gündüz/gece sınıflandırması
yapılmıyor; başka kamera veya maçta aynı başarı iddia edilmiyor.

`True` açık deneysel seçim; `False` zorla kapatır. Önbellek CLI'sında
`--filter-off-pitch-tracks` / `--keep-off-pitch-tracks` aynı seçimleri yapar.
Yeni gece kalibrasyonu otomatik açılmaz. Yerel ışık normalizasyonu kapalı kalır.
Bu kamera için kontrol sonucuyla sürüme alma, yöntemi bütün kameralara
genellemekten ayrıdır; daha geniş kullanım yeni, görülmemiş maçlar gerektirir.

## Önizleme doğruluğu

25 fps kaynak / 15 fps istek gerçekte 12,5 fps gözlem üretirken eski önizleme
bağımsız 5 fps kare seçiyordu; bazı görüntülerde karşılık gelen takip kutusu
yoktu. Önizleme artık çıktı gözlem ızgarasını ve **fiilî oynatma hızını** kullanır.
Bu örnekte varsayılan çıktı 4,167 fps; daha yoğun önizleme 12,5 fps'dir.
Görüntü ile kutu aynı kaynak karesindedir, video süresi korunur.

TPS panoramasında yalnız homografinin tersini çizmek eğri saha çizgilerini
yanlış gösteriyordu. Artık doğrudan işaretlenmiş çevre ve orta çizgi gösterilir;
geçersiz düz ceza sahası çizimi yapılmaz. Bu düzeltme takip tahminlerini değiştirmez.

4096×1080 görüntüyü 1600 genişliğe indirirken eski yazıcı 421 piksel yükseklik
bekliyor, ölçekleyici 422 üretiyordu; bu durumda video kareleri yazılamıyordu.
Yazıcı ve ölçekleyici artık aynı, codec'e uygun çift boyutları kullanır.
Yazıcı açılamazsa açık hata döner.

117093 segment 3 **gerçek dedektör ve ByteTrack ile yeniden çalıştırıldı**.
375 gözlemin tamamı, 28 takip/2.441 kutuluk eleme ve bütün takım atamaları
dondurulmuş karşılaştırmayla birebir aynı çıktı. Kamera profili kendiliğinden
etkinleşti. [Üretim doğrulaması](measurements/perimeter-production-verification.json).
125 TrackingFrame çıktısı üretildi; anonim takım numaraları ve tahmini olay
niteliği korunur. Önizlemelerin bütün kareleri ayrıca çözülerek sayıldı:
[video doğrulaması](measurements/perimeter-preview-verification.json).
[Görüntü örneği](measurements/perimeter-preview.jpg).
Yerel H.264 video: `data/tracking/bench/perimeter_final_day/daylight-improved.mp4`.

## Kanıtlar ve tekrar üretim

- Geliştirme: [gündüz](measurements/perimeter-development-day.json),
  [gece](measurements/perimeter-development-night.json).
- Kontrol: [gündüz sonuç](measurements/perimeter-control-day.json),
  [gece sonuç](measurements/perimeter-control-night.json).
- Kontrol etiketleri: [gündüz](measurements/perimeter-control-day-labels.json),
  [gece](measurements/perimeter-control-night-labels.json).
- Kör kutu görüntüleri: [gündüz 0](measurements/perimeter-control-day-0.jpg),
  [3](measurements/perimeter-control-day-3.jpg), [6](measurements/perimeter-control-day-6.jpg),
  [gece 20](measurements/perimeter-control-night-20.jpg), [30](measurements/perimeter-control-night-30.jpg).
- [Yeni gece kaynak/hash kayıtları](measurements/perimeter-night-source.json).
  Görseller/kırpmalar: Atom Scott ve diğerleri, SoccerTrack v2 (2025),
  [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/),
  [resmî proje](https://atomscott.github.io/SoccerTrack-v2/).

Yerel kaynaklar mevcutken, yeni çıktı yollarıyla:

```powershell
.\venv\Scripts\python.exe -m scripts.soccertrack_v2.benchmark_person_filter --cache data/tracking/bench/daylight_117093/raw --labels docs/measurements/perimeter-control-day-labels.json --mapping-labels docs/measurements/daylight-117093-labels.json --decision docs/measurements/perimeter-decision.json --out data/tracking/bench/perimeter_day_repeat.json
.\venv\Scripts\python.exe -m scripts.soccertrack_v2.benchmark_person_filter --cache data/tracking/bench/perimeter_control_night/raw data/tracking/bench/signal_quality_v1 --labels docs/measurements/perimeter-control-night-labels.json --mapping-labels docs/measurements/kit-fixed-development-labels.json --decision docs/measurements/perimeter-decision.json --out data/tracking/bench/perimeter_night_repeat.json
```

Yeni ham deney önbelleğinde `--keep-off-pitch-tracks` gerekir; doğrulanmış
kalibrasyon profili yok sayılmalıdır. Büyük videolar/önbellekler yerelde korunur;
canlı maç veritabanına yazılmaz. Konum, top, pas, savunma olayı veya gerçek oyuncu
kimliği için yeni bir doğruluk iddiası yapılmadı.

89 ilgili test geçti. İzole SQLite ile tam yerel paket 2.608 geçti, 1 atlandı;
ardından eklenen kamera profili ve önizleme testleri ilgili pakette doğrulandı.
Ruff temiz, mypy 506 kaynak dosyasında temiz. Son birleşik PR head'inin tam CI
kontrolleri ayrıca takip edilir.
