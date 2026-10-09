# Manager: Codex ile devam, 9 Ekim 2026

GitHub ana dalı kontrol edildi: son birleşme `3afc324` / PR #276,
19 Eylül 2026. PR #274–276 yerel `codex-work` dalına fast-forward ile alındı.
Açık PR yoktu. Kullanıcının tercihiyle geliştirme Codex üzerinden sürüyor;
eski Claude çalışma alanı korunuyor.

## Yerel uygulama

Önceki 3000/3001/8000 portlarında başka projeler çalışıyordu. Bu adreslerdeki
404 yanıtları Manager'ın kendi sunucusundan gelmiyordu. Yeni
[`launcher/CODEX.bat`](../launcher/CODEX.bat) ayrı 3100/8100 portlarını kullanır,
iki portun sahipliğini herhangi bir yeniden başlatmadan önce kontrol eder,
derlemeyi sınırlı işçiyle yapar ve mevcut veritabanını kullanır. Eski otomatik
açılış kaydı değiştirilmedi. Başlatıcı kullanımında gerçek API modu açıktır.

Gerçek API moduna dönünce ikinci sorun ortaya çıktı: video/kalibrasyon/iş
listeleri kimlik doğrulaması istiyordu, `/login` ise hâlâ demo yönlendirmesiydi.
Giriş formu yalnız gerçek veri modunda geri getirildi. Başarısız kimlik
doğrulaması artık boş video listesi gibi gösterilmez; panel giriş bağlantısı
sunar. Normal JWT girişi kullanılır, sunucu yetki kontrolleri değiştirilmedi.
Demo modunun eski yönlendirmesi korunur.

Doğrulamalar:

- Güncel arayüz derlemesi, tip ve lint kontrolleri tamamlandı.
- Önceki demo ekranlarının 11 tarayıcı testi geçti; 2 backend koşullu test
  o koşuda atlandı. Bunlar canlı maç doğruluğu ölçümü değildir.
- Gerçek veri modu için 5 tarayıcı regresyonu geçti: 401 görünürlüğü, yanlış
  parola, normal dönüş, harici dönüşün engellenmesi ve bozuk dönüş adresi.
  Bu testler ayrıca ayrı CI işinde çalışır; API yanıtları taklit edilir.
- Ayrı uçtan uca kontrolde mevcut yerel demo hesabıyla gerçek API'ye giriş
  yapıldı. Video, kalibrasyon ve iş listeleri; 990100 maçının kareleri,
  takipleri ve yerleşimi yüklendi. 12 takip isteğinde HTTP hatası, tarayıcıda
  JavaScript hatası görülmedi. Saha 150 karelik pencereyi gösterdi.
- Veritabanı salt okunur `quick_check`: `ok`. Veri sıfırlama/seed yapılmadı.
- Başlatıcı başka projenin 3000 portunu reddetti; süreç kapatmadı.

## Yarım kalan kimlik kontrolü

19 Eylül'de sabitlenmiş palet adayının kod/model/girdi/sürüm kontrolü geçti.
Model, karar eşikleri, kalibrasyon ve seçilmiş dört kesit değiştirilmedi.
Üretim varsayılanı hâlâ ByteTrack; palet adayı terfi ettirilmedi.

- Gündüz 64/66 ham kayıtları tamam: kesit başına 375, toplam 750 örnek.
  İkinci kesitin kör inceleme görselleri de üretildi. Toplam 198 başlangıç
  kutusu var. Kör kaynak incelemesi henüz tamamlanmadı; mühürlü etiket yok.
- Gece 78/84 kaynak videoları mevcut; tam ve geçerli ham kayıt henüz yok.
  Başarısız ilk edinim 78 için sıfır örnek yazdı, sonraki kesitte CUDA hatası
  verdi. Bu dosya `raw-failed-memory-20261009` altında korunuyor.
- Ayrı tanıda gerçek hata FP16 hazırlığı sırasında bellek tahsisiydi.
  Gradyan hesabı kapalı hazırlık aynı 15'li grupta geçti. Bu çalışma biçimi,
  önceden kayıtlı iki gündüz karesindeki 102 ham kutu/güven/renk gözlemini
  birebir korudu. Bu dar eşitlik kontrolü genel doğruluk kanıtı değildir.
- Aynı sabitlenmiş gece edinimi gradyan hesabı kapalı ve tek video çözücü
  iş parçacığıyla yeniden denendi. 250. örneğe / 20. saniyeye kadar ilerledi;
  sonra OpenCV 21.957.120 baytlık kare belleğini ayıramadı. Tamamlama manifesti
  oluşmadı. Bu yürütme değişiklikleri yeni başarı sonucu olarak sunulmaz.
