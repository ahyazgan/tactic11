# Canlı mod kılavuzu (kamera → panel → telestrasyon)

Bir maçı canlı izlerken takım şekli, pres ve hat sinyallerini antrenör panelinde,
telestrasyonlu (halka, blok çizgileri, faz etiketi) videoyu da aynı ekranda görmek
için adım adım yol. Tüm komutlar proje kökünden (`football-intelligence`).

## Ne alırsın, ne almazsın

- Her 30 sn'lik segment işlenince panel güncellenir; ekranda **gecikme** yazar.
- Bu dizüstü bilgisayarda (RTX 5060, 8 GB) 4K panorama segmenti ~100 sn'de
  işlenir: gerçek zamanın ~3 katı yavaş, gecikme maç boyunca birikir. Devre arası
  ve 60–80. dk kararları için uygundur, son dakika anlık kararı için değil.
- Telestrasyon yalnız **sabit kamerada** çalışır (yayın kamerasında takip var,
  telestrasyon yok).
- Doğruluk (SoccerTrack gece maçı, gerçek konumlara karşı): blok etiketi dengeli
  doğruluk %71–75, savunma hattı hatası medyan ~6 m; takım ataması ~%70.
  Ayrıntı: `docs/OTOMATIK-TELESTRASYON.md`, `docs/TESPIT-KALITESI-DENETIMI.md`.

## 1. Başlat

```powershell
BASLAT.bat
```

Sunucu ve panel açılır. Canlı veri için `frontend/.env.local` içinde
`NEXT_PUBLIC_DEMO_MODE=false` olmalı (demo modunda canlı kartlar gizlenir).

## 2. Kalibrasyon (stadyum başına bir kez, sabit kamera)

Panelde **Video Analiz → kalibrasyon** (`/video-tracking/calibrate`): videodan bir kare al, saha işaretlerine
(köşeler, ceza sahası köşeleri, orta nokta, orta yuvarlak…) tıkla, kaydet.

- **En az 5 nokta** gir. 4 noktaya her homografi kusursuz oturur; hata ölçülemez
  ve telestrasyon bu kalibrasyonla çizgi/etiket çizmez ("doğrulanmamış").
- Noktalar sahanın farklı bölgelerine yayılsın; çizilen saha çizgileri kareye
  oturmuyorsa kaydetme.
- Otomatik öneri: `venv-cv\Scripts\python.exe -m scripts.propose_calibration --video mac.mp4 --at-seconds 30 --out data/tracking/calibrations/saha.json --preview onizleme.png`.
  Öneri saha çizgilerine karşı doğrulanır (`line_validation_error_m`); çizgiler
  yeterince eşleşmezse kalibrasyon doğrulanmamış kalır. Önizlemeye mutlaka bak.

Telestrasyon kalibrasyon hatası 2,0 m'yi aşarsa çizgi/etiket çizmez.

## 3. Canlı modu çalıştır

```powershell
venv-cv\Scripts\python.exe -m scripts.canli_mac --source rtsp://kamera/stream --match-id 990201 --home-team 611 --away-team 612 --calibration data/tracking/calibrations/saha.json --telestration --home-attack x+
```

- `--source`: video dosyası (gerçek hızda prova), `rtsp://…` (stadyum/kulüp
  kamerası) ya da `https://…/index.m3u8` (canlı yayın).
- `--home-attack x+` / `x-`: ev sahibi kalibrasyonun saha x ekseninde hangi
  yöne hücum ediyor. Devre arasında yön değişir; ikinci yarıda tersini ver.
  `auto` çoğu zaman karar veremez (kaleciler görünmüyor).
- `--height 1080`: segmentleri 1080p'ye indirir; hız için ilk denenecek ayar.
- Provada `--source mac.mp4` dosyayı gerçek hızda akıtır: "sisteme kaç dakika
  geriden gelir" sorusunun dürüst cevabı budur.

## 4. Panel

**Maç-içi Karar** (`/decisions/live`): maçı seç, **Canlı mod** kutusunu işaretle (5 sn'de bir yenilenir).
"Canlı Telestrasyon" kartı son işlenen segmenti oynatır; başlıkta faz etiketi,
segment dakikası ve çizilen kare oranı görünür.

## Sorun giderme

| Belirti | Neden / çözüm |
|---|---|
| Telestrasyonda yalnız halkalar var | Kalibrasyon doğrulanmamış (4 nokta, oyuncudan türetilmiş ya da çizgilerle eşleşmeyen öneri) veya hata > 2 m. İşçi başlarken uyarı yazar. |
| Etiket hiç çıkmıyor | Hücum yönü verilmedi (`--home-attack`) ya da savunan takımdan 6 oyuncu görünmüyor. |
| Gecikme sürekli artıyor | Bilgisayar segmenti 30 sn'den uzun sürede işliyor. `--height 1080` dene. |
| Kart "canlı telestrasyon yok" diyor | `--telestration` verilmedi ya da henüz ilk segment işlenmedi (`data/tracking/live/<maç>/tele/latest.json`). |
| Segment atlandı | `data/tracking/live/<maç>/tele/seg_XXXX.error.json` hatayı içerir; akış durmaz. |
