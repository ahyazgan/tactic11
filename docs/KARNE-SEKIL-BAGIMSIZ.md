# Şekil önseli külliyat dışında: bağımsız doğrulama — 14 Eylül 2026

Şekil kapısı bugüne kadar yalnız tek külliyatın (100 La Liga maçı, Barcelona,
2018/19–2020/21) ayrık yarılarında ölçülmüştü. Ayrık yarı eşik seçimini dürüst
tutar ama "aynı takımın aynı sezonlardaki alışkanlığını ezberledi mi" sorusunu
elemez. Bu çalışma kapıyı hiç görmediği maçlara taşıdı.

**Sonuç: taşınıyor.** Külliyattan öğrenilip dondurulan önsel, iki bağımsız
kümede de tabanın **2,0–2,2 katı** isabetle bayrak kaldırıyor (permütasyon
p = 0,0025). Premier League'de dondurulmuş önsel, o kümenin **kendi içinde
öğrenilebilecek tavana eşit** çıktı.

Ayrıca ölçüm bir kusur buldu ve giderildi: önselin hiç görmediği hücrelerde kapı
bayrak kaldırıyordu ve o bayrakların kaldırması **tam 1,0** — sıfır bilgi.
Kapı artık görülmemiş hücrede susuyor (`SHAPE_UNKNOWN_CELL`).

Kod: `71f3512` üzerine. Sayısal kanıt:
[La Liga 2015/16](measurements/karne-sekil-bagimsiz-laliga-2015-16.json) ·
[Premier League 2015/16](measurements/karne-sekil-bagimsiz-premier-league-2015-16.json) ·
[külliyat v3](measurements/karne-sekil-seciciligi-2026-09-14-v3.json).
Sabit kamera / takip dosyalarına dokunulmadı.

## Bağımsız kümeler ve kesişim güvencesi

| Küme | Maç | Izgara tiki | Diziliş taban oranı |
|---|---:|---:|---:|
| Külliyat (La Liga 18/19–20/21, Barcelona) | 100 | 514 motor tiki | 0,212 |
| La Liga 2015/16 | 100 | 3200 | 0,145 |
| Premier League 2015/16 | 100 | 3200 | 0,107 |

Örnekler 380'er maçlık havuzlardan **belirlenimci** olarak (eşit aralıkla)
seçildi. Script külliyat kimlikleriyle kesişimi kendisi denetler ve kesişim
varsa durur: sızıntılı bir "bağımsız" küme ölçüm değildir. Her iki kümede de
kesişim 0.

