# Kiracının kendi "kim çıkar" önseli — 14 Eylül 2026

Karnenin en iyi boyutu "kim çıkacak": motor doğru mevki grubunu buluyor. Ama
bağımsız doğrulama bu boyutun sınırını da ölçmüştü:

> **Barcelona benzeri bir kulüp için genel tablo eskisinden KÖTÜ.**
> (`docs/KARNE-KIM-BAGIMSIZ.md`)

Sebebi de yazılıydı: Barcelona'da en çok **orta saha** çıkıyor, veri kümesindeki
başka her yerde **forvet**. Tek bir genel tablo bu iki alışkanlığa aynı anda
doğru cevap veremez.

Dokümante edilmiş çözüm de oradaydı: *"Doğru çözüm kiracının kendi geçmişinden
fit etmektir ve kanca zaten var."* Bu tur o çözümü kurdu ve **ölçtü**.

## Sorulan soru

Kiracının kendi tablosu, kendi maçlarında genel tabloyu geçiyor mu — ve
geçiyorsa kaç maçtan sonra?

## Cetvel

- **Ayrık yarı, MAÇ bazında.** Tablo bir yarıda fit edilir, öteki yarıda
  ölçülür. Genel tablo AYNI ölçüm yarısında değerlendirilir, yani ikisi de
  örneklem dışıdır ve kıyas adildir.
- **Beraberlik tarafsız** (`who_prior_agreement`). Tablo yalnız sekiz hücre;
  aynı gruptaki adaylar birebir eşit değer alır. Beraberliği oyuncu kimliğiyle
  çözmek bu veri kümesinde isabet@1'i 0,125'ten 0,181'e çıkarıyordu — beceri
  değil, tesadüf (`docs/KARNE-SIRALAMA.md`).
- **Kapı kuralı VERİDEN ÖNCE yazıldı:** genel tabloyu **İKİ KOLDA da** en az
  0,02 geçen **en küçük** maç sayısı. Eğri noktaları (10/20/30/40/50) de
  önceden kapatıldı. Eğrinin en iyi noktasını seçmek, on bir adayın en iyisini
  seçmekle aynı hatadır.

## Sonuç

100 maç, 331 hamle (Barcelona 2018–21).

| | kiracı tablosu | genel tablo | rastgele |
|---|---:|---:|---:|
| A'da fit → B'de ölç, isabet@3 | **0,498** | 0,457 | 0,273 |
| B'de fit → A'da ölç, isabet@3 | **0,569** | 0,427 | 0,273 |
| **ortalama** | **0,534** | 0,442 | 0,273 |
| ortalama isabet@1 | 0,181 | 0,125 | — |

İki kol da geçiyor. Kazanç isabet@3'te **+0,092**.

**Kollar arasındaki fark büyük** (+0,041 ve +0,142) — bu tek bir sayıya değil,
yönün iki kolda da aynı olmasına bakılması gerektiği anlamına geliyor. Bakıldı:
aynı.

### Öğrenme eğrisi ve kapı

| eğitim maçı | A kolu isabet@3 | B kolu isabet@3 | ikisi de geçti mi |
|---:|---:|---:|---|
| 10 | 0,430 | 0,518 | hayır (A geçmiyor) |
| **20** | 0,496 | 0,563 | **evet** |
| 30 | 0,498 | 0,566 | evet |
| 40 | 0,498 | 0,566 | evet |
| 50 | 0,498 | 0,569 | evet |

**Kapı: 20 maç.** 10 maçta bir kol geçiyor, öteki geçmiyor — ayrık yarının
bütün amacı bu tür tek kollu sonuçları elemektir. 20'den sonra eğri düzleşiyor;
tablo sekiz hücreli olduğu için daha fazla veri fazla bir şey eklemiyor.

### Fit edilen tablo, belgelenen sebebi bağımsız olarak yeniden buldu

