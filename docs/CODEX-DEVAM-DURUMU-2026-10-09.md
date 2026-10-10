# Manager: Codex ile devam, 9 Ekim 2026

**Güncel adım — 10 Ekim kontrol dondurması:** PR #283 / `8f4e66a` sonrasında
birleşik adayın yeni kontrol araçları ve kararı hazırlandı. 103 kod, 19
girdi/kanıt ve ortam sürümleri sabit; 67 test başarılı. Yeni görüntüler
henüz açılmadı. Sonraki iş gündüz 68/72, gece 74/76 ham edinimi; bütün kör
etiketler ve mühürler kaydedildikten sonra üç kolun karşılaştırılmasıdır.
[Dondurma kaydı ve kabul sınırları](BIRLESIK-KIMLIK-KONTROL-DONDURMA.md).

**10 Ekim devam noktası:** GitHub `main`, PR #282 / `8dff2c5` ile günceldi;
CI başarılı, açık PR yoktu. Geliştirme yalnız Codex'te devam ediyor.
Birleşik aday artık deneysel `--tracker guarded` ile gerçek video ve canlı
segmentte çalışıyor. 19/19 üretim tekrarı, 22 eski çıktı, gündüz/gece gerçek
dedektörle kayıtlı/canlı eşitliği ve bellek DB doğrulaması tamamlandı.
3.104 uygulama testi, 150 ilgili CV testi, Ruff ve mypy geçti. Yeni kontrol
öncesi dondurma, kör etiket ve değerlendirme sıradaki iştir. Gerçek zaman,
genel forma ve top/olay doğruluğu tamamlanmadı.
[Son entegrasyon kaydı](BIRLESIK-KIMLIK-VIDEO-ENTEGRASYONU.md),
[görüntü açılmadan hazırlanan kontrol planı](BIRLESIK-KIMLIK-KONTROL-PLANI.md).

Son çalışma başlangıcında GitHub ana dalı yeniden kontrol edildi:
`eece9cd` / PR #280, 9 Ekim 2026; ana dal CI başarılıydı, açık PR yoktu.
Yeni kör etiketler `e3d9618` ile tahminler açılmadan
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

İlk mühürlü puanlamada gündüz aynı-kişi doğrusu 72/108 çıktı. Kaynak tekrar
incelemesi iki ters bitiş indeksi ortaya çıkardı; etiket hataları ayrı kaydedildi,
özgün mühür ve rapor değiştirilmedi. Tahmin sonrası tanı puanı gündüz 74/108,
gecede 49/53; toplam 11 yanlış ve 27 kapsanmayan aynı-kişi ilişkisi var.
Bu düzeltme yeni kör kontrol veya bağımsız hakem doğrulaması değildir. Farklı-kişi doğrusu
gündüz 75/108, gecede 49/53; 1 yanlış birleşme, 36 kapsanmayan ilişki var.
Kısmi/mükerrer kutular bulunduğundan bunlar benzersiz oyuncu sayıları değildir.
Gece forma ölçümü 35 doğru, 8 yanlış, 14 atanamayan; 1 kişi olmayan kutu
takipte kaldı ve 2 kimlikte kaynak forma çelişkisi var.

Bu dört kesit artık tanı verisi. Sonraki geliştirme tam/kısmi kutu kopmaları,
örtüşmede kişi devri ve gece forma hatalarını ayıracak; yeni aday ayrı bir
kontrol açılmadan dondurulacak. Top/olay ve tam maç gerçek zaman hedefleri açık.
Tam sayımlar, süreler, hashler ve kalan hatalar:
[palet kontrol sonuçları](PALET-UZLASISI-KONTROL-SONUCLARI.md).

## Kısa kopma araştırmasının devam noktası

İlk 11 geliştirme ve son dört palet kesiti yeniden değerlendirildi. Kısa
kaybolmada gözlenen hareketi kullanan aday, rakip yakınlığı ve gerçek eşleştirme
maliyetinin tekilliğiyle sınırlandı. Palet/bağımsız takip birlikte değişince
kimlik ayrılır; başlangıçtaki forma kararları kaynak kutularından taşınır.
Bir eski kutu kaybolursa o kesitte hareket onarımından vazgeçilir.

15 kesitte iki aynı-kişi bağlantısı ve bir yanlış birleşme düzeldi;
114.602 başlangıç gözlemi eksilmedi, forma kararları değişmedi. 16 önerinin
14'ü kullanıldı, üç kimlik ayrımı yapıldı. Seyrek etiketlerdeki doğrular korundu.
42 yeni regresyon testi geçti. Tek iş parçacığı isteyen ortam değişkeninin
fiilen 16 çözücü iş parçacığı açtığı görüldü; araştırma çözücüsü artık doğrudan
1 iş parçacığıyla açılıp doğrulanıyor. Önceki bellek hatası kaydı korunuyor.

Bu aday henüz canlı API/işçi seçeneği veya üretim varsayılanı değildir.
Sonraki iş önceki uzlaşı kontrolünün 60/62 ve 80/82 kesitlerini de kapsamak,
beyaz 6'nın yanlış bölünmesini reddederken altı eski doğru ayrımı korumak;
ardından aynı iki-akış kanıtını canlı akışa bağlayıp yeni kontrol öncesi
sabitlemektir. Yeni kör kontrol henüz açılmadı.
[Ayrıntı ve makine kanıtı](KISA-KOPMA-GELISTIRME-SONUCLARI.md).

## Birleşik aday 19 bilinen kesitte doğrulandı

Önceki dört uzlaşı kesiti eklendi. Kısa kopma adayı tek başına eski altı
doğru ayrımın yalnız birini koruyordu; eski görünüş/palet koşuluyla birleşimi
altısını da korudu, beyaz 6'yı yanlış bölmedi. İlk birleşik koşudaki iki kayıp
ayrım, kesitte hesaplanan başlangıç merkezleri yerine sabit renk çapalarının
verilmesinden kaynaklandı. Bu iki veri artık ayrı zorunlu girdiler; ilk
başarısız sonuç ve kaynakları korunuyor.

19 kesitte 144.623 eski gözlem ve forma kararı eksiksiz korundu, 63 ek kaynak
tespiti çıktıya girdi. 18 hareket önerisinin 16'sı kullanıldı; sekiz kimlik
ayrımı var. Bütün seyrek gerileme ve yedi eski sınır koşulu geçti. Eski palet
yolunun 15 kesit / 112.852 gözlemi kimlikler dahil birebir yeniden üretildi.
58 ilgili test, Ruff ve mypy geçti. Canlı motor varsayılanı değişmedi.

Devam noktası artık 19 kesit seçimi değil, bu kanıt akışının gerçek video ve
canlı segment yollarına eşit biçimde bağlanmasıdır. Başlangıç kutu/forma
kararları korunmalı; gecikmeli ayrım ve kapsam geri dönüşü çıktı/DB yolunda
doğrulanmalı. Sonra yeni kontrol öncesi dondurma yapılacak.
[Sonuçlar ve yeniden çalıştırma](BIRLESIK-KIMLIK-19-KESIT-SONUCLARI.md).
