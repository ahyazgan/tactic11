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

## Bekleyen kullanıcı kararları
- Dedektör v2'yi (rfdetr_soccertrack_ft_v2) üretime almak: ön kayıt dışı ürün kararı.
  Lehine: kesinlik +19 puan, top korunuyor, panorama/klip her eksende daha iyi.
  Aleyhine: bağımsız maçta tespit artışı +2,1 (+3 istenmişti). Alternatif: yeni bir
  bağımsız maçla (Drive'da Challenge/Test klipleri; indirme izni gerekir) yeniden sına.
