# Değişiklik önerisi sıralaması: doğru grup, yanlış kişi — 14 Eylül 2026

Motor bir değişiklik önerirken üç isim veriyor ve bunları sıralıyor. İki ayrı
soru var ve bugüne kadar tek sayıda karışıyorlardı:

- **Doğru grubu mu buluyor?** Antrenörün çıkardığı oyuncu ilk üçte mi?
- **Doğru kişiyi mi seçiyor?** İlk sıradaki gerçekten o mu?

**Cevap: grubu buluyor, kişiyi bulmuyor.** İlk üçte %47 isabet (rastgele %28),
ama ilk sırada %12,5 (rastgele %9). Ters kontrol bunu doğruluyor: yorgunluk
sıralamasını TERS çevirmek sonucu kötüleştirmiyor, hatta ilk sırada hafifçe
iyileştiriyor. Yani grup içindeki sıralama bilgi taşımıyor.

Ayrıca bir kusur bulundu ve giderildi: eşit aday puanlarında sıralama `set`
yineleme sırasına düşüyordu — koça gösterilen 1. öneri oyuncu kimliğinin
hash'ine bağlıydı.

Ölçüm: [sub-ranking-2026-09-14-v2.json](measurements/sub-ranking-2026-09-14-v2.json) (düzeltme sonrası); önceki koşum [sub-ranking-2026-09-14.json](measurements/sub-ranking-2026-09-14.json).
Sabit kamera / takip dosyalarına dokunulmadı.

> **Yeniden koşuldu (14 Eylül, denetim sonrası).** Ölçümden sonra iki motor
> kusuru düzeltildi — yorgunluk skorunun eylem bileşeni 45. dakikadan sonra
> herkes için 1,0'a kilitleniyordu, ve önsel normalizasyonu motorunkinden
> farklıydı (`docs/KARNE-DENETIM.md`). İkisi de buradaki sıralamayı besliyor,
> bu yüzden ölçüm AYNI 101 maçla baştan koşuldu. Aşağıdaki tablo düzeltme
> SONRASIdır; önce/sonra kıyası hemen altında.

## Sonuçlar

Külliyat: 331 gerçek taktik değişiklik, ortalama 10,8 aday.

| Sıralama kuralı | isabet@1 | isabet@3 |
|---|---:|---:|
| Motor harmanı (w = 0,6) — bugünkü | 0,125 | 0,474 |
| Saf yorgunluk bileşiği (w = 0) | 0,103 | 0,317 |
| Saf önsel (w = 1) | 0,125 | 0,442 |
| Önsel, eşitlikte bileşik | 0,125 | **0,476** |
| **TERS KONTROL: önsel, eşitlikte TERS bileşik** | **0,131** | 0,435 |
| Rastgele | 0,093 | 0,279 |

n = 331, standart hata ≈ 0,018. isabet@1 sütunundaki bütün değerler birbirinin
ve rastgelenin 1–2 standart hatası içinde.

### Düzeltme öncesi / sonrası

| Sıralama kuralı | önce@1 | sonra@1 | önce@3 | sonra@3 |
|---|---:|---:|---:|---:|
| Motor harmanı (w = 0,6) | 0,114 | 0,125 | 0,466 | 0,474 |
| Saf yorgunluk bileşiği (w = 0) | 0,125 | 0,103 | 0,357 | 0,317 |
| Saf önsel (w = 1) | 0,125 | 0,125 | 0,442 | 0,442 |
| Önsel, eşitlikte bileşik | 0,114 | 0,125 | 0,466 | 0,476 |
| TERS KONTROL | 0,126 | 0,131 | 0,434 | 0,435 |
| Rastgele | 0,093 | 0,093 | 0,279 | 0,279 |

**İki sağlama tuttu.** *Saf önsel* yorgunluğa hiç dokunmaz ve kılı kıpırdamadı
(0,125 / 0,442). Rastgele taban da aynı kaldı — yani aynı 331 vaka seçildi,
ortalama aday 10,78 ile birebir aynı. Değişen yalnız yorgunluğun karıştığı
satırlar; değişmesi gerekenler değişti, değişmemesi gerekenler durdu.