| hücre | kiracı (A kolu) | kiracı (B kolu) | genel tablo |
|---|---:|---:|---:|
| ilk 11 **orta saha** | **0,209** | **0,166** | 0,140 |
| ilk 11 **forvet** | 0,123 | 0,145 | **0,215** |
| ilk 11 defans | 0,056 | 0,062 | 0,029 |
| ilk 11 kaleci | 0,006 | 0,006 | 0,001 |

Sıralama **ters dönüyor**: genel tabloda en yüksek hücre forvet, Barcelona'nın
kendi tablosunda orta saha. İki kol da aynı şeyi söylüyor. Kazancın nereden
geldiği böylece görünür — sayı düzelmiyor, *sıra* düzeliyor.

## Kurulan şey

`app/data/loaders/tenant_prior.py`:

- `tenant_who_states` — `player_appearances`'tan her değişikliği ve o andaki
  aday havuzunu çıkarır.
- `fit_tenant_off_prior` — 20 maçın altında **None** döner; kiracı genel
  tabloyu kullanmaya devam eder.
- `off_prior_for` — görülmemiş hücrede **None** döner. Uydurma 0,5
  ("bilinmiyor") konmaz: genel tablonun o hücre için ölçülmüş bir değeri var ve
  uydurma sayı ondan kötüdür. (Yedek kaleci hücresi tam olarak böyle: kiracı
  verisinde hiç görülmedi.)

Hem admin canlı-karar ucu hem WebSocket paneli aynı yolu kullanıyor. İkisinin
ayrışması bir kez hata oldu (`subs_used`/`off_prior` WebSocket'te hiç
geçilmiyordu, `docs/KARNE-DENETIM.md`); bir test bunu bir daha açtırmıyor.

Panel hangi tablonun konuştuğunu **söylüyor**: `kadro.onsel_kaynagi` alanı
"kiracının kendi geçmişi" ya da "genel elit tablo" der. Kullanılan tabloyu
gizlemek, ölçülmüş sınırı gizlemek olurdu.

## Sızıntı koruması

Canlı maçta fit yapılırken **o maç dışarıda bırakılır** (`exclude_match_id`).
Bırakılmazsa tablo tam da tahmin etmeye çalıştığı hamleden öğrenir. Bu çağıranın
seçimi değil, varsayılan davranıştır ve bir test kapıyı da daralttığını
gösteriyor: sınırdayken bir maç eksilince tablo üretilmiyor.

## İki bilinen sınır

1. **Sakatlık hamleleri — KAPATILDI (19 Eylül).** Bu sınır yazıldığında
   `player_appearances` taktik/sakatlık ayrımı taşımıyordu; sakatlık bir karar
   değil mecburiyettir ve önsele girince tabloyu seyreltiyordu. `0036` göçü
   `substitution_reason` alanını ekledi ("tactical" | "injury" | "red_card"),
   değişiklik ucu sebebi yazıyor, kadro giriş ekranı tek dokunuşla soruyor ve
   fitter sakatlıkları süzüyor.

   **Eski satırlar NULL kalır ve geriye dönük "taktik" VARSAYILMAZ** —
   "sakatlıktı" demek de "taktikti" demek kadar uydurma olurdu. Kullanılırlar
   ama sebepsiz oldukları raporlanır: `reason_coverage` kaç çıkışın sebepli
   kaydedildiğini verir ve panel bunu `kadro.onsel_sebep_kapsamasi` ile
   gösterir. Kapsama düşükken tablo hâlâ seyreltilmiş demektir, ve artık bu
   **görünür**.

   Yukarıdaki 0,092'lik ölçüm olay verisinden `tactical` bayrağıyla süzülmüş
   hamleler üzerinde yapılmıştı; üretim yolu kapsama %100'e çıktıkça o ölçüme
   yaklaşır. Kapsama düşükken **gerçek kazanç 0,092'nin altındadır.**
2. **Tek kiracı ölçüldü — KAPATILDI (19 Eylül), aşağıda.** İki kulüp daha
   ölçüldü; biri kazandı, biri tam sıfır çıktı. Yöntemin her yerde kazanmaması
   sızıntı hipotezini öldürdü ve kapıyı değiştirdi.

## İkinci ve üçüncü kulüp — 19 Eylül 2026