Bağımsız maçlarda motor tiki yoktur (o maçlar için karar külliyatı üretilmedi),
bu yüzden anlar sabit bir ızgaradan alınır (10–85 dk arası her 5 dk, iki takım
için ayrı ayrı — `coach_iq`'nun plasebo ızgarasıyla aynı).

## Ne taşındı, ne taşınamaz

Kapı üç parçadır: motorun `adjust_shape` bayrağı ∧ durum önseli ∧ destekleyici
sinyal sayısı ≥ eşik. Bağımsız maçlarda motor tiki olmadığı için yalnız **durum
önseli** taşınabilir. Bu bir eksiklik değil, önceki ölçümün sonucudur: motor
bayrağının külliyattaki kaldırması 0,91/1,08 idi — bilgi taşımıyor. Sinyali
taşıyan parça önseldir ve sınanan da odur. Destek eşiği motor tikine bağlıdır
ve bu sınavın dışındadır.

## Taşıma sonuçları

| | La Liga 2015/16 | Premier League 2015/16 |
|---|---:|---:|
| Hep-evet (taban referansı) | kaldırma 1,00 | kaldırma 1,00 |
| **Karne önseli, dondurulmuş** | **2,01** (bayrak 0,27 · isabet 0,29 · yakalama 0,54) | **2,21** (bayrak 0,25 · isabet 0,24 · yakalama 0,56) |
| Izgara önseli, dondurulmuş | 2,08 (bayrak 0,18) | 2,16 (bayrak 0,18) |
| Küme içi tavan (ayrık yarı) | 2,51 / 2,22 | 2,19 / 2,16 |
| Permütasyon p (dondurulmuş önsel) | 0,0025 | 0,0025 |

"Izgara önseli" aynı külliyat maçlarından ama aynı ızgara üzerinde kurulan
önseldir; motor tiklerinin dağılımı ile ızgaranın farkını taşıma farkından
ayırır. İkisi birbirine yakın çıktı: taşımayı bozan şey tik dağılımı değil.

**Premier League'de dondurulmuş önsel (2,21) küme içi tavana (2,19/2,16) eşit.**
Yani Barcelona'nın üç sezonundan öğrenilen durum yapısı, başka bir ülkenin
başka bir dönemindeki yirmi takım için de o kümede öğrenilebilecek her şeyi
veriyor. La Liga 2015/16'da tavanın biraz altında (2,01 vs 2,51/2,22).

Permütasyon sınavında önsel **yeniden kurulmaz** — taşınan nesne sabittir,
sınanan tek şey onun bu kümedeki isabetidir. 400 denemede karıştırılmış
etiketler gerçeği hiç yakalamadı; p = (0+1)/(400+1) = 0,0025.

## Bulunan kusur: "bilinmiyor" bayrak sayılıyordu

Önselin hiç görmediği hücrede kapı 0,5 varsayıp bayrak kaldırıyordu. Bağımsız
kümelerde bu bayrakların ne kadar işe yaradığı ölçüldü:

| Hücre türü | La Liga 15/16 | Premier League 15/16 |
|---|---:|---:|
| Görülmüş hücre | 2867 tik · bayrak 861 · **kaldırma 2,06** | 2820 tik · bayrak 811 · **kaldırma 2,23** |
| Görülmemiş hücre | 333 tik · bayrak 333 · **kaldırma 1,00** | 380 tik · bayrak 380 · **kaldırma 1,00** |

Görülmemiş hücrede kaldırma tam 1,00: bayrak taban oranından fazlasını
bilmiyor, ama bütçenin yaklaşık %30'unu harcıyor ve genel kaldırmayı aşağı
çekiyor. Zamanlama ve "kim çıkar" önsellerinde "bilinmiyor = 0,5" doğrudur,
çünkü orada soru **sıralamadır**; burada soru **seçiciliktir** ve "bu durumu hiç
görmedim" şekil değiştirmek için kanıt değildir.

Kapı artık görülmemiş hücrede susuyor (`SHAPE_UNKNOWN_CELL = 0.0`). Karar
külliyatın ayrık yarısında verildi — orada da iki yarıda birden iyileşiyor:

| Külliyat, ayrık yarı A / B | Önce (bilinmiyor = bayrak) | Sonra (bilinmiyor = sus) |
|---|---:|---:|
| Bayrak oranı | 0,193 / 0,208 | 0,155 / 0,200 |
| İsabet | 0,314 / 0,327 | 0,341 / 0,340 |
| **Kaldırma** | 1,427 / 1,603 | **1,550 / 1,667** |
| Yakalama | 0,276 / 0,333 | 0,241 / 0,333 |
| Permütasyon p | 0,042 / 0,005 | 0,005 / 0,005 |

Zamanlama önseli (`apply_timing_prior`) ve "kim çıkar" önseli
(`apply_who_prior`) **değişmedi**; oradaki 0,5 varsayılanı yerinde duruyor.

## Ölçüm sınırları

- **Provenans dürüstlüğü.** Görülmemiş-hücre kusuru bağımsız kümelerde fark
  edildi. Değişiklik kararı yalnız külliyatın ayrık yarısında verildi (yukarıdaki
  tablo), ama bağımsız kümelerin taşıma sayıları bu özel seçim için artık saf
  "hiç görülmemiş veri" sayılmaz. Bağımsız kalan asıl iddia şudur ve değişiklikten
  ÖNCE de ölçülmüştü: eski varsayılanla bile kaldırma 1,78 / 1,83 idi.
- **Hedef hâlâ zayıf vekil.** StatsBomb "Tactical Shift" etiketi kadro değişince
  de yeniden yazılıyor. Önsel hücresinde `subs_used` zaten var, yani önsel kısmen
  "değişiklik anı"nı öğreniyor olabilir. Bağımsız diziliş etiketi olmadan bu
  ayrılamaz ve iki bağımsız küme de aynı etiketi kullanıyor.
- **Izgara ≠ motor tiki.** Bağımsız kümede anlar 5 dakikalık ızgaradan alındı.
  "Izgara önseli" sütunu bu farkın taşımayı bozmadığını gösteriyor ama aynı şey
  değil. Bağımsız maçlarda gerçek motor tiki ancak o maçlar için karar külliyatı
  üretilirse olur.
- **Değişiklik hakkı farkı.** Külliyatın 2020/21 sezonunda 5, öteki sezonlarda ve
  iki bağımsız kümede 3 değişiklik hakkı vardı. Önsel hücresi `subs_used`'ı 3'te
  kapatıyor; bu fark ölçülmedi.
- **Motorun canlı çıktısı hâlâ kısılmadı.** Yakalama 0,54–0,56; kapı gerçek
  diziliş değişimlerinin yaklaşık yarısını kaçırıyor. Canlı filtreyi açmak
  pilot kararıdır, ölçüm kararı değil.

## Tekrar üretim

Ham olaylar `statsbomb/open-data` deposundan; bağımsız örnek listeleri
`matches/11/27.json` ve `matches/2/27.json` içindeki maç kimliklerinin sıralı
listesinden eşit aralıkla 100'er maçtır. Izgara tik tablolarının SHA-256'ları
ölçüm JSON'larında (`bagimsiz_kume.girdi_sha256`).

```powershell
.\venv\Scripts\python.exe -m scripts.measure_shape_selectivity --tenant t-default --team 217 --events-dir C:\sb --out docs/measurements/karne-sekil-seciciligi-2026-09-14-v3.json
.\venv\Scripts\python.exe -m scripts.validate_shape_prior --tenant t-default --team 217 --events-dir C:\sb --independent-dir C:\sb-laliga1516 --label "La Liga 2015/16" --out docs/measurements/karne-sekil-bagimsiz-laliga-2015-16.json
.\venv\Scripts\python.exe -m scripts.validate_shape_prior --tenant t-default --team 217 --events-dir C:\sb --independent-dir C:\sb-pl1516 --label "Premier League 2015/16" --out docs/measurements/karne-sekil-bagimsiz-premier-league-2015-16.json
```

Kontroller: **2522 test geçti, 1 atlandı**; ruff temiz; mypy 490 kaynak dosyasında
temiz. Külliyat veritabanına ve ham maç dosyalarına yazılmadı.
