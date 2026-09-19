# Sabit kamera kontrol etiketleme protokolü

Bu protokol 14 Eylül 2026 tarihinde görüntüler açılmadan hazırlanmıştır.
**Durum: üretim adayı dondurulmayı bekliyor.** Kod, parametre, kalibrasyon ve
özellik dosyalarının SHA256 değerleri ana görev tarafından kaydedilmeden kontrol
görüntüleri üretilmez, açılmaz veya etiketlenmez. Aşağıdaki seçim bundan önce
değiştirilecekse değişiklik yeni bir protokol sürümü olarak kaydedilir.

## Sabit seçim

- Gündüz: 117093 segmentleri 0, 3, 6; her klipte kare **374 ve 686**
  (14,96 ve 27,44 saniye). Kliplerin diğer kareleri geliştirmede görüldüğünden
  bu bölüm yalnız zamansal kontrol sayılır; bağımsız maç doğrulaması değildir.
- Gece: 117092 segmentleri **40 ve 50**, kaynakta 1800–1830 ve 2100–2130
  saniye. Aynı değerlendirme çizelgesi için bu kliplerde de kare **374 ve 686**
  kullanılır. Kaynak dosyaları ve SHA değerleri
  [kaynak manifestinde](measurements/joint-identity-control-source.json) bulunur.
- Forma ve kutu incelemesi, bu on karenin **saha filtresinden ve takipçiden önceki
  bütün person sınıfı tespitlerini** kapsar. Başarılı model çıktıları, yüksek
  güvenli kutular veya yalnız sahada kalan kimlikler seçilmez.
- Kişi sürekliliği için her başlangıç karesi `f`, `f+30` karesine bağlanır
  (1,20 saniye). Görsel bağlam `f-8` ile `f+38` arasında dört kare aralıkla ve
  ayrıca tam `f`/`f+30` kareleriyle gösterilir. Bu pencere, adayın hatasına göre
  genişletilmez veya başka bir pencereyle değiştirilmez.

## Kör inceleme

1. Dondurulmuş aynı dedektör çıktısı, video ve kalibrasyon kullanılır. Kaynak
   video/tespit SHA değerleri ve gerçek kare indeksleri manifestte tutulur.
2. İnceleme görüntüsü orijinal kaynak kareyi ve yerel bağlamı gösterir. Kutular
   yalnız `segment–kare–dedektör_sırası` ile numaralanır. Takip kimliği, takım
   tahmini, renk merkezi, bağlantı kararı, model adı veya hata işareti gösterilmez.
3. Her başlangıç kutusu `blue`, `white`, `other`, `not_person` veya `uncertain`
   olarak etiketlenir. `other` görünür diğer giysi rengidir; tek görüntüden hakem,
   kaleci veya kulüp rolü varsayılmaz. Bir kutu iki kişiyi belirgin biçimde
   kapsıyorsa tek bir forma tahmini zorlanmaz; `uncertain` kullanılır.
4. Gerçek kişi içeren her başlangıç kutusu için zaman şeridi izlenir. Aynı kişi
   bitiş karesindeki tek bir kaynak kutuyla açıkça eşleşiyorsa `same` bağı yazılır.
   Örtüşme, aynı formalı kişilerin ayırt edilememesi veya birleşik kutu nedeniyle
   bağ kurulamıyorsa `uncertain` yazılır; tahmin edilmiş takip kimliği yardımcı
   kanıt olarak kullanılamaz.
5. Açık bir `same` bağı olan başlangıç için bitiş karesinde farklı olduğu açık
   başka bir kişi varsa, kutu merkezleri arasındaki piksel mesafesine göre en
   yakın farklı kişi bir `different` bağı olarak kaydedilir. Eşitlikte soldaki,
   ardından yukarıdaki kutu seçilir. Böylece yalnız kolay uzak rakipler seçilmez.
6. Kişi bitiş karesinde görünür olduğu hâlde kaynak dedektörde ayrı kutusu yoksa
   bu durum `visible_person_without_source_box` olarak ayrıca sayılır. Birleşik
   kutuya sahte bir kişi etiketi eklenmez; dedektör kapsamı ile takipçi kaybı
   birbirine karıştırılmaz.
7. İkinci inceleyici mümkün olduğunda bütün `different` bağlarını ve bütün
   belirsiz kutuları, ayrıca sıralamadaki her beşinci `same` bağını kaynakla
   karşılaştırır. Görüş ayrılığı çözülmüyorsa `uncertain` korunur. İnceleyici ve
   görüş ayrılıkları açıkça kaydedilir; insan incelemesi yapılmadıysa iddia edilmez.
8. Bütün seçilmiş kutular ve ilişkiler tamamlanıp etiket JSON'u SHA256 ile
   dondurulduktan sonra başlangıç ve aday sonuçları açılır. Sonuç görüldükten
   sonra etiket düzeltmesi gerekirse özgün dosya korunur ve ayrı adjudication
   kaydı tutulur; bu düzeltme aynı adayın başarısız kontrolünü geçirmez.

## Birlikte raporlanacak ölçüler

- Forma: doğru, yanlış, atanamayan, model çıktısında eksik kaynak kutu;
  başka giysiye takım atanması ve kalan `not_person` kutuları.
- Kişi bağları: `same` korunması, `different` ayrılması, yanlış birleşme,
  yanlış parçalanma, belirsiz ilişki sayısı ve kaynak kutu kapsamı.
- Kaynakta kutusu bulunmayan görünür kişi sayısı ayrı verilir. Çıkıştan silinen
  veya birden fazla kimlikle aynı kutuya bağlanan etiketli gözlem başarı sayılmaz.
- Gündüz ve gece ayrı verilir; toplam skor bir kaynaktaki kaybı gizlemez. Orijinal
  etiketli ve adjudication uygulanmış geliştirme sonuçları ayrıca gösterilir.
- Bunlar seyrek görsel kişi bağlarıdır. Tam video IDF1, HOTA veya gerçek kadro
  oyuncusu doğruluğu olarak adlandırılmaz. Resmî GSR kutularının piksel/zaman
  hizası doğrulanmadan bu metrikler GSR'den üretilmez.

Kontrol başarısızsa aynı kareler üzerinde parametre aranıp aynı kontrol tekrar
başarı kanıtı olarak kullanılmaz. Bulgular geliştirme tanısına geçer; yeni bir
aday için yeniden bağımsız kontrol seçilir veya başarısızlık açıkça raporlanır.
