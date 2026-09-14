# Takip sürekliliği sonuçları — 2026-09-14

Kamera kesmesi, tekrar veya kalibrasyonu bulunamayan karelerden sonra ByteTrack
belleği artık sıfırlanıyor. Yerel takipçi ID sayacını da sıfırladığı için yeni
ID'ler önceki en büyük ID'nin üstüne taşınıyor. Böylece eski oyuncunun forma
geçmişi ve kısa takip sayacı yeni oyuncuya aktarılmıyor. Topun eski görüntüdeki
arama merkezi de bırakılıyor. Oyuncu ve top hızı yalnız aynı çekimdeki komşu
gözlemlerden hesaplanıyor; tek gözlem varsa hız üretilmiyor.

Bu düzeltme farklı çekimler arasında yanlış bağlantıyı önler. Sabit kamerada
oyuncular yan yana geldiğinde oluşan ID değişimlerini veya aynı oyuncunun
farklı takipler halinde görünmesini çözmüş sayılmaz. Kalibrasyondaki tek karelik
boşluk bile yeni kimlik başlatır: doğrulanamayan devamlılık yerine ayrı anonim
takipler üretilir. Gerçek oyuncu/kadro eşleştirmesi yapılmaz.

## Forma hatasının kimlik bileşeni

Önceden incelenmiş gündüz etiketlerinde 96 takipte 218 mavi/beyaz gözlemi var;
7 ID iki forma renginde görülüyor. Bu ID'lerin her birine tek takım atanırsa,
etiketler doğru kabul edildiğinde en az 9 gözlem yanlış olmak zorunda.
Yeni gece geliştirme kümesinde 49 takip/67 gözlemden 2 ID iki renkte görülüyor.
Bu bulgu daha iyi renk kümelemesinin tek başına bütün hataları çözemeyeceğini
gösteriyor. Aynı takım oyuncuları arasındaki değişimleri ölçmüyor.
Kanıt: [kimlik denetimi](measurements/track-identity-development-audit.json).

## Kayıp takip süresi deneyi

Supervision 0.30.2 ByteTrack, `lost_track_buffer` değerini ayrıca
`frame_rate / 30` ile çarpıyor. Mevcut ayarda 25 fps kaynak → 12,5 fps takip,
1,5 saniye yapılandırması → 18 tampon → **7 kare / 0,56 saniye** oluyor.
Deneyde tek ölçekleme **19 kare / 1,52 saniye** verdi.

| Geliştirme kümesi | Ayar | Doğru | Yanlış | Atanamayan | Başka renk atanmış | İki renkte görülen ID |
|---|---|---:|---:|---:|---:|---:|
| Gündüz, 218 forma kutusu | Mevcut | 195 | 22 | 1 | 16 | 7 |
| Gündüz, aynı kutular | Süreyi tek ölçekle | 194 | 23 | 1 | 13 | 8 |
| Gece, 123 forma kutusu | Mevcut | 95 | 13 | 15 | 4 | 3 |
| Gece, aynı kutular | Süreyi tek ölçekle | 98 | 13 | 12 | 4 | 3 |

Her iki deneyde etiketli forma kutusu kaybı sıfır. Gündüz toplam takip sayısı
257→247 azalıyor, ancak kimlik ve forma hatası artıyor. **Süre değişikliği
reddedildi; üretim ayarı korunuyor.** İstenen ve gerçekte uygulanan süre artık
`calibration_stats` içinde ayrı raporlanıyor. Gündüz geliştirme eşiği geçilmediği
için yeni kontrol görüntüsü açılmadı ve dış doğrulama başarısı iddia edilmiyor.

Gündüz üç klip RF-DETR ile yeniden işlendi; takipçi öncesindeki bütün tespit
kutuları ve renkleri kaydedildi. Her iki ayar aynı kayıtta
tekrar çalıştırıldı. Etiketler **kare + tam kutu koordinatıyla** eşleştirildi;
değişebilen takip numarası eşleştirme anahtarı olmadı. Mevcut ayarın bütün takip
satırlarını ve renk geçmişini birebir üretmesi zorunlu tutuldu. Gece dört eski
tespit kaydı kullanıldı; bu karşılaştırmada iki ayar da aynı 65 işaretli
kalibrasyonu kullanır. Eski 500 noktalı gece sonuçlarıyla doğrudan kıyaslanmaz.

- [Gündüz ölçümü ve hash'ler](measurements/track-buffer-day-development.json)
- [Gece ölçümü ve hash'ler](measurements/track-buffer-night-development-verified.json)
- [Üretim yolunun 1.125 karelik tekrarı](measurements/tracking-continuity-production-replay.json)

Tekrar çalıştırma:

```powershell
venv-cv\Scripts\python.exe -m scripts.soccertrack_v2.cache_ball_candidates --segments 0 3 6 --source data/tracking/bench/daylight_117093/source --out YENI_TESPIT_DIZINI --calibration data/tracking/calibrations/soccertrack_v2_117093_landmarks.json
venv-cv\Scripts\python.exe -m scripts.soccertrack_v2.benchmark_track_buffer --cache YENI_TESPIT_DIZINI --labels docs/measurements/daylight-117093-labels.json docs/measurements/perimeter-control-day-labels.json --out YENI_SONUC.json
```

## Doğrulama

- Kamera kesmesi, tekrar, kalibrasyon boşluğu, ardışık iki kesme, kesmesiz takip,
  forma geçmişi ayrımı, eski top merkezinin bırakılması ve hız sınırları testli.
- Gerçek Supervision/ByteTrack ile CV ortamında **13 test geçti**.
  Komut: `venv-cv\Scripts\python.exe -m pytest --noconftest tests/test_tracking_continuity.py -q`.
- Uygulama ortamında **87 ilgili test geçti**; CV bağımlılığı gerektiren 5 test
  burada atlanır, yukarıdaki CV çalıştırmasında geçer.
- Tam yerel paket **2.635 geçti, 1 atlandı** (CV parametreleri eklenmeden önce);
  sonrasında değişen testler ayrıca çalıştırıldı. Son PR başlığındaki CI tüm
  paketi yeniden çalıştırır. Ruff ve mypy (508 kaynak dosyası) temiz.
- Düzeltilmiş gerçek `collect_observations` ve ByteTrack ile üç sabit kamera
  kaydında 1.125 karenin bütün oyuncu satırları ve renk geçmişi eşit;
  gereksiz sıfırlama sayısı 0. Bu tekrar önbellekli tespit/renk ve kayıtlı ROI
  girdilerini kullanır; yeni model çıkarımı iddiası değildir.

Ölçümler tek inceleyicili, daha önce görülmüş ve aynı maç içinde ilişkili
kutulardır. Genel oyuncu kimliği doğruluğu, oyuncu yakalama oranı veya olay
doğruluğu olarak sunulmaz.
