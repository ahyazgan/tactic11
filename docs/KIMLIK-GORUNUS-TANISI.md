# Kimlik ayrımında görünüş ve GTA bağlantı tanısı

19 Eylül 2026. **Mevcut görünüş modeli değiştirilmedi.** Genel OSNet ve spor
OSNet modeli, aynı oyuncunun ışık/poz değişimini her zaman farklı oyuncudan
ayıramıyor. İncelenen bütün yedi ayrımda tek eşikli, güvenilir bir yeni düzeltme
kanıtı oluşmadı. Bu rapor geliştirme tanısıdır; yeni kontrol veya tam maç doğruluk
ölçümü değildir.

## İncelenen kanıt

Önceki üç geliştirme ayrımı ve kapatılmış kontrolün dört ayrımının tamamı
incelendi. Önce/sonra en fazla 12 kaynak gözlemi alındı. İlk üç ayrımın kaynak
şeritleri bu aşamada görsel olarak da incelendi: farklı formalar arasında geçiş
var; geçişte karışık kutular ve kesin zaman belirsizliği korunuyor. Dört eski
kontrol ayrımından üçü doğru, beyaz 6 numara ise aynı kişinin yanlış bölünmesi.
Etiketler tek Codex görsel değerlendiricisinden gelir; insan hakem veya yeni
kör kontrol değildir.

Beyaz 6'nın rengi 310–320 örnekleri arasında yaklaşık RGB (120,163,229)'dan
(246,246,251)'e kayıyor. Kalıcı renk değişimi ile ikinci motorun kimlik değişimi
aynı anda görülebiliyor; iki sinyal birlikte olsa da gerçek kişi değişimi
olduğu sonucu çıkarılamaz.

## İki modelin karşılaştırması