**Hüküm değişmedi.** Grup bilgisi var (isabet@3'te rastgelenin +0,195 üstü,
yaklaşık 10 standart hata). Grup içi bilgi yok: ters kontrol hâlâ doğru yönü
geçiyor (0,131 vs 0,125).

**Düzeltilmiş yorgunluk tek başına daha KÖTÜ** (0,125 → 0,103). Bu ters gibi
görünüyor ama abartılmamalı: fark 1,2 standart hata, yani gürültü. Mekanizması
da anlaşılır — bozuk bileşen herkeste 1,0'a doymuş olduğu için bileşiğe hiçbir
şey katmıyordu; düzeltilince katkı vermeye başladı ve kattığı şey bilgi değil.
Bu, ana bulguyu zayıflatmıyor, **güçlendiriyor**: yorgunluk grup içindeki
sırayı gerçekten bilmiyor, üstelik şimdi bunu doğru hesaplanmış hâliyle
bilmiyor.

## Ters kontrol neden belirleyici

Bir sinyalin bilgi taşıyıp taşımadığını anlamanın en ucuz yolu yönünü ters
çevirmektir. Yorgunluk grup içindeki sırayı gerçekten belirliyorsa, "en az yorgun
önce" kuralının "en yorgun önce"den **kötü** olması gerekir.

Olmuyor: ters yön ilk sırada 0,131, doğru yön 0,125. Fark gürültü bandında ama
yön yanlış. Yorgunluk bileşiği grup içinde hangi oyuncunun çıkacağını
**bilmiyor**.

Bu, sözlük sıralamasıyla (önsel önce, bileşik yalnız eşitlik bozar) ölçülmüş
bir hükümdür. Harman ağırlığını değiştirmek ayrı bir sorudur ve ayrıca sınandı
— sonuç aşağıda: ayrık yarı bir ipucu verdi, ters kontrol onu tutmadı.

## Harman ağırlığı: ayrık yarı bir ipucu verdi, ters kontrol onu tutmadı

Yeniden koşumda eski bir cümle çöktü: "harman ağırlığının isabet@3'e etkisi yok,
w ≥ 0,2 için sabit" artık doğru değil. Ağırlık süpürmesi düz değil:

| w | isabet@1 | isabet@3 |
|---:|---:|---:|
| 0,0 (saf bileşik) | 0,103 | 0,317 |
| **0,2** | **0,154** | 0,453 |
| **0,4** | 0,136 | **0,482** |
| 0,6 (bugünkü) | 0,125 | 0,474 |
| 1,0 (saf önsel) | 0,125 | 0,442 |

On bir adayın örneklem-içi en iyisini seçmek tam da bu deponun tekrar tekrar
yakaladığı hata, bu yüzden ağırlık **ayrık yarıda** seçildi: bir yarıda seç,
öteki yarıda ölç.

| ölçüt | A'da seç → B'de ölç | B'de seç → A'da ölç | örneklem dışı | seçim bedeli |
|---|---|---|---:|---:|
| isabet@1 | w = 0,2 → 0,183 | w = 0,2 → 0,123 | **0,153** | 0,001 |
| isabet@3 | w = 0,4 → 0,509 | w = 0,4 → 0,454 | **0,482** | 0,000 |

**İki yarı da aynı ağırlığı seçti ve seçim bedeli sıfıra yakın.** Ön-kayıtlı
kararlılık ölçütü (`docs/MAC-ICI-YUK-PLANI.md`, madde 3) sağlanıyor. Örneklem
dışı isabet@1 0,153; bugünkü w = 0,6 ise 0,125, rastgele 0,093.

### Ama ağırlık DEĞİŞTİRİLMEDİ

Ters kontrol temiz geçmiyor:

