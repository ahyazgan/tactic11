# Çalışma günlüğü — 1 Kasım 2026 (otonom oturum, 12:00'ye kadar)

Kullanıcı isteği: top sorununu çöz, diğer geliştirmeleri yap, durmadan 12:00'ye kadar
çalış; sorun olursa kaydet ve üzerine devam et. İş listesi: `BACKLOG.md` → "Claude
otonom oturum 2026-11-01". Her kayıt saat + ne yapıldı + sonuç/sorun.

## 06:40 — Top kaybı teşhisi
- TeamTrack test bölümünde (gerçek top etiketi, 1470 görüntü / 136 top) ince ayarlı
  model topu UNUTMAMIŞ: bulma %79,4 → %81,6, kesinlik %94,7 → %96,5.
- 117092 panoramasında kayıp gerçek: top tespitli kare %16,4 → %9,8 (hepsi saha içinde,
  oyuncu yakınında); oyundaki 37 olay anında topu görme %35 → %16.
- Sonuç: kayıp SoccerTrack kamerasına özgü; MOT dilimlerindeki etiketsiz toplar modele
  bu kamerada "top = arka plan" öğretti.
- Plan: v2 — MOT dilimlerinde topları eski modelle etiketle (öğretmen), 128058'i bağımsız
  test için tamamen ayır.

## 06:45 — Dedektör v2 başlatıldı
- Ön kayıt `docs/measurements/detector-finetune-v2-plan.json`: öğretmen top etiketleri
  (eski model, güven ≥0,5, oyuncu ayak bandında, oyuncuya ≤3 boy), 128058 bağımsız test.
- Öğretmen 480 eğitim karesinin 74'ünde top etiketledi (top etiketi 345 → 419).
- 128058 başlangıç (eski model): klip recall %92,3, kesinlik %71,9.
- Eğitim arka planda (~55 dk).

## 06:50 — Canlı telestrasyon (PR #301, birleşti)
- `scripts/telestrate_live.py` + `canli_mac --telestration`; segment başına H.264 video,
  marks ve latest.json; hata kaydı + devam. Duman testi: 2 segment 57 sn.
- Sorun (çözüldü): geçici dosya `.mp4.part` → yazıcılar biçimi uzantıdan seçiyor; `.tmp.mp4`.

## 07:00 — Panel kartı (PR #302, birleşti)
- API `/tracking/live/{id}/telestration` (+ video), panelde "Canlı Telestrasyon" kartı.
- Kayıt: panel görsel doğrulaması YAPILMADI — yerel kurulum demo modunda, `.env.local`
  değiştirilmedi.

