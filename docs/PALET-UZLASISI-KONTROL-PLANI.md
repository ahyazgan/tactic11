# RGB palet destekli kimlik uzlaşısı: yeni kontrol planı

19 Eylül 2026. Bu plan aşağıdaki yeni aralıkların görüntüleri açılmadan yazıldı.
Önceki beyaz 6 başarısızlığı artık geliştirme verisidir. Mevcut RGB takım
merkezlerine ek bir koşul getiren aday, ilk 15 eski kesitte incelendi.

Aday önceki ByteTrack + Deep OC-SORT/OSNet + kalıcı renk değişimi kararına,
mevcut üç önce/üç onay gözleminin medyan RGB renginin farklı mevcut takım
merkezlerine en yakın olması koşulunu ekler. Geçersiz/ayırt edilemeyen palet,
eksik renk veya eşit uzaklık destek sağlamaz. Mesafe eşiği, ağırlık, kalibrasyon
veya yeni takım paleti öğrenilmez. Ana kişi tespitleri ve gözlem takımları
korunur; aynı takım içindeki kişi değişimini çözdüğü iddia edilmez.

## Önceden ayrılan aralıklar

| Grup | Kaynak | Kesit | Başlangıç | Süre |
|---|---|---:|---:|---:|
| Gündüz | 117093 ilk yarı | 64 | 1920 sn | 30 sn |
| Gündüz | 117093 ilk yarı | 66 | 1980 sn | 30 sn |
| Gece | 117092 ilk yarı | 78 | 2340 sn | 30 sn |
| Gece | 117092 ilk yarı | 84 | 2520 sn | 30 sn |

Bunlar mevcut maçların yeni zamanlarıdır, yeni bağımsız maçlar değildir.
Kaynak başlığı/kare sayısı/fps kontrolü görüntü incelemesi sayılmaz; başlangıç
ve bitiş kaynak içinde olmalıdır. Aynı yeni aralıkta ayar değiştirilmez veya
başarısız sonuç gizlenerek başka kesit seçilmez.

## Çalışma sırası

1. Eski 15 kesitte gerçek RGB/OSNet üretim yolu ile araştırma kararları ve bütün
   gözlemler eşleştirilir. Testler geçtikten sonra aday kodu, araştırma araçları,
   testler, model, kaynak, kalibrasyon, ortam sürümleri ve bu plan hash'lenerek
   Git'e kaydedilir. Yeni görüntüler ancak bundan sonra açılır.
2. Gerçek RF-DETR ve mevcut ana Torch gruplamasıyla aynı tespit önbelleği alınır.
   Tek görüntülük ROI deneysel seçeneği kapalıdır. Kaynaklar ve eski kanıtlar
   değiştirilmez; yeni dizinlere yazılır.
3. Eski kör etiketleme protokolü aynen kullanılır: kaynak 374 ve 686. karelerde
   bütün tespitler, 30 kare sonraki uçlar ve sabit ara bağlam görüntüleri.
   Takip kimliği/takım tahmini göstermeden forma, kişi/kutu kapsamı ve aynı/farklı
   kişi ilişkileri değerlendirilir; belirsiz gözleme kesin etiket verilmez.
   Etiketler tahmin tekrarından önce hash ile mühürlenir.
4. Üç kol aynı girdilerde çalışır: varsayılan supervision, önceki deneysel
   consensus ve palet adayı. Kamera/ayar/etiket/kod bütünlüğü denetlenir.
5. Aday ve önceki consensus'un bütün ayrımları kaynak görüntüde incelenir.
   Adayın reddettiği önceki ayrımlar da dahil edilir; yalnız olumlu örnekler
   seçilmez. Kaynak incelemesi tek AI değerlendiricisidir, insan hakem değildir.

## Kabul koşulları

- Her kaynak grubunda hem supervision'a hem önceki consensus'a göre forma,
  kişi ilişkisi, önceden doğru uç ilişkisi, kapsam, çelişkili forma taşıyan
  kimlik ve kişi olmayan takip ölçülerinde gerileme olmamalı.
- Kaynak kutuları, güvenler, zaman/süreklilik ve gözlem takımları birebir
  korunmalı. Hiçbir tespit eklenmemeli veya çıkarılmamalı.
- Bütün yeni/kaldırılan ayrımlar incelenmeli. Yanlış bir yeni ayrım veya doğru
  bir önceki ayrımın kaldırılması kabul edilmez. Belirsiz değişiklik olumlu
  doğrulama sayılmaz; bağımsız olumlu düzeltme olmadan genel başarı ilan edilmez.
- Test veya donmuş kanıt kontrolü başarısızken üretime terfi yapılmaz.
  Geliştirmedeki beyaz 6 düzeltmesi yeni kontrol başarısı yerine kullanılamaz.

Bu çalışma tam maç HOTA/IDF1, kadro/forma numarası doğruluğu, pas doğruluğu veya
canlı gerçek zaman onayı sağlamaz. Kontrol sonucuna göre deneysel adayın
entegrasyonuna karar verilir; varsayılan ByteTrack otomatik değiştirilmez.
