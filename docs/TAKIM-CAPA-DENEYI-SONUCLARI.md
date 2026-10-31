# Çapalı takım ataması: iki ön kayıtlı deney

1 Kasım 2026. **İki aday da kontrol kapısını geçmedi; üretim değiştirilmedi.**

## Neden denendi

Telestrasyon doğruluk ölçümü (`docs/OTOMATIK-TELESTRASYON.md`) en büyük hata
kaynağının takım ataması olduğunu gösterdi. 117092'nin 12 segmentinde (600–960 sn)
takım uyumu segmentten segmente %53–88 arasında değişiyordu; hataların %63'ü
baştan sona ters takıma atanmış 71 izdeydi.

Canlı akışta her segment k=2 k-means ile sıfırdan kümelenir; ilk segmentin renkleri
(çapa) yalnız kümelerin hangisinin ev sahibi olduğunu sıralar. Hipotez: kötü
segmentlerde kümeleme takımları değil ışığı ayırıyor; çapayla sınıflandırmak bunu
düzeltir. Çapayla sınıflandırma daha önce denenmemişti.

Önceki takım ölçümleri yalnız 0/3/6/9 segmentlerini kullanıyordu; bunlar kümelemenin
iyi çalıştığı segmentlerdir. Bu deneyde 12 segmentin hepsi güncel kodla yeniden
önbelleklendi (`data/tracking/bench/team_tele_v1`, git'e alınmadı).

## Düzen

- Ön kayıt: `docs/measurements/team-anchor-plan.json` (`246a77b`, sonuçlardan önce).
- Geliştirme 0–5, kontrol 6–11; çapa segment 0'ın üretim ataması; ev sahibi = GT sol takım.
- Ölçüt: ≤3 m uzamsal GT eşleşmesindeki saha oyuncularında takım uyumu (kaleciler hariç);
  birincil "doğru / tüm eşleşen" — atamayı bırakmak ödüllenmez.
- Adaylar: `nearest_anchor` (en yakın çapa rengi, üretimle aynı aykırılık kuralı),
  `seeded` (k-means çapadan başlar, 40 RGB kayma sınırı), `anchor_chroma` (renk oranında en yakın çapa).
- Karar geliştirmeden sonra, kontrolden önce mühürlendi: `team-anchor-decision.json` (`56fddce`).
- Komut: `scripts/soccertrack_v2/anchored_team_experiment.py`.

## Geliştirme (0–5, 7629 eşleşme)

| Yöntem | Doğru / eşleşen | Atananda doğru | En kötü segment |
|---|---:|---:|---:|
| üretim | %65,3 | %70,4 | %56,9 |
| **nearest_anchor** (seçildi) | %71,8 | %74,5 | %65,4 |
| seeded | %69,3 | %74,7 | %67,5 |
| anchor_chroma | %55,1 | %56,6 | %42,0 |

Segment bazında üretim → nearest_anchor: 1: %56,9 → %69,0, 4: %66,3 → %73,6,
5: %66,2 → %72,2; 0, 2, 3 değişmedi. Renk oranı yöntemi gece görüntüsünde iki
grileşmiş formayı ayıramadı (önceki `FORMA-RENK-ORANI` bulgusuyla tutarlı).

## Kontrol (6–11, 11325 eşleşme)

| Ölçüt | Üretim | nearest_anchor | Şart | Sonuç |
|---|---:|---:|---|---|
| Doğru / eşleşen | %75,42 | %75,12 | ≥ üretim + 3 puan | geçmedi |
| Atananda doğru | %81,86 | %82,66 | ≥ üretim | geçti |
| En kötü segment | %73,09 | %73,09 | ≥ üretim − 2 puan | geçti |

Kontrol segmentlerinin hiçbirinde kümeleme çökmedi (üretim %73–89). Çapa,
çöken segmentleri kurtarıyor, çökme olmayan yerde nötr kalıyor; atanmamış oranı
%7,9 → %9,1 arttı. Ön kayıt gereği yöntem, parametre ve şart sonradan değiştirilmedi.

## İkinci deney: kapılı çapa (GT'siz çökme tespiti) — kabul edilmedi

Ön kayıt: `docs/measurements/team-gate-plan.json` (`f4a8ba2`). Kural: üretim
atamasının küme merkezlerinden biri çapadan 30 RGB'den (üretimdeki
`RGB_MIN_DISTANCE`) uzaksa segment çökmüş sayılır ve en yakın çapa kullanılır;
değilse üretim aynen kalır. Geliştirme (yukarıdaki 12 segment, artık örneklem içi):
üretim %71,4, kapılı %73,5, her yerde çapa %73,8; kapı 4 segmentte açıldı.

Yeni kontrol: daha önce kullanılmamış 1200–1560 sn, 12 segment
(`scripts/soccertrack_v2/cut_segments.py` ile panoramanın aynı kare ızgarasından
kesildi; 990401'in 600 sn başlangıcı piksel farkı 0 ile doğrulandı), yeni GT
dilimi, çapa 10 dk önceki 600 sn segmentinden (canlı işçideki gibi).

| Kontrol (11670 eşleşme) | Üretim | Kapılı çapa | Şart | Sonuç |
|---|---:|---:|---|---|
| Doğru / eşleşen | %68,45 | %69,66 | ≥ +2 puan | geçmedi (+1,2) |
| Segment gerilemesi | — | en kötü −0,3 puan | ≤ 2 puan | geçti |
| Atananda doğru | %72,25 | %71,26 | ≥ üretim | geçmedi |

Kapı 3 segmentte açıldı (sonuç belirsiz değil): segment 1 +3,5, segment 5
+10,1, segment 4 −0,3 puan. Segment 4 asıl dersi verir: üretim gözlemlerin
%48,5'ini zaten atamamıştı (kalanında %88,7 doğru); çapa hepsini atadı ve yalnız
%45,3'ü doğru. Çöken segmentte çapa, güvenli "bilinmiyor"u yazı tura etiketine
çevirebiliyor; telestrasyonda yanlış takım, bilinmeyen takımdan kötüdür. Her
segmentte çapa (karar dışı, bilgi için) %69,6 verdi ama tek segmentte −8,3 puan
düşürdü; kapı bu zararı önledi.

## Ne öğrendik, sırada ne var

- Gece maçında yalnız renge dayalı takım ataması bu iki dilimde %68–71
  düzeyinde; iki deney de rengin nasıl kümelendiğini değiştirerek kalıcı kazanç
  getirmedi. Kazanç küçük ve dengesiz (bazı segmentlerde +10, bazılarında atanmış
  doğruluk düşüyor).
- Sıradaki eksen renk kümelemesi değil, ek bilgi olmalı: takip kimliği boyunca
  oylama ve görünüş (ReID) özellikleri, ya da renk belirsizken "bilinmiyor"u
  koruyup telestrasyonun bunu tolere etmesi.

- 117092'de gerçek 6 dakikalık takım uyumu (12 segment, üretim) %70,9: geliştirme
  4985+kontrol 8541 doğru / 18954 eşleşme. Önceki "%81" yalnız iyi segmentlerdi.
- Üretime alınacak her yöntem dondurulmuş `app/tracking/teams.py`'ye dokunur ve
  kendi değişiklik belgesini (amendment + eşitlik kanıtı) ister.
