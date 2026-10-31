# Otomatik telestrasyon (adım 1)

1 Kasım 2026. Analistin elle çizdiği halka, çizgi ve etiketi sistemin kendisi
çizer. Kod: `app/tracking/telestration.py`, komut: `scripts/telestrate_video.py`,
test: `tests/test_telestration.py`.

## Ne çizer

| Öğe | Kaynak | Not |
|---|---|---|
| Oyuncu halkası | ayak noktasında 0,9 m saha çemberinin izdüşümü | takım rengi; uzakta yatıklaşır |
| Blok çizgileri + şerit | savunan takımın x-boşluk hatları (8 m, ≥3 oyuncu) | hattaki oyuncuların genişliğinde, ±3 m |
| Hatlar arası mesafe | iki hattın derinlik farkı | "13 m" gibi, şeridin ortasında |
| Pres vurgusu | topa ≤5 m savunanlar (en yakın ≤3 m, ≥2 oyuncu) | halka kırmızı ve kalın |
| Faz etiketi | savunma hattının kendi kalesine uzaklığı: <30 alçak, 30–45 orta, üstü yüksek | savunan takımın renk noktasıyla; ≥1 s kararlıysa değişir |

Savunan takım: karenin `possession_team_external_id` alanının 1 sn çoğunluğu.
Hücum yönü: operatör (`--home-attack x+|x-`) ya da `space_map.infer_attack_direction`.

## Neden takip hattının dışında

`app/tracking/pipeline.py` ve `scripts/track_video.py` birleşik kimlik kontrolü
için dondurulmuştur (`docs/measurements/joint-identity-frozen-decision.json`).
Telestrasyon takip çıktısını (`TrackingFrame`, saha koordinatı) okur ve her öğeyi
saha uzayından görüntüye geri izdüşürür. Bu yüzden dondurmaya dokunmaz. Aynı
çizim öğeleri `--marks-json` ile kare başına yazılır; canlı panel katmanı bunları
kullanabilir.

## İzdüşüm ve güven kapıları

- Homografi: kapalı biçimde ters; ufkun arkasına düşen nokta reddedilir.
- TPS: ileri modelin sayısal tersi (homografi tersinden Gauss-Newton). İleri
  dönüşümle 0,1 m içinde doğrulanmayan nokta reddedilir. Yalnız destek bölgesinde
  çizilir: işaretli saha sınırı, yoksa kontrol noktalarının görüntüdeki dışbükey
  zarfı. Zarf dışı ekstrapolasyondur; gece kaydındaki top hatası buradan doğmuştu
  (`docs/TOP-SINIR-UYUSMAZLIGI-TANI.md`). Destek dışındaki top ve oyuncu sayılmaz.
- Çizgi ve etiket yalnız şu koşullarda: kalibrasyon hatası ≤1,5 m, sahiplik
  biliniyor, yön biliniyor, savunan takımdan ≥6 oyuncu görünür. Her kare için
  çizilmeme nedeni `gate_counts` içinde sayılır.

## Ölçüm: SoccerTrack v2 117092, ilk 30 sn (gece, sabit panoramik kamera)

Takip: `track_video --camera static --weights data/tracking/models/rfdetr_mixed_small --tiles 4 --max-seconds 30`.
Kalibrasyon: TPS, 500 nokta, LOO 0,76 m (köşeler işaretli değil → dışbükey zarf).

| Yön | Çizilen kare | Kapı dağılımı |
|---|---:|---|
| otomatik (`auto`) | 1 / 126 (%1) | possession 3, direction 87, players 35, drawn 1 — iki kaleci de çoğunlukla görünmüyor |
| operatör (`x+`) | 68 / 126 (%54) | possession 3, players 55, drawn 68 |

`players` kapısı takım atamasının dengesizliğinden gelir (karede ortalama 9,5'e
6,1 atanmış oyuncu). Eşikler bu klibe bakılarak gevşetilmedi. Çizim hızı aşağıda (25 fps bölümü).

![SoccerTrack önizleme](measurements/telestration-soccertrack-117092.jpg)

Görsel denetim (4 kare): top ev sahibi kalesi önündeyken "Alçak blok" (yeşil),
top ortadayken deplasman "Yüksek blok" — oyun durumuyla tutarlı. Etiket doğruluğu
etiketli maçla **ölçülmedi**; bu bir görsel kontroldür.

## Doğruluk: saha gerçeğiyle karşılaştırma (SoccerTrack v2 GSR)

