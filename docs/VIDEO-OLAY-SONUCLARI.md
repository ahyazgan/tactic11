# Video olayları: ölçüm ve değişiklikler — 14 Eylül 2026

Güvenilirlik ve veri aktarım hataları düzeltildi. Pas duyarlılığını artırma ve
gerçek görüntüde savunma olayını doğrulama hedefleri **henüz geçilmedi**.
Yoğun kare kullanımı denendi; kontrol sonucuyla varsayılan olarak açılmadı.
Kaynak maç dosyaları ve mevcut veritabanı değiştirilmedi.

Başlangıç: `ad8da25`. Sayısal kanıt ve olay bazlı tanılar:
[video-events-2026-09-14.json](measurements/video-events-2026-09-14.json).

## Ne düzeldi?

- Topun iki gözlem arasında tamamlanması gerçek geçen süreyi kullanıyor.
  Kamera kesmesi, tekrar, değişen kalibrasyon veya fiziksel olarak olanaksız
  geçiş üzerinden piksel konumu tamamlanmıyor. İki komşu gözlemin desteklediği
  tekil sıçramalar ayıklanıyor; tamamlanan konumlar gözlem diye sunulmuyor.
- Pas durum makinesi maç, yarı, kamera sürekliliği ve geri giden saatte
  sıfırlanıyor. Tutuş kararlılığı kare sayısıyla birlikte süre gerektiriyor.
  Son kontrol konumu ve zamanı adaydan bağımsız tutuluyor. Videoda fiziksel
  hız sınırı, aynı kimlikte takım değişimi ve eksik top etiketi denetleniyor.
- `ball_estimated` DB'de tutulmasına rağmen karar motoruna yüklenirken
  kayboluyordu. Artık bu işaret, kamera sürekliliği ve görünür alan korunuyor.
- Yalnız gözlenmiş, kararlı rakip→oyuncu kontrol değişimi `ball_recovery`
  üretebiliyor. Müdahale/pas arası ayrımı uydurulmuyor. Eksik/enterpole top,
  12+ kişilik takım ve süreklilik kopması kanıt zincirini kesiyor.
- Pas ve top kazanımı video/canlı JSON→DB→domain boyunca ayrı kaynak ve
  `estimated=True` ile taşınıyor. Kısmi video savunma olayları PPDA paydasını
  veya alan üstünlüğü kıyasını etkinleştirmiyor. Birinci yarının 47. dakikası
  artık otomatik ikinci yarı sayılmıyor. Açıkça boş olay listesiyle tam yeniden
  yükleme eski türetilmiş olayları temizliyor; sağlayıcı olayları korunuyor.
- `--dense-events` hem tek video hem canlı/izole işçide mevcut. Dedektörü
  yeniden çalıştırmadan tüm takip karelerinden olay çıkarıyor; dışa aktarılan
  kare sıklığını değiştirmiyor. **Deneysel ve varsayılan kapalı.**

## Altı dakikalık mevcut çıktının kontrolü

Maç 117092, ilk yarı 600–960 sn; yerel analiz kimliği 990401. Güncel 12 JSON
dosyasında **38 pas** vardı; önceki konuşmadaki 25 sayısı bu sürüme ait değil.
`player_nodes.csv` 68 pas/orta olayı taşıyor. Kompakt 12-sınıf dosyası
60 PASS + 9 HIGH PASS + 1 CROSS = 70 içeriyor. Sözlükler farklı; bu rapor
zaman, başlangıç/son konum ve sonuç içeren 68 olaylık dosyayı kullanıyor.

Eşleme birebir: aynı referans iki kez doğru sayılmıyor. Zaman toleransı ±2 sn,
başlangıç konumu 5 m. Daha sıkı sütun ayrıca takım, tamamlanma sonucu ve
başarılı pasta son konumun 8 m içinde olmasını gerektiriyor.

