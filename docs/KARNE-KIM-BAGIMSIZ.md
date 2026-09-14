# "Kim çıkar" önseli: bağımsız doğrulama ve tablonun değişmesi — 14 Eylül 2026

`ELITE_OFF_PRIOR`, karnede taban çizgisini geçen **tek** boyutun çekirdeğidir ve
şekil kapısından farklı olarak **canlı öneri motorunda kullanılır**
(`ROLE_PRIOR_WEIGHT = 0.6`). Kaynağı tek kulübün üç sezonuydu: Barcelona,
La Liga 2018–21, 331 taktik değişiklik. Bugüne kadar hiç külliyat dışında
sınanmamıştı.

**Bulunan:** tablo taban çizgisini her yerde geçiyor ama **tek kulübe özgü**.
Barcelona'da en çok orta saha çıkıyor; başka her yerde en çok forvet. Ayrımı
yapan deney: Barcelona'nın **aynı maçlardaki rakipleri** de forvet-önde
davranıyor → bu bir **kulüp** farkı, dönem ya da lig farkı değil.

**Yapılan:** varsayılan tablo Barcelona-dışı 1409 değişiklikten yeniden fit
edildi. Kiracının kendi geçmişinden fit etme kancası zaten var
(`compute_live_sub_recommendation(off_prior=...)`); yeni tablo o veri yokken
kullanılacak genel varsayılandır.

**İkinci bulgu:** aday havuzu her hamlede en az bir kişi şişiyordu — o dakika
sahaya giren oyuncu da aday sayılıyordu, oysa aynı anda çıkamaz. Rastgele
isabet@3 tabanı 0,243 görünüyordu; doğrusu **0,273**. Hem bu scriptte hem
`coach_iq`'da düzeltildi.

Sayısal kanıt:
[La Liga 2015/16](measurements/karne-kim-bagimsiz-laliga-2015-16.json) ·
[Premier League 2015/16](measurements/karne-kim-bagimsiz-premier-league-2015-16.json).
Sabit kamera / takip dosyalarına dokunulmadı.

## Kulüp mü, dönem mi? — ayırt edici deney

Külliyat Barcelona'nın 2018–21 maçlarıdır; bağımsız kümeler 2015/16'dır. Bu iki
fark birbirine karışır. Ayırmak için **aynı 100 maçtaki rakip takımlar**
kullanıldı: aynı sezon, aynı lig, aynı maçlar — yalnız takım farklı.

| Popülasyon | FWD/ilk11 | MID/ilk11 | En çok çıkan |
|---|---:|---:|---|
| Barcelona 2018–21 (331 değişiklik) | 0,133 | **0,185** | ORTA SAHA |
| Barcelona'nın rakipleri 2018–21 (340) | **0,235** | 0,152 | FORVET |
| La Liga 2015/16 (544) | **0,207** | 0,138 | FORVET |
| Premier League 2015/16 (525) | **0,215** | 0,135 | FORVET |

Rakipler aynı dönemde, aynı ligde, forvet-önde. Dönem ya da lig açıklaması
elenir: **Barcelona bu veri kümesindeki atipik takımdır.** Futbol olarak da
makul — Messi-Suárez döneminde forvetler nadiren çıkar, orta saha rotasyona
girer.

## Eski tablo ne kadar taşınıyordu?

isabet@3, rastgele sahadaki oyuncu tabanı 0,273 (düzeltilmiş). Havuz tablosu için
**leave-one-out**: her küme, o küme hariç öteki iki Barcelona-dışı
popülasyondan fit edilen tabloyla ölçüldü.

| Uygulanan küme | Eski tablo (Barça) | Yeni tablo (havuz, LOO) |
|---|---:|---:|
| Barcelona 2018–21 | **0,562** | 0,417 ← tek gerileme |
| Barcelona'nın rakipleri 2018–21 | 0,526 | **0,647** |
| La Liga 2015/16 | 0,452 | **0,575** |
| Premier League 2015/16 | 0,438 | **0,623** |

Üç Barcelona-dışı popülasyon **aynı sıralamayı** üretiyor, bu yüzden LOO ile
tam havuz aynı sayıyı veriyor; tablo tek bir kümeye tutunmuş değil.

Yeni tablo bağımsız kümelerde **küme içi tavana oturuyor**: La Liga 2015/16'da
0,575 (tavan 0,59/0,56), Premier League'de 0,623 (tavan 0,598/0,646). isabet@1
de 0,105→0,210 ve 0,131→0,215 ile ikiye katlanıyor. Permütasyon sınavında
(çıkan oyuncu sahadakilerden rastgele seçilerek, tablo dondurulmuş, 400 deneme)
p = 0,0025.

## Yeni varsayılan tablo

Barcelona-dışı 1409 taktik değişiklik / 300 maç; Laplace düzeltmeli.

| Hücre | Çıkan | Aday gözlemi | Önsel |
|---|---:|---:|---:|
| FWD / ilk 11 | 716 | 3332 | **0,2151** |
| MID / ilk 11 | 526 | 3762 | 0,1400 |
| DEF / ilk 11 | 162 | 5588 | 0,0292 |
| MID / giren | 3 | 536 | 0,0074 |
| DEF / giren | 0 | 214 | 0,0046 |
| FWD / giren | 2 | 658 | 0,0045 |
| GK / ilk 11 | 0 | 1409 | 0,0007 |
| GK / giren | — | 0 | 0,0007 (taban) |

