# Takip entegrasyonlarının durumu

**10 Ekim güncellemesi:** birleşik kimlik adayı `--tracker guarded` seçeneğiyle
video ve canlı segment yollarına entegre edildi. 19 bilinen kesitte üretim/
araştırma eşitliği, 22 eski varsayılan çıktı, gerçek gündüz/gece RF-DETR
kayıtlı/canlı eşitliği ve bellek DB aktarımı geçti. 3.104 uygulama testi ve
150 ilgili CV testi başarılı. Varsayılan değişmedi; yeni kontrol dondurması
ve doğruluk değerlendirmesi açık. Gerçek 30 saniyelik koşular önizleme dahil
231–359 saniye sürdü; gerçek zaman hedefi geçilmedi. Gece önizlemesindeki
saha dışı görünen top işareti ayrıca tanı gerektiriyor.
[Ayrıntılar ve ölçümler](BIRLESIK-KIMLIK-VIDEO-ENTEGRASYONU.md),
[yeni kontrol planı](BIRLESIK-KIMLIK-KONTROL-PLANI.md).

**9 Ekim güncellemesi:** GitHub'daki son Claude değişiklikleri Codex dalına
alındı; yerel gerçek API erişimi ve giriş akışı onarıldı. Palet adayı kontrolü
tamamlandı: dört kesitte 273 başlangıç, 282 bitiş kutusu ve 322 ilişki kör
etiketlenip mühürlendi. On iki tekrarda üç yöntemin çıktıları birebir aynı;
olumlu kontrol düzeltmesi yok, üretime terfi yok. Sonuç ve kalan hatalar:
[palet kontrolü](PALET-UZLASISI-KONTROL-SONUCLARI.md). Ayrıntı ve devam noktası:
[Codex devam durumu](CODEX-DEVAM-DURUMU-2026-10-09.md).
Son kaynak incelemesinde iki ters bitiş etiketi bulundu; ilk kayıtlar korunarak
tahmin sonrası düzeltme eklendi. Bu düzeltme kör doğruluk kanıtı sayılmaz.
Üretim takip varsayılanı değişmedi.

19 Eylül 2026. Sistem gerçek görüntü üzerinde çalıştırıldı, kaynak kutularından
video çıktısına ve bellek veritabanı aktarımına kadar doğrulandı. **Çalışması,
oyuncu kimliği ve maç olaylarının yeterince doğru olduğu anlamına gelmiyor.**
Aşağıdaki ayrım üretim tercihlerini ve kalan işleri tek yerde tutar.

## Kullanılabilir olanlar

| Alan | Mevcut tercih / tamamlanan çalışma | Kanıt ve sınır |
|---|---|---|
| Ana dedektör | RF-DETR; gerçek örtüşen dilim sayısına göre Torch gruplaması | Yeni gündüz/gece kontrolünde son kare ve olaylar birebir; [sonuç](TORCH-GRUPLAMA-SONUCLARI.md) |
| Top ROI hızlandırması | Ayrı tek görüntü modeli açık seçimle, varsayılan kapalı | Gündüz iki top karesi değişti; gece hız kazanmadı; [sonuç](ROI-GRUPLAMA-SONUCLARI.md) |
| Takip motoru | Varsayılan supervision ByteTrack | Dört motor aynı tespitlerle ölçüldü; alternatifler bütün geliştirme koşullarını geçmedi; [karşılaştırma](TAKIP-MOTORU-KARSILASTIRMA-SONUCLARI.md) |
| Görünüş desteği | Deep OC-SORT + sabit OSNet ağırlıkları, deneysel seçim | Bazı kişi ilişkileri iyileşti, bazı eski doğru ilişkiler kayboldu; [sonuç](TAKIP-REID-SONUCLARI.md) |
| İki motorun uzlaşısı | Deneysel `--tracker consensus` | Eski kontrolün dört yeni ayrımından üçü doğru, biri aynı beyaz 6'yı böldü; [kontrol](KIMLIK-UZLASISI-KONTROL-SONUCLARI.md) |
| Forma / takım | Doğrulanmış kamera profili ve belirsiz atama davranışı | Aydınlık maçta ışık normalizasyonu başarısız oldu ve varsayılandan çıkarıldı; [gündüz](GUNDUZ-MACI-SONUCLARI.md), [belirsizlik](TAKIM-RENK-BELIRSIZLIGI-SONUCLARI.md) |
| Süreklilik | Kesit/yarı/kamera kimlik alanları ayrılmış | Kesitler arası aynı gerçek kişi olduğu iddia edilmez; [kimlik](SABIT-KAMERA-KIMLIK-SONUCLARI.md) |
| Top / kalibrasyon | Mevcut top seçimi, boyut ve süreklilik korumaları | ROI/çizgi alternatifleri doğruluk koşullarını geçmedi; [sonuç](TOP-SECIMI-SONUCLARI.md) |
| Pas / savunma | Türetilmiş ve kısmi kanıt olarak aktarım | Eksik top ve belirsiz takım korunur; gerçek olay duyarlılığı hedefi açık; [sonuç](VIDEO-OLAY-SONUCLARI.md) |
| Video / canlı entegrasyonu | Aynı açık seçenekler kayıtlı, sıcak ve izole işçiye taşınır | CLI aktarımı ve eski çıktı eşitliği testli; performans bütün kaynaklarda gerçek zaman değil |

