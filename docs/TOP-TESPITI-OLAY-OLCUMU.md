# Top tespiti: olaylara karşı ölçüm, teşhis ve aday izi (2026-11-01)

Soru: panoramada sistemin "top" dediği şey gerçekten top mu, ve topu kimin
sürdüğünü (telestrasyonda savunan takım) ne kadar doğru biliyoruz?

## 1. Ölçüm: dokunuş olayları top GT'si yerine

SoccerTrack v2 panoramasında top etiketi yok. Ama `117092_player_nodes.csv` her
topa dokunuşta dokunan oyuncunun saha konumunu veriyor (ilk yarı 1225 dokunuş).
Dokunuş anında top o oyuncunun ayağındadır.

Eşleme GSR oyuncularına karşı bulundu (`scripts/soccertrack_v2/evaluate_ball_events.py`):

- x/y eksenleri yer değiştirmiş ve takıma göre normalize: 30798 iki eksende
  ters, 9834 düz (her takım kendi hücum yönüne göre yazılmış).
- Zaman: GSR karesi = olay_ms·25/1000 + 3; video saniyesi = olay − 0,28.
- Bu eşlemeyle dokunuş konumu en yakın GSR oyuncusuna medyan 1,0 m, %85'i ≤ 2 m.
- Olay takımı → GSR takımı konumla: 30798 → sağ (1), 9834 → sol (0) (%88 çoğunluk).

Ölçütler:

- **dokunuş**: olay anına en yakın karede top ≤ R m → isabet; uzak → yanlış; yok → kayıp.
- **uçuş**: başarılı kısa pasın zaman ortasında top, pasör–alıcı doğru parçasına ≤ R m.
  Topu hep bir oyuncunun ayağına koyan yöntem burada kaybeder.
- **savunan takım** (`eval_telestration --possession-events`): telestrasyonun çizdiği
  karelerde savunan takım, aynı takımın ardışık iki dokunuşu arasındaki (≤ 4 sn)
  sahipliğin tersi mi. Koça giden asıl çıktı bu.

Sınır: takip konumlarının kendisi GSR'ye karşı medyan ~2,4–3 m sapıyor (kalibrasyon +
hayalet tespitler); bu yüzden ana yarıçap 5 m, 3 m ikincil.

## 2. Teşhis: "top"un çoğu saha dışındaki sabit bir nesne

v2 ile üretim takibi (600–960 sn, 1080p koşu 990611):

| | Değer |
|---|---|
| Top bulunan kare | %92,4 |
| Bunların tek bir noktadaki payı (saha x≈58, y≈97) | %78 |
| Dokunuşta top ≤ 5 m | %8,8 |
| Dokunuşta top yanlış yerde | %87,5 (medyan hata 43 m) |
| Çizilen karelerde savunan takım doğru | %78,5 |

Tek nokta, saha sınırının ~310 px dışındaki parlak bir nesne (gece maçı; daha önceki
tanı gündüz kaydında hiç görmemişti, `docs/TOP-SINIR-UYUSMAZLIGI-TANI.md`). Takip her
karede en güvenli adayı seçiyor; hattın saha kontrolü yalnız metreye bakıyor ve TPS
dış kestirimi nesneyi saha içine taşıyor. Dondurulmuş takip koduna dokunulmadı.

Dokunuş anlarında (geliştirme, 80 dokunuş) tam kare dedektör adayları:

| | Ham | Saha dışı karartılmış |
|---|---|---|
| Topa ≤ 5 m aday (güven ≥ 0,1) | %40 | %39 |
| Topa ≤ 5 m aday (güven ≥ 0,4) | %15 | %17 |
| En güvenli aday topa ≤ 5 m | %12 | %17 |

Sahte nesneyi atmak yanlışları siliyor ama dokunuşta isabeti artırmıyor: ayak
dibindeki gerçek top çoğunlukla düşük güvenle bulunuyor ve üretim eşiği (0,3) onu
eliyor. Asıl kaldıraç düşük güvenli adaylar + zaman tutarlılığı.

## 3. Aday kaydı: takip aynı, düşük güvenli toplar yan dosyada

`scripts/track_live_candidates.py` dondurulmuş `track_live`'ı sarar: dedektör 0,1
eşikle kurulur ama hatta yine üretim eşiğinin (0,3) üstü verilir; her örneklenen
karedeki bütün top adayları `<watch>/ball_candidates/<segment>.json` dosyasına yazılır.
Ek GPU işi yoktur.

Doğrulama (aynı segment, iki koşu): 375 karenin hepsinde top ve oyuncular birebir
aynı, top kaynak sayıları aynı (det 217 / roi 35 / interp 86). Karede ortalama 12,8
aday kaydedildi; bunların %23'ü 0,3'ün üstünde.

