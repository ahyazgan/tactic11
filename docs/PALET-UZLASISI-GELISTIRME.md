# RGB palet desteği: geliştirme adayı

19 Eylül 2026. Üretim varsayılanı değişmedi. Aday araştırma modülünde durur;
`--tracker consensus` hâlâ önceki deneysel sürümü kullanır.

Mevcut uzlaşı, geçmişe göre kalıcı gövde rengi değişimini ve bağımsız OSNet
motorundaki kimlik değişimini birlikte arıyordu. Beyaz 6 numaranın aydınlanması
iki koşulu da sağladı. Ek aday koşulu, mevcut üç önce/üç onay gözleminin medyan
RGB renginin **farklı mevcut takım merkezlerine** en yakın olmasını gerektirir.
Eksik renk, geçersiz/ayırt edilemeyen palet ve eşit mesafe destek sağlamaz.
Bu bir kadro veya aynı takım içindeki gerçek kişi tanıma yöntemi değildir.

## Tam eski veri kontrolü

- Önceki 11 geliştirme kesiti ve dört kapatılmış kontrol kesiti birlikte alındı.
- Önbellek karar tekrarında altı doğru ayrım korundu; beyaz 6 yanlış bölünmesi
  reddedildi. İlk 11 kesitte bütün örnekler ve kimlikler birebir aynı kaldı.
- Ardından 15 kesit gerçek kaynak RGB'si ve gerçek OSNet/CUDA ile ortak üretim
  akışından geçirildi. **112.852 kişi gözlemi** araştırma sonucuyla birebir
  eşleşti; altı ayrım kaldı. Kutular, güvenler, zamanlar ve takımlar korundu.
- Eski kontrol etiketleriyle yeniden puanlamada önceki consensus'a veya
  supervision'a göre gerileme yok. Bu seyrek etiketlerde beyaz 6 düzeltmesi
  ayrıca olumlu kişi çifti puanı üretmedi; kaynak sınır incelemesi ayrı kanıttır.

RF-DETR kişi tespitleri bu tekrarda önbellekten geldi. Kaynak RGB, OSNet,
iki takip motoru, renk çıkarımı, kimlik koşulu ve çıktı kurma gerçek çalıştı.
Top çıkarımı ve DB aktarımı bu deneyin parçası değildi. Süreler dosyada vardır,
ancak gerçek zaman/hız kıyaslaması olarak kullanılmaz.

İlk çalıştırma bazı eski önbelleklerde `video` alanı bulunmadığından kaynak
okumadan durdu. İkinci çalıştırma doğrulanmış kaynak dizinlerini açıkça seçti;
ilk günlük ve boş çıktı dizini korundu. Aday mantığı değiştirilmedi.
Araştırma modülüne alınırken yalnız tek satırlık koşul/atamalar açıldı;
Python AST eşitliği ve her iki kaynak hash'i kaydedildi.

- [Geliştirme kararları ve eski etiket puanları](measurements/identity-palette-development-results.json)
- [Gerçek üretim akışı eşitliği ve tam tekrar betiği](measurements/identity-palette-production-parity.json)
- [Önceki görünüş, hareket ve renk tanıları](KIMLIK-GORUNUS-TANISI.md)
- [Yeni kontrol planı](PALET-UZLASISI-KONTROL-PLANI.md)

Yeni bağımsız kontrol henüz tamamlanmadı. Geliştirmedeki bu sonuç, genellenmiş
kimlik doğruluğu veya varsayılan değiştirme onayı değildir. Kontrol öncesinde
kod/model/parametre/ortam ve plan sabitlenir; eski kontrol sonuçları değiştirilmez.

Doğrulama: tam uygulama koşusunda 2.986 başarılı / 60 atlanan test; son iki
dondurma koruması dahil 19 ilgili aday/kontrol testi başarılı. Ruff temiz,
mypy 556 kaynak dosyasında hatasız. Son iki koruma testi tam koşudan sonra
ayrıca çalıştırıldı; üretim kodu değişmedi.