Mevcut OSNet-AIN modeli ile resmi [GTA-Link kaynağındaki spor OSNet modeli](https://github.com/sjc042/gta-link/tree/e4d5cc4065ceb1ec3fa9dc7478455f13a8d7f9ca)
karşılaştırıldı. Kaynak, spor modelinin SportsMOT ile eğitildiğini bildiriyor;
eğitim verisi örtüşmesi bağımsız doğrulanmadı. Mimari ve iki lisans dosyası sabit
commit'ten alındı. Ağırlık SHA256 ve 616 sınıflı durum sözlüğü doğrulandı;
yerel güvenli ağırlık yüklemesi kullanıldı. Üretim modeli değiştirilmedi.

Mevcut OpenCV önişlemesi ve kaynağın PIL önişlemesi spor modeli için ayrı ayrı
ölçüldü. Aşağıda iki taraftaki en yakın üçer gözlem arasındaki medyan kosinüs
uzaklığı yer alır. Büyük değer daha farklı görünüş demektir; olasılık değildir.

| Kesit / eski kimlik | Kaynak incelemesi | Genel OSNet | Spor OSNet + PIL |
|---|---|---:|---:|
| 0 / 68 | Doğru ayrım | 0.2495 | 0.2641 |
| 0 / 72 | Doğru ayrım | 0.3042 | 0.2007 |
| 3 / 8 | Doğru ayrım | 0.3675 | 0.2978 |
| 60 / 13 | Doğru ayrım | 0.2039 | 0.2000 |
| 60 / 186 | Yanlış bölünme | 0.1934 | 0.2321 |
| 62 / 73 | Doğru ayrım | 0.2364 | 0.1974 |
| 62 / 86 | Doğru ayrım | 0.3000 | 0.2178 |

Genel modelde yanlış bölünme 0,1934, en yakın doğru ayrım 0,2039'dur. Bu küçük
aralığa bir eşik koymak yedi örneğe uyum sağlar, genelleme kanıtı sağlamaz.
Üçer gözlemde iki taraf arası farkı taraf içi değişkenlikle karşılaştıran kural,
beyaz 6'yı reddediyor; beşer gözleme geçince aynı örneği kabul ediyor. Spor
modelinde ise beyaz 6'nın farkı bazı doğru ayrımlardan büyüktür. PIL/OpenCV
önişlemesi bu sıralama sorununu gidermedi.

## GTA bağlantı adımının dar kapsamlı denemesi

GTA-Link, çevrimdışı bir takip parçası bölme/bağlama yöntemidir. İncelenen
commit'in bağlantı fonksiyonları değiştirilmeden CPU'da çalıştırıldı; resmi
0,4 bağlama eşiği ve 1,0 mekân katsayısı kullanıldı. Her ayrımın en fazla
12 önce ve 12 sonra gözlemi iki ayrı parça olarak verildi. Üç görünüş kolunda
toplam 21 küçük denemenin **21'i iki parçayı yeniden birleştirdi**. Bu, doğru
ayrımların kısa parçalarında da oldu; kaynak kutuları silinmedi.

Bu sonuç **tam GTA yönteminin başarısızlığı** olarak sunulamaz: tam parça
geçmişi, başka zamanlardaki eşzamanlı görünürlük ve bölme adımı dahil değildir.
Yalnız bu varsayılanları kısa parçalara doğrudan uygulamanın doğrulanmış bir
kişi tanıma çözümü olmadığını gösterir. Kaynağın CLI'si çalıştırılmadı; paket
ortamı değiştirilmedi, dış pickle dosyası açılmadı.

## Hareket ve nokta rengi tanısı

Yedi geçişin tamamında son üç eski gözlemden ayrı ayrı Lucas–Kanade noktaları
başlatıldı. Aradaki bütün kaynak kareleri kullanıldı; en çok 30 gövde köşesi,
15×15 pencere, iki piramit seviyesi ve en fazla 1 piksel ileri/geri hata
uygulandı. En az üç nokta kalmayan sonuç belirsizdir. Bu ayarlar kimlik sınıfı
eşiği değildir. Aşağıdaki değer, onay örneğinde akışla beklenen hareket ile
kutu hareketi farkının gövde genişliğine oranıdır; üç başlangıç sırasıyla verilir.

| Kesit / eski kimlik | Üç başlangıçta hareket farkı |
|---|---|
| 0 / 68 | 0.636 / 0.951 / 0.822 |
| 0 / 72 | 0.136 / 0.009 / 0.196 |
| 3 / 8 | 2.262 / 1.955 / 2.098 |
| 60 / 13 | 0.243 / 0.304 / 0.252 |
| 60 / 186 | 0.142 / 0.160 / 0.062 |
| 62 / 73 | 0.852 / 0.688 / 0.727 |
| 62 / 86 | 0.352 / 0.670 / 0.219 |

Beyaz 6'nın hareketi devam ediyor; fakat doğru ayrım olan 0/72'de de çok küçük
farklar var. Görsellerde noktalar yakın geçen diğer oyuncuya taşınabiliyor.
60/13 ve 62/86'da örtüşen gövdeler nokta sahipliğini de belirsizleştiriyor.
Bu yüzden düşük hareket farkı tek başına aynı kişi kanıtı değildir.

İkinci tanıda her hayatta kalan noktanın başlangıç/hedef 5×5 RGB medyanı ve
parlaklığa normalize renk uzaklığı ölçüldü. Beyaz 6'nın onay anı medyan kosinüs
farkı üç başlangıçta 0,03102 / 0,01678 / 0,00153; doğru ayrım 0/72'de
0,01750 / 0,01253 / 0,01063. Başlangıç değişince sıralama değişiyor; yalnız
son başlangıcı seçmek yine bu yedi örneğe uyarlama olur. Yeni karar eşiği
seçilmedi ve takip kodu değiştirilmedi.

[Hareket/nokta rengi ham verisi, kaynak hashleri ve tam betikler](measurements/identity-motion-diagnostics-20260919.json).
Yedi görsel `measurements/identity-motion-boundary-0.jpg` ile `-6.jpg` arasındadır;
kutu sarı, akış tahmini camgöbeği, noktalar kırmızıdır. Görsellerin tamamı
kaynak bağlamıyla incelendi; değerlendirme tek AI incelemesidir.

## Mevcut takım paletiyle destek: yeni geliştirme adayı

Ek tanıda aynı kaynak gövde renkleri mevcut iki RGB takım merkezine göre
karşılaştırıldı. Yedi geçişte 3/5/8/12 gözlemlik medyanlar incelendi. Altı doğru
ayrımda en yakın RGB takım merkezi değişiyor; beyaz 6'da iki taraf da aynı
merkeze yakın. Normalize renk karşılaştırması bazı doğru geçişleri kaçırıyor.

Yeni geliştirme adayı, mevcut uzlaşıdaki üç önce/üç onay gözleminin medyan RGB
renginin farklı mevcut takım merkezlerine yakın olmasını ek koşul yapıyor.
Yeni mesafe eşiği aranmadı; geçersiz/ayırt edilemeyen palet, eksik renk veya
eşit uzaklıkta destek verilmez. Bu bir kişi etiketi değildir ve aynı takım
oyuncularının birbirine geçmesini çözmez.

15 eski kesidin önbellek karar tekrarında altı doğru ayrım korunurken beyaz
6'nın yanlış bölünmesi reddedildi. Kutular, zamanlar ve gözlem başına takımlar
birebir korundu. İlk 11 kesitte değişiklik yok; kapatılmış kontrol artık
**geliştirme verisi** olarak kullanıldı. Bu, gerçek dedektör veya yeni bağımsız
kontrol başarısı değildir. [Palet tanısı ve 15 kesit kanıtı](measurements/identity-palette-diagnostics-20260919.json).

Sonraki adım bu adayın gerçek RGB/OSNet takip akışındaki eşitliğini doğrulamak,
bütün eski kaynakların kapsam/kimlik ölçümlerini korumak ve yeni görüntü
öncesinde kod/model/planı sabitlemektir. `consensus` deneysel ve ByteTrack
varsayılan kalır; bu rapor hiçbir üretim takip kararını değiştirmez.

Ölçüler, dosya/model hashleri, ham yerel rapor adresleri ve deney betiklerinin
tam metni: [kanıt kaydı](measurements/identity-appearance-diagnostics-20260919.json).
İlk üç görsel: `measurements/identity-appearance-development-boundary-0.jpg`,
`-1.jpg`, `-2.jpg`. Kaynak SoccerTrack v2, Atom Scott ve diğerleri,
[CC BY 4.0](https://github.com/AtomScott/SoccerTrack-v2/blob/main/LICENSE-DATA);
görüntüler kesildi, ölçeklendi ve kutu/örnek sırası eklendi.
