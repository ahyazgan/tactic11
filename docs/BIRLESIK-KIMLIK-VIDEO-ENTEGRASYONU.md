# Birleşik kimliğin video ve canlı segment entegrasyonu

10 Ekim 2026. `guarded`, sabit ve kalibre edilmiş kamera için açıkça seçilen
deneysel takip profilidir. Varsayılan `supervision` profili korunur. Önceki
19 kesitlik araştırma adayı artık `process_video` ve aynı fonksiyonu kullanan
sıcak/izole canlı işçi yollarına bağlanmıştır. Yeni bağımsız kontrol başarısı
ve gerçek zaman performansı bu entegrasyonun sonucu olarak kabul edilmez.

## Kaynak kanıtının sahipliği

Dedektör bir kez çalışır. Aynı tespitlerin ayrı kopyalarını üç takipçi alır:
özgün ByteTrack, kısa kopma onarımlı ByteTrack ve Deep OC-SORT/OSNet. Özgün
ByteTrack'in renk geçmişi, kısa takip ve saha sınırı filtreleri değişmez.
Takım renkleri yalnız bu başlangıç akışından öğrenilir; onarım veya kimlik
ayrımı sonrasında yeniden öğrenilmez.

Sabit önceki renk çapaları ile segmentte özgün akışın hesapladığı renk
merkezleri ayrı girdilerdir. Palet geçişi ilkini, eski görünüş uzlaşısı
ikincisini kullanır. Böylece önceki altı doğru ayrımı kaybettiren iki palet
kaynağının karışması önlenir. Her ayrım ayrıca bağımsız takip numarasının
istikrarlı biçimde değişmesini gerektirir.

Onarım akışı filtrelerden sonra tek bir eski kaynak kutusunu kaybetse bile
segmentin tamamında başlangıç akışı seçilir. Palet/görünüş ayrımı bu korunan
akış üzerinde çalışabilir. Ek kaynak gözlemlerine takım uydurulmaz; onların
takımı `None` kalır. Eski gözlemlerin kutu, güven ve takım kararı aynen taşınır.
Bir kimliğin gözlem bazındaki takımları farklıysa küresel takım etiketi
belirsizdir; kare ve önizleme yolları gözlem bazındaki kararı kullanır.

Kararlar segment tamamlandığında geçmiş gözlemlere uygulanır. Bu, kare gelir
gelmez kesin kimlik kararı verildiği anlamına gelmez. Kamera/zaman boşluğunda
üç takipçi sıfırlanır; onarım numaralarının önceki dönemdeki numaralarla
çakışması ayrıca önlenir. Segmentlerin kimlik alanı ortak çıktı katmanında
ayrıdır; aynı kişinin segmentler arasında tanındığı iddia edilmez.

## Kullanım

Mevcut video komutuna `--tracker guarded --refine-identities off` eklenir.
Kalibrasyon ve `--camera static` gereklidir. Önceden sabitlenmiş renk çapası,
mevcut `--team-anchor-json` argümanıyla verilebilir. Işık normalizasyonu ve
ikinci bir kimlik düzelticiyle birlikte kullanımı reddedilir.

Sabit renk çapası henüz yoksa ilk segment özgün akıştan bir başlangıç
ölçümü üretir. Özette `baseline_warmup_missing_fixed_palette` durumu yer
alır; onarım veya ayrım uygulanmaz. Canlı işçi ilk geçerli iki renk merkezini
kaydeder ve sonraki segmentlerde bunları sabit çapa olarak kullanır. Tek
renk/belirsiz atama geçerli çapa sayılmaz.

Sıcak ve izole canlı komutlarında aynı `--tracker guarded` seçeneği vardır.
Kaydedilmiş canlı durum, `bytetrack-osnet-guarded-identity-v2` profilini ve
doğrulanmış model hashini taşır; eski `consensus` durumuyla karıştırılmaz.

## Doğrulama kapsamı