Tek kulüpte ölçülmüş bir kazanç, kazanç değil ipucudur. StatsBomb açık
verisinden, genel tablonun fit havuzunun DIŞINDA iki kulüp daha alındı:

- **PSG** — Ligue 1 2015/16, 2021/22, 2022/23: 94 maç, 298 taktik hamle.
  Barcelona profiline en yakın kulüp (erkek, elit, 3-hak ve 5-hak dönemleri).
- **Arsenal WFC** — FA WSL 2018/19–2020/21 ve 2023/24: 74 maç, 242 hamle.
  Bambaşka bir dünya.

### Ön-kayıtlı beklenti ve neden yanlıştı

Veri gelmeden şu yazıldı: *"PSG genel tablonun fit edildiği dünyaya benziyor;
kazanç orada küçük olmalı (0 ile +0,05). Barcelona'daki +0,092 kadar çıkarsa
sonuca değil ölçüme şüpheyle bakılır — her yerde kazanan yöntem sızıntı kokar."*

PSG'de kazanç **+0,123 / +0,150** çıktı. Beklenti yanlıştı; şüphe protokolü
işledi ve iki teşhis yapıldı. Cetvel temizdi (`UNK` hücresi yok, yarılar
maç bazında, her iki tablo da örneklem dışı). Fit edilen PSG tablosu ise
sebebi gösterdi: **orta saha 0,196 > forvet 0,121** — PSG de Barcelona gibi
orta-saha-önce. Genel tablonun forvet-önce sırası (0,215 > 0,140) ölçülen
**her iki elit erkek kulübünde de tersine dönüyor**. Genel tablo 2015/16 tam
liglerinden (çoğu orta/alt sıra kulübü) ve Barcelona'nın rakiplerinden fit
edilmişti; topa sahip olan elit kulüpler orta sahayı çıkarıyor gibi
görünüyor. Bu bir hipotezdir, iki kulüpten çıkarılmış bir kural değil.

**Arsenal WFC'de fark iki kolda da tam 0,000** — isabet@1 dahil. Bu ancak iki
tablonun her durumda aynı sırayı vermesiyle mümkündür ve teşhis bunu doğruladı:
Arsenal'in hücre sırası genel tablonunkiyle **birebir aynı**
(forvet > orta saha > defans, ilk 11 > yedek). Genel tablo o kulüp için zaten
doğru tablo. Kapı doğru şekilde "bağlanmaz" dedi.

| kulüp | hamle | kiracı isabet@3 | genel | fark (A / B) | kapı |
|---|---:|---:|---:|---|---|
| Barcelona | 331 | 0,534 | 0,442 | +0,041 / +0,142 | geçti |
| PSG | 298 | 0,537 | 0,400 | +0,123 / +0,150 | geçti |
| Arsenal WFC | 242 | 0,429 | 0,429 | 0,000 / 0,000 | **bağlanmaz** |

Yöntem her yerde kazanmıyor: kulübün sırası genel tablodan farklıysa kazanıyor,
aynıysa sıfır. Sızıntı olsaydı Arsenal'de de kazanırdı.

### Bulunan iki zaaf ve düzeltmeleri

**İnce hücre.** PSG tablosunda `('GK', False)` hücresi 1-2 gözlemle Laplace
yüzünden ikinci sıraya tırmandı. Sekiz hücreli tabloda tek bir gözlem bir
hücreyi tepeye taşıyabilir. `WhoPrior` artık hücre başına gözlem sayısını
taşıyor ve `MIN_CELL_OBS` (20) altındaki hücre genel tablonun ölçülmüş değerine
düşüyor — hem üretimde (`off_prior_for`) hem ölçüm scriptinde, yoksa ölçüm
üretimde çalışmayan bir nesneyi ölçerdi. Sayılara etkisi küçük (PSG B kolu
0,541 → 0,544), ama koruma gerçek.

