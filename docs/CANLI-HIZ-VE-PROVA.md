# Canlı mod: prova, hız ve canlı kalma (2026-11-01)

Soru: canlı maçta koç ne kadar eski bir resim görür, ve bu kapatılabilir mi?

## 1. Gerçek hızda prova

6 dakikalık SoccerTrack v2 117092 panoraması gerçek hızda akıtıldı (1080p'ye
indirildi, landmark kalibrasyonu ölçeklendi, 4 dilim, telestrasyon açık, RTX 5060 8 GB).
Ölçüm `docs/measurements/live-rehearsal-990601.json`.

| | Değer |
|---|---|
| Segment (30 sn) takip süresi | ort. 96 sn (89–102) |
| Takipten sonra telestrasyon | ort. 21 sn |
| Gerçek zaman oranı | 3,2× yavaş |
| Gecikme büyümesi | segment başına ~66 sn |
| 6. dakikanın sonunda gecikme | 824 sn (telestrasyon 838 sn) |
| Hata / DB'ye yazılan kare | 0 / 1500 (1145'inde top var) |

İlk prova denemesi bir hata ortaya çıkardı: `.env`'deki şablon `DATABASE_URL` ile 12
segmentin hepsinin DB yazımı sessizce reddedildi ve gecikme göstergesi takıldı.
Düzeltme: başlamadan önce veritabanı ön kontrolü (PR #308).

## 2. Hız matrisi (ön kayıtlı)

Plan `docs/measurements/live-speed-plan.json` (sonuçlardan önce commit 3d2b0d4).
Aynı üç segment, ölçeklenmiş kalibrasyon, GT'ye karşı tespit denetimi. Sonuç
`docs/measurements/live-speed-results.json`.

| Arka uç | Dilim | sn / segment | GT oyuncu tespit | Hayalet payı |
|---|---|---|---|---|
| torch | 4 | 89 | %49,9 | %46,1 |
| torch | 3 | 48 | %44,1 | %46,9 |
| torch | 2 | 36 | %26,3 | %46,4 |
| onnx | 4 | 185 | %49,8 | %46,1 |
| onnx | 3 | 98 | %44,1 | %47,0 |
| onnx | 2 | 58 | %26,3 | %46,5 |

- Ön kayıtlı şart (tespit kaybı ≤ 2 puan) hiçbir hızlı ayarda geçmedi: 3 dilim −5,8,
  2 dilim −23,6 puan. Öneri değişmedi: torch, 4 dilim.
- ONNX aynı tespitleri veriyor ama derlenmiş fp16 torch yolundan ~2× yavaş.
- `--height 1080` tespiti hızlandırmaz: dilim sayısı satır sayısından ve en-boy
  oranından gelir, çözünürlükten değil.
- Gerçek zamana ulaşılmadı. En hızlı ayar bile (2 dilim, oyuncuların yarısı kayıp)
  30 sn'lik segmenti 36 sn'de işliyor.
- Ölçülüp elenen: iki takip işçisini paralel çalıştırmak. Tek işçide GPU zaten
  ort. %76 meşgul (p90 %88, 3,4 GB / 8 GB); kazanç en çok ~1,3× olurdu, bellek de dar.
- Düşünülüp elenen: görüntüyü saha bandına kırpmak. Oyuncular yüksekliğin ~%52'sinde
  ama genişliğin tamamında; dilim ızgarası en-boy oranını izlediği için kazanç
  sınırlı, `detect.py` de dondurulmuş.

## 3. Canlı kalma (`--keep-up`)

Ayarlar gecikmeyi kapatamadığına göre, koçun gördüğü resim eskimesin diye
`canli_mac --keep-up` eklendi: ffmpeg segmentleri `incoming/` klasörüne yazar,
takip boşalınca yalnız en yeni kapanmış segment işlenir, aradakiler atlanır.
Atlananlar silinmez (maç sonu tam işlenebilir). Segment adı dakikayı taşır
(`seg_0007_m13.500`), takip dakikayı addan okur.

Aynı 6 dk'lık prova `--keep-up` ile (`docs/measurements/live-rehearsal-990602-keep-up.json`):

| | `--keep-up` yok | `--keep-up` |
|---|---|---|
| İşlenen segment | 12 / 12 | 5 / 12 (%42) |
| Akış sürerken takip gecikmesi | 98 → 750 sn, büyüyor | 96–116 sn, sabit |
| Telestrasyon gecikmesi | 122 → 838 sn | 117–133 sn |
| Son segment | 824 sn | 185 sn (bir tur bekledi) |

Kare dakikaları segment adlarıyla birebir tuttu (ör. `seg_0007_m13.500` → 13,5–14,0).
Koçun gördüğü resim her an yaklaşık 2 dakika eskidir; buna karşılık maçın %40 kadarı
işlenir.

Atlamadan sonra telestratör durumu (hat yumuşatma, etiket bekletme, sahiplik penceresi)
sıfırlanır: aynı beş segment yeniden işlendiğinde sıfırlama yalnız üç boşlukta oldu,
ardışık 10→11'de olmadı. Bedeli segment başında 9–33 karelik (~1 sn) "sahiplik
bekleniyor" süresi; karşılığında 1,5 dk önceki sahiplik ve hat yeni resme karışmıyor.

## Sınırlar

- Tek GPU (RTX 5060 8 GB), tek maç, sabit panorama kamerası. Daha güçlü GPU ya da
  daha dar açılı kamera sonucu değiştirir; ölçüm komutları belgelerde.
- `--keep-up` gecikmeyi sınırlar ama kapsamayı düşürür; hangisinin seçileceği
  maç durumuna bağlı (devre arası analizi için tam işleme, maç içi karar için canlı kalma).