Adayların çoğu sabit: aynı pikselde segment boyunca duran ışık, çizgi kesişimi gibi
nesneler (bir segmentte 36 hücre). Bunlar ayıklanınca karede ortalama 2,6 aday kalıyor.
Kalanların bir kısmı oyuncu ayakkabısı/çorabı; topu süren oyuncunun ayağındaki gerçek
toptan ayırmak asıl zorluk.

## 4. Aday izi ve ön kayıtlı kontrol sınavı

`app/tracking/ball_track.py`: segmentte sabit pikselde duran adaylar ve işaretli saha
sınırının 80 px dışı atılır; kalan adaylardan fiziksel olarak bağlanabilen (≤ 40 m/sn,
≤ 1,5 sn boşluk) en yüksek puanlı yol dinamik programlamayla seçilir (puan: güven +
bağlantı ödülü − boşluk/mesafe/yeniden başlatma bedeli), ≤ 1 sn boşluklar doğrusal
doldurulur, sonra yanında oyuncu olmadan ≥ 3 sn yerinde duran top atılır.

Geliştirme (600–960 ve 1200–1560 sn, 293 dokunuş): dokunuşta isabet %6,5 → %32,1,
yanlış %90,1 → %52,6, uçuş %19,5 → %51,2; savunan takım %52,3 → %77,0 ve %49,6 → %73,8.
Ayar yalnız burada yapıldı (yeniden başlatma bedeli 0,7 → 1,2; topu son süren oyuncuya
bağlama denendi, kazandırmadı, çıkarıldı).

Ön kayıt `docs/measurements/ball-track-plan.json` (commit 7a577b2) kontrol sonucundan
önce yazıldı. Kontrol 1800–2400 sn (20 segment, hiçbir karar için kullanılmamıştı),
tek sefer (`docs/measurements/ball-track-control.json`):

| Kontrol | Üretim topu | Aday izi | Şart | Sonuç |
|---|---:|---:|---|---|
| Dokunuşta top ≤ 5 m (241 dokunuş) | %0,8 | %19,1 | ≥ +10 | geçti (+18,3) |
| Çizilen karelerde savunan takım doğru | %46,1 | %68,1 | ≥ +5 | geçti (+22,0) |
| Dokunuşta yanlış top | %99,2 | %57,7 | artmasın | geçti |
| Pas uçuşunda top ≤ 5 m (42 pas) | %0 | %50 | ≥ −5 | geçti |
| Sahiplik karelerinde doğru savunan | %43,6 | %63,4 | düşmesin | geçti |
| Uçtan uca blok etiketi (dengeli) | %51,5 | %63,7 | ≥ −3 | geçti |

Karar: canlı telestrasyon aday izini kullanır (`canli_mac --telestration` takibi
`track_live_candidates` ile başlatır, `telestrate_live` topu çizimden önce değiştirir).

## 5. Gündüz, görülmemiş maç (132877): ön kayıtlı ek sınav

132877 SoccerTrack test maçı: eğitimde, ayarda ya da hiçbir kararda kullanılmadı;
gündüz, 4096×1084 panorama. Ön kayıt `docs/measurements/ball-track-daylight-132877-plan.json`
(44758cb) takipten önce yazıldı; indirince videonun başlama vuruşuyla başladığı
görüldü ve zaman varsayımı, hiçbir sonuca bakmadan ek olarak düzeltildi.