**Sayı kapısı yetmiyor.** Arsenal WFC'nin 20-30 maçlık alt-tablosu A kolunda
genel tablodan **kötü** (0,373 vs 0,443). Üretimdeki kapı yalnız maç sayısına
bakıyordu (20); Arsenal benzeri bir kiracıya 20 maçta genel tablodan kötü bir
tabloyu bağlardı. Ölçülen güvenlik hiçbir zaman maç sayısından gelmiyordu;
"genel tabloyu iki kolda da geçme" kuralından geliyordu — sayı onun
Barcelona'daki vekiliydi. Üretim kapısı artık **o kuralın kendisi**:
`fit_tenant_off_prior` kiracının geçmişini maç bazında ikiye böler, her
yarıdan fit ettiği (ince-hücre korumalı) tabloyu öteki yarıda genel tabloyla
kıyaslar ve tablo ancak iki kolda da en az 0,02 geçerse döner. Bir test,
forvet-önce sentetik bir kulübün 30 maçta bile bağlanmadığını sabitliyor.

`TENANT_PRIOR_MIN_MATCHES` artık kapı değil **taban** (10): sınavın anlamlı
olması için her yarıda birkaç maç gerekir. Değerin 20'den 10'a inmesinin
sebebi ölçümdür, tercih değil — ince-hücre koruması eklenince Barcelona'nın
10 maçlık A-kolu tablosu 0,430'dan 0,498'e çıktı ve iki kulüpte de eğri 10
maçtan itibaren dümdüz kaldı (sekiz hücrede yalnız *sıra* önemli ve 10 maç
sırayı sabitliyor). 10, önceden kapatılmış eğrinin en alt noktasıdır; gerçek
asgari daha düşük olabilir, ölçülmedi.

### Ne bilinmiyor

- "Elit erkek kulüpleri orta-saha-önce" iki kulüpten çıkan bir hipotezdir.
  Üçüncü bir elit kulüp (Bayern 2015/16 ya da 2023/24 açık veride var) bunu
  sınayabilir; ölçülmedi.
- Arsenal WFC bir kadın kulübü. "Kadın futbolu genel-tablo-benzeri" denemez;
  tek kulüp. Chelsea FCW / Manchester City WFC aynı veride mevcut.
- Üretim yolu hâlâ `substitution_reason` kapsamasına bağlı (sınır 1); üç
  ölçüm de olay verisindeki `tactical` bayrağıyla süzülmüş hamlelerle yapıldı.

Ölçümler: [tenant-prior-131-psg.json](measurements/tenant-prior-131-psg.json),
[tenant-prior-968-arsenal-wfc.json](measurements/tenant-prior-968-arsenal-wfc.json);
Barcelona ince-hücre korumasıyla yeniden koşuldu ve güncellendi.

## Tekrar üretim

```powershell
# Veritabanı gerekmez: hamleler ve kadrolar olay dosyalarından okunur.
.\venv\Scripts\python.exe -m scripts.fit_tenant_prior --tenant t-default --team 217 --events-dir C:\sb --out docs/measurements/tenant-prior-217.json
.\venv\Scripts\python.exe -m scripts.fit_tenant_prior --tenant psg --team 131 --events-dir C:\sb-psg --out docs/measurements/tenant-prior-131-psg.json
.\venv\Scripts\python.exe -m scripts.fit_tenant_prior --tenant arsenal-wfc --team 968 --events-dir C:\sb-arsenal-wfc --out docs/measurements/tenant-prior-968-arsenal-wfc.json
```

PSG: Ligue 1 `7/27`, `7/108`, `7/235`; Arsenal WFC: FA WSL `37/4`, `37/42`,
`37/90`, `37/281` (`open-data/data/matches/`). Takım kimliğine göre süzülür.

`--events-dir`: düz klasörde `{match_id}.json` (StatsBomb açık verisi,
`open-data/data/events/`). Girdi tablosunun SHA-256'sı ölçüm JSON'unda.

Ölçüm: [tenant-prior-217.json](measurements/tenant-prior-217.json).

Kontroller: ruff temiz; mypy temiz; `tests/test_tenant_prior.py` kapıyı,
sızıntı korumasını, kırmızı kart ayıklamasını ve geri düşüşü sabitliyor.