| Mevcut kareler, yalnız olay motoru değişti | Önce | Sonra |
|---|---:|---:|
| Pas adayı | 38 | 36 |
| Zaman + başlangıç konumu eşleşmesi | 8 | 8 |
| Zaman/başlangıçla eşleşmeyen aday | 30 | 28 |
| Takım + sonuç + son konum dahil eşleşme | 3 | 3 |
| Çıkarılan top kazanımı | 0 | 0 |

İki elenen aday kontrol aralığındaydı: 23→21 aday, 7 eşleşme korundu.
Bu küçük örnekteki temizlik, genel doğruluk başarısı değildir. Oyuncu kimlikleri
ayrıca doğrulanmadığından bu sütunlar doğrudan pas kesinliği sayılmamalı.

Top gözlem sorunu görünenden büyük: referans temas zamanının ±0,6 saniyesinde,
etiketli başlangıç konumuna 5 m içinde bir gözlenmiş top yalnız **19/68** olayda
var. Bu temas göstergesidir; bağımsız kare başına top GT'si/recall değildir.
GSR oyuncu ve kaleci etiketleri içeriyor, top kutusu içermiyor. Olay tanılarında
12 olay civarında hiç gözlem yok, 35 olayda bulunan top temas konumundan uzak.
Zaman/konum eşleşmesi tanıda öncelikli olduğundan bu nedenler birbirinden
ayrılmıştır; toleranslar farklı olduğu için doğrudan birbirini tamamlamazlar.

## Aynı dedektör gözlemleriyle seyrek/yoğun karşılaştırma

Önceden dondurulmuş seg_0000/0003 geliştirme, seg_0006/0009 kontrol örnekleri;
toplam 120 sn. 25 fps kaynakta gerçek takip sıklığı 12,5 fps, seyrek çıktı
4,17 fps. Takım ataması iki sürümde de önceki renk düzeltmesini kullanıyor.
Tam altı dakikalık eski çıktı farklı tespit çalıştırmasıdır; iki deney
birbirine karıştırılmamalı. Kontrol aralığında 12 referans pas var.

| Kontrol, iki adet 30 sn segment | Aday | Zaman + konum eşleşmesi | Eşleşmeyen |
|---|---:|---:|---:|
| Önce, seyrek | 9 | 3 | 6 |
| Sonra, seyrek (varsayılan) | 9 | 3 | 6 |
| Önce, yoğun | 17 | 2 | 15 |
| Sonra, yoğun | 12 | 2 | 10 |
| Yeni olay mantığı, yoğun, top temizliği kapalı | 11 | 2 | 9 |

Yoğun sürüm önceki yoğun denemeden daha az eşleşmeyen olay çıkarıyor; yine de
seyrek varsayılandan kötü. Bu nedenle devreye alınmadı. Geliştirmede de yoğun
eski 12 aday/2 eşleşme, yeni 9 aday/1 eşleşme: iyileşme ilan edilemez.

Top filtresi geliştirmede 1, kontrolde 5 tekil sıçramayı ayıkladı. Bunların
etiketli yanlış tespit olduğu kanıtlanmış değil. Temas göstergesi artmadı;
yoğun sürümde tamamlama bir eşleşmeyen aday ekledi. Varsayılan seyrek olay
sonucu değişmedi. Bu fiziksel tutarlılık düzeltmesi top recall artışı değildir.

## Savunma ve dış veri regresyonu

Yeni top kazanımı modülü sentetik pozitif ve olumsuz senaryolarda, canlı
çıktıda ve izole DB yüklemesinde doğrulandı. Gerçek örnekte katı gözlem
zinciri sağlanmadı: **0 olay**. Eşikleri sırf sıfırı kaldırmak için gevşetmedik.
CSV'deki possession/intercept/tackleSucceeded/cutoff/duelSucceeded birleşimi
21 aday referans veriyor; bu da tam savunma GT'si değildir. Savunma doğruluğu
ve duyarlılığı bu çalışmayla doğrulanmış sayılmaz.

