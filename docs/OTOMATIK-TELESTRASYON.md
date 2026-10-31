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
6,1 atanmış oyuncu). Eşikler bu klibe bakılarak gevşetilmedi. 30 sn 4K video
17 sn'de çizildi (takip hariç).

![SoccerTrack önizleme](measurements/telestration-soccertrack-117092.jpg)

Görsel denetim (4 kare): top ev sahibi kalesi önündeyken "Alçak blok" (yeşil),
top ortadayken deplasman "Yüksek blok" — oyun durumuyla tutarlı. Etiket doğruluğu
etiketli maçla **ölçülmedi**; bu bir görsel kontroldür.

## Sınırlar ve sıradaki adımlar

- Yalnız sabit kalibrasyon. Kare başına kalibrasyonla işlenen hareketli kamera
  karelerin kendi homografisini çıktıya yazmadığı için desteklenmez.
- Çıktı takip kare hızındadır (~4–5 fps); oyuncu konumları kareler arasında
  enterpole edilmez.
- Blok eşikleri sezgiseldir; etiketli faz verisiyle ayarlanmadı.
- Sırada: canlı mod segmentlerine bağlama (`scripts/canli_mac.py`) ve panelde
  video üstü katman (`--marks-json`), topsuz koşu okları, boşluk boyama.