- Üretim ve araştırma fonksiyonları aynı gerçek kaynak geçmişi testlerinden
  geçer: altı eski doğru ayrım, beyaz 6 koruması, gece 84 kopması ve kalabalık
  gece 3'te onarımın geri çekilmesi.
- Üç akışın aktarımı, kamera boşluğu, sabit çapa yokluğu, geçersiz çapa,
  ek kutunun belirsiz takımı ve bütün segmentin başlangıca dönmesi test edilir.
- Video/sıcak/izole seçenek aktarımı ve yeniden başlatma bağlamı üç deneysel
  takip profilinin her biriyle sınanır.
- Ayrımın ilk ve onaylandığı gözlem farklıdır. JSON → bellek SQLite → uygulama
  okumasında ayrılmış kimlikler, takımlar ve segment kapsamı korunur; tekrar
  aktarım yeni kopya üretmez.

Özgün varsayılan/refiner yolunun 22 eski çıktısında 164.772 gözlem birebir
korundu. Eski referansta bulunmayan iki takip ayarı ve kapalı
`roi_single_batch=False` alanı yalnız ayar metaverisi karşılaştırmasından
çıkarılır; kutu, renk geçmişi, kalibrasyon, top, atama ve istatistikler çıkarılmaz.
Özgün karar ve dört önceki entegrasyon kaydı değiştirilmeden beşinci kayıt
onlara SHA-256 ile bağlanır.

[Varsayılan çıktı eşitliği](measurements/joint-identity-guarded-integration-parity.json),
[entegrasyon kaydı](measurements/joint-identity-guarded-integration-amendment.json).

Gerçek RGB/OSNet üretim tekrarı **19/19 bilinen geliştirme kesitinde** hem
başlangıç hem birleşik araştırma çıktısıyla birebir eşleşti. Toplam 144.686
kişi gözleminde 144.623 eski kutu/güven/takım kararı korundu, 63 ek kaynak
tespiti kaldı. Sekiz kimlik ayrımı ve 18 hareket önerisinin 16'sının
uygulanması önceki araştırmayla aynı. Kod/model/girdi hashleri koşu sonunda
yeniden doğrulandı. Dedektör kişi kutuları bu eşitlik ölçümünde sabittir;
gerçek görüntü çözme, RGB çıkarımı ve OSNet hesaplaması yeniden çalışır.
Ölçüm komutu:

```powershell
.\venv-cv\Scripts\python.exe -m scripts.soccertrack_v2.replay_guarded_integration --expected .cache/guarded-identity-19-20261009-v2 --out .cache/guarded-production-new
```

Bu 19 kesitin 2.375 çıktı karesi ve 48.227 oyuncu kaydı ayrıca JSON → bellek
SQLite → uygulama okumasından geçti. Yinelenen aktarım kopya üretmedi;
kalıcı maç veritabanı açılmadı. Örnekleme sıklığı farklı olduğu için çıktı
oyuncu kaydı sayısı iç takip gözlemi sayısından düşüktür. Bu kişi kutusu
tekrarında top girdisi yoktur; top/olay doğruluğu bu ölçümle doğrulanmaz.

[19 kesit üretim eşitliği](measurements/identity-guarded-production-19.json),
[veritabanı doğrulaması](measurements/identity-guarded-production-db.json),
[veritabanı doğrulama komutu kaynak kopyası](measurements/identity-guarded-db-driver.txt).

150 ilgili CV testi, 60 uygulama/aktarım testi ve tam uygulama koşusunda
3.104 test geçti; 97 koşullu test atlandı. Ruff ve 569 kaynak dosyada mypy
başarılı. Windows sandbox'ta yerel TestClient soketi beklemeye girdiği için
iki eksik koşu korunmuş, tam koşu yerel soket erişimiyle tamamlanmıştır.

## Gerçek dedektör ve canlı işçi doğrulaması

