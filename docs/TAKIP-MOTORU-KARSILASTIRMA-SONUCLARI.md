# Açık kaynak takip motorları — sonuç

19 Eylül 2026. **Bu ayarlarla hiçbir alternatif üretim kabulünü geçmedi.**
Mevcut Supervision ByteTrack korunuyor. Deneysel kimlik bölme/bağlama açılmadı.
Roboflow ByteTrack bazı ilişkilerde iyileşme ve daha düşük güncelleme süresi
gösterdi; başka ilişkiler ve forma atamasındaki gerilemeler geçişi engelledi.
Bu sonuç algoritmaların her veri kümesindeki başarısı hakkında hüküm değildir.

## Karşılaştırmanın kapsamı

[Plan](TAKIP-MOTORU-KARSILASTIRMA-PLANI.md) uyarınca 11 kesit, motor başına
4.125 kare ve toplam 44 tekrar çalıştırıldı. Gündüz 117093: 0/3/6; gece 117092:
0/3/6/9/20/30/40/50. Daha önce kontrol olarak adlandırılan görüntüler bu yeni
deneyde **geliştirme verisidir**. Yeni ayrılan 2400–2430 ve 2460–2490 saniye
kontrolleri, hiçbir aday geliştirme kapısını geçmediği için açılmadı.