## 07:05 — Kalibrasyon doğrulama açığı (PR #303)
- Sorun (benim #298 kapımın yan etkisi): `propose_calibration` yapay ızgara noktaları yazıyor
  → kapı her öneriyi "doğrulanmamış" sayıyordu. Çözüm: saha çizgilerine karşı yön gruplu
  doğrulama (`line_validation_error_m`); tek medyan çizgi yönündeki kaymayı görmüyordu
  (test yakaladı).
- Ek açık: 4 noktalık homografi her zaman 0 hata → en az 5 nokta şartı.
- Kayıt: VLSC ve pan_zoom karelerinde `propose_calibration` kendi %90 kapısını geçemedi
  (önceden var olan durum) — gerçek karede çizgi doğrulaması gösterilemedi.
- `docs/CANLI-MOD-KILAVUZU.md` eklendi.

## 07:50 — Dedektör v2 sonucu
- 7 şartın 6'sı geçti: top kaybı çözüldü (olay anında top %35 → %38; v1 %16), 128058
  kesinlik %71,9 → %90,8, panorama tespit %60,7 → %61,9. Kalan: 128058 tespit +2,08
  (şart +3). Ön kayıt gereği kabul edilmedi; üretim değişmedi.
- Sorun (çözüldü): değerlendirme zinciri yanlış dalda çalıştı (evaluate_ball.py yoktu);
  dal değiştirilip eksik ölçümler tekrarlandı.

## 08:50 — Veritabanı ön kontrolü (PR #308, birleşti)
- Sorun: prova ingest'i `.env`'deki şablon `DATABASE_URL` (`host`) yüzünden 12 segmentte de
  reddedildi; gecikme göstergesi "işlenen dk 10.0"da kaldı. `canli_mac` artık başlamadan
  bağlantıyı dener, hata sınıfı + ilk satırı yazıp 2 ile çıkar.
- Sorun (çözüldü): ilk test kapalı porta bağlanıyordu; bu makinede güvenlik duvarı yanıt
  vermediği için 30 sn zaman aşımına düştü. Test ağsız hale getirildi (açılamayan sqlite yolu).

## 09:00–09:20 — Doğru veritabanıyla prova
- 12 segment, 0 hata, 1500 kare DB'de. Segment 96 sn (3,2× yavaş), gecikme segment başına
  ~66 sn büyüyor; 6. dakikada 824 sn. `docs/measurements/live-rehearsal-990601.json`.

## 09:20–09:46 — Hız matrisi (ön kayıtlı)
- torch/onnx × 4/3/2 dilim. Hiçbir hızlı ayar şartı geçmedi (3 dilim −5,8, 2 dilim −23,6
  puan); ONNX aynı tespit, ~2× yavaş. Öneri değişmedi. Gerçek zamana ulaşılmadı.

## 09:50 — Canlı kalma modu (`--keep-up`)
- Takip boşalınca en yeni segment işlenir, aradakiler atlanır (incoming/ içinde kalır);
  dakika segment adından okunur. API segment adı kuralı genişletildi.
- Sorun (çözüldü): arka plan komutu `frontend/` klasöründen çalıştı, göreli yollar bulunamadı.

## 10:20 — Savunan oyuncu eşiği deneyi (PR #313, ön kayıtlı, geçmedi)
- 6 → 5/4: doğruluk bozulmadı, kapsama kazancı +5 puan şartının altında (4: +5,2 / +4,9).
  Üretim 6'da kaldı.

## 10:22 — Sorun: kilit dosyası CI'da reddedildi (PR #314)
- #312 yerel npm 11.6.2 ile üretilen kilitle birleşti; CI'nin npm 11.19.1'i `npm ci`'yi
  reddetti, e2e/live_auth kırmızı (zorunlu kontrol olmadıkları için auto-merge birleştirdi).
  Kilit CI'nin npm sürümüyle yeniden üretildi; e2e/live_auth yeşil.
- Kayıt: Vercel ücretsiz plan dağıtım sınırına takıldı ("24 saat sonra"), kodla ilgisi yok.

## 10:30–11:05 — Dedektör v2 telestrasyonda (betimsel)
- Aynı komut, yalnız ağırlık: iki pencerede de v2 her ölçütte iyi (dengeli doğruluk
  %67→%77 ve %53→%82; hat medyanı 5,9→2,6 m ve 6,4→1,9 m). Üretim değişmedi.
- Açık soru: 1080p provasında eski model (%67,3) 4K koşusundan (%73,2) düşük; ayarları
  kaydedilmemiş koşuyla karşılaştırma temiz değil.

## 11:05–11:28 — 4K ve 1080p (PR #316)
- Aynı model ve komut: 4K çizilen kare %78,2 / 1080p %70,9; süre aynı (~99 / ~96 sn).
  Panoramada 1080p önerisi kaldırıldı; README'deki "serbest kazanç" sonucu drone klibine ait.

## 13:45 — Dedektör v2 üretimde (kullanıcı kararı)
- Kullanıcı "v2'ye geç" dedi. `canli_mac` sabit kamerada ve API işleri varsayılan
  olarak v2 kullanıyor; yayın/operatörlü kamera değişmedi (v2 orada ölçülmedi).
- TeamTrack doğrulamasında (drone/yan açı) v2 eşit: F1 0,822 / 0,822, mAP50 −2,3 puan.

## 14:00–16:29 — Top tespiti (PR açık)
- Panoramada top GT'si yerine dokunuş olayları (1225, konum + zaman eşlemesi GSR'ye karşı
  bulundu: eksenler yer değiştirmiş, takıma göre normalize; medyan 1,0 m).
- Teşhis: üretim "topu"nun %78'i saha dışındaki sabit bir parlak nesne (gece); dokunuşta
  isabet %9, savunan takım %52 (12,5 fps, 4K).
- Saha dışını karartma denendi; sahte nesneyi siliyor ama isabeti artırmıyor → bırakıldı.
- `track_live_candidates`: dondurulmuş takibi değiştirmeden düşük güvenli top adaylarını
  kaydediyor (çıktı birebir aynı, doğrulandı). `ball_track`: sabit aday ayıklama + zaman
  tutarlı iz (dinamik programlama).
- Ön kayıtlı kontrol (1800–2400 sn) 6/6 geçti: dokunuşta isabet %0,8 → %19,1, savunan
  takım %46,1 → %68,1, uçtan uca blok etiketi %51,5 → %63,7.
- Sorunlar: durdurduğumu sandığım eski takip koşusu GPU'yu paylaşıp her segmenti 2 kat
  yavaşlattı (süreçler ayrıca kapatıldı); paralel değerlendirmeler kabuk kapanınca
  sessizce öldü (tek arka plan işinde `wait` ile yeniden koşuldu).

## 16:30–17:10 — Panel gerçek modda, top veritabanında, tam zincir provası
- Panel ilk kez gerçek modda açıldı (API 8100 + next dev 3100; kullanıcının 3000'deki
  demo derlemesine dokunulmadı). Canlı Telestrasyon kartı videoyu oynatıyor.
