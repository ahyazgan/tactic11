# Kimlik uzlaşısı: yeni kontrol protokolü

19 Eylül 2026. Bu plan yeni kontrol görüntüleri çözümlenmeden yazıldı.
Geliştirmeyi geçen aday, orijinal ByteTrack gözlemleri + orijinal Deep OC-SORT/
OSNet desteği + kalıcı renk değişimi uzlaşısıdır. Geometrik eşleştirme deneyleri
adayın parçası değildir. Önce üretim eşitliği ve testler, sonra kod/model/
parametre hash'leri ile dondurma tamamlanacak.

## Önceden belirlenen görüntüler

| Kaynak | Kesit | Kaynak başlangıç | Süre |
|---|---:|---:|---:|
| 117092 birinci yarı, gece | 80 | 2400 sn | 30 sn |
| 117092 birinci yarı, gece | 82 | 2460 sn | 30 sn |
| 117093 birinci yarı, gündüz | 60 | 1800 sn | 30 sn |
| 117093 birinci yarı, gündüz | 62 | 1860 sn | 30 sn |

Gece aralıkları önceki deneylerde ayrılmış ve açılmamıştır. Gündüzde yalnız
600, 690, 780. saniyelerdeki eski klipler görüldü; yeni iki aralık bu planla
ayrılıyor. Gündüz kaynağı resmî dağıtımdan ediniliyor. Dosya aktarma ve başlık/
süre kontrolü, görüntü veya takip sonucu inceleme değildir. Kaynağa erişilemezse
başka zaman seçilmeyecek; kapsam eksikliği raporlanacak.

Kalibrasyon ve dedektör ayarları ilgili kaynağın mevcut geliştirme önbelleğinden
alınır ve dondurma belgesinde hash'lenir. Kontrolde kalibrasyon, palet veya
eşik öğrenilmez. Mevcut geliştirme takım çapaları kullanılır.

## Etiketleme ve değerlendirme sırası

1. Dondurma belgesi, üretim/deney kodu, model, kalibrasyon ve değerlendirme
   araçlarının hash'lerini ve bu planı içerir. Her çalışma önce bunları doğrular.
2. Dört kaynak kesit yeni klasörlere çıkarılır. Kaynak video ve eski ölçümlerin
   üzerine yazılmaz. Aynı RF-DETR tespitleri iki kola da verilir.
3. `prepare_identity_control` protokolü kullanılır: kaynak 374 ve 686.
   karelerde tüm kişi kutuları; her başlangıçtan 30 kare sonraki uçlar ve
   aradaki sabit görüntü bağlamı. Takip ID'si veya takım tahmini gösterilmez.
4. Forma (mavi/beyaz/başka/belirsiz/kişi değil), kutu kapsamı ve aynı/farklı
   kişi ilişkileri kaynak görüntüden etiketlenir. Gerçek ikinci kişi ile
   parçalı/karışık kutu ayrımı belirsizse kesin kişi etiketi üretilmez.
   Tek otomatik değerlendirici kullanıldığı, insan hakem doğrulaması olmadığı
   ve seyrek kişi çiftlerinin tam maç doğruluğu olmadığı açıkça belirtilir.
5. Etiket dosyaları sabitlendikten sonra iki kolun skorları açılır. Önceki
   `regressions` kuralları her kaynak grubunda ayrı uygulanır: forma doğru/
   yanlış/atanamayan, kutu kaybı, başka giysiye atama, kişi bağlantısı ve
   önceden doğru bağlantı kaybı. Çelişkili forma taşıyan kimlik artışı da ret nedenidir.
6. Adayın kontrol boyunca ürettiği bütün yeni kimlik ayrımları ayrıca kaynak
   görüntüde incelenir. Yalnız sorunlu örneklerin seçilip gösterilmesi veya
   hiç değişmeyen bir kontrolün doğruluk kazanımı sayılması önlenir.

## Kabul sınırı

Herhangi bir doğruluk/kapsam gerilemesinde aday varsayılan yapılmaz. Bağımsız
kontrolde doğrulanmış olumlu ayrım yoksa, eski sonuçları korumak tek başına
genel doğruluk artışı değildir; otomatik açılma için yeterli sayılmaz.
Gündüz erişimi veya etiket kapsamı eksikse genel gündüz onayı verilmez.

Başarısız kontrol bu aday için kapanır. Aynı kontrol üzerinde eşik taraması,
kişi etiketini tahmine uydurma veya palet düzeltmesi yapılmaz. Sonraki aday
bu verileri geliştirme olarak kullanabilir, fakat yeni bağımsız kontrol gerekir.