| ölçüt | doğru yön | ters yön | fark | saf önsel | saf bileşik | rastgele |
|---|---:|---:|---:|---:|---:|---:|
| isabet@1 (w = 0,2) | 0,154 | 0,140 | 0,014 | 0,125 | 0,103 | 0,093 |
| isabet@3 (w = 0,4) | 0,482 | 0,450 | 0,032 | 0,442 | 0,317 | 0,279 |

Bileşiğin yönünü çevirmek isabet@1'i yalnız 0,014 düşürüyor — **0,8 standart
hata**, yani gürültü. Daha belirleyicisi: ters sürüm (0,140) hâlâ hem saf
önseli (0,125) hem saf bileşiği (0,103) geçiyor. Bileşik gerçekten kimin
çıkacağını bilseydi, yönü çevrilince saf önselin ALTINA düşmesi gerekirdi.

Kazanç bilginin değil, karışımın kendisinin: önselin yalnız sekiz ayrık değeri
var ve adayların çoğu beraberlikte. Bileşiği karıştırmak o beraberlikleri
açıyor — hangi yönde açtığı neredeyse fark etmiyor. Yönden bağımsız bir kazanç,
tanımı gereği o sinyalin bilgisi değildir.

Buna ek olarak külliyat **tek kulübün** 101 maçı ve o kulüp veri kümesinin en
atipik takımı (`docs/KARNE-KIM-BAGIMSIZ.md`). Tek kümede ayarlanmış bir ağırlık
zaten taşınmazdı.

**Karar: `ROLE_PRIOR_WEIGHT` 0,6'da kaldı.** Değiştirmek için iki şey gerekir —
bağımsız bir külliyatta tekrar eden aynı ağırlık, ve ters kontrolün gerçekten
DÜŞMESİ (ters yön saf önselin altına inmeli). İkisi de yok. İpucu kayda geçiyor,
ürüne girmiyor.

### İkinci külliyatta tekrar: PSG — 19 Eylül 2026, ipucu düştü

PSG'nin 95 maçı veritabanına alındı (`scripts/ingest_club_matches.py`, yerel
StatsBomb dosyalarından) ve aynı ölçüm `--all-matches` ile koşuldu: 298 taktik
değişiklik, ortalama 10,77 aday. Ölçümden önce kayda geçen beklenti: *ipucu
tekrar etmez; ayrıca harmanın önseli genel tablodur ve genel tablo PSG için
yanlış sıradadır (PSG orta-saha-önce, `docs/KARNE-KIRACI-ONSELI.md`), yani saf
önsel burada zayıf kalmalı.*

| Sıralama kuralı | isabet@1 | isabet@3 |
|---|---:|---:|
| Motor harmanı (w = 0,6) — bugünkü | 0,107 | 0,389 |
| Saf yorgunluk bileşiği (w = 0) | 0,120 | 0,299 |
| Saf önsel (w = 1) | 0,115 | 0,401 |
| Önsel, eşitlikte bileşik | 0,111 | 0,389 |
| **TERS KONTROL** | **0,131** | **0,402** |
| Rastgele | 0,093 | 0,279 |

Ana bulgu PSG'de de aynı: grup bilgisi var (+0,110 isabet@3), grup içi bilgi
yok — ters yön yine doğru yönü geçiyor. Grup kazancı Barcelona'dakinden küçük
(+0,110 vs +0,195), tam da beklendiği gibi: bu ölçümde motor **genel** önseli
kullanıyor ve genel tablo PSG'nin sırasını yanlış biliyor.

**Ağırlık ipucunun iki şartı da düştü:**

| ölçüt | A'da seç → B'de ölç | B'de seç → A'da ölç | örneklem dışı | bugünkü w = 0,6 |
|---|---|---|---:|---:|
| isabet@1 | w = 0,2 → 0,137 | w = **0,1** → 0,113 | 0,125 | 0,107 |
| isabet@3 | w = 0,2 → 0,379 | w = **0,9** → 0,361 | 0,370 | **0,389** |