`scripts/soccertrack_v2/eval_telestration.py`, rapor
`docs/measurements/telestration-eval-117092.json`. Girdi: canlı mod koşusunun
12 segmenti (`data/tracking/live/990401/frames`, dk 10–16, 1500 kare). Aynı
`Telestrator` üç girdiyle çalışır: GSR konum + takım (referans), takip çıktısı,
takip konumu + eşleşen GT takımı (≤3 m Macar eşlemesi). Sahiplik üçünde de
takip karesinden, hücum yönü GT kalecilerinden gelir; yani sahiplik ve yön
**ölçülmez**. Hizalama geliştirme segmentlerinde sabitlenmiş kaydırmadır; eşikler
bu veriye bakılarak ayarlanmadı.

| 1500 kare | Çizilen | Blok etiketi = GT | Taban (hep en sık) | Dengeli doğruluk | Savunma hattı hatası medyan / p90 |
|---|---:|---:|---:|---:|---:|
| GT konum + GT takım | %99,8 | — | — | — | — |
| **takip (üretim)** | %78,6 | %75,8 | %68,6 | **%71,3** | 6,1 / 25,1 m |

GT etiketlerinin %69'u "Yüksek blok"; ham isabet tabanın yalnız 7,2 puan üstündedir.
Dengeli doğruluk (sınıf başına duyarlılık ortalaması, sabit tahmin = %33,3)
%71,3'tür: alçak %75, orta %57, yüksek %82.

Hata kaynağı, üç koşunun da çizdiği aynı 360 karede:

| aynı 360 kare | Blok = GT | Dengeli | Hat hatası medyan / p90 |
|---|---:|---:|---:|
| takip | %81,4 | %67,6 | 4,4 / 14,0 m |
| takip konumu + doğru takım | %94,9 | %74,5 | 3,3 / 14,9 m |

Takım ataması bu kayıtta %77 doğru (11739 eşleşmenin 9065'i). Düzeltilirse
dengeli doğrulukta ~7 puan ve hatta ~1 m kazanç var; kalan p90 hatası
tespit/konumdan (karede ortalama 8,5 oyuncu GT ile eşleşiyor). Doğru takımlı
koşu yalnız %25,5 karede çizer, çünkü eşleşmeyen oyuncular takımsız kalır ve
savunan takımda 6 oyuncu bulunamaz; bu yüzden karşılaştırma aynı karelerde yapılır.

## 25 fps enterpolasyon

`telestrate_video` varsayılan olarak kaynak kare hızında yazar: takip kareleri
arasında oyuncular kimliğe göre doğrusal enterpole edilir (kamera kesmesinde ve
0,6 sn'den uzun boşlukta yapılmaz). Hat yumuşatması zamana bağlıdır (0,2 sn'de
yeni değerin payı 0,35), kare hızı değişince davranış değişmez.

Ölçüm (aynı rapor, `interpolation`): takip kareleri arasındaki GT karelerinde,
iki karede de bulunan oyuncular için eşleşme hatası medyanı **son kareyi tutma
1,959 m → enterpolasyon 1,952 m** (~60 bin eşleşme). Kazanç görsel akıcılıktır,
doğruluk değil: hata tespit/kalibrasyon tabanından (~1,9 m) gelir; 0,24 sn'lik
aralıkta oyuncunun yer değiştirmesi bunun yanında küçüktür.

Hız: 30 sn 4K kaynak 25 fps'te 31 sn'de çizilir (~4 sn'si tek seferlik açılış:
importlar ve TPS kalibrasyonunun LOO hatası). Kare başına ~11 ms çözme, ~3 ms
küçültme, ~21 ms çizim öğesi hesabı, ~3 ms çizim. İlk sürüm 4K karede ve oyuncu
başına ayrı TPS tersiyle gerçek zamanın ~3 katıydı; çizim artık çıktı boyutunda,
halkalar tek toplu ters dönüşüm + merkezde yerel Jacobian ile (tam izdüşümden
<0,5 px fark, `test_batched_rings_match_exact_projection`).

## Sınırlar ve sıradaki adımlar

- Yalnız sabit kalibrasyon. Kare başına kalibrasyonla işlenen hareketli kamera
  karelerin kendi homografisini çıktıya yazmadığı için desteklenmez.
- Blok eşikleri sezgiseldir; etiketli faz verisiyle ayarlanmadı.
- Doğruluğu en çok takım ataması sınırlıyor (yukarıdaki ayrıştırma); sonra
  tespit kapsaması (karede 8,5 eşleşen oyuncu).
- Sırada: canlı mod segmentlerine bağlama (`scripts/canli_mac.py`) ve panelde
  video üstü katman (`--marks-json`), topsuz koşu okları, boşluk boyama.
