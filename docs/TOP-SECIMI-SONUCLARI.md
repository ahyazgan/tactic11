# Top seçimi ve kalibrasyon kontrolü — 14 Eylül 2026

Başlangıç `4eb685b`. Bu çalışmada genel doğruluk hedefi geçilmedi. Üretime
eklenen davranış: video çözünürlüğü kalibrasyonun piksel boyutuyla farklıysa
dedektör kurulmadan hata verilir. Aynı geometriyi farklı görüntüye uygulayıp
yanlış saha konumu üretmek önlenir. Top rengi, ek ROI ve alternatif kalibrasyon
varsayılan üretim davranışına alınmadı.

Ölçüm: [ball-calibration-2026-09-14.json](measurements/ball-calibration-2026-09-14.json).
Yeni kalibrasyon ayrı dosyada ve `experimental=true`, `not_promoted` etiketlidir:
`data/tracking/calibrations/soccertrack_v2_117092_landmarks.json`.

## Kalibrasyon bulgusu

GSR kutularının görüntüsü 3840×1504, kullanılan panorama 3840×1906.
Ham GSR pikselini doğrudan panorama kalibrasyonuna vermek geçersizdir.
İlk şüphe bu iki uzay farkı ayrıldıktan sonra **65 saha çizgisi noktasıyla**
ayrıca kontrol edildi. Mevcut oyuncu eşleşmelerinden türetilen kalibrasyonun
bu çizgilerde ortalama hatası **10,71 m**, medyanı **6,27 m**, p90'ı **27,46 m**.
Önceki 1,59 m ölçüsü seçilmiş oyuncu eşleşmelerine koşulluydu; tüm saha için
geçerli hata ölçüsü sayılmamalı.

Sağlanan saha noktalarından homografi + TPS artığıyla ayrı kalibrasyon kuruldu.
Oyuncu/pas etiketleriyle parametre öğrenilmedi. Bir çizgi noktasını dışarıda
bırakarak doğrulama ortalaması **1,76 m**. Bu, eski modelin çizgi hatasıyla
aynı değerlendirme düzeni değildir; bağımsız maç doğruluğu da değildir.

Yalnız kayıtlı oyuncuları yeni koordinata çevirmek yeterli olmadı. Saha dışında
eleme, ByteTrack, renk biriktirme ve olay üretimi baştan çalıştırıldı. Ardından
**aynı tam kare tespitleriyle** eski kalibrasyon tekrar çalıştırılarak farkın
yalnız ayrı GPU çalıştırmalarından kaynaklanması önlendi. ROI aramaları kaynak
çalıştırmanın eski konumunu koruyor; bu sınırlama çıktıya yazılıyor.

## Önce/sonra (aynı tam kare tespitleri)

Sabit eşikler: 0/3 segmentleri geliştirme, 6/9 kontrol; dört adet 30 sn bölüm.
Önceden dondurulmuş zaman ve takım eşlemeleri kullanıldı. Kontrolde eşik veya
zaman kaydırma araması yapılmadı. Her bölümde seyrek 250, yoğun 750 kare var.

| Seyrek olay akışı | Geliştirme eski → yeni | Kontrol eski → yeni |
|---|---:|---:|
| Referans pas | 11 | 12 |
| Pas adayı | 7 → 7 | 9 → 8 |
| Zaman + başlangıç konumu eşleşmesi | 1 → 3 | 3 → 2 |
| Eşleşmeyen pas adayı | 6 → 4 | 6 → 6 |
| Gözlenmiş top bulunan kare | %22,8 → %34,4 | %32,0 → %46,8 |
| Etiketli temas yakınında top bulunan olay | 0 → 4 | 4 → 5 |
| 12+ kişilik takım bulunan kare | %13,6 → %34,0 | %36,8 → %6,0 |
| Top kazanımı adayı | 0 → 0 | 0 → 1 |

Sıkı takım/sonuç/son konum eşleşmesi iki modelde de 0. Yeni top kazanımının
mevcut referans sözlüğünde eşleşmesi yok; doğrulanmış savunma olayı diye
sunulmuyor. Toplu sayıların artması top recall veya gerçek pas kesinliği değildir.

Takım GT kontrolü, ayrı seyreltilmiş konum eşleşmeleri ve tüm takip kareleriyle:

| Kontrol | Eski | Yeni |
|---|---:|---:|
| Konumla eşleşmiş saha oyuncusu gözlemi | 646 | 672 |
| Takım atanmış eşleşme | 630 | 587 |
| Doğru takım eşleşmesi | 511 | 468 |
| Atanmış eşleşmelerde koşullu doğruluk | %81,11 | %79,73 |
| 12+ oyunculu kare, tüm takip kareleri | %36,40 | %5,47 |