- Bulunan hata: genel bakış, kulübün oyuncusu yokken "backend bağlı değil" diyordu → ayrıldı (PR #319).
- Düzeltilmiş top artık veritabanına da yazılıyor; takip aktarımı bittikten sonra (PR #319).
  990723'te veritabanındaki topun ışıkta olma payı %99,8 → %0.
- Segment boyu sahiplik yumuşatması denendi: geliştirmede tutarlı kazanç yok → alınmadı.
- Tam zincir canlı prova (990731, gerçek hız, keep-up): hata 0, her segment adaylı/düzeltilmiş/
  aktarılmış/çizilmiş; panel başlığı "akış bitti · atlanan 6 segment".
- `docs/VIDEO-DOGRULUK-KARNESI.md`: kulübe verilecek tek sayfalık doğruluk özeti.

## 17:15–18:50 — Gündüz sınavı (görülmemiş maç 132877)
- Disk 6,2 GB boştu; kullanıcı onayıyla gereksiz 12 test klasörü silindi (→ 15 GB).
- Drive küçük resimleriyle 4 kullanılmamış maçın dördünün de gündüz olduğu görüldü;
  132877 seçildi, yalnız ilk yarı + olay dosyaları indirildi (3,3 GB).
- Ön kayıt (44758cb) takipten önce; indirince videonun başlama vuruşundan başladığı
  görüldü → zaman varsayımı sonuçtan önce ek olarak düzeltildi.
- 5/5 geçti (aşağı yönlü değil): savunan takım %82,7 → %81,3, dokunuş %71,9 → %73,2.
  Gündüzde sistem çok daha iyi; top izinin gece kazancı ışık adaylarından.

## 18:55–20:10 — Başka stadyum sınavı (132831) — geçmedi
- Ön kayıt (60e7b47) indirmeden önce. Disk iki kez daraldı: işi biten 132877 panoraması
  (3,3 GB, yeniden indirilebilir) ve 117092'den kesilmiş segment videoları (990721–23,
  6,2 GB; panoramadan yeniden kesilebilir, kareler/adaylar duruyor) silindi.
- Sonuç: D1/D3 geçti, D2 (yanlış top +5,0) kaldı; D4/D5 ölçülemedi — takım ataması bu sahada
  iki takımı tutarlı ayıramadı. Kod değişmedi; sınır karnede.
- Bulunan veri tutarsızlığı: aday izi topu değiştirirken aktör/sahip alanı eski topta kalıyor;
  yeniden hesaplamak geliştirmede fark yaratmadı → değiştirilmedi.

## 20:10–21:05 — Takım ayrımı (132831): teşhis doğru, çözüm kontrolü geçmedi
- Göz etiketli 98 kutu: üretim net renkte %97 doğru; "takım ayrımı çalışmıyor" iddiası
  düzeltildi. Hata güneşte beyaza dönen uzak oyuncularda (15/15 tek takım, 5'i mavi tonlu).
- Çözüm: takip başına gövde ortanca rengi kaydı (frozen koda dokunmadan) + renk oranı
  ana ekseninde yeniden atama; geliştirmede soluk 5 maviyi düzeltti.
- Ön kayıt (c00188d) → kontrol: 1/4 geçti. Soluk hata kontrol karelerinde tekrarlamadı
  (üretim 14/16), gece uyumu 0,75 → 0,54 çöktü, atanan payı −13 puan. Canlıdan çıkarıldı,
  araçlar kaldı.
- Tuzak: taze takip koşusunda ev/deplasman adı ilk segmentin küme büyüklüğünden
  geliyor; 990753'te mavi "ev" oldu, etiket eşlemesi buna göre not edildi.

## 21:10–22:05 — Pas listesi düzeltilmiş topla: iki ön kayıt, ikisi de geçmedi
- Geliştirmede aktörü yeni topa göre kurmak eşleşen pası 6→20 / 1→18 yaptı.
- Plan 1: gece 0→15 eşleşme ama "≥2×" şartı %68 tabanlı gündüzde ulaşılamazdı (tasarım
  hatası, gevşetilmedi) ve sahiplik yeniden kurulunca savunan takım −4,2.
- Plan 2 (taze pencereler, aşağı yönlü olmama): 132831'de kesinlik −7,9, 990731'de savunan
  takım −21,7 → geçmedi. recompute_actors canlı yoldan çıkarıldı, araç olarak kaldı.

## 22:05–22:30 — Kalibrasyon ön kontrolü, temizlik
- `canli_mac --telestration` başlamadan kalibrasyonu telestrasyon kapısından geçiriyor;
  geçmeyen kalibrasyonla başlamıyor (`--allow-unverified-calibration` ile zorlanır).
- Ölçüm dosyalarındaki saat tahminleri yanlıştı; commit zamanına işaret edecek şekilde düzeltildi.
- Tam paket 3274 test yeşil. PR #323 CI bekliyor (takım + pas sonuçları + ön kontrol).

## 22:30–23:00 — Gündüz maçı GSR'ye karşı (karne tamamlandı)
- 132877 GSR tablosu indirildi (2,7 GB; export sonrası silindi). Hizalama −24 kare
  (oyuncu uzaklığı taramasıyla). 990741 (10 dk): takım rengi %91,6, blok etiketi dengeli
  %80,8, hat medyanı 1,9 m, pres %93,8, kapsama %100. Karnede gündüz sütunu doldu.

## 23:00–23:25 — Üçüncü stadyum GSR'ye karşı
- 132831 GSR (base 3917000000, hizalama −21): takım %76,7, blok dengeli %64,3, hat 5,2 m,
  karede eşleşen oyuncu 9,1. Sınır takım rengi değil tespit/konum. Karne güncellendi.

