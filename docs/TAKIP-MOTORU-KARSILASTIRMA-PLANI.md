# Açık kaynak takip motorları — 19 Eylül 2026

Amaç: mevcut Supervision ByteTrack ile Roboflow Trackers 2.6.0 içindeki
ByteTrack, BoT-SORT ve OC-SORT'u aynı ham tespitlerde karşılaştırmak. RF-DETR,
saha filtresi, minimum iz süresi ve forma sınıflandırması aynı kalır. Önceki
deneysel kimlik bölme/bağlama ve parça filtresi bu karşılaştırmada kapalıdır.

Dosyalar: `scripts/soccertrack_v2/benchmark_tracker_backends.py`, ilgili test,
bu plan, sonuç raporu ve yeni ölçüm JSON'u. Üretim takip seçimi değiştirilmez.
Araştırma bağımlılığı `trackers==2.6.0`; mevcut numpy/Supervision/CV paketleri
yükseltilmez. Kaynak: https://github.com/roboflow/trackers (Apache-2.0).

1. İlk olarak orijinal ByteTrack kişi kutularını ve renk geçmişlerini önceki
   kayıttan birebir tekrar üret. Alternatifler de yalnız girdi tespitlerine
   kimlik atayabilir; tahmini/yeni kutular ve doğrulanmamış -1 kimlikler kişi
   kanıtı olarak kullanılamaz. Her karede tekil kimlik ve kaynak indeksini denetle.
2. Ortak kayıp iz süresini mevcut gerçek kare sayısıyla eşleştir; iki defa FPS
   ölçekleme yapma. Ortak yüksek güven sınırı mevcut 0.25, yeni iz eşiği destekleyen
   motorlarda 0.35, doğrulama sayısı 1. Yönteme özgü eşleme varsayılanları ayrıca
   raporlanır. BoT-SORT CMC kapalı: sabit kamera, görünüş/ReID kullanılmıyor.
3. Bütün daha önce açılmış gündüz 0/3/6 ve gece 0/3/6/9/20/30/40/50 kesitleri
   bu yeni çalışmada geliştirme verisidir. Eski kontrol kayıtlarını değiştirme
   veya bağımsız yeni başarı kanıtı olarak sunma. Eski dondurma dosyaları korunur.
4. Etiketleri segment+kare+özgün kutuyla eşleştir. Kişi ilişkilerini her etiket
   kümesinde ayrı raporla; gündüz parça uçlarını tekil kişi skorundan çıkar.
   Forma doğrusu/yanlışı/atanamayan, kayıp kutu ve başka giysiye atama birlikte
   ölçülür. Her motor için güncelleme süresi ölçülür; dedektör/video çözme ve
   GPU dahil uçtan uca FPS iddiası yapılmaz.
5. Geliştirme kabulü: hiçbir kümede doğru kişi ilişkisi/kapsam veya doğru forma
   azalmasın; yanlış forma/başka giysi/kayıp kutu artmasın; önceden doğru kişi
   ilişkilerinde yeni hata olmasın. En az bir kişi ilişkisi iyileşsin. Geçmeyen
   motor otomatik etkinleştirilmez. Parametre taraması bu turda yapılmaz.
6. Bir aday geçerse kod/ayar özetini dondur; yeni gece kaynak aralıkları
   2400–2430 ve 2460–2490 saniyeyi ancak bundan sonra açıp etiketle ve doğrula.
   Gündüz yeni kaynak yoksa gündüz üretim kabulü iddia etme. Aday geliştirmede
   kalırsa kontrolü açma ve başarısız geliştirme sonucunu teslim et.
7. Deep OC-SORT için resmi deponun API/bağımlılık/yeniden tanıma ağırlıkları ve
   yerel ONNX/CUDA uyumunu incele. Çalıştırılmayan motoru ölçülmüş sayma.
   SoccerNet Game State'i futbol değerlendirmesi için referans olarak incele;
   bu turda bütün çerçeveyi ürüne taşımak kapsamda değildir.
8. Anlamlı adapter/ölçüm testleri, gerçek CV tekrarı, Ruff/mypy, gerekli uygulama
   kontrolleri, sonuç ve otomatik PR/son commit kontrolleri/birleştirme.