1. **Yarılar aynı ağırlığı seçmedi.** isabet@3'te biri 0,2, öteki 0,9 — yani
   ölçek üzerinde neredeyse iki uç. Bu, kararsızlığın ta kendisi. Üstelik
   örneklem dışı isabet@3 (0,370) bugünkü ağırlığın altında kaldı.
2. **Ters kontrol düşmedi, tersine döndü.** w = 0,2'de bileşiğin yönünü
   çevirmek isabet@1'i 0,131'den 0,133'e, isabet@3'ü 0,399'dan **0,419'a**
   çıkarıyor. Yorgunluk bileşiği PSG'de de kimin çıkacağını bilmiyor; çevrilmiş
   hâli daha iyi.

Barcelona'daki w = 0,2 kazancı, tek kulübe özgü bir beraberlik-açma
artefaktıymış. `ROLE_PRIOR_WEIGHT` 0,6'da kalıyor ve bu soru **kapandı**.

Açık kalan tek şey ayrı bir sorudur: bu ölçüm motorun genel önselini kullanır.
PSG kendi tablosunu kullansaydı (üretimde kullanacak — kapıyı geçti) grup
kazancı büyür; ölçüm scripti henüz kiracı tablosuyla koşmuyor.

Ölçüm: [sub-ranking-psg-2026-09-19.json](measurements/sub-ranking-psg-2026-09-19.json).

## Beraberlik tarafsızlığı — ölçümün kendisi de düzeltildi

Motor aciliyeti 3 haneye yuvarlıyor, bu yüzden aynı mevki grubundaki oyuncular
sık sık eşitleniyor. Eşitliği herhangi bir **sabit** kurala bırakmak ölçümü
bozuyor:

- Küme yineleme sırası → oyuncu kimliğinin hash'i.
- Oyuncu kimliğine göre artan sıra → bu veri kümesinde küçük kimlik daha eski
  oyuncu demek ve eski oyuncular daha çok çıkıyor. Tek başına bu tercih
  isabet@1'i 0,093'ten 0,181'e çıkarıyordu. **Beceri değil, veri kümesi
  tesadüfü.** İlk okumada bunu "saf önsel iki kat daha iyi" diye yorumladım;
  yanlıştı.

**Bu düzeltme önce YALNIZ bu scripte uygulandı.** Karnenin kendi cetveli
(`apply_who_prior` + `who_agreement`) aynı kimlik sırasını kullanmaya devam
ediyordu ve bir denetimde yakalandı: orada da külliyat isabet@1'ini 0,125'ten
0,181'e çıkarıyordu. Ölçüm artık kademe sayıyor (`who_prior_agreement`).
Ders: bir ölçüm tuzağı bulunduğunda aynı tuzağın ÖTEKİ kullanım yerleri de
taranmalı — bir yerde düzeltmek yetmiyor.

Script artık beraberlikleri rastgele sayıyor ve **beklenen** isabeti
hesaplıyor: aynı anahtarı paylaşan t aday ilk sırayı paylaşıyorsa isabet@1 =
1/t; ilk üç sınırı bir kademeyi ortadan bölüyorsa beklenen pay
kalan yer / kademe boyu. Beraberlik yoksa sonuç yine 0/1.

## Motordaki düzeltme

`candidates.sort(key=lambda c: -c.urgency_score)` kararlı bir sıralamadır, yani
eşitlikte listeye ekleme sırası korunur — o da `my_player_ids` **kümesinin**
yineleme sırasıydı. Sonuç: koça gösterilen 1. öneri eşit adaylar arasında
oyuncu kimliğinin hash'ine göre seçiliyordu. Tekrar üretilemez ve savunulamaz.

Sıralama artık açık: **aciliyet, sonra yorgunluk, sonra oyuncu kimliği.**
Ölçülen isabeti değiştirmez (yukarıdaki tabloya göre grup içi sıra zaten bilgi
taşımıyor); değiştirdiği şey çıktının belirlenimli ve açıklanabilir olmasıdır.

## Bunun ürüne anlamı

