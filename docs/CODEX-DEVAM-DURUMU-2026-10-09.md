# Manager: Codex ile devam, 9 Ekim 2026

GitHub ana dalı yeniden kontrol edildi: `fd0620b` / PR #279, 9 Ekim 2026;
ana dal CI başarılıydı. Yeni kör etiketler `e3d9618` ile tahminler açılmadan
mühürlendi; tamamlanan kontrol sonuçları aşağıda. PR #274–276 ile
birleşen Claude çalışmaları başlangıçta fast-forward ile alınmıştı.
Kullanıcının tercihiyle geliştirme Codex üzerinden sürüyor;
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

## Kimlik kontrolünün ilk edinim denemeleri

Bu bölüm önceki başarısız koşuları korur. Daha sonraki ölçümlü koşuda gece
edinimi tamamlandı; güncel devam noktası aşağıdaki bölümde bulunur.

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

İlk denemelerden sonraki iş gece edinimini tamamlamaktı. Bu adım aşağıdaki
ölçümlü koşuda geçti. Bütün kör etiketler daha sonra mühürlendi ve üç takip
kolu karşılaştırıldı; son sonuç bu belgenin sonunda bulunur.
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

PR #278 normal merge ile `dd49e6c` olarak birleşti; son PR başının ve ana dalın
CI/Vercel kontrolleri başarılı. CI'da 3.010 test geçti, 60 koşullu test atlandı.

## Gece edinimi ve ilk kör etiketleme aşaması

9 Ekim 13:56–13:59 UTC koşusu aynı dondurulmuş edinim betiğini,
`torch.set_grad_enabled(False)` ve `OPENCV_FFMPEG_THREADS=1` ile çalıştırdı.
Aday kodu, model, eşik, kalibrasyon veya kontrol aralıkları değiştirilmedi.
Başlangıçta kullanılabilir fiziksel bellek 3,65 GiB, kullanılabilir sistem
commit belleği 10,67 GiB idi. İşlem belleği on saniyede bir ölçüldü.

Gece 78 ve 84'ün her biri **375 örnekle** tamamlandı. Toplam koşu, doğrulama
ve model hazırlığı dahil **221,453 saniye** sürdü. On saniyelik ölçümlerde
en yüksek private bellek 5,235 GiB, en düşük kullanılabilir sistem commit
belleği 5,408 GiB oldu. Bu koşu sürekli büyüyen bir birikim göstermedi;
önceki bellek hatasının kesin kök nedeni tek başarılı koşudan çıkarılamaz.
Diskte yaklaşık 0,8 GiB boş alan kalması genel kaynak kısıtının sürdüğünü gösterir.

Gündüz ve gece salt okunur edinim kapısından geçti: **dört kesit, 1.500 örnek**.
Kaynak/model/kod hashleri aynı, başarısız eski edinim kanıtları korunuyor.
Gece için 91 kör inceleme görseli üretildi; iki kesitte toplam 75 başlangıç
kutusu var. Gündüzde 198 başlangıç kutusu bulunuyor.

Bellek için kullanılan yürütme biçimi, gündüz 64'ün önceki ham kaydıyla
kesitin tamamında karşılaştırıldı: **375 örnek ve 17.434 kişi gözleminde**
kutu, güven, RGB renk ve örnek zamanı birebir aynı; farklı örnek sayısı sıfır.
Kaynak ve ham kayıt hashleri değişmedi. Bu sonuç bir kesitte ham veri eşitliğini
gösterir; takip kimliği doğruluğu veya tam maç gerçek zaman kanıtı değildir.

Gündüz 64'ün her iki sabit karesi kaynak görüntülerden incelendi:
103 başlangıç ve 103 bitiş kutusu. 53 açık aynı-kişi bağı, 13 belirsiz ilişki,
6 görünür fakat ayrı bitiş kutusu olmayan kişi gözlemi ve 31 kişi olmayan
başlangıç kutusu kaydedildi. En yakın açık farklı kişi kuralıyla 53 negatif
bağ da yazıldı. Bunlar **kaynak etiketleri**, takip başarısı puanı değildir.
Kısmi bacak/gövde kutuları, örtüşen kişiler ve mükerrer kutular ayrı gerekçelerle
ele alındı. İnceleyici tek AI'dır; insan hakem doğrulaması yapılmadı.

Bu edinim aşamasında kalan gündüz 66'nın 95 ve gecenin 75 başlangıcı,
toplam **170 kutu**, sonraki kör incelemede tamamlandı. Önceki edinim ve
kısmi etiket kanıtları değiştirilmedi; birleşik etiketler ayrı mühürlendi.

Edinim bütünlüğü, kör seçim, dondurma korumaları ve palet adayı için mevcut
40 test geçti. İlk koşuda Windows sandbox geçici dizini oluşturulamadığından
sekiz test kurulamadı; çalışma alanındaki yeni, ayrı geçici dizinle tamamı geçti.

Kanıt: [edinim ve bellek ölçümü](measurements/identity-palette-acquisition-20261009.json),
[103 kutunun kaynak incelemesi](measurements/identity-palette-control-day64-source-review.json).

## Palet kontrolü tamamlandı; aday üretime alınmadı

273 başlangıç ve 282 bitiş kutusunun tamamı, 161 aynı ve 161 farklı kişi
ilişkisiyle birlikte tahminler açılmadan `e3d9618` commit'inde mühürlendi.
35 belirsiz, 10 görünür fakat ayrı bitiş kutusu olmayan ve 67 kişi olmayan
başlangıç ayrıca kaydedildi. İnceleyici tek AI; bağımsız insan hakem yok.

İki grubun edinim/hash kapıları ve on iki üretim tekrarı tamamlandı.
Supervision ByteTrack, önceki consensus ve palet adayı toplam 31.771 çıktı
kişi gözleminde kimlikler dahil birebir aynı. Yeni veya reddedilen önceki
sınır yok. Gerileme görülmediği gibi olumlu kontrol düzeltmesi de yok;
üretim varsayılanı ByteTrack olarak kalıyor.

Gündüz aynı-kişi doğrusu 72/108, gecede 49/53; toplam 13 yanlış bölünme
ilişkisi ve 27 kapsanmayan aynı-kişi ilişkisi var. Farklı-kişi doğrusu
gündüz 75/108, gecede 49/53; 1 yanlış birleşme, 36 kapsanmayan ilişki var.
Kısmi/mükerrer kutular bulunduğundan bunlar benzersiz oyuncu sayıları değildir.
Gece forma ölçümü 35 doğru, 8 yanlış, 14 atanamayan; 1 kişi olmayan kutu
takipte kaldı ve 2 kimlikte kaynak forma çelişkisi var.

Bu dört kesit artık tanı verisi. Sonraki geliştirme tam/kısmi kutu kopmaları,
örtüşmede kişi devri ve gece forma hatalarını ayıracak; yeni aday ayrı bir
kontrol açılmadan dondurulacak. Top/olay ve tam maç gerçek zaman hedefleri açık.
Tam sayımlar, süreler, hashler ve kalan hatalar:
[palet kontrol sonuçları](PALET-UZLASISI-KONTROL-SONUCLARI.md).