SkillCorner 2017461, 40.404 kare, 824 referans geçiş: hem eski hem yeni motor
380 pas adayı, 215 birebir eşleşme veriyor (**%56,6 kesinlik, %26,1 duyarlılık**).
Yeni doğrulayıcı iki oyuncu kimliğini, iki uçtaki zamanı (±3 sn), sonuç türünü
ve referansın yalnız bir kez kullanılmasını denetliyor. Eski %72 sayısı ara
sahiplik atlamalarını da doğru kabul ediyordu; aynı metrik değil. Aktörler ve
referans aynı sağlayıcıdan geldiği için bu bağımsız video doğruluğu testi değil.

## Ölçüm sınırları ve kabul kararı

CSV koordinatları enine x/boyuna y ve ters yön taşıyor; GSR sistemine dönüşüm
`(100*(1-y), 100*(1-x))`. Geliştirme olaylarında oyuncu GT konumuyla kontrol
edildi. Mevcut TPS kalibrasyonu aynı maçtan türetilmiş; bağımsız maç sınavı yok.

Otomatik forma kümeleri gerçek kulüp adını kendiliğinden bilmez. Takım
permutasyonu geliştirmedeki tek zaman/konum eşleşmesinden seçilip donduruldu
(oylar 0/1); zayıf dayanak. Sıkı takım sütunu bu eşlemeye koşulludur. Ana
zaman/konum sütunu takım eşlemesine bağlı değildir. Kontrolde zaman kaydırma,
eşik tarama veya takım permutasyonu seçimi yapılmadı.

Hızlandırma/TensorRT, Karne şekil seçiciliği ve yeni kamera kaydı bu olay
çalışmasının ölçümü değildir. 30 saniyeyi 30 saniyenin altında işleme hedefi
bu değişikliklerle geçmiş sayılmıyor. Gelecek doğruluk adımı: geliştirme ve
ayrı kontrol görüntülerinde top kutuları/gerçek kulüp renkleri doğrulanmış
etiketler, ardından dedektör/ROI karşılaştırması. GPU'yu tekrar çalıştırıp
yalnız olay sayısını artırmak kabul kanıtı olmayacak.

## Tekrar üretim ve kontroller

Komutlar repo kökünden, yeni çıktı klasörleriyle çalıştırılır. Baseline dosya
`ad8da25:app/tracking/passes.py` içeriğinin yerel kopyasıdır.

```powershell
.\venv-cv\Scripts\python.exe -m scripts.soccertrack_v2.replay_events --cache data/tracking/bench/signal_quality_v1 --out data/tracking/bench/events_new_run
.\venv-cv\Scripts\python.exe -m scripts.soccertrack_v2.replay_events --frames data/tracking/live/990401/frames --out data/tracking/bench/events_new_existing
.\venv-cv\Scripts\python.exe -m scripts.soccertrack_v2.audit_event_evidence --frames data/tracking/bench/events_new_run/dense --nodes data/tracking/datasets/soccertrack_v2/117092/117092_player_nodes.csv --alignment data/tracking/bench/events_alignment.json --out data/tracking/bench/events_new_audit.json
.\venv\Scripts\python.exe -m scripts.audit_skillcorner_passes --dir data/tracking/skillcorner/2017461 --baseline-module data/tracking/bench/passes_before.py --out data/tracking/bench/skillcorner_new_audit.json
```

Yeni ortamda hizalamayı ilk olarak eski altı dakikalık çıktı üzerinde üret;
mevcut dosya yokken kontrol çıktısıyla hizalama seçme. Dondurulmuş eşleme ve
girdi SHA-256 değerleri ölçüm JSON'unda bulunuyor. `--keep-cached-ball` yeni
olay mantığını top temizliğinden ayrı ölçer.

Kontroller: **2489 test geçti, 1 atlandı**, 15 mevcut kullanım dışı API uyarısı;
ruff temiz; mypy 482 kaynak dosyasında temiz. Gerçek maç veritabanına yazılmadı.
