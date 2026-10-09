# Palet destekli uzlaşı: sabit kontrol sonucu

9 Ekim 2026. **Kontrol tamamlandı; üretime terfi yok.** Varsayılan supervision
ByteTrack, önceki deneysel consensus ve dondurulmuş palet adayı dört kesitte
aynı örnek çıktılarını ve aynı puanları verdi. Gerileme görülmedi; yeni bir
olumlu kimlik düzeltmesi de doğrulanmadı. Önceden yazılan kabul koşulu yalnız
değişmeyen çıktı ile geçilmiş sayılmaz. Üretim varsayılanı ByteTrack'tir.

**Etiket düzeltmesi:** Son incelemede iki bitiş kutusu numarasının ters
yazıldığı bulundu. İlk mühürlü etiket ve puanlar aynen korunur; aşağıdaki
düzeltme tahminler açıldıktan sonra yapılmıştır ve yeni kör kontrol sayılmaz.

## Kaynak etiketleri ve bütünlük

117093 gündüz maçının 64/66, 117092 gece maçının 78/84 kesitleri kullanıldı.
Dört 30 saniyelik kesitte 1.500 ham örnek edinim kapısından geçti. Aday,
model, eşikler, kalibrasyon, kaynaklar ve özgün kontrol betikleri değişmedi.

Kaynak 374/686 karelerindeki **273 başlangıç** ve 404/716 karelerindeki
**282 bitiş kutusu**, takip kimliği veya takım tahmini gösterilmeden incelendi.
161 açık aynı-kişi ve önceden belirlenen en yakın açık farklı-kişi kuralıyla
161 negatif ilişki yazıldı. 35 belirsiz ilişki, 10 görünür fakat ayrı bitiş
kutusu olmayan kişi ve 67 kişi olmayan başlangıç açıkça kaydedildi.
İnceleyici tek AI'dır; insan hakem doğrulaması yapılmadı.

Etiketler `e3d9618` commit'inde tahminler açılmadan mühürlendi. Bütün kutular,
örnek zamanları, başlangıç/bitiş kapsamı, mükerrer kişileri dışlayan negatif
seçim kuralı ve mühür hashleri ayrıca denetlendi. [Etiket denetimi](measurements/identity-palette-control-label-audit-20261009.json).

## Üç yöntemin ilk mühürlü etiketlerle aynı çıkan puanları

Forma tablosu mavi/beyaz kaynak kutularını sayar; kısmi ve mükerrer kutular
bağımsız oyuncu sayısı değildir. Eksik kutular, atanamayan toplamına dahildir.
Diğer giysili kişinin takıma atanması ayrıca gösterilir.

| Grup | Doğru forma | Yanlış forma | Atanamayan | Çıktıda eksik kutu | Diğer giysiye takım ataması |
|---|---:|---:|---:|---:|---:|
| Gündüz | 77 | 1 | 12 | 9 | 11 |
| Gece | 35 | 8 | 14 | 2 | 3 |

| Kaynak ilişkisi | Toplam | Doğru | Yanlış bölünme/birleşme | En az bir ucu kapsam dışı |
|---|---:|---:|---:|---:|
| Gündüz, aynı kişi | 108 | 72 | 12 | 24 |
| Gündüz, farklı kişi | 108 | 75 | 1 | 32 |
| Gece, aynı kişi | 53 | 49 | 1 | 3 |
| Gece, farklı kişi | 53 | 49 | 0 | 4 |

Bu ilişki tablosu ilk mühürlü puanlamadır; gündüz aynı-kişi satırındaki iki
yanlış, aşağıda açıklanan etiket hatalarından gelir. Doğrulanmış takip hatası
sayısı olarak kullanılmamalıdır.

Her iki grupta da iki referansa göre gerileme listeleri boş. Gündüzde etiketli
kişi olmayan kutulardan takipte kalan ve çelişkili forma etiketi taşıyan kimlik
sayısı sıfır. Gece ise 1 kişi olmayan kutu takipte kaldı; 2 takip kimliğinde
çelişkili kaynak forma etiketleri var. Bu sayılar yalnız etiketli kutuları kapsar.

Her yöntem toplam **31,771 çıktı kişi gözlemi** üretti.
Üç kolun bütün örnek nesneleri, kimlikler dahil, birebir aynı. Kutu/güven,
zaman/süreklilik ve gözlem takımı eşitliği özgün tekrar betiğinden de geçti.

## Kimlik sınırları ve kalan hatalar