Gündüz 3 ve tüketilmiş gece 84 kesitleri, her biri 30 saniye, gerçek
RF-DETR/Torch, top ROI ve OSNet ile iki kez çalıştı: kayıtlı `process_video`
ve gerçek `WarmTracker.run`. Dedektör önbelleği kullanılmadı; canlı tekrar
aynı yüklenmiş dedektörü kullandı, takipçiler her segmentte yeniden kuruldu.
Her kaynakta 125 karenin bütün oyuncu/top alanları, kimlik kararları ve
JSON'daki türetilmiş olaylar birebir aynı. İki yolun önizleme videoları da
bayt düzeyinde aynı; dört video baştan sona 125'er kareyle açıldı.

Dört gerçek çıktı ayrıca bellek SQLite'a aktarıldı: **500 kare, 10.618
oyuncu kaydı ve 16 olay kaydı**. Tekrar aktarım yeni kopya üretmedi. Olay
kayıtlarının sayısı/tekrar aktarımı doğrulandı; bu, gerçek pasların doğru
tanındığı anlamına gelmez. Kod/model/kaynak ve bütün çıktı hashleri sonunda
yeniden kontrol edildi. İlk kesilen koşu ve çıktı üretmeyen sandbox
başlatıcısı başarı sayılmadı; tamamlanmış kanıt `v3` koşusudur.

| 30 saniyelik kaynak | Kayıtlı yol | Sıcak canlı işçi |
|---|---:|---:|
| Gündüz 3 | 230,557 sn | 303,628 sn |
| Gece 84 | 343,967 sn | 359,142 sn |

Bu süreler RTX 5060 Laptop GPU kullanılan paylaşımlı Windows makinede
önizleme üretimini içerir; ilk dedektör kurulumunu içermez. Kontrollü hız
kıyaslaması değildir. Bu çalıştırma gerçek zaman hedefini karşılamaz;
önizlemesiz tam akış, model hazırlığı ve kaynak kullanımı ayrıca ölçülmelidir.

Görsel incelemede oyuncu kutuları, kimlik yazıları ve saha çizgileri üretildi.
Gece önizlemesinin 9,6. saniyesinde top işareti çizilen saha sınırının altında
görünüyor. Bu gözlem top seçimi/kalibrasyon tanısı olarak açık kalır; yeni
gece forma doğruluğu da bu aktarım testiyle kanıtlanmaz. Görsel inceleyici
tek AI'dır; bağımsız insan hakem veya tam kişi etiketi doğrulaması değildir.

[Gerçek video/canlı ölçümü](measurements/identity-guarded-real-live.json),
[gerçek çıktı DB kontrolü](measurements/identity-guarded-real-live-db.json),
[bütünlük ve görsel inceleme](measurements/identity-guarded-integration-audit.json),
[ortam sürümleri](measurements/identity-guarded-live-environment.json).
Yeniden üretim için [video/canlı komut kaynağı](measurements/identity-guarded-live-driver.txt)
ve [DB komut kaynağı](measurements/identity-guarded-live-db-driver.txt), depo
kökünden sırasıyla CV ve uygulama Python ortamlarıyla, yeni çıktı dizinleri
verilerek çalıştırılır. Kaynak kopyaları koşudaki betiklerle bayt düzeyinde aynıdır.

[Gündüz önizleme karesi](measurements/identity-guarded-day-preview.jpg),
[gece önizleme karesi](measurements/identity-guarded-night-preview.jpg).

Entegrasyon tamamlandı; yeni kontrol için dondurma ve kör kaynak etiketleri
henüz tamamlanmadı. [Sonraki kontrol planı](BIRLESIK-KIMLIK-KONTROL-PLANI.md)
görüntüler açılmadan hazırlandı. Genel forma, mükerrer kutu, kadro kimliği,
segmentler arası kişi sürekliliği, top/olay doğruluğu ve gerçek zaman
hedefleri açık kalır.
