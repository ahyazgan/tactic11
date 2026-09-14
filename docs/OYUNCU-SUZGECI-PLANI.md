# Oyuncu tespitini sağlamlaştırma — 14 Eylül 2026

Başlangıç: PR 246, `66b5502`. Kapsam kamera/takip doğruluğu.

1. Geliştirme: 117093 segment 0/3/6'nın daha önce etiketlenmiş 4,96/20 sn
   kutuları ve 117092'nin mevcut gece etiketleri. Önceki kontroller artık
   geliştirme verisi. Kaynak, eski etiket ve önbellekler korunacak.
2. Saha dışı yazı/ekipman için kalibrasyonun doğrudan işaretlenmiş sınırından
   görüntü poligonu kur. Tam sınır bilinmiyorsa mevcut metre filtresini koru.
   Çizgi üzerindeki ayak noktaları küçük piksel toleransıyla korunur. Yalnız
   fiziksel olarak temellendirilen filtreler denenecek; hareketsiz oyuncuyu
   hareket etmediği için eleme, sabit 22 kişi seçme veya renge göre kutu silme yok.
3. `app/tracking/person_filter.py`, kalibrasyon/pipeline bağlantısı, ölçüm ve
   regresyon testleri: izlenmiş kutuyu renk birikiminden önce filtrele; sebepleri
   özete taşı. Yeni kutu dizisiyle aynı takip kimliklerini koruyarak karşılaştır.
   Filtre sonrası kısa takip kuralı üretimle aynı uygulanır.
4. Geliştirmede doğru atama ve gerçek forma kutusu kaybı artmamalı; saha dışı
   yanlış tespit/atama azalmalı. Kararı/parametreleri/hash'leri sabitle.
5. Karardan sonra yeni kontrol: gündüz mevcut üç klibin 10/25. saniyeleri
   (aynı klip/takiplerle ilişkili zamansal kontrol; bağımsız maç değil), ayrıca
   yereldeki 117092 tam ilk yarıdan 1200 ve 1500. saniyelerde başlayan 30 sn'lik
   yeni gece kliplerinin 5/20. saniyeleri. Kontrol görüntü/etiketleri karar
   dondurulmadan açılmaz; kontrol sonucuna göre ayar yapılmaz.
6. Gerçek kişi kaybını, kalan sahte tespitleri, doğru/yanlış/atanamayan formayı,
   takım başına fazla sayımı ve konum/top/olay sınırlarını birlikte raporla.
   Geçen değişikliği video/canlı hatta bağla; yeni önizleme üret. Anlamlı
   testler, Ruff, mypy ve son PR head'inin bütün CI kontrollerinden sonra birleştir.

Profesyonel kullanıma hazır olma iddiası yalnız bu küçük ölçümle yapılmaz.
Bu turdaki teslim: kanıtlı saha/oyuncu filtresi ve izlenebilir kalite çıktısı;
oyuncu kimliği veya pas doğruluğu ayrıca doğrulanmadan başarılı sayılmaz.

Geliştirmedeki geometri incelemesi: tek karede sınır dışını silmek, taç
çizgisinden dışarı çıkan oyuncuyu da silebilir. Bu yüzden karar takip düzeyinde:
aynı süreklilikte en az iki saha içi ayak gözlemi olan takip bütünüyle korunur.
Kümeleme öncesi bu kanıtı olmayan takipler çıkarılır; renk birikimi ve ByteTrack
kimlikleri değiştirilmez, elenen takipler uygun-kimlik filtresiyle palete katılmaz.
Tolerans max(1 px, görüntü yüksekliğinin %0,2'si); TPS'de dört köşe ve kenar
başına en az üç işaret gerekir. Eksik/hareketli sınırda mevcut davranış korunur.

Görsel denetim düzeltmesi: önizleme, takip/çıktı örnekleme ızgarasında çizilip
fiilî fps ile yazılır. TPS kameralarda yalnız homografinin tersini çizmek yerine
işaretlenmiş saha sınırı ve orta çizgi gösterilir. Bu değişiklikler dondurulan
filtre kararını veya ölçüm tahminlerini etkilemez.

Kontrol sonrası dağıtım kararı: gündüz zamansal kontrol geçti; yeni gece
kontrolünde başka renkli kişiye atama 3→4 arttığı için genel kabul başarısız.
Filtre/eşikler değiştirilmez. Yalnız 117093 kalibrasyon profilinde otomatik
etkinleştir; diğer kameralarda varsayılan kapalı, açık deneysel seçim mümkün.
Gece başarısızlığı ve bu sınırlama sonuç raporunda korunacak.