Önceki consensus ve palet adayı dört kesitin hiçbirinde ayrım üretmedi:
yeni sınır 0, adayın reddettiği önceki sınır 0, incelemesi bekleyen sınır 0.
Dolayısıyla genel başarı için gereken olumlu kontrol düzeltmesi yoktur.
Geliştirmedeki beyaz 6 düzeltmesi bu eksik kontrol kanıtının yerine geçmez.

İlk puanlamanın bütün yanlış ve kapsanmayan ilişkileri, kutunun kapsamı ve
kaynak gerekçesiyle [ilk karar kaydında](measurements/identity-palette-control-decision-20261009.json) listelendi.

## Tahminler açıldıktan sonraki etiket düzeltmesi

Yanlış çıkan 14 ilişkinin kaynak şeritleri yeniden okundu. `66-374-d13`
merkez daire yanındaki beyaz oyuncuyu `66-404-d16` kutusuna bağlamalı;
`66-374-d15` sağdaki öndeki beyaz koşucuyu `66-404-d18` kutusuna bağlamalı.
İlk etiketler bu iki bitiş indeksini ters yazmış. Bitiş `d34`, sağdaki `d18`
oyuncusunun bacak parçasıdır; bu fiziksel kişi grubu değişmedi. İki negatif
ilişki doğru kişi dışlama kuralıyla yeniden hesaplandı ve değişmedi.

Özgün görüntü şeritleri, bitiş kutu sayfaları ve tüm saha görünümü düzeltmeyi
destekliyor. İnceleme yine aynı AI tarafından, tahminler görüldükten sonra
yapıldı. İlk 14 yanlış ilişkiden ikisi etiket hatası; diğer 12 ilişkinin kaynak
eşlemesi tekrar desteklendi. Diğer doğru/kapsanmayan etiketler bu aşamada
bağımsız bir ikinci incelemeden geçmedi.

Düzeltme sonrası **tanı puanı**: gündüz aynı kişi 74 doğru / 10 yanlış / 24
kapsanmayan; diğer satırlar aynı. Toplam 322 ilişkide 247 doğru, 12 yanlış,
63 kapsanmayan bulunuyor. Üç yöntemin puanı yine aynı; aday kazanımı yok.
Gündüz kalan 10 yanlış aynı-kişi ilişkisinin 6'sı kısmi, 4'ü tek kişi kutusunda;
gecede 1 yanlış aynı-kişi ilişkisi ve gündüzde 1 yanlış farklı-kişi birleşmesi
var. Bunlar benzersiz oyuncu sayıları veya yeni kör kontrol başarısı değildir.
Özgün etiketler/raporlar değiştirilmedi: [ek düzeltme, kaynak hashleri ve yeniden puanlama](measurements/identity-palette-control-label-errata-20261009.json).

## Yürütme ve sonraki çalışma

Önceden ham veri eşitliği doğrulanan bellek ayarları kullanıldı:
`torch.set_grad_enabled(False)` ve `OPENCV_FFMPEG_THREADS=1`. Gündüzün altı
tekrarı doğrulama dahil 404.594 sn, gecenin altı tekrarı
364.453 sn sürdü. İşlem belleği on saniyede bir kaydedildi.
Bunlar önbellekteki kişi tespitleriyle tekrar süreleridir; RF-DETR maliyeti,
top/olay doğruluğu veya canlı gerçek zaman başarısı ölçülmedi.

Başlangıçta dolan disk için yalnız üç yeniden üretilebilir mypy önbelleği
temizlendi; yaklaşık 329 MiB alan açıldı. Kaynak videolar, modeller, ölçüm
kayıtları ve canlı maç veritabanı korundu.

Bu kontrol kapanmıştır. Bu kesitler bundan sonra hata tanılama verisidir;
üzerlerinde ayar değiştirip aynı puanları yeni kontrol başarısı olarak kullanmak
yasaktır. Sonraki geliştirme, tam kişi kutularında kopma, kısmi/mükerrer kutu
kimlikleri ve örtüşmede kişi devrini ayrı sorunlar olarak ele almalı; eski
geliştirme kesitlerinde gerilemeyi engellemeli ve yeni kararı başka bir kontrol
açılmadan dondurmalıdır. İnsan hakemli bağımsız maç doğrulaması, tam maç
HOTA/IDF1, kadro kimliği, top/pas doğruluğu ve gerçek zaman hedefleri açıktır.

Sayısal kayıtlar: [gündüz](measurements/identity-palette-control-day-results.json),
[gece](measurements/identity-palette-control-night-results.json),
[mühür, eşitlik, bellek ve bütün başarısız ilişkiler](measurements/identity-palette-control-decision-20261009.json).
