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

1. **Sakatlık hamleleri ayıklanamıyor.** `player_appearances` taktik/sakatlık
   ayrımı taşımıyor. Kırmızı kartlar ayıklanıyor (`red_cards`), sakatlıklar
   ayıklanamıyor ve tabloyu seyreltiyor. Yukarıdaki ölçüm taktik hamleleri
   süzebiliyordu (olay verisinden `tactical` bayrağı), üretim yolu süzemiyor —
   **yani gerçek kazanç buradaki 0,092'den bir miktar DÜŞÜK olabilir.** Bunu
   kapatmanın yolu değişiklik kaydına sebep alanı eklemektir; eklenmedi.
2. **Tek kiracı ölçüldü.** Sonuç "bir kiracının kendi tablosu kendi maçlarında
   genel tabloyu geçer" der. Mekanizma geneldir (genel tablo kulüp-dışı fit
   edilmiştir) ama ikinci bir kiracıda tekrarlanmadı. Barcelona bu veri
   kümesinin en atipik takımı, yani kazanç muhtemelen **üst sınıra yakın**.

## Tekrar üretim

```powershell
$env:DATABASE_URL = "sqlite:///C:/.../demo.db"
.\venv\Scripts\python.exe -m scripts.fit_tenant_prior --tenant t-default --team 217 --events-dir C:\sb --out docs/measurements/tenant-prior-217.json
```

`--events-dir`: düz klasörde `{match_id}.json` (StatsBomb açık verisi,
`open-data/data/events/`). Girdi tablosunun SHA-256'sı ölçüm JSON'unda.

Ölçüm: [tenant-prior-217.json](measurements/tenant-prior-217.json).

Kontroller: ruff temiz; mypy temiz; `tests/test_tenant_prior.py` kapıyı,
sızıntı korumasını, kırmızı kart ayıklamasını ve geri düşüşü sabitliyor.
