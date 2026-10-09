# Palet destekli uzlaşı: sabit kontrol sonucu

9 Ekim 2026. **Kontrol tamamlandı; üretime terfi yok.** Varsayılan supervision
ByteTrack, önceki deneysel consensus ve dondurulmuş palet adayı dört kesitte
aynı örnek çıktılarını ve aynı puanları verdi. Gerileme görülmedi; yeni bir
olumlu kimlik düzeltmesi de doğrulanmadı. Önceden yazılan kabul koşulu yalnız
değişmeyen çıktı ile geçilmiş sayılmaz. Üretim varsayılanı ByteTrack'tir.

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

## Üç yöntemin aynı çıkan puanları

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

Gündüzdeki 12 yanlış aynı-kişi ilişkisinin 6'sı kısmi gövde/bacak,
6'sı tek kişi kapsamındaki başlangıç kutusudur; ayrıca 1 yanlış farklı-kişi
birleşmesi vardır. Kısmi kutuların hataları doğrudan benzersiz oyuncu kimlik
değişimi sayısı olarak okunmamalı. Gecede ayrıca tek kişi kapsamındaki bir
başlangıç için yanlış bölünme var. Bütün yanlış ve kapsanmayan ilişkiler,
kutunun kapsamı ve kaynak gerekçesiyle [karar kaydında](measurements/identity-palette-control-decision-20261009.json) listelendi.

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
