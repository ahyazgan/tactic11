# Güneşli sahada takım ayrımı (132831) — teşhis ve yeniden atama (2026-11-01)

Başka stadyum sınavında (`docs/TOP-TESPITI-OLAY-OLCUMU.md` §6) "takım ataması
çalışmıyor" denmişti. Bu belge o iddiayı ölçer, düzeltir ve çözümü sınar.

## 1. Teşhis: iddia fazla genişti, hata soluk oyuncularda

Üç segmentten (11,5 / 16,0 / 19,5. dk) dört karede v2 dedektörünün 98 saha içi
kutusu 60×120 montajda tek değerlendirici (Claude) tarafından göz etiketlendi:
29 sarı (ev), 45 mavi (deplasman), 8 başka renk (hakem/kaleci), 16 "soluk"
(uzak/küçük, beyaza dönmüş; göz karar veremedi). Etiketler
`docs/measurements/team-eye-dev-132831-labels.json`, kutular `...-boxes.json`.
Üretim ataması kutunun ayak noktasının sahaya izdüşümüyle (≤ 1 m) alındı:

| Göz etiketi | Üretim ataması |
|---|---|
| Sarı (29) | 29 ev |
| Mavi (45) | 37 deplasman · 2 ev · 4 belirsiz · 2 eşleşmedi |
| Başka renk (8) | 4 deplasman · 2 belirsiz · 2 eşleşmedi |
| Soluk (16) | **15 ev** · 1 eşleşmedi |

Yani net renkli oyuncularda üretim %97 doğru; sorun, iki takımdan da
beyaza dönmüş uzak oyuncuların hepsinin "ev" (sarı) sayılması. Sebep özellik:
dondurulmuş `teams.torso_color` gövdedeki en parlak %40 pikselin ortalamasını
alır; güneşte küçük kutuda bu pikseller beyaz şerit ve pusladır; iki takım da
[250, 250, 236] gibi "beyaz" çıkar. Oysa aynı kutuların gövde **ortanca** rengi
oranı (255·RGB/ΣRGB) mavi payını korur: soluk-mavi örneklerde B oranı 90–101,
soluk-sarıda 76–81, net mavide 100–116, net sarıda 71–80.

Önceki sonuçta kullanılan iki dolaylı gösterge yanıltıcıydı: "bir takımda 12+
oyuncu" oranı 132877'de (takımların iyi ayrıldığı gündüz maçı) %57, 132831'de
%28; dokunuş oyları ise bu sahada dokunuşların yalnız %23'ünde 2 m içinde takip
edilen oyuncu olduğu için zayıf. Üçüncü stadyum sonucunun "takım ayrımı
çalışmıyor" cümlesi bu ölçümle **düzeltilmiştir**: üretim net renklerde doğru,
soluk/uzak oyuncularda sistematik yanlış.

## 2. Geliştirme: renk oranı ekseninde yeniden atama

Takip hattı dondurulmuş olduğu için düzeltme takip ÇIKTISI üzerinde:
`scripts.track_live_candidates` her takibin gövde ortanca rengini de kaydeder
(`kit_colors/`), `app/tracking/team_refit.py` bu renklerin oranından takımı yeniden
kurar. Takip başına "mavilik" (oran B − (R+G)/2) göz etiketli kutularda:

| | Mavilik aralığı |
|---|---|
| Sarı (29) | −27 … −2 (bir aykırı +6) |
| Mavi (45) | +5 … +55 (iki aykırı −15/−12: üretimde de "ev"; muhtemelen karışmış takip) |
| Soluk (15) | 10'u −14 … −1 (soluk sarı), 5'i +9 … +20 (soluk mavi) |
| Başka renk (6) | 0 … +21 |

Üç deneme sırayla elendi: 3 boyutlu oran kümelemesi ve 1 boyutlu küme ortası soluk
mavileri yine beyaz kümeye attı; parlak-%40 özelliği de değiştirmedi. Kalan yöntem:
oranların birinci ana bileşeni (forma ekseni) üzerine izdüşüm, eşik eksendeki
**nötr gri** noktası (iki küme merkezi arasında %25 payla sınırlı), küme→takım
sırası üretim atamasıyla uyuşmaya göre, eksen dışı renkler (hakem/kaleci) None.

Geliştirme sonucu (aynı 98 kutu): net renkli kutularda üretim 66/68, yeniden atama
65/68; soluk 15 kutu üretimde 15 ev → yeniden atamada 10 ev / 5 deplasman (mavilik
kanıtıyla birebir); başka renkli kişiye takım verme 4 → 2.

Ön kayıt `docs/measurements/team-refit-plan.json`; kontrol kareleri ve ölçütler
orada, hiçbir kontrol sonucu görülmeden yazıldı.

## 3. Ön kayıtlı kontrol — geçmedi

Kontrol kareleri (132831 segment 5/9/15/17: 12,5 / 14,5 / 17,5 / 18,5. dk, 94 kutu) göz
etiketlendi; etiketler bu kareler için hiçbir yeniden atama çıktısı hesaplanmadan yazıldı
(`docs/measurements/team-eye-control-132831-labels.json`). Gece kontrolü 117092
1800–1980 sn (6 segment, GSR takım etiketleri). Sonuç `docs/measurements/team-refit-control-result.json`.

| Ölçüt | Üretim | Yeniden atama | Şart | Sonuç |
|---|---:|---:|---|---|
| C1 Net renkte doğruluk (56/48 atanmış kutu) | %92,9 | %93,8 | ≥ −3 | geçti |
| C2 Karar verilebilen soluk kutular (16) | %87,5 | %78,6 | ≥ +30 | **kaldı** |
| C3 Gece takım uyumu (GSR, 20 403 eşleşme) | 0,748 | 0,538 | ≥ −0,02 | **kaldı** |
| C4 Net renkte atanan payı | %88,9 | %76,2 | ≥ −5 | **kaldı** |

Karar (plan gereği): yeniden atama canlı işçiden çıkarıldı; araçlar (`kit_colors`
kaydı, `team_refit`, `refit_team_frames`, göz etiketi değerlendiricisi) kaldı; kod ve
ölçüt sonuçtan sonra değişmedi.

Ne öğrenildi:
- Bu sahada üretim takım ataması net renkli oyuncularda %93–97 doğru. Üçüncü stadyum
  sınavındaki "takım ayrımı çalışmıyor" cümlesi yanlıştı; §1'de düzeltildi.
- Geliştirmedeki soluk-oyuncu hatası (15'inin hepsi tek takıma, 5'i mavi tonlu) kontrol
  karelerinde tekrarlamadı: üretim karar verilebilen 16 soluk kutunun 14'ünü doğru
  bildi. Geliştirme bulgusu 5 takibe dayanıyordu; genellemek için azdı.
- Gecede takip başına renk oranının ana bileşeni forma ekseni değil: iki takımın
  izdüşümleri üst üste (medyan −0,3 ve +1,4), yöntem başka bir eksende bölüp
  takipleri tek takıma yığıyor. Dondurulmuş `teams.py`'nin gece için seçtiği
  parlaklık taşıyan RGB özelliği bu durumda doğru seçim.
- Açık kalan gerçek sorun küçük: uzak/soluk oyuncuların bir kısmı; ölçmek için
  kare başına GT (GSR) olan bir gündüz maçı gerekir, göz etiketi bu çözünürlükte
  güvenilir değil (16 kutu "karar verilemez" kaldı).