Eşleşen gözlem kümeleri aynı olmadığı için doğruluk oranları doğrudan sınıflandırıcı
iyileşmesi/kötüleşmesi olarak okunmamalı. Buna rağmen doğru atama sayısındaki
kayıp, yalnız 12+ oranına bakarak yeni modeli açmamak için yeterli neden.
Geliştirmede koşullu doğruluk %85,78→%64,99 ve doğru eşleşme 350→336 oldu.

## Top tespiti denemeleri

**Renk tercihi:** görünür sarı top için sabit bir renk tercihi, geliştirmedeki
750 karede mevcut güven seçimini **0 kez** değiştirdi. İlk segmentte top adayı
olan 134 karenin yalnız 5'inde birden çok uygun aday vardı. İkinci segmentte
28 karede aday vardı. Bu örnekte temel sorun çoğunlukla adaylar arasında seçim
değil, yeterli adayın hiç oluşmaması. Renk deneyi `scripts/` altında kaldı.

**Oyuncu çevresinde ROI:** geliştirmeden eşit aralıkla seçilmiş 8 etiketli temas,
her birinde −0,24 / 0 / +0,24 sn kareler. 320×180 arama bölgeleri yalnız tespit
edilen oyuncu ayaklarından seçildi; GT konumu arama bölgesi belirlemedi.
Tam kare adayları 1/8, ROI adayları 2/8 temasa yakın top içerdi; **seçilen doğru
top 1/8'de kaldı**. Bütün adaylarda en yüksek güveni seçmek de artırmadı.
Bu nedenle kontrol verisi üzerinde daha fazla arama yapılıp eşik uydurulmadı.
Tam-video pas artışı veya üretim başarısı iddiası yok.

ROI deneyi 24 karede toplam yaklaşık 4,45 sn ek arama süresi kullandı (duvar saati).
Kalibrasyonlu tanısal tam segment çalıştırmaları 123,9 / 126,6 / 144,5 / 144,0 sn
sürdü. Bunlar tüm aday/renk kanıtını kaydeden tanısal çalıştırmalardır; önceki
62 sn hız rekoruyla adil karşılaştırma veya 30 sn hedefinin başarısı değildir.

## Araçlar ve tekrar üretim

- `calibration_from_keypoints`: veri setinin saha çizgilerini kalibrasyona aktarır;
  `--compare` eski kalibrasyonun aynı çizgilerdeki hatasını verir.
- `cache_ball_candidates`: tüm top adaylarını ve yeni sürümde saha filtresinden
  önceki oyuncu kutularını/renklerini kaydeder. `observation_hook` varsayılan
  kapalıdır; normal hat tüm bu kanıtı diske yazmaz.
- `retrack_cached_candidates`: GPU'yu tekrar çalıştırmadan saha elemesi, takip
  ve renk atamasını karşılaştırır; ROI sınırlamasını belirtir.
- `select_cached_balls`, `probe_player_ball_roi`: başarısız renk/ROI denemelerini
  yeniden üretir. Üretim dedektörünün davranışını değiştirmezler.

```powershell
.\venv-cv\Scripts\python.exe -m scripts.soccertrack_v2.calibration_from_keypoints --keypoints data/tracking/datasets/soccertrack_v2/117092/117092_keypoints.json --width 3840 --height 1906 --out data/tracking/bench/new_landmarks.json --compare data/tracking/calibrations/soccertrack_v2_117092.json
.\venv-cv\Scripts\python.exe -m scripts.soccertrack_v2.cache_ball_candidates --segments 0 3 6 9 --calibration data/tracking/bench/new_landmarks.json --out data/tracking/bench/new_candidates
.\venv-cv\Scripts\python.exe -m scripts.soccertrack_v2.retrack_cached_candidates --cache data/tracking/bench/new_candidates --calibration data/tracking/calibrations/soccertrack_v2_117092.json --out data/tracking/bench/old_retracked
.\venv-cv\Scripts\python.exe -m scripts.soccertrack_v2.replay_events --cache data/tracking/bench/new_candidates --out data/tracking/bench/new_events
```

Olaylar önceki `audit_event_evidence` aracıyla, takım atamaları `evaluate_teams`
ile denetlenir. Eski dondurulmuş hizalama dosyaları aynı tutulur. Kontrol
sonucunu gördükten sonra yeni bir hizalama seçilmez.

Kontroller: **2499 test geçti, 1 atlandı**, 15 mevcut kullanım dışı API uyarısı.
Ruff ve mypy temiz. Mevcut kalibrasyon dosyası, video kayıtları ve maç
veritabanı üzerine yazılmadı. Kalibrasyon/renk/ROI için geniş doğruluk hedefi
geçilmedi; sonraki model çalışmasının gerçek top kutuları ve doğrulanmış oyuncu
kimlikleriyle ayrı eğitim/kontrol verisi gerektirdiği bu deneylerle somutlaştı.