- Tanı anında boş fiziksel bellek yaklaşık 1,5 GiB, C: alanı yaklaşık
  0,8 GiB'ye kadar düştü. Yalnız yeniden üretilebilir webpack önbelleği
  temizlendi; kaynaklar, ölçümler ve diğer projeler korunuyor.

[`validate_palette_acquisition`](../scripts/soccertrack_v2/validate_palette_acquisition.py)
ek bir salt okunur kapıdır. Eski donmuş edinim betiğine dokunmadan; tamamlanma
manifestini, kaynak çıkarım aralığını/hashlerini, ayarları, bütün örneklerin
sırasını, zamanını ve ham tespit kapsamını doğrular. Sıfır/kısa çıktı, hashleri
yenilenmiş olsa bile geçemez. 17 regresyon testi geçti; mevcut gündüz kayıtları
bu kapıdan geçti. Gece verisi eksik kaldığı için değerlendirmeye alınamaz.

Çalıştırma:

```powershell
.\venv\Scripts\python.exe -m scripts.soccertrack_v2.validate_palette_acquisition --group day
.\venv\Scripts\python.exe -m scripts.soccertrack_v2.validate_palette_acquisition --group night
```

Sonraki adım: gece edinimi için yeterli sistem belleği/disk alanıyla sabit
kontrolü tamamlamak; bütün kör etiketleri mühürlemek; üç takip kolunu
karşılaştırmak. Kaynak incelemesi tamamlanmadan aday puanlanmayacak.
Gerçek kişi/kadro eşlemesi, top/pas doğruluğu ve tam maç gerçek zaman hedefleri
açık kalıyor.

Makine kayıtları ve sınırlı eşitlik kanıtı:
[devam ölçümü](measurements/codex-resume-20261009.json).

## GitHub doğrulaması

[PR #277](https://github.com/ahyazgan/tactic11/pull/277) açıldı. İlk CI koşusunda
3.006 uygulama testi geçti, 60 koşullu test atlandı; demo ve gerçek giriş modu
tarayıcı işleri, iki veritabanı göç kontrolü, takip motorları ve Docker derlemesi
geçti. CI'ın kurduğu SQLAlchemy 2.1.4, yerel 2.0.50 ortamında görünmeyen sekiz
tip denetimi hatası ortaya çıkardı. Takip sorgularının sonuç satırı tipleri açıklandı,
beş özet sorgusunun satırları açık anahtar/değer açılımıyla sözlüğe dönüştürüldü.
Sorgu filtreleri ve sonuç davranışı korunur; bu uyumluluk düzeltmesi de PR'dadır.

İlk Vercel önizlemeleri başarısız oldu. Derleme günlüğünü okuyan CLI mevcut
oturumu geçersiz buldu, tarayıcı da giriş istedi. Ardından bağımsız bir
dağıtım uyumsuzluğu doğrulandı: proje `engines.node=20.x` istiyordu;
[Vercel'in 1 Ekim 2026 kapanışı](https://vercel.com/changelog/node-js-20-is-being-deprecated)
bu sürümle yeni dağıtımları engelliyor. Paket/lock dosyası ve iki tarayıcı CI
işi Node.js 24'e geçirildi; yerel derleme zaten 24.13.0 ile çalışıyordu.
Node 24 önizlemesi ve sekiz CI işi geçti. PR #277 normal merge ile
`476e5d0` olarak birleşti; ana dalın CI ve Vercel yayını da başarılı.

## Kalibrasyon listesinin zaman aşımı

Son gerçek ekran kontrolünde kalibrasyon listesi ayrı bir gecikme gösterdi.
500 noktalı TPS dosyasının leave-one-out hata hesabı her listede yeniden
yapılıyordu: doğrudan API 49,146 saniye sürerken Next proxy 30,06 saniyede
HTTP 500 / bağlantı kesilmesi verdi.

API özet hesabında BLAS iş parçacığı sayısı geçici olarak bire indirildi;
hesap sonunda eski limit geri yüklenir. Özetler dosyanın bütün JSON içeriğine
göre, en fazla 64 girdilik önbellekte tutulur. İçerik değişince yeniden
hesaplanır; yanıt kopyalanır ve ilk hesaplar kilitle sıraya alınır.
Kalibrasyon matematiği, kaynak dosyalar ve donmuş takip adayı değiştirilmedi.

Gerçek proxy ölçümü: ilk istek **6,734 sn**, tekrar istek **0,027 sn**;
ikisi de HTTP 200. Beş kalibrasyonun tüm yanıt alanları eski API ile birebir
aynı. Bunlar tek yerel ölçümlerdir; genel kapasite veya takip doğruluğu
iddiası değildir. 12 video/kalibrasyon API testi, Ruff ve mypy geçti.
Kaynak hashleri ve ölçüm: [kalibrasyon kaydı](measurements/calibration-api-cache-20261009.json).