## Bu aşamada ölçülen dış kaynaklar

GTA-Link'in sabit resmi kaynak sürümü ve spor OSNet ağırlıkları incelendi.
Yedi eski geçişte genel OSNet/spor OSNet, OpenCV/PIL önişlemesi, kısa parça
bağlama, kaynak hareketi ve nokta rengi karşılaştırıldı. Bu tanılardan sonra mevcut RGB takım paletine dayanan ek
koşul, 15 eski kesitte beyaz 6 yanlış bölünmesini reddedip altı doğru ayrımı
korudu. Adayın sonraki dört kontrol kesitindeki üretim tekrarları tamamlandı;
üç kol aynı çıktıları verdiği için olumlu kontrol düzeltmesi doğrulanmadı ve
aday üretime alınmadı. Bu kontrol aynı iki maçtan zamansal kesitler kullanır;
bağımsız maç, tam GTA kıyaslaması veya HOTA/IDF1 başarısı olarak sunulmaz.
Ayrıntı: [görünüş, hareket ve kaynak tanısı](KIMLIK-GORUNUS-TANISI.md).

## Kalan işler, çalışma sırasıyla

9 Ekim kısa kopma devamı: ilk 11 + son dört palet kesitinde iki aynı-kişi bağı
ve bir yanlış birleşme düzeldi. 114.602 eski gözlem ve forma kararları korundu;
42 yeni test geçti. 16 hareket önerisinin 14'ü sonuca alındı, üç ayrım yapıldı;
tek kutu kaybı görülen kesitte hareket onarımı geri çekildi. Bu çevrimdışı
araştırma adayı henüz canlı motor değildir. Önceki uzlaşı kontrolünün dört
kesiti ve altı eski doğru ayrım da doğrulanmalıdır.
[Kısa kopma ölçümü](KISA-KOPMA-GELISTIRME-SONUCLARI.md).

1. **Örtüşmede kimlik hatası:** karışık gövde kutusunda hangi görünüş/noktanın
   hangi kişiye ait olduğunu ayırmak; yetersiz kanıtta otomatik kişi kararı
   üretmemek. Beyaz 6 düzeltmesi diğer altı doğru ayrımı bozmamalı; bütün eski
   kesitlerde oyuncu/forma kapsamı ve kişi ilişkileri birlikte ölçülmeli.
2. **Yeni adayın bağımsız kontrolü:** geliştirmede seçilen kod/model/parametre
   ve kabul koşullarını önce sabitlemek, ardından daha önce açılmamış kaynakta
   değerlendirmek. Bu rapordaki tanı örnekleri artık geliştirme verisidir.
3. **Gerçek kişi / kadro ilişkisi:** yerel takip numarasından forma numarası veya
   kadro kimliği çıkarmamak; ayrı etiket ve eşleme kanıtı oluşturmak. Uzun kesit
   bağlantısı da aynı kişiyi gösteren kaynak kanıtıyla doğrulanmalı.
4. **Top ve olay doğruluğu:** temas anlarında doğru top gözlemini artırmak;
   gerçek olaylarla birebir zaman/konum/takım/sonuç eşlemesi yapmak. Daha çok
   pas adayı üretmek başarı ölçütü değil.
5. **Canlı işlem süresi:** kaliteli aday sabitken tam akış, model hazırlığı,
   GPU belleği ve gecikmeyi ayrı ölçmek. ROI olmayan/geçici ROI olan kesitler
   dahil; çıktı gerilemesiyle elde edilen hız varsayılan yapılmamalı.

Kod/API/aktarım sağlamlığı için testler geçti; doğruluk hedefleri için kaynak
etiketleri gerekir. Son ROI kodunda 2.969 uygulama testi başarılı, 60 atlandı;
71 ilgili CV ve 27 kanıt zinciri testi başarılı; 22 eski çıktı / 164.772 kişi
gözlemi birebir korundu. Bunlar gerçek oyuncu doğruluğu yüzdesi değildir.

Görev kapsamı kamera/takiptir. Diğer çalışma alanındaki karne/karar değişiklikleri
korunur; PDF, e-posta ve i18n bu kamera işinin tamamlanma koşulu değildir.
## 19 kesitlik birleşik aday güncellemesi — 9 Ekim 2026

Kısa kopma ve eski görünüş/palet ayrımı birlikte 19 tüketilmiş kesitte
doğrulandı: 144.623 eski gözlem/takım kararı korundu, 63 kaynak tespiti eklendi;
altı eski doğru ayrım ve beyaz 6 koruması geçti. 15 eski kesitte 112.852
gözlemin eski palet çıktılarıyla birebir eşitliği ayrıca doğrulandı.
58 ilgili test, Ruff ve mypy geçti. Bu araştırma bileşeninin video/canlı
entegrasyonu, dondurulması ve yeni bağımsız kontrolü henüz tamamlanmadı.
[Ayrıntı ve başarısız ilk ölçüm](BIRLESIK-KIMLIK-19-KESIT-SONUCLARI.md).
