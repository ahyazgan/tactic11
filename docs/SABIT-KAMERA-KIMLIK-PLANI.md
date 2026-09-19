# Sabit kamera kimliği ve forma — çalışma planı

2026-09-14. Hedef, aynı oyuncunun kimlik sürekliliğini ve takım atamasını birlikte
düzeltmek; takip sayısının azalmasını doğruluk artışı saymamak. Önceki süre uzatma
deneyi geliştirmede başarısızdır ve üretim değişikliği değildir.

## İş bölümü ve veri sınırı

- Kimlik incelemesi: mevcut ByteTrack eşleştirmesine hareket ve güvenilir kısa
  renk geçmişi eklenmesi; belirsiz/örtüşen oyuncuların zorla birleştirilmemesi.
- Forma incelemesi: gölge ile kimlik karışmasını ayıran renk ve zaman kanıtı.
- Bağımsız ölçüm: SoccerTrack gerçek kimlik şeması, video koordinatı ve zaman
  hizasının doğrulanması; geçersiz eşleşmelerden IDF1/ID değişimi üretilmemesi.
- Ana çalışma: iç içe kutu tanısı, üretim entegrasyonu, kör kontrol ve önizleme.

Bütün mevcut etiketler ve 117093 klipleri geliştirme verisidir. 117092 için
yeni kontrol aralıkları **1800–1830 ve 2100–2130 saniye** olarak ayrılır; model
ve eşikler dondurulmadan bu aralıkların görüntüsü/etiketi açılmaz. Gündüzde
mevcut üç klibin 14,96 ve 27,44 saniyeleri ayrıca görüntü kontrolü için ayrılır;
aynı klipte olduklarından bağımsız maç testi sayılmaz. Ek kaynak varsa kapsamı
ve eğitim/önceki inceleme örtüşmesi ayrıca kaydedilir.

## Kabul

1. Aynı tespitleri ve aynı kalibrasyonu kullan; önce mevcut çıktıyı birebir
   tekrar et. Değişmiş ID'lerle etiket eşleştirme: kare + kutu koordinatı.
2. Takım doğrusu, yanlışı, atanamayan, forma kutusu kaybı ve başka-renk ataması
   birlikte raporlanır. Örtüşen ayrı oyuncular ve hakem/kaleci korunur.
3. Kimlik ölçümü görünür gerçek kişi eşleşmesiyle veya hizası doğrulanmış GT
   ile yapılır. Yalnız karışık forma ID sayısı, genel kimlik metriği değildir.
4. Geliştirmede seçilen kod/parametre hash'leri kontrol incelemesinden önce
   dondurulur. Başarısız kontrol aynı aday için yeniden ayar verisi olamaz.
5. Üretim entegrasyonu video, canlı işçi, önizleme ve anonim kimlik sözleşmesini
   kapsar. Kamera kesmesi izolasyonu, belirsizlik ve mevcut güvenlik kapıları
   korunur. Hiçbir kimlik gerçek kadro oyuncusu olarak sunulmaz.
6. İlgili/tam testler, gerçek CV takipçisi, Ruff/mypy, kaynak hash'leri ve
   oynatılabilir önizleme; ardından otomatik PR ve son commit kontrolleriyle merge.

Üretim akışı: `pipeline.py` içinde ham tespitlerden parça süzme ve eşzamanlı
forma kanıtı; `player_identity.py` içinde kimlik bölme → forma öğrenme → temkinli
bağlantı. `person_parts.py`, `identity_split.py`, `identity_links.py` ve
`kit_evidence.py` bağımsız yardımcı modüllerdir. Eski `teams.py` davranışı
korunur. Yeni yol önce sabit kamera/ham renk seçimiyle sınanır; otomatik profil
yalnız ilgili görüntü kontrollerini geçen kaynakta etkinleştirilir.

Bağımsız incelemede canlı parçaların ByteTrack kimliğini yeniden kullandığı
doğrulandı. `identity_namespace.py` ve kare oluşturma, periyot + klip başlangıcını
kimliğe dahil eder. Bu, farklı parçaların yanlışlıkla aynı kişi sayılmasını
önler; parçalar arasında kişi tanıma iddiası değildir. Video ve canlı işçi aynı
başlangıç zamanıyla aynı kimlikleri üretmelidir; pas/savunma çıktısı da aynı
kare kimliklerini kullanmalıdır.

Kontrol kabulünde gündüz ve gece ayrı değerlendirilir: doğru forma ve gerçek
kişi kutusu kapsamı başlangıçtan azalmamalı, yanlış forma/başka giysiye atama
artmamalıdır. Aynı kişi ilişkilerinde yeni kayıp veya farklı kişi ilişkilerinde
yeni yanlış birleştirme olmamalıdır. Başarısız kaynak otomatik profile alınmaz.
Mükerrer parça kutuları, destekleyen asıl kişi kutusu korunarak ayrı sayılır;
ham kutu ölçümü de saklanır.
Araştırma scriptleri `scripts/soccertrack_v2/identity_*`, `kit_joint_*` altında
ayrı tutulur; model geliştirme ve kontrol verisi karıştırılmaz.
