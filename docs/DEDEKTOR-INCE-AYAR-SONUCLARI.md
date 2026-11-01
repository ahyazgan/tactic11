# Dedektör ince ayarı (SoccerTrack MOT): ön kayıtlı sonuç

1 Kasım 2026. **Model kabul şartlarının üçünü geçmedi; üretim ağırlıkları değişmedi.**

## Neden

Tespit denetimi (`docs/TESPIT-KALITESI-DENETIMI.md`) GT oyuncularının yaklaşık
yarısının kaçırıldığını, dedektörün çalışma ayarlarının (dilim, eşik) bunu
değiştirmediğini gösterdi. Model `rfdetr_mixed_small` yalnız TeamTrack verisiyle
eğitilmişti.

## Veri ve düzen

- Kaynak: SoccerTrack Challenge 2025 organizatörlerinin herkese açık Drive klasörü
  (ScoccerChllenge2025 / Training Dataset); kullanıcı izniyle 6 klip indirildi
  (~1,95 GB, `data/tracking/datasets/soccertrack_mot/`, git dışı). Klipler 4096×1080,
  25 fps, her karede 22 gerçek oyuncu kutusu (MOT). Top etiketi yok.
- Ön kayıt: `docs/measurements/detector-finetune-plan.json` (`e8f6b7c`, veri seti ve
  eğitimden önce). Eğitim 117093, 118575, 118576, 118577; checkpoint seçimi 128058;
  test 117092 (gece) — eğitimde ve seçimde hiç kullanılmadı.
- Dilim: klipte 3 satır (oyuncu/dilim yüksekliği 0,114; üretim panoramasında 0,123).
  Her 50. kare. Top unutulmasın diye TeamTrack veri seti (top etiketli) aynı
  bölünmelere eklendi: eğitim 6624 görüntü (2656 SoccerTrack dilimi).
- Eğitim: `rfdetr_mixed_small`'dan başlayarak 8 epoch, lr 1e-4, 512 çözünürlük,
  52 dk (RTX 5060 Laptop). Doğrulama mAP50 0,806 → 0,837 (en iyi checkpoint).
- Ölçüt kutu biçiminden bağımsız AYAK NOKTASI eşleşmesi (≤0,5 × GT kutu
  yüksekliği). IoU kullanılmadı: TeamTrack ile eğitilmiş model MOT kutularından
  geniş çizer; MOT ile eğitilen model yalnız biçimi öğrenerek IoU'da iyileşmiş
  görünürdü (aynı oyuncularda IoU ≥0,3 %41–77, ≥0,5 %9–45).

## Sonuç (117092, eğitimde görülmemiş)

| Ölçüt | Eski | İnce ayar | Şart | Sonuç |
|---|---:|---:|---|---|
| Klip tespit oranı (240 kare) | %75,04 | %79,83 | ≥ +5 puan | geçmedi (+4,79) |
| Klip kesinliği | %85,15 | %91,31 | ≥ −2 puan | geçti |
| Panorama tespit oranı (seg. 1, 5, 9; çizgi kalibrasyonu) | %60,7 | %62,0 | ≥ +3 puan | geçmedi (+1,3) |
| Panorama hayalet payı | %34,1 | %36,1 | ≤ +3 puan | geçti |
| Panoramada top tespiti olan kare | %16,4 | %9,8 | ≥ 0,8 × eski | geçmedi (0,60×) |

Bölgesel klip tespit oranı: sol uç uzak %25 → %75, sol yakın %52 → %61, sağ uzak
%76 → %79, orta yakın %91 → %95. Panoramada uçlar %53,9 → %54,1, uzak bant
%44,2 → %43,1; "iyi" tespit payı %47,5 → %51,0. Hız aynı mimari: panorama
segmenti 92–102 sn → 96–124 sn (ölçüm gürültüsü içinde), klipte kare başına
0,18 → 0,12 sn.

Okuma: model SoccerTrack kliplerinde belirgin daha iyi (özellikle sol uç ve
yanlış alarm), ama bizim panoramamızdaki kazanç küçük. Klipler ile panorama aynı
kamera sisteminden ama farklı izdüşümde (4096×1080 ve 3840×1906); panorama
denetimi kalibrasyon hatasını da taşır. Top tespiti %40 düştü: TeamTrack verisi
karıştırılmasına rağmen SoccerTrack dilimlerindeki etiketsiz toplar modele "top =
arka plan" öğretti (eski modelin top tespitlerinin bir kısmı projektör ışığıdır;
GT olmadığından gerçek top kaybı ölçülemedi, şart bu yüzden koruyucu).

Ön kayıt gereği veri bölünmesi, eğitim ayarı, checkpoint ve şartlar sonradan
değiştirilmedi. Ağırlıklar yerelde `data/tracking/models/rfdetr_soccertrack_ft`
(git dışı); meta ve eğitim eğrisi `docs/measurements/detector-finetune-*`.

## Sıradaki adımlar

- Top sorununu ayırmak: oyuncu tespiti için ince ayarlı, top için eski modeli
  kullanmak (iki model, iki kat süre) ya da top başlığını dondurup ince ayar.
- Panoramaya özgü veri: kliplerin izdüşümü yerine panoramanın kendisinden etiket
  (GSR konumları + doğrulanmış kalibrasyon + tespit iyileştirmesi).
- Her yeni deneme yeni bir test maçı ister; 117092 artık bu soruda kullanıldı.

## Tekrar üretim

```powershell
venv-cv\Scripts\python.exe -X utf8 -m scripts.soccertrack_v2.build_mot_dataset --clips-dir data/tracking/datasets/soccertrack_mot --train 117093 118575 118576 118577 --valid 128058 --base-dataset data/tracking/datasets/teamtrack_mixed --tiles 3 --every 50 --out data/tracking/datasets/soccertrack_mot_ft
venv-cv\Scripts\python.exe -X utf8 -m scripts.train_topview_detector --dataset data/tracking/datasets/soccertrack_mot_ft --out data/tracking/models/rfdetr_soccertrack_ft --model small --epochs 8 --init-weights data/tracking/models/rfdetr_mixed_small
venv-cv\Scripts\python.exe -X utf8 -m scripts.soccertrack_v2.evaluate_detector_mot --clip data/tracking/datasets/soccertrack_mot/117092 --weights data/tracking/models/rfdetr_soccertrack_ft --tiles 3 --out docs/measurements/detector-mot-117092-finetuned.json
venv-cv\Scripts\python.exe -X utf8 -m scripts.soccertrack_v2.detection_variants --segments 1 5 9 --tiles 4 --weights data/tracking/models/rfdetr_soccertrack_ft --out data/tracking/bench/det_ft_t4
venv-cv\Scripts\python.exe -X utf8 -m scripts.soccertrack_v2.detection_audit --cache data/tracking/bench/det_ft_t4 --segments 1 5 9 --gt data/tracking/bench/signal_quality_gt.npy --start-seconds 600 --calibration data/tracking/calibrations/soccertrack_v2_117092_landmarks.json --out docs/measurements/detection-variant-finetuned-t4.json
```
