# Kamera takım ataması: ölçüm ile gerçek hatayı ayırma

14 Eylül 2026. Başlangıç `883faea`; önceki PR #237'nin tüm kontrolleri geçti,
`14ec056` ile main'e birleşti ve Codex dalına alındı.

**%81,11 gerçek forma/oyuncu doğruluğu olarak kullanılamaz.** Bu değer,
kalibrasyonla 3 m içinde eşleştirilen GT takım etiketleriyle uyumdur. Görsel
inceleme, bazı GT eşlemelerinin tespit kutusundaki formayla çeliştiğini gösterdi.
119 uyuşmazlığın tümünü forma sınıflandırıcısına yüklemek yanlış olur.

## Tam kayıt tanısı

Önce geliştirme, ardından aynı yöntemle kontrol değerlendirildi. Eski +9 kare
hizalaması, takım permütasyonu ve 3 m birebir konum eşlemesi korundu.

| Tanısal sayım | Geliştirme | Kontrol |
|---|---:|---:|
| Konumla eşleşmiş saha oyuncusu gözlemi | 425 | 646 |
| Takım atanmış gözlem | 408 | 630 |
| Konumsal GT takım etiketiyle uyuşmazlık | 58 | 119 |
| Uyuşmazlık ve aynı takipte birden fazla GT takımı | 54 | 117 |
| Uyuşmazlık ve aynı takipte birden fazla GT kimliği | 56 | 117 |
| Uyuşmazlık ve 3 m içinde alternatif karşı takım GT'si | 14 | 29 |
| Uyuşmazlık ve en yakın GT yerine başka GT ile eşleme | 5 | 9 |
| Uyuşmazlık ve eşleme mesafesi ≤1,5 m | 12 | 39 |

Satırlar örtüşür; toplanamaz. Bir takip numarasının birden fazla GT takımıyla
eşleşmesi **kesin kimlik değişimi demek değildir**: kalibrasyon hatası,
geometrik eşleme veya gerçek takip kayması olabilir. 1,5 m satırı aynı 3 m
eşlemelerinin altkümesidir; daha dar yarıçapla yeniden eşleme sonucu değildir.

## Görsel inceleme

Geliştirmede en fazla uyuşmazlık taşıyan altı takipten ilk/orta/son uyuşmazlık
ve ortadaki uyum örneği seçildi, tekrarlar çıkarıldı: 23 farklı görüntü.
Bir görüntüde üst üste iki oyuncu bulunduğu için net renk etiketi verilmedi.
Kalan 22 görüntünün 14'ünde konumsal GT takım etiketi görünen forma rengiyle
çelişti. Tahmin ise dört görüntüde görünen formayla çelişti; dördü de aynı
beyaz formalı takibin farklı anları. Bu sayılar genel başarı oranı değildir.

- Segment 0, takip 28, 610,4/612/613,6 sn: kutuda mavi forma, modelde mavi takım;
  konumsal eşleme beyaz takımın GT etiketini getiriyor.
- Segment 0, takip 16, 624/625,6/626,4 sn: kutuda beyaz forma, modelde beyaz;
  konumsal eşleme mavi takıma gidiyor.
- Segment 3, takip 9, 690/700,4/709,2/710,8 sn: kutuda beyaz forma, modelde
  mavi takım. Bu gerçek renk hatasıdır. Takibin medyan RGB'si yaklaşık
  (127,132,123); gölge altındaki beyaz forma karanlık kümeye düşüyor.
  710,8 sn'deki konumsal ölçüm bu yanlış kararı yanlışlıkla doğru sayıyor.

[İncelenen görüntüler](measurements/team-errors-development-review.jpg).
Görüntüler Codex tarafından incelendi; bağımsız ikinci değerlendirici yok.
Seçim özellikle sorunlu takiplerden yapıldı. Yalnız forma rengi etiketlendi;
oyuncu adı, sırt numarası veya kimlik doğruluğu iddiası yok. Kontrol görüntülerine
bu elle etiketleme uygulanmadı ve kontrol verisiyle eşik ayarlanmadı.

## Geliştirme kararı

Bu tur üretim renk sınıflandırıcısını değiştirmedi. Konumsal GT'ye uyumu artırmak
için gölgeli beyaz oyuncuyu veya doğru sınıflandırılmış mavi oyuncuyu yeniden
etiketlemek, birbirine zıt sonuçlar doğurabilir. Renk modeli karşılaştırmasının
sonraki kabul verisi, doğrudan video kutularına verilmiş forma etiketleri ve
ayrı kontrol görüntüleri olmalı. Bu yanlı 23 görüntü bağımsız kontrol olamaz.

Kalibrasyon çizgi hatası önceki çalışmada zaten saptanmıştı. Bu tanı, mevcut
kalibrasyonun hatanın tamamını açıkladığını veya takip kayması olmadığını
kanıtlamaz. Gerçek takip kayması için ardışık görüntü/kimlik etiketleri gerekir.

## Araçlar, kanıt ve doğrulama

- `audit_team_errors`: gözlem bazında bbox/zaman/renk, GT mesafesi, alternatif
  rakip, takip başına GT değişimi; örtüşen tanı sayaçları. Çıktı üzerine yazmaz.
- `render_team_error_review`: özgün videodan aynı örnekleri tekrar görüntüler;
  seçilen örnekleri JSON manifestine kaydeder, örnek tekrarlarını çıkarır.
- `evaluate_teams`: çıktıya ölçütün yalnız konumsal GT uyumu olduğunu ekler.
- [Ölçüm ve görsel etiketler](measurements/team-errors-2026-09-14.json): girdi ve
  kaynak video SHA-256 değerleri; 23 görüntünün konumu ve inceleme notları.

```powershell
.\venv\Scripts\python.exe -m scripts.soccertrack_v2.audit_team_errors --cache data/tracking/bench/signal_quality_v1 --gt data/tracking/bench/signal_quality_gt.npy --alignment data/tracking/bench/signal_quality_alignment.json --out data/tracking/bench/audit_recheck_dev.json --development-only
.\venv\Scripts\python.exe -m scripts.soccertrack_v2.audit_team_errors --cache data/tracking/bench/signal_quality_v1 --gt data/tracking/bench/signal_quality_gt.npy --alignment data/tracking/bench/signal_quality_alignment.json --out data/tracking/bench/audit_recheck_all.json
.\venv-cv\Scripts\python.exe -m scripts.soccertrack_v2.render_team_error_review --audit data/tracking/bench/audit_recheck_dev.json --out data/tracking/bench/review_recheck
```

Tanı regresyonları: segmentler arasında takip numarası tekrar kullanımı,
örtüşen bayrakların çift hata saymaması, belirsiz/boş gözlemler, görsel örnek
tekilleştirme ve dondurulmuş zaman/alternatif GT eşlemesi.

Bu tur ilgili **49 test geçti**, ruff temiz, mypy 492 kaynak dosyasında temiz.
Üretim takip/renk kodu değişmedi; tam proje koşusu PR CI tarafından doğrulanır.