- Kalibrasyon: 65 resmî saha işareti, bir-dışarıda doğrulama 1,53 m.
- Olay eşlemesi yalnız takip edilen oyunculardan (`derive_event_mapping`): eksen
  çevirmesi ve takım tarafı belirgin (oylar 57:19, 56:18); zaman kayması önceden
  sabitlenen −0,28 sn (oyunculardan bulunan −0,20 sn ile uyumlu). GSR yok; savunan
  takım `eval_defending_events` ile ölçüldü (117092'de `eval_telestration` ile birebir aynı sonucu verdiği doğrulandı).

| 600–1200 sn (20 segment) | Üretim topu | Aday izi | Şart | Sonuç |
|---|---:|---:|---|---|
| Dokunuşta top ≤ 5 m (299 dokunuş) | %71,9 | %73,2 | ≥ −2 | geçti |
| Dokunuşta yanlış top | %20,4 | %22,1 | ≤ +2 | geçti |
| Pas uçuşunda top ≤ 5 m (79 pas) | %91,1 | %91,1 | ≥ −5 | geçti |
| Çizilen karelerde savunan takım doğru | %82,7 | %81,3 | ≥ −2 | geçti |
| Sahiplik karelerinde doğru savunan | %82,7 | %81,3 | ≥ −2 | geçti |
| Çizim kapsaması | %99,0 | %100 | — | — |

GSR'ye karşı ek ölçüm (betimsel, `docs/measurements/daylight-132877-gsr-telestration.json`):
takım rengi uyumu %91,6, blok etiketi dengeli %80,8 / tam %85,0, savunma hattı
medyan 1,9 m, pres uyumu %93,8, kapsama %100 (aday izi; üretim topuyla dengeli %80,2).

Okuma: gündüzde üretim topu zaten iyi; aday izi kazandırmıyor, kaybettirmiyor.
Gecedeki kazanç (+22 puan savunan takım) ışık gibi sahte adayları ayıklamaktan
geliyordu. Aday izi varsayılan kalır. Sonuç: `docs/measurements/ball-track-daylight-132877-result.json`.

## 6. Başka stadyum (132831): ön kayıtlı sınav — geçmedi

132831 SoccerTrack Challenge maçı: başka saha, başka kamera yerleşimi, gündüz, 3840×1504.
Ön kayıt `docs/measurements/ball-track-stadium-132831-plan.json` (60e7b47) indirmeden önce.
Kalibrasyon 65 işaret, bir-dışarıda 1,57 m. Olay eşlemesi oyunculardan: eksen
çevirmesi bulundu, ama **takım tarafı bulunamadı** — iki olay takımı da takibin aynı
takımına oy verdi (27:18, 19:9) ve oylar segmentten segmente tutarsız.

| 600–1200 sn (20 segment) | Üretim topu | Aday izi | Şart | Sonuç |
|---|---:|---:|---|---|
| Dokunuşta top ≤ 5 m (339 dokunuş) | %35,4 | %42,2 | ≥ −2 | geçti |
| Dokunuşta yanlış top | %36,0 | %41,0 | ≤ +2 | **kaldı (+5,0)** |
| Pas uçuşunda top ≤ 5 m (70 pas) | %65,7 | %71,4 | ≥ −5 | geçti |
| Savunan takım (D4, D5) | — | — | ≥ −2 | **ölçülemedi** |

Karar (plan gereği): sınav geçmedi; kod ve ölçüt değişmedi, sınır olarak yazıldı.
Aday izi bu sahada daha çok kareye top koyuyor (kayıp %28,6 → %16,8): 23 dokunuş
daha isabetli, 17 dokunuş daha yanlış.

GSR'ye karşı (betimsel, `docs/measurements/venue-132831-gsr-telestration.json`): takım
rengi %76,7, blok dengeli %64,3, hat medyanı 5,2 m, karede eşleşen oyuncu 9,1
(132877: 15,2). Sonraki ölçüm (`venue-132831-detector-and-geometry.json`) bunun
tespit değil referans geometrisi olduğunu gösterdi: MOT klibinde v2 tespit %96,1,
panoramada karede 22,4 takip edilen oyuncu; GSR konumları ile kalibrasyon arasında
en boyunca 2–3 m sistemli kayma.

Bulgular:
- ~~Takım ataması bu sahada çalışmıyor~~ — **sonradan düzeltildi**
  (`docs/TAKIM-AYRIMI-GUNES.md`): göz etiketli 98 kutuda üretim net renkli
  oyuncularda %97 doğru; hata, güneşte beyaza dönen uzak oyuncuların hepsinin "ev"
  sayılması. "Bir takımda 12+ oyuncu" oranı takım kalitesinin göstergesi değil
  (iyi ayrılan 132877'de %57). Dokunuş oylarının tutarsızlığı bu sahada
  dokunuşların yalnız %23'ünün 2 m içinde takip edilen oyuncuya denk gelmesinden.
- Dokunuşların yalnız %23,5'inde 2 m içinde takip edilen oyuncu var (132877: %52,
  117092: %30); dokunuş hatası medyanı ~5 m.

Ayrıca geliştirmede görüldü (sınav dışı): aday izi topu değiştirirken karedeki
"topu tutan oyuncu" ve sahip takım alanları eski topa göre kalıyor. Yeniden hesaplamak
ölçülebilir fark yaratmadı (gece %77,0 → %77,7 ve %73,8 → %71,4; gündüz %81,3 → %81,2);
davranış değiştirilmedi, veri tutarsızlığı olarak iş listesinde.

## 7. Pas listesini düzeltilmiş topla yeniden türetmek — iki ön kayıtlı sınav, ikisi de geçmedi

Veritabanındaki paslar (`video_passes`) karelerdeki aktör/sahip alanından türer
(`passes.extract_passes`); top izi bu alanlara dokunmadığı için paslar eski topa
göre kalıyordu. Geliştirmede (990721/990722) aktörü yeni topa göre yeniden kurmak
(`ball_track.recompute_actors`, `build_frame` kuralı) eşleşen pası 6 → 20 ve 1 → 18
yaptı (olay pasları ±1,5 sn, 6 m).

Plan 1 (`pass-refined-ball-plan.json`, c7038aa) kontrol: gece 990723'te eşleşen
pas 0/97 → 15/97, kesinlik 0 → %11,5; gündüz 990741'de duyarlılık %67,8 → %68,5,
kesinlik %69,2 → %67,6. "Duyarlılık ≥ 2×" şartı %68 tabanda ulaşılamazdı (plan
tasarım hatası; gevşetilmedi), ayrıca yeniden kurulan sahiplik telestrasyonun savunan
takımını gecede −4,2 puan düşürdü → geçmedi.

Plan 2 (`pass-refined-ball-plan-2.json`, 17ddf5f; aşağı yönlü olmama + bir pencerede
kazanç) taze pencereler: gece 990731 eşleşen 0/49 → 5/49; 132831 (7 segment) 11/234 →
12/234 ama kesinlik %37,9 → %30,0 (şart ≥ −3) ve 990731'de savunan takım %63,8 →
%42,1 (231 kare) → geçmedi. Sonuçlar `pass-refined-ball-result.json`, `-result-2.json`.

Karar: paslar yeniden türetilmedi; `recompute_actors` canlı yoldan çıkarıldı, araç
olarak duruyor. Öğrenilen: telestratörün kendi sahiplik kuralı (≤ 4 m en yakın +
pencere çoğunluğu), kare başına 2,5 m aktörden daha sağlam; pas motorunun asıl
sınırı gecede top görünürlüğü (üretimde 10 dakikada 2–3 pas).

## Sınırlar

- Gece: tek maç, 10 dk kontrol. Gündüz: tek maç (132877), 10 dk; uçtan uca blok
  etiketi ve takım rengi gündüzde ölçülmedi (GSR indirilmedi).
- Dokunuşta top hâlâ çoğunlukla yanlış ya da yok (%58 / %23): ayak dibindeki top ile
  başka oyuncunun ayakkabısı ayrılamıyor. Kazanç asıl olarak "top kimde" tarafında.
- Veritabanı: `canli_mac --telestration` düzeltilmiş kareleri, takip işçisinin
  kendi aktarımı bittikten sonra aynı zaman damgalarına yeniden yazar (güncelleme,
  çoğaltma yok). Doğrulama (990723, 30–31,5 dk, 1125 kare): veritabanındaki topun
  saha dışı ışıkta olma payı %99,8 → %0; topu olan kare 1125 → 863. Takipten
  çıkarılan paslar (`derived_passes`) hâlâ ham topla hesaplanır.
- Takip konumlarının kendisi GSR'ye karşı medyan ~2,4–3 m sapıyor; 5 m yarıçap bunu taşır.

## Tekrar üretim

```powershell
venv-cv\Scripts\python.exe -X utf8 -m scripts.track_live_candidates --watch data/tracking/live/990723 --match-id 990723 --home-team 30798 --away-team 30799 --segment-seconds 30 --start-minute 30 --camera static --tiles 4 --track-fps 15 --fps 12.5 --calibration data/tracking/calibrations/soccertrack_v2_117092_landmarks.json --weights data/tracking/models/rfdetr_soccertrack_ft_v2 --once
venv-cv\Scripts\python.exe -m scripts.clean_ball_frames --frames data/tracking/live/990723/frames --out data/tracking/live/990723/frames_ball --candidates data/tracking/live/990723/ball_candidates --calibration data/tracking/calibrations/soccertrack_v2_117092_landmarks.json
venv\Scripts\python.exe -X utf8 -m scripts.soccertrack_v2.evaluate_ball_events --frames data/tracking/live/990723/frames_ball --radius 5
venv-cv\Scripts\python.exe -X utf8 -m scripts.soccertrack_v2.eval_telestration --frames "data/tracking/live/990723/frames_ball/seg_*.json" --gt data/tracking/bench/gsr_first_half_gt.npy --alignment data/tracking/bench/signal_quality_alignment.json --calibration data/tracking/calibrations/soccertrack_v2_117092_landmarks.json --out out.json --reference-default --possession-events
```

Segmentler panoramadan `ffmpeg -ss <sn> -t 30` ile kesildi (kare hizası mevcut
990401 segmentleriyle birebir doğrulandı); GSR tablosu
`export_gt --start-frame 1 --end-frame 67400`.
