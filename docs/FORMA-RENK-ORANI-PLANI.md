# Forma renk oranı denemesi — 14 Eylül 2026

Başlangıç `1e8e9f2`. Önceki parlak dörtte birlik denemesinden farklı olarak
RGB kanal oranlarıyla gölgede renk koruması sınanır. PR akışı otomatik tamamlanır.

1. Önceki 0/3/6/9 segmentlerinin 142 etiketi artık geliştirme verisidir.
   Yeni kontrol: daha önce renk etiketlemesinde kullanılmamış 2/8 segmentleri;
   aynı ayarlarla ham gözlem önbelleği oluşturulur, 5/20 sn tüm kişi kutuları
   karar sabitlendikten sonra tahminler gösterilmeden etiketlenir.
2. Mevcut üretim atamasını taban al. RGB oranlarının en yakın takım merkezi
   ile uyuşmasını, gerektiğinde takip boyunca renk oylamasını geliştirmede
   karşılaştır. Parlaklık oranıyla farklı formaları ayırmanın sınırlarını
   koru; hakem/kaleci veya belirsiz kişi sayısını başarıdan çıkarma.
3. Üretime alınma şartı: aynı etiketli gözlemlerde doğru oyuncu ataması artsın,
   yanlışlar ve başka renkli kişilere takım ataması artmasın. Seçilen kural ve
   parametreler kontrol görüntüleri açılmadan dosyaya yazılır. Kontrolden
   sonra eşik değiştirilmez. Veri tek maç/tek değerlendirici olduğundan
   maçlar arası genelleme iddiası yoktur.
4. Geçen yöntem üretime bağlanır; sentetik renk/ışık/sınır ve canlı çapa
   regresyonları, aynı ham gözlemlerde tekrar ölçüm, gerekli tam test/lint/tip
   kontrolü, PR, son commit CI ve birleştirme. Geçmeyen deney varsayılan olmaz.

Geliştirme kararı: salt renk oranı ve renk oylaması gölgeli örneği güvenli
biçimde çözmedi. Önceki parlak yaklaşım yalnız her iki hesap da bir takım
verdiğinde kullanılırsa doğru/yanlış 102/17 → 106/13 oldu; belirsizler aynı
kaldı. Yeni kontrol açılmadan `kit-reassignment-decision.json` ile bu sınırlı
yeniden atama kuralı seçildi. Önceki 6/9 artık kontrol olarak raporlanmayacak.

Kontrol 2/8: 55 doğru / 10 yanlış / 10 belirsiz iki yöntemde de aynı kaldı;
yeniden atama varsayılan yapılmadı. İkinci aşamada 2/8 de geliştirmeye katılır.
Yerel çim aydınlığıyla normalizasyon ham video kutularında denenir. Bu ikinci
aşamanın yeni kontrolü 1/7 segmentleridir; kural seçilene kadar görüntüleri ve
etiketleri incelenmez. Aynı kabul şartları geçerlidir.

Yerel çim yöntemi geliştirmede 157/27/14 → 160/11/27 (doğru/yanlış/atanamayan)
verdi. `kit-local-light-decision.json` kontrol 1/7 açılmadan sabitlendi. Yeni
kontrolde 54/7/5 → 56/4/6; başka renklilere atama 0 kaldı. Koşullar geçti.
Üretim entegrasyonu: `teams.kit_color` ve ortak video/canlı `pipeline`, yöntem
bilgisi özette; ham karşılaştırma için config ve önbellek CLI seçeneği. Reddedilen
parlak yeniden atama yalnız deney script'inde kalır. Yeni üretim fonksiyonuyla
tüm aynı kutulardan tekrar renk çıkarılır; ham gözlemlerin birebir eşitliği,
donmuş sonuç, sınır/ışık, toplama hattı ve canlı çapa regresyonları doğrulanır.
