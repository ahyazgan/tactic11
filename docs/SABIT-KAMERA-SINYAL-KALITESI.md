# Sabit kamera sinyal kalitesi — ilk ölçümlü iyileştirme

14 Eylül 2026. Başlangıç kodu: `6ca634e`. Dal: `feat/sabit-kamera-sinyal-kalitesi`.

Takım atamasındaki fazla kişi sorunu azaldı; gerçek takım sınıflandırması hâlâ
yaklaşık %81 düzeyinde. Bu değişiklik canlı kulüp kullanımına hazır olunduğu
anlamına gelmez. Pas ve savunma çıkarımı henüz iyileştirilmedi.

## Değişiklik

- Takip hattının kısa ömürlü diye elediği kimlikler artık forma renklerini
  öğrenirken kullanılmıyor. Önceden silinen takiplerin renkleri kümeyi bozabiliyordu.
- RGB kümelemesi korunuyor. Ek olarak RGB toplamına göre normalize edilen renk
  oranı denetleniyor. Benzer parlaklıktaki farklı renkli kişilerin takım ataması
  reddediliyor. Eşik, küme içi medyan uzaklığın 2.5 katı ve en az 15/255;
  ilk iki geliştirme segmentinde seçildi. Oyuncu sayısı 11'e kırpılmıyor.
- Video özeti artık fazla oyuncu atanan kareleri, oranını ve takım atanmış
  kişi ortalamasını ayrı raporluyor. Bu özet tek başına karar motorlarını susturmaz;
  kalan hatalı atamalar hâlâ risk taşır.
- Yetersiz pozisyon verisinde `tracking_signals` raporu artık gerçek kapsama/kalite
  değerlerini taşıyor; varsayılan %100 kalite ile audit arasında çelişki kalmıyor.
- GT çıkarma, ham gözlem önbellekleme, takım karşılaştırması ve olay denetimi
  komutları repoya eklendi. Önceki geçici scratchpad betiklerine gerek yok.

## Ölçüm düzeni

SoccerTrack v2 117092, sabit panoramik kamera, yerel `990401` videoları.
Geliştirme: 600–630 ve 690–720 saniye. Kontrol: 780–810 ve 870–900 saniye.
Dört segmentte toplam 120 saniye video, 1500 ham takip örneği (etkin 12.5 fps).
Dedektör: `rfdetr_mixed_small`, 512 çözünürlük, tiles=4, istenen track-fps=15.
Eski ve yeni atama tamamen aynı önbelleklenmiş takip/renk gözlemlerine uygulandı.

GT-video zaman farkı ilk iki segmentte **+9 kare** seçilip kontrolde sabitlendi.
Kontrol karelerinde en iyi ofset aranmadı. Takım isimlerinin eşlemesi de geliştirme
verisinden geldi. Her 10. takip örneğinde 3 m içinde birebir oyuncu-GT eşlemesi
kullanıldı; kaleciler forma doğruluğu hesabından çıkarıldı.

| Ölçüt | Eski | Yeni |
|---|---:|---:|
| Geliştirme: bir takımda 12+ kişi olan kare | %23.87 | %12.40 |
| Kontrol: bir takımda 12+ kişi olan kare | %51.87 | %36.40 |
| Kontrol: takım atanmış kişi/kare | 19.11 | 18.23 |
| Kontrol: GT eşleşmelerinde doğru/atanmış | 509/628 | 511/630 |
| Kontrol: atanmış eşleşmelerde takım doğruluğu | %81.05 | %81.11 |
| Kontrol: eşleşen 646 oyuncu gözleminden belirsiz kalan | 18 | 16 |
| Geliştirme: eşleşen 425 gözlemden belirsiz kalan | 7 | 17 |
| Geliştirme: doğru takım atanmış gözlem | 359 | 350 |

Kontrolde fazla atama oranı 15.47 puan düştü. Ancak geliştirme bölümünde 9 doğru
gözlem de kaybedildi. Filtre kusursuz değildir; sırf daha az kişi saymak başarı
ölçütü sayılamaz. Temel sınıflandırma doğruluğunda anlamlı artış gösterilmedi.

Daha sıkı **1.5 m** eşleşme kontrolünde 229 saha oyuncusu gözlemi kaldı:
doğru atama 173/225 → 172/225 (%76.89 → %76.44). Bu da doğrulukta artış iddiasını
desteklemiyor; kazanım, fazla takım atamalarının azaltılmasıdır.

