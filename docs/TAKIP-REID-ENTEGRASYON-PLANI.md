# Görünüş destekli takip entegrasyonu

Kapsam: RF-DETR tespitlerini koruyarak resmî Deep OC-SORT + OSNet görünüş
eşleştirmesini video ve canlı segment hattına seçilebilir motor olarak bağlamak.
Önceki dört motor karşılaştırmasında tüm doğruluk kapılarını geçen alternatif
olmadığından doğrulanmış Supervision ByteTrack varsayılanı korunur. Bir aday
ancak geliştirme ve yeni kontrol kapılarını geçerse otomatik seçime alınabilir.

## Sabit deney

- Kaynak: GerardMaggiolino/Deep-OC-SORT, `6bb51d027b137233f5c520b6fcc4f2ae387a6ba9`.
- Model: kaynağın resmî ağırlık klasöründeki `osnet_ain_ms_d_c.pth.tar`.
  Model mimarisi aynı depodaki MIT lisanslı deep-person-reid OSNet-AIN x1.0.
- Kaynak kutular, güvenler, renkler ve saha filtreleri değişmez. Kamera hareket
  düzeltmesi kapalı; bütün gövde RGB 128×256, ImageNet normalizasyonu, FP32.
- Eşik .25, min_hits=1, mevcut motorla aynı etkin kayıp ömrü (bu veri için 7 kare),
  IoU .3, delta_t=3, inertia=.2, appearance weight=.75, alpha=.95,
  adaptive weight=.5. Resmî README ablation ayarı: grid_off ve new_kf_off açık.
  Görünüş açık/kapalı iki kol; görünüş kapalıyken upstream'in gerektirdiği gibi
  adaptive appearance weighting de kapatılır. Geliştirme sırasında parametre araması yapılmaz.
- Önceki 11 kesit geliştirme verisidir. Önceki JSON/etiketler ve sonuçlar değişmez.
  Aynı kişi/başka kişi çiftleri, forma, kapsam ve önceden doğru çift kayıpları
  önceki karşılaştırmadaki kapılarla değerlendirilir. Süreye ReID dahil edilir;
  dedektör dahil olmayan süre canlı FPS olarak sunulmaz.
- Önceden ayrılmış 2400–2430 ve 2460–2490 saniyeler, yalnız geliştirmeyi geçen
  adayın kodu/modeli/parametreleri dondurulduktan sonra kontrol için açılır.
  Kontrolde başarısız aday aynı kontrol verisine göre yeniden ayarlanmaz.

## Üretim sözleşmesi

Motor seçimi video/canlı CLI ve PipelineConfig içinde açıkça taşınır. Kaynak
kutular ve metadata korunur; tahmin edilen konumlar gerçek tespit gibi dışarı
çıkmaz. Boş kareler takip ömrünü ilerletir. Kesme/kalibrasyon boşluğu kimlik
ve görünüş geçmişini sıfırlar. Motor örneklerinin ID sayaçları birbirinden
bağımsızdır. Model dosyası SHA-256 ile doğrulanır, çalışma sırasında indirilmez;
hatalı model veya desteklenmeyen kamera seçimi sessizce başka motora düşmez.
Canlı çapa bağlamı motor/model değişimini ayırır. Deneysel motor açık seçimle
çalışır; doğruluk kapısı geçmeden "en iyi"/otomatik onaylı diye gösterilmez.

Orijinal dondurma ve önceki entegrasyon kanıtları korunur. Yeni varsayılan yolun
birebir tekrar kanıtı, sürümlü ek belge ve doğrulayıcıyla ilişkilendirilir.
Gerçek CV testleri, CLI/reset/metadata/boş kare regresyonları ve ilgili tam
kontroller tamamlandıktan sonra PR son head kontrolleriyle normal birleştirilir.
