# Tek görüntülük top ROI kontrol planı

19 Eylül 2026. Kontrol görüntüleri açılmadan hazırlanmıştır. Geliştirme kaynakları
eski gündüz 117093/kesit 3 ve gece 117092/kesit 20'dir. Mevcut ana Torch gruplaması
PR #270'te doğrulanan gerçek dilim sayısı hesabıdır.

Aday, başarılı CUDA FP16 çoklu grup hazırlığından sonra ilk ROI çağrısında aynı
model sınıfı/ağırlık/çözünürlükle bağımsız bir model örneğini bir görüntülük
çıkarıma hazırlar. Ana model değiştirilmez. Hazırlık başarısızsa bir kez uyarı
verilir ve eski dolgulu çıkarım kullanılır; her karede tekrar hazırlanmaz.
CPU, ONNX, FP32, derlenememiş veya zaten tek görüntülük ana model korunur.

Geliştirme araştırmasında iki model birlikte yaklaşık 190 MB ek etkin GPU
belleği kullandı; sıcak tam akışta gündüz %11,2, gece %6,0 ek süre azalması
ölçüldü. Oyuncu/top kare JSON'u ve olaylar eşit kaldı. **Ham ROI tespitleri
birebir eşit değildir.** Çoğu fark güven puanındadır; bir top kutusunda
yaklaşık 0,003 piksel kenar farkı vardır. Sonuç eşitliği bu farkları gizlemek
için kullanılmayacak; aşağıdaki yoğun gözlem kapısı ayrıca uygulanacaktır.

## Sabit yeni aralıklar

| Grup | Kaynak | Başlangıç | Süre |
|---|---|---:|---:|
| Gündüz | 117093 birinci yarı | 2220 sn | 30 sn |
| Gece | 117092 birinci yarı | 2640 sn | 30 sn |

Kaynak kare sayısı/fps yalnız metadata üzerinden, aralıklar açılmadan kontrol
edilir. Özellikle gece kaynak 2695 saniyede bittiği için 2640–2670 aralığının
tamamı içeride olmalıdır. Bunlar mevcut maçların yeni zamanlarıdır; bağımsız
yeni maç değildir. İlk gruplama kontrolünün aralıkları yeniden kullanılmaz.

Kod, araçlar, testler, model, kalibrasyon, plan ve kaynak hashleri sabitlenip
Git'e kaydedildikten sonra her aralık kayıpsız yeni dosyaya çıkarılır. Gerçek
ana RF-DETR, gerçek ROI ve varsayılan supervision takibi iki kolda çalışır:
`roi_single_batch=False` mevcut dolgu; `True` aday. Her kol iki tekrar yapar.
Bu kontroller boyunca başka GPU işi veya tam uygulama testi çalıştırılmaz.

## Önceden seçilmiş kabul koşulları

- Dört çalışmanın son kare JSON'u ve üretilen olayları birebir eşit olmalı.
- Her kol kendi iki tekrarında bütün yoğun gözlem JSON'unu birebir üretmeli.
- Yoğun gözlemlerde kişi kutusu/güveni/kimliği/takımı, sıra/zaman/kamera
  sürekliliği, top varlığı ve top kaynağı birebir aynı olmalı.
- Her örnekte top merkezi farkı Öklid uzaklığıyla en fazla **0,25 piksel**,
  güven farkı en fazla **0,005** olabilir. Bunlar FP16 sayısal farkı için
  mühendislik sınırlarıdır; gerçek top konumu doğruluğu ölçümü değildir.
- Aday gerçekten ROI modeli hazırlamış ve her tekrarda en az bir ROI çağrısı
  yapmış olmalı; çalışmayan/hiç kullanılmayan optimizasyon başarı sayılamaz.
- Kaynak/kod/ortam bütünlüğü, tam kaynak süresi ve kayıt hashleri korunmalı.

Herhangi bir kapı başarısızsa aday varsayılan olarak kabul edilmez; aynı
kontrolde ayar değiştirilip başarı ilan edilmez. Hız ve başlangıç maliyeti ayrı
raporlanır. Boş olay listeleri doğrulanmış olay başarısı sayılmaz. Yeni insan
etiketi veya HOTA/IDF1 yoktur; bu kontrol önceki gözlem davranışının korunmasını
sınar. Geçse de gerçek zaman, forma/kadro kimliği veya genel olay doğruluğu
tamamlanmış sayılmaz.
