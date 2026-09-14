# Grup içinde kimin çıkacağını bilen sinyal yok — 14 Eylül 2026

Karne şunu ölçmüştü: motor doğru **grubu** buluyor (isabet@3 %47, rastgele %28),
doğru **kişiyi** bulmuyor (%11, rastgele %9 — `docs/KARNE-SIRALAMA.md`). O ölçüm
yorgunluğu **bileşik** olarak sınadı; bileşik içinde tek bir bileşenin maskelenmiş
olma ihtimali açıktı.

Bu çalışma soruyu daralttı: **aynı mevki grubundaki oyuncular arasında**, hangi
tek sinyal antrenörün çıkardığı kişiyi bulur?

**Cevap: hiçbiri.** Ayrık yarıda kazanç **+0,001**, permütasyon **p = 0,62**, ve
iki yarı **farklı** sinyal seçiyor.

Ölçüm: [within-group-signal-2026-09-14.json](measurements/within-group-signal-2026-09-14.json).
Sabit kamera / takip dosyalarına dokunulmadı.

## Neden bu sınav öncekinden sert

- **Grup içi.** Adaylar yalnız çıkan oyuncuyla aynı mevki grubundakiler
  (ortalama 3,6 kişi). Önselin zaten bildiği bilgi tekrar ölçülmüyor; sınanan
  şey saf grup-içi ayrım.
- **Ters yön aday listesinde.** Her sinyal iki yönde de deneniyor. Gerçekten
  bilgi taşıyan bir sinyalin doğru yönü ters yönü açık farkla geçmeli.
- **Beraberlik tarafsız.** Eşit değerli t aday ilk sırayı paylaşıyor → 1/t.
  Sabit bir sıralama kuralı (kimlik, liste sırası) beceri gibi görünürdü — bu
  tuzağa daha önce düşmüştüm.
- **Seçim ayrık yarıda, maç bazında.** Altı sinyal × iki yön = on iki aday.

## Çoklu karşılaştırma tuzağı — canlı örnek

Aynı veride on iki adayın hepsine bakınca tablo umut verici görünüyor:

| Aday | isabet@1 (aynı veride) |
|---|---:|
| son 10 dk müdahale (+) | 0,355 |
| pas isabeti düşüşü (+) | 0,349 |
| son 10 dk pas isabeti (−) | 0,340 |
| dokunuş düşüşü (+) | 0,336 |
| *rastgele* | *0,299* |

İlk okumada "iki sinyal yön gösteriyor" diye yazmıştım. **Yanlıştı.** Ayrık
yarıya geçince:

| Kol | Seçilen | İsabet@1 | Rastgele |
|---|---|---:|---:|
| A'da seç → B'de ölç | son 10 dk müdahale (+) | 0,327 | 0,301 |
| B'de seç → A'da ölç | son 10 dk dokunuş (−) | 0,273 | 0,298 |
| **Ortalama** | — | **0,300** | **0,299** |

İki yarı **farklı** sinyal seçiyor ve ikisi birlikte rastgeleyi geçmiyor.
Permütasyonda (çıkan oyuncu grup içinden rastgele seçilerek, 400 deneme)
p = 0,62.

Bu tabloyu raporda bırakıyorum çünkü ölçümün nasıl yanıltabileceğini gösteren
en iyi örnek bu: on iki adaydan en iyisi, hiçbir şey olmasa bile taban
çizgisinin ~0,05 üstünde görünür.

## Ne anlama geliyor

Motor **grubu** biliyor ve bu bilgi bağımsız maçlarda doğrulandı
(`docs/KARNE-KIM-BAGIMSIZ.md`). Grubun **içinde** kimin çıkacağını olay
verisinden çıkarmanın yolu yok — denenen altı sinyalin hiçbiri, iki yönde de,
rastgeleyi geçmiyor.

Ürün açısından sonuç değişmiyor ama artık ölçülmüş: motor dürüstçe **"bu üç
oyuncudan biri"** diyebilir, **"kesinlikle bu"** diyemez. Arayüzün üç ismi
sıralı liste gibi göstermesi olmayan bir kesinlik iddia eder.

Geliştirme açısından daha değerli olan şudur: **bu yön kapalı.** Yorgunluk
bileşiğinin ağırlığını ayarlamak, yeni bir olay-türevi sinyal denemek ya da
bileşeni yeniden harmanlamak bu kararı düzeltmez. Grup içi seçim için elimizde
olmayan veri gerekiyor:

- GPS yükü (gerçek koşu mesafesi, hızlanma sayısı)
- sakatlık riski / kas durumu
- kart durumu ve hakem eğilimi
- antrenörün maç öncesi planı ("60'ta onu alacağım")

## Ölçüm sınırları

- **Tek külliyat.** 329 değişiklik, 100 maç, Barcelona. Bağımsız kümelerde
  tekrarlanmadı: pas/müdahale olayları yalnız külliyat veritabanında var, ham
  StatsBomb dosyalarından ayrıca çıkarılması gerekir.
- **Altı sinyal denendi**, hepsi olay sıklığı/isabeti türevi. Başka türetmeler
  (xT katkısı, alan kazanımı, ikili mücadele) denenmedi; ama hepsi aynı olay
  akışından gelir ve aynı sınırın içindedir.
- **Grup = kaba mevki** (GK/DEF/MID/FWD). Kanat-stoper ayrımı yapılsaydı gruplar
  1-2 kişiye düşerdi ve soru anlamını yitirirdi.
- **Yalnız taktik değişiklikler**; sakatlık hamleleri dışarıda.
- **Olumsuz sonuç "imkânsız" demek değildir.** Bu veriyle, bu sinyallerle,
  bu n'de bulunamadı demektir.

## Tekrar üretim

```powershell
.\venv\Scripts\python.exe -m scripts.measure_within_group_signal --tenant t-default --team 217 --events-dir C:\sb --out docs/measurements/within-group-signal-2026-09-14.json
```

Girdi tablosunun SHA-256'sı ölçüm JSON'unda.

Kontroller: **2607 test geçti, 1 atlandı**; ruff temiz; mypy 506 kaynak
dosyasında temiz. Külliyat veritabanına ve ham maç dosyalarına yazılmadı.
