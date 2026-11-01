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

## 10:00 — Canlı kalma provası (PR #309, birleşti)
- `--keep-up` ile aynı 6 dk: 5/12 segment işlendi, gecikme 96–116 sn'de sabit (önce 824 sn'ye
  büyüyordu), dakikalar adlarla birebir. `docs/CANLI-HIZ-VE-PROVA.md`.

## 10:03 — Paralel işçi ölçümü
- Tek takip işçisinde GPU ort. %76 (p90 %88), 3,4/8 GB → ikinci işçi en çok ~1,3×; denenmedi.

## 10:05 — Gecikme panelde (PR #310)
- `canli_mac` `status.json` yazar; API telestrasyon yanıtına beyaz listeli `status` ekler;
  kart "gecikme 1 dk 45 sn · atlanan 2 segment" gösterir.
- Kayıt: panel görsel doğrulaması yapılmadı (yerel kurulum demo modunda; kart demo modda gizli).

## 10:09 — Atlama sonrası telestrasyon durumu (PR #311)
- Atlanan segmentten sonra telestratör sıfırlanır (> 2 sn boşluk). Yeniden işlemede
  sıfırlama yalnız üç boşlukta oldu; bedeli ~1 sn sahiplik bekleme.

## 10:12 — Sorun: Next.js kritik güvenlik açığı (PR #312)
- CI e2e `npm audit` adımında düştü: next 16.0–16.4.0 için yeni kritik danışmalar (RCE).
  Benim değişikliğimden değil; frontend'e dokunan bütün PR'ları bekletiyordu.
  next + eslint-config-next 16.4.3; yerelde audit 0, tsc/eslint/build temiz.

## Bekleyen kullanıcı kararları
- Dedektör v2'yi (rfdetr_soccertrack_ft_v2) üretime almak: ön kayıt dışı ürün kararı.
  Lehine: kesinlik +19 puan, top korunuyor, panorama/klip her eksende daha iyi.
  Aleyhine: bağımsız maçta tespit artışı +2,1 (+3 istenmişti). Alternatif: yeni bir
  bağımsız maçla (Drive'da Challenge/Test klipleri; indirme izni gerekir) yeniden sına.
