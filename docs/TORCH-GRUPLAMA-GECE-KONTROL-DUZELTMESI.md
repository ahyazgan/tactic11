# Gece kontrolü kaynak aralığı düzeltmesi

19 Eylül 2026. İlk karar `4f1ec8a`, aday `154968d`.
Gündüz 2100–2110 saniye kontrolü tamamlandı ve dört çıktı/olay tekrarı eşit.

İlk gece başlangıcı 2700 saniye olarak yanlış seçildi. Kaynak yalnız 67.375 kare,
25 fps, yani 2695 saniye uzunluğunda. Çıkarma 261 baytlık, sıfır kareli dosya
üretti; araç kare sayısı kontrolünde durdu. Gece dedektörü veya takipçisi
çalışmadı, gece kontrol pikseli açılmadı. Bu başarısız hazırlık başarı sayılmaz.
İlk karar ve boş dosya korunur; ilk protokol gece kısmında tamamlanmamıştır.

Geçerli ikame aralık **117092, 2580–2590 saniye** olarak şimdi, görüntüler
açılmadan seçilir. Aynı maçın yeni zamanıdır; bağımsız yeni maç değildir.
Kod/model/kalibrasyon/grup boyutu ve bütün eşitlik koşulları değiştirilmez.
İlk adayın tüm kod hashleri aynen korunur; bu belge, ek kontrol aracı, eski
karar ve boş dosyanın hashleri yeni karar dosyasına eklenir. İkame kontrol ayrı
bir klasöre yazılır. Eski dosyaların üzerine yazılmaz.

Bu düzeltme yanlış kaynak zamanını değiştirir; görülen tahmin sonucuna göre
algoritma veya eşik seçmez. İkame gece kontrolü de tamamlanmadan varsayılan
değişiklik kabul edilemez. Eski gündüz sonucu açıkça ilk karara, yeni gece
sonucu bu düzeltmeye bağlanacaktır.