Bu yüzdeler tüm oyuncuların doğruluğu değildir: yalnız geometrik olarak
eşleşebilen altküme ölçülüyor. GT'de bu aralık için 20 saha oyuncusu ve 2 kaleci
var; hakem/kenar kişi etiketleri yok. Elenenlerin tamamının hakem olduğunu
kanıtlayamıyoruz. Mevcut TPS aynı maçın GT'sinden türetilmişti; bu deney bağımsız
kalibrasyon doğrulaması da değildir. Ardışık kareler bağımsız örnekler değildir.

Eski 6 dakikalık 1500 **çıktı** karesindeki %35.2 ile bu tablodaki kontrol oranı
aynı örnekleme değildir; doğrudan karşılaştırılmamalıdır.

## Pas ve savunmanın kesin başlangıç tablosu

Bu bölüm değiştirilmemiş, kayıtlı 600–960 sn çıktısını denetler; takım filtresinin
paslara etkisini ölçmez. Önceki "25 pas / yaklaşık 60" notu güncel dosyaları
temsil etmiyordu.

- GT: **60 normal pas, 9 yüksek pas, 1 orta = 70 pas türü olay**.
- Mevcut video çıktısı: **38 pas denemesi**, 22 tamamlanmış tahmini.
- GT: 2 başarılı tackle ve 2 block. Video: **0 savunma olayı**.
- Top mevcut (enterpolasyon dahil): karelerin %67.87'si.
- Top doğrudan gözlenmiş: %45.20.
- Topu tutan oyuncu belirlenmiş: %29.07.
- Pas reddi: 8 uzun gözlem boşluğu, 4 kısa mesafeli kaptırma.
- Bir GT olayını iki kez kullanmadan zaman yakınlığı: ±1 sn 21, ±2 sn 25,
  ±3 sn 26 eşleşme. Saat, takım ve alıcı kimliği doğrulanmadan bunlar kesinlik
  veya duyarlılık olarak sunulamaz; 38/70 de duyarlılık değildir.

Savunma sıfırının nedeni yalnız model kalitesi değil: `process_video`,
`track_video`, `track_live` ve ingest zinciri yalnız türetilmiş pasları taşıyor.
Her takım değişimini tackle diye adlandırmak hatalı olur. Sıradaki çalışma,
gözlenen top sahipliği ve yakın mücadele kanıtını koruyarak savunma adaylarını
üretmek ve gerçek olaylarla doğrulamaktır. Pas için önce top/aktör kapsaması ve
kısa tutuşların kaybı ölçülmeli; eşik gevşetmek tek başına çözüm değildir.

## Tekrarlama

Proje kökünde `venv-cv/Scripts/python.exe -X utf8 -m` ardından ilgili modül:

```powershell
scripts.soccertrack_v2.export_gt --gsr data/tracking/datasets/soccertrack_v2/117092/117092_gsr_1st.json --start-frame 14750 --end-frame 24300 --out data/tracking/bench/signal_quality_gt.npy
scripts.soccertrack_v2.cache_observations --out data/tracking/bench/signal_quality_v1
scripts.soccertrack_v2.evaluate_teams --cache data/tracking/bench/signal_quality_v1 --gt data/tracking/bench/signal_quality_gt.npy --alignment data/tracking/bench/signal_quality_alignment.json --out data/tracking/bench/signal_quality_before.json --baseline
scripts.soccertrack_v2.evaluate_teams --cache data/tracking/bench/signal_quality_v1 --gt data/tracking/bench/signal_quality_gt.npy --alignment data/tracking/bench/signal_quality_alignment.json --out data/tracking/bench/signal_quality_after.json
scripts.soccertrack_v2.evaluate_events --frames data/tracking/live/990401/frames --events data/tracking/datasets/soccertrack_v2/117092/117092_12_class_events.json --out data/tracking/bench/signal_quality_events.json
```

Mevcut önbellek varsa ikinci komutu atla; araç kanıt dosyalarını üzerine yazmaz.
Yeni deney için farklı önbellek/rapor yolları kullan. Eşleşme duyarlılık kontrolü
için iki değerlendirme komutuna `--match-radius 1.5` ekle ve ayrı raporlara yaz.
GSR'den 210122 etiket satırı çıkarıldı; ham veriler/önbellekler git'e alınmadı.
Küçük ölçüm raporu `docs/measurements/soccertrack-signal-2026-09-14.json` içindedir.

Doğrulama: 2458 test geçti, 1 atlandı; ruff temiz; mypy 478 dosyada temiz.
Frontend, canlı DB ve çalışan sunucu değiştirilmedi. Yeni filtre sonraki
video işleme koşularına uygulanır; daha önce DB'ye yazılmış kareler aynı kalır.