Motor şunu dürüstçe söyleyebilir: *"Bu üç oyuncudan biri çıkacak"* — ve %47
haklı çıkar, rastgelenin %28'ine karşı. Söyleyemeyeceği şey: *"Kesinlikle bu
oyuncu."* Orada rastgeleden farkı yok.

Arayüz üç ismi **sıralı bir liste** gibi gösteriyorsa, olmayan bir kesinlik
iddia ediyor demektir. Üçünü eşit ağırlıkta bir küme olarak sunmak ölçümle
uyumlu olan tek gösterimdir. Bu çalışma arayüzü değiştirmedi; kararı ve
gerekçesi burada duruyor.

Grup içinde kimin çıkacağını bilmek için elimizde olmayan veri gerekiyor:
GPS yükü, sakatlık riski, kart durumu, antrenörün maç planı. Daha önce
denenenler (sarı kart, son 15 dk düşük katılım, skor durumu) ölçüldü ve kazanç
vermedi (bkz. `coach_benchmark` ölçüm günlüğü).

**Sonradan daha sert sınandı:** altı olay-türevi sinyal, iki yönde, yalnız grup
İÇİNDE, seçim maç bazında ayrık yarıda — kazanç +0,001, permütasyon p = 0,62,
iki yarı farklı sinyal seçti. Bu yön kapalıdır:
[grup içi sinyal ölçümü](KARNE-GRUP-ICI-SINYAL.md).

## Ölçüm sınırları

- **Tek külliyat, tek takım.** 331 değişiklik, Barcelona 2018–21. Önselin
  kendisi bağımsız maçlarda doğrulandı (`docs/KARNE-KIM-BAGIMSIZ.md`) ama bu
  sıralama ölçümü tekrarlanmadı: bağımsız maçlar için pas/müdahale olayları
  veritabanında yok, yalnız ham StatsBomb dosyaları var.
- **Yorgunluk vekil.** `fatigue_signal` olay sıklığının erken/geç oranıdır,
  gerçek fiziksel yük değil. "Yorgunluk bilgi taşımıyor" sonucu bu vekile
  aittir; GPS yüküyle sonuç farklı olabilir.
- **Aday eşiği motorunkiyle aynı**: penceresinde 5'ten az olayı olan oyuncu
  değerlendirilmiyor, bu yüzden ortalama aday 11 değil 10,8.
- **Yalnız taktik değişiklikler**; sakatlık değişiklikleri dışarıda.

## Tekrar üretim

```powershell
# Külliyat veritabanı ŞART: adaylar oradan, olaylar --events-dir'den gelir.
$env:DATABASE_URL = "sqlite:///C:/.../demo.db"
# --events-dir: düz klasörde {match_id}.json (StatsBomb açık verisi,
# open-data/data/events/). Külliyattaki 101 maçın 100'ü gerçek maçtır.
.\venv\Scripts\python.exe -m scripts.measure_sub_ranking --tenant t-default --team 217 --events-dir C:\sb --out docs/measurements/sub-ranking-2026-09-14-v2.json

# İkinci kulüp (karar külliyatı yok): önce maçlar ve olaylar yerel dosyalardan DB'ye, sonra --all-matches.
.\venv\Scripts\python.exe -m scripts.ingest_club_matches --tenant psg --team 131 --matches C:\sb-matches\7_27.json --matches C:\sb-matches\7_108.json --matches C:\sb-matches\7_235.json --events-dir C:\sb-psg
.\venv\Scripts\python.exe -m scripts.measure_sub_ranking --tenant psg --team 131 --events-dir C:\sb-psg --all-matches --out docs/measurements/sub-ranking-psg-2026-09-19.json
```

Aday tablosunun SHA-256'sı ölçüm JSON'unda (`kaynak.girdi_sha256`).

Kontroller: **2670 test geçti, 6 atlandı**; ruff temiz; mypy 510 kaynak
dosyasında temiz. Külliyat veritabanına ve ham maç dosyalarına yazılmadı.