Motorlar: Supervision 0.30.2 ByteTrack; [Roboflow Trackers 2.6.0](https://github.com/roboflow/trackers)
ByteTrack, BoT-SORT ve OC-SORT. Roboflow paketi Apache-2.0 lisanslıdır.
Bu uygulamalarda ReID kullanılmadı; BoT-SORT kamera hareketi düzeltmesi sabit
kamera deneyi için kapalıydı. Hareketli kamera sonucu çıkarılamaz.

RF-DETR tekrar çalıştırılmadı: önbellekteki **aynı ham tespitler** kullanıldı.
Saha, kısa iz ve çevre kişi filtreleri ile forma öğrenmesi mevcut üretim
yardımcılarından geldi. Önceki deneysel parça/kimlik iyileştirmesi kapalıdır.
Özgün ByteTrack'in kişi satırları ve renk geçmişleri 11 kesitte önceki kayıtla
birebir eşleşti. Alternatiflerde her kutu, güven skoru ve kaynak indeksi
korundu; hayalî kutulara izin verilmedi. Doğrulanmamış `-1` kimlikleri ortak
bir oyuncuya dönüştürülmedi. Her karede kimliklerin tekilliği kontrol edildi.

Ortak parametreler: yüksek güven sınırı 0,25; destekleyen motorlarda yeni iz
eşiği 0,35; bir gözlemle doğrulama. Gerçek kayıp iz ömrü **7 güncelleme**
(12,5 fps'te 0,56 saniye). Dış API'ye 30 fps ve 7 kare tampon verilmesi yalnız
tampon birimi dönüşümüdür: zaman damgası verilmez, hareket adımı bir kare kalır.
Motorlara özgü diğer varsayılanlar değişmedi ve raporda kayıtlıdır. Bu bir
parametre taraması veya her projeyi stok ayarlarıyla yarıştırma değildir.

Forma paletleri önceki geliştirme kaydının `before` merkezlerinden sabitlendi;
anonim mavi takım yuvası 0. Etiketler takip ID'siyle değil, kesit+kare+tam kaynak
kutusuyla eşleştirildi. İşaretlenmiş mükerrer vücut parçaları tekil kişi
skorlarından çıkarıldı. Her kişi etiket kümesi ayrı tutuldu; belirsiz ilişkiler
başarı puanına katılmadı. Kapsam alanı, ilgili etiket belgesinde tutulan gözlemleri
sayar; tam videonun gerçek kişi kapsamı değildir. IDF1/HOTA raporlanmadı.

## Gündüz sonuçları

Forma tablosu önceki geliştirme ve artık geliştirme sayılan zaman kontrolünün
toplam **315 tekil forma etiketini** içerir; önceki yalnız 216 etiketlik
geliştirme tablosuyla doğrudan karşılaştırılmaz. Kayıp kutu, atanamayanın alt
kümesidir ve bütün motorlarda 1'dir.

| Motor | Doğru | Yanlış | Atanamayan | Başka giysiye takım |
|---|---:|---:|---:|---:|
| Mevcut ByteTrack | 285 | 28 | 2 | 27 |
| Roboflow ByteTrack | 284 | 30 | 1 | 32 |
| BoT-SORT | 279 | 30 | 6 | 30 |
| OC-SORT | 281 | 33 | 1 | 32 |

| Motor | İlk kişi denetimi: aynı /22 | Ayrı bağlantı denetimi: aynı /5 | Eski zaman kontrolü: aynı /134 | Eski zaman kontrolü: farklı /134 |
|---|---:|---:|---:|---:|
| Mevcut ByteTrack | 15 | 2 | 92 | 84 |
| Roboflow ByteTrack | 15 | 3 | 96 | 85 |
| BoT-SORT | 13 | 3 | 92 | 83 |
| OC-SORT | 13 | 3 | 95 | 85 |

Toplam sayı tek başına yeterli değildir. Roboflow ByteTrack ilk denetimde
15 doğru ilişkiyi korumuş görünse de önceden doğru `0-280-d20→0-310-d18` ve
`6-0-d22→6-40-d24` ilişkilerini kaybetti; başka ilişkilerde kazanç bunları
sayısal olarak örttü. Kabul kontrolü her eski doğru ilişkiyi ayrı denetledi.
BoT-SORT eski zaman kontrolünde iki yeni yanlış kişi birleştirmesi üretti.

## Gece sonuçları

Hücreler **doğru / yanlış / atanamayan** forma sayısıdır. Bütün motorlarda
etiketli forma kutusu kaybı 0'dır.

| Motor | İlk gece kümesi, 123 etiket | Ek gece, 67 etiket | Eski gece kontrolü, 65 etiket |
|---|---:|---:|---:|
| Mevcut ByteTrack | 95 / 13 / 15 | 50 / 12 / 5 | 52 / 9 / 4 |
| Roboflow ByteTrack | 95 / 17 / 11 | 50 / 14 / 3 | 55 / 6 / 4 |
| BoT-SORT | 99 / 12 / 12 | 48 / 14 / 5 | 51 / 10 / 4 |
| OC-SORT | 98 / 20 / 5 | 53 / 11 / 3 | 49 / 10 / 6 |

Eski gece kontrolünde aynı kişi doğru bağlantısı mevcut motorda 59/63,
Roboflow ByteTrack'te 62/63, BoT-SORT ve OC-SORT'ta 60/63. Farklı kişi
ayırımı sırasıyla 61/63, 62/63, 61/63, 61/63. BoT-SORT ek gece kümesinde
başka giysiye takım atamasını 3'ten 5'e çıkardı. Bu iyileşme/gerilemeler
nedeniyle tüm kaynaklarda güvenli geçiş gösterilemedi.

## İşlem süresi ve tekrar doğrulaması

Motor başına 4.125 güncellemenin ortalama süresi: mevcut ByteTrack **1,961 ms**,
Roboflow ByteTrack **0,618 ms**, BoT-SORT **1,203 ms**, OC-SORT **1,063 ms**.
Ölçüm bu makinede tek süreçte `tracker.update` içindir; paket yükleme, kaynak
denetimi, video çözme, dedektör ve forma ataması dahil değildir. Tek koşunun
betimleyici ölçümüdür; uçtan uca canlı FPS veya genel hız garantisi değildir.

Girdi belleğini değiştiren motorlara karşı eklenen doğrulama sonrasında
karşılaştırma baştan tekrarlandı. **44 kişi çıktı dosyası ilk koşuyla bayt
düzeyinde eşleşti**; yalnız süre ve kod özetleri doğal olarak değişti.
[Tekrar kanıtı](measurements/tracker-backends-replay-verification.json),
[ayrıntılı sonuç](measurements/tracker-backends-development-results.json).
Son rapor girdilerin ve uygulama/paket kaynaklarının işlem öncesi/sonrası
SHA-256 değerlerini içerir. Büyük kaynaklar ve 44 çıktı yerel `.cache`/`data`
altındadır; ham ölçüm kaynakları değiştirilmedi.

## Deep OC-SORT ve futbol çerçevesi

[Deep OC-SORT](https://github.com/GerardMaggiolino/Deep-OC-SORT) resmi
`6bb51d027b137233f5c520b6fcc4f2ae387a6ba9` commit'inin README, kök MIT lisansı,
standart/entegre görünüş modülleri ve ana akışı incelendi. Yerel Torch
**2.11.0+cu128**, RTX 5060 Laptop GPU üzerinde CUDA tensör hesabını geçti.
ONNX Runtime da CUDA sağlayıcısını görüyor. Eski CUDA erişim sorunu bu güncel
ortamın durumu olarak kullanılmadı.

Ancak Deep OC-SORT için FastReID/torchreid ve doğrulanmış model ağırlıkları
henüz hazır değil. İncelenen görünüş kodu CUDA/FP16 kullanıyor, ONNX yolu
sunmuyor; veri kümesine göre ağırlık seçiyor. Önbellek eşleşmesinde yalnız
gözlem adedi kontrol edildiğinden, entegrasyonda kaynak/kutu/model/ön işlem
özetleriyle bağlanan yeni önbellek gerekir. Bu turda **ReID ağırlığı yüklenmedi,
Deep OC-SORT çıkarımı veya doğruluk ölçümü yapılmadı**. Kök lisans bilgisi model
ağırlıklarının veya bütün bağımlılıkların lisansını onayladığımız anlamına gelmez.
[Uyumluluk kaydı](measurements/tracker-backends-deepocsort-compatibility.json).

[SoccerNet Game State](https://github.com/SoccerNet/sn-gamestate), takım/forma
numarası/saha konumu ve GS-HOTA değerlendirmesi için futbol referansı olarak
incelendi. TrackLab üstüne kuruludur; kök lisansı GPL-3.0'dır. Çerçeve veya
kodları bu ürüne taşınmadı. Sonraki görünüş deneyi, aynı formalı oyuncular için
doğrulanmış bir model ve gerçek kaynak kutularına bağlı özelliklerle hazırlanmalı.

## Yeniden çalıştırma ve testler

Mevcut `venv-cv` bağımlılıkları yükseltilmeden `trackers==2.6.0` araştırma paketi
kuruldu. Tekrar için paket/Supervision sürümü ve manifestteki girdiler aynı
olmalıdır; kod farklıysa aynı deney adı altında sonuç üzerine yazılmaz.

```powershell
venv-cv\Scripts\python.exe -m scripts.soccertrack_v2.benchmark_tracker_backends `
  --out .cache/tracker_backends_reproduction
```

Yerel tam uygulama koşusu **2.882 geçti, 24 atlandı** (124,66 saniye).
Ardından eklenen girdi belleği koruması dahil gerçek CV ortamında **65 test
geçti**; bunun 15'i yeni motor/ölçüm testidir. Ruff temiz, mypy **533 dosyada
hatasız**. CI'a sabit sürümlerle dört gerçek motoru çalıştıran ayrı kontrol
eklendi; uygulama testindeki opsiyonel CV atlamaları bu kontrolü ikame etmez.
Bu turda üretim/frontend/veritabanı davranışı değiştirilmedi.

`3eb023b` commit'inin [CI koşusunda](https://github.com/ahyazgan/tactic11/actions/runs/35436144822)
uygulama **2.882 geçti, 25 atlandı**; ayrı gerçek motor işi **15 geçti, 0
atlandı**. Son eklenen CV testi uygulama ortamında da atlandığından yerel tam
koşunun 24 atlaması CI'da 25'tir. Sekiz PR kontrolünün tamamı geçti. Frontend
değişmediği için yol filtreli e2e işi bu PR'da tetiklenmedi; geçmiş e2e koşusu
bu commit'in testi gibi sunulmadı.
