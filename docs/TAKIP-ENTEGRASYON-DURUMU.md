# Takip entegrasyonlarının durumu

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
korudu. Bu geliştirme adayı henüz gerçek akış/yeni bağımsız kontrol geçmedi. Tam GTA
kıyaslaması veya HOTA/IDF1 başarısı olarak sunulmaz.
Ayrıntı: [görünüş, hareket ve kaynak tanısı](KIMLIK-GORUNUS-TANISI.md).

## Kalan işler, çalışma sırasıyla

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