`GK/giren` hiç gözlenmedi (yedek kaleci girip sonra çıkmıyor); gözlenen en küçük
hücrenin değeri taban olarak kondu — Laplace 0/0 hücresine 0,5 verirdi ve bu
yanlış olurdu. Bilinmeyen mevki `elite_off_prior` içinde orta sahaya düşer: en
yüksek önsele değil, **en kalabalık gruba** (3762 aday gözlemi).

## Aday havuzu düzeltmesi

Bir hamlenin adayları "o an sahada olanlar"dır. Eski süzgeç
`start_minute <= hamle dakikası` diyordu; değişiklik olayının kendisi giren
oyuncuya o dakikayı başlangıç yazdığı için **giren oyuncu da aday sayılıyordu**.
Üç popülasyonda da hamlelerin **%100'ünde** havuz 11 yerine 12–14 kişiydi.

Etkisi: rastgele taban k/n olduğu için havuz şiştikçe taban düşüyor, yani her
"kim çıkacak" sonucu olduğundan iyi duruyordu. Düzeltme sonrası her hamlede tam
11 aday var ve taban 0,243 → **0,273** oldu.

İsabet sayıları değişmedi (fazla aday zaten en sona sıralanıyordu, ilk üçü
kimseyi dışarı itmiyordu); değişen yalnız tabandır ve "giren" hücrelerinin
paydasıdır. Karnenin satırı da düzeldi ve boyut geçmeye devam ediyor:

| Karne — "Kim çıkacak" | Önce | Sonra |
|---|---:|---:|
| Motor isabet@3 | 0,524 | 0,524 |
| Rastgele taban@3 | 0,243 | **0,273** |
| Motor isabet@1 | 0,173 | 0,173 |
| Rastgele taban@1 | 0,081 | **0,091** |
| Hüküm | taban çizgisini geçiyor | taban çizgisini geçiyor |

Aynı kusur `coach_iq.py` içinde de vardı ve orada da düzeltildi.

## Bunun bedeli ve kime yarıyor

- **Barcelona benzeri bir kulüp için yeni tablo eskisinden KÖTÜ** (0,562 → 0,417).
  Gizlenmiyor: motor notunda ve burada yazılı.
- Ürünün kendi demo/pilot takımı Beşiktaş'tır, Barcelona değil. Gerçek
  kiracıların hepsi "Barcelona-dışı" popülasyondadır.
- **Karnenin "Kim çıkacak" satırı bu ölçümle otomatik güncellenmez.** O satır
  külliyatta SAKLI `sub_candidates` listelerinden okunur ve o listeler eski
  tabloyla üretildi. `decision_corpus enrich --force` çalıştırılırsa satır
  yeniden hesaplanır ve külliyat Barcelona olduğu için **düşmesi beklenir**
  (önsel tek başına 0,562 → 0,417). Demo sayısının düşmesi ile gerçek kulüpte
  isabetin artması aynı değişikliğin iki yüzüdür.
- Kalıcı çözüm tek tablo değil: yeterli kendi geçmişi olan kiracı
  `fit_who_prior` ile kendi tablosunu kurup `off_prior` ile geçirmelidir.
  Kanca kodda mevcut, bu çalışma onu kullanan bir hat kurmadı.

## Ölçüm sınırları

- **Aday havuzu = o an sahadaki 11 kişi.** Kaleci de sayılır; antrenör kaleciyi
  neredeyse hiç taktik gerekçeyle çıkarmadığı için gerçek seçim havuzu 10 kişiye
  yakındır ve taban (0,273) bu yüzden hafif düşüktür. Karnedeki `who_agreement`
  ile aynı cetvel.
- **Yalnız TAKTİK değişiklikler.** Sakatlık değişiklikleri dışarıda; `CoachMove`
  `substitution.outcome` alanına güvenir.
- **Mevki grubu kaba.** GK/DEF/MID/FWD × ilk11. Kanat/stoper ayrımı, yorgunluk,
  kart, skor durumu yok — daha önce denenip kazanç vermedikleri ölçülmüştü.
- **Üç popülasyon aynı sıralamayı veriyor** ama üçü de Avrupa'nın beş büyük
  liginden. Başka rekabet düzeyi (Süper Lig dahil) sınanmadı.
- **Kadro kaydı eksik hamleler atlandı**: çıkan oyuncu sahadakiler listesinde
  yoksa uydurma aday listesi kurulmadı.

## Tekrar üretim

```powershell
.\venv\Scripts\python.exe -m scripts.validate_who_prior --team 217 --events-dir C:\sb --independent-dir C:\sb-laliga1516 --label "La Liga 2015/16" --out docs/measurements/karne-kim-bagimsiz-laliga-2015-16.json
.\venv\Scripts\python.exe -m scripts.validate_who_prior --team 217 --events-dir C:\sb --independent-dir C:\sb-pl1516 --label "Premier League 2015/16" --out docs/measurements/karne-kim-bagimsiz-premier-league-2015-16.json
```

Script, bağımsız kümenin külliyatla kesişmediğini kendisi denetler ve kesişim
varsa durur. Aday listelerinin SHA-256'sı ölçüm JSON'larında.

Kontroller: **2526 test geçti, 1 atlandı**; ruff temiz; mypy 491 kaynak
dosyasında temiz. Külliyat veritabanına ve ham maç dosyalarına yazılmadı.
