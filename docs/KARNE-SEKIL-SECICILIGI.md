# Karne: şekil değişikliği seçiciliği — ölçüm ve değişiklikler — 14 Eylül 2026

> **Tarihsel ölçüm — güncel sonuçlar ayrı raporda.** Aşağıdaki sonuçlar
> `e0237df` koduna aittir. İncelemede uygun aday yokken ilk eşiğin seçildiği ve
> aynı dakikadaki iki oyuncu değişikliğinin tek sayıldığı bulundu. Düzeltme
> eğitim/kontrol bütçelerini gerçek sayılarla kontrol eder, uygun aday yoksa
> hüküm vermez ve oyuncuları ayrı sayar. Sonlu permütasyonda p=0 raporlanmaz;
> yetersiz veride p değeri yoktur. Aşağıdaki sayılar düzeltilmiş kodun başarısı
> olarak kullanılamaz. Aynı 100 maç ve 514 tik, eski girdi SHA-256'sı birebir
> eşleştirilerek yeniden ölçüldü: güncel kaldırma **1,427/1,603**, isabet
> **0,314/0,327**. [Düzeltme sonuçları](KARNE-DUZELTME-SONUCLARI.md).

Motor 514 tikin **%74'ünde** "şekil ayarla" diyordu; gerçek antrenör aynı
pencerede dizilişi tiklerin yalnız **%21'inde** değiştiriyordu. Bu çalışma
önce cetvelin kendisini, sonra bayrağın seçiciliğini ölçtü.

**Sonuç:** ham bayrak hiçbir şey bilmiyor (kaldırma 0,91/1,08 ≈ 1,0).
Elit diziliş önseli + destekleyici sinyal eşiğiyle kapatılan bayrak, bayrak
oranını **%74 → %19**'a indirirken isabeti **%21 → %37**'ye çıkarıyor
(kaldırma **1,65/1,85**, permütasyon p = 0,005 / 0,000). Eşikler ayrık
yarıda seçildi, ölçüm öteki yarıda yapıldı.

Başlangıç: `4eb685b`. Sayısal kanıt:
[karne-sekil-seciciligi-2026-09-14.json](measurements/karne-sekil-seciciligi-2026-09-14.json).
Kaynak maç dosyaları ve veritabanı değiştirilmedi. Sabit kamera / takip
dosyalarına dokunulmadı.

## Bulgu 1 — eski cetvel (F1) bu soruda cetvel değil

Karne diziliş satırını F1 ile tartıyordu ve motor saatin altında çıkıyordu.
Aynı veride **hep-evet** demenin F1'i motorunkinden yüksek:

| Kural | F1 | Bayrak oranı |
|---|---:|---:|
| Motor "şekil ayarla" teması | 0,328 | 0,72 / 0,76 |
| Hep-evet (hiç bilgi yok) | **0,350** | 1,00 |
| Saat kuralı (eşik ayrık yarıda) | 0,412 | 0,80 |

Hedef nadir olduğunda (taban %21) F1, recall'ü ucuza satın alan bol bayrağı
ödüllendirir. "Daha seçici ol" ile "F1'i yükselt" bu tabloda **zıt** yönlerdir;
saat kuralının 0,412'si de seçicilikten değil, %80 bayrak oranından geliyor.

Seçicilik cetveli bu yüzden **kaldırma**: `precision / taban oranı`. 1,0 =
bayrak taban oranından fazlasını bilmiyor. Yanına her zaman bayrak oranı
yazılır — kaç öneriyle bunu yaptığı sorunun yarısıdır.

## Bulgu 2 — motorun hiçbir sayısı diziliş değişimini ayırmıyor

Tik başına saklanan her sürekli sayı için diziliş değişiminin AUC'si:

| Sinyal | AUC | Sinyal | AUC |
|---|---:|---|---:|
| dakika | **0,634** | corroboration | 0,565 |
| priority | 0,561 | n_support | 0,557 |
| score | 0,552 | subs_used | 0,550 |
| urgency | 0,543 | magnitude | 0,515 |
| confidence | 0,492 | quality / sample | 0,500 |

Tema oranı da aynı şeyi söylüyor: `adjust_shape` tiklerinde diziliş değişimi
oranı **0,211**, genel taban **0,212**. Tema, diziliş hakkında bir iddia değil;
`context_engine` içinde tactical / momentum / spatial / matchup / feed /
hot_hand sinyallerinin ortak ETİKETİ ve eşleşmeyen tipin varsayılanı. Aşırı
öneri burada başlıyor: bayrak "diziliş değişmeli" demiyor, "taktik bir şey var"
diyor. Bilgi taşıyan tek değişken zaman (ve dolaylı olarak skor/değişiklik
durumu) — yani motorun kendi kanıtı değil, **anın durumu**.

## Bulgu 3 — kapı: elit önsel × destekleyici sinyal eşiği

İki eşik, eğitim yarısında seçilir, öteki yarıda ölçülür:

1. **Diziliş değişimi önseli** — hücre `(dakika bandı × skor durumu × yapılan
   değişiklik)`, Laplace düzeltmeli oran, görülmemiş hücre 0,5 (bilinmiyor).
2. **Destekleyici sinyal sayısı** — o tikte kaç sinyalin birlikte yandığı.

Eşik seçim ölçütü **F1 değil**: bayrak bütçesi en az `SHAPE_MIN_FLAG_RATE`
(0,15) olan adaylar arasında en yüksek precision. F1'e göre seçmek bütçeyi
sonuna kadar harcayıp seçiciliği ortadan kaldırırdı. Alt bütçe sınırı da bir
avuç bayrakla şişmiş precision'ın kazanmasını engelliyor.

| Ayrık yarı A / B | Bayrak oranı | Bayrak sayısı | İsabet | **Kaldırma** | Yakalama |
|---|---:|---:|---:|---:|---:|
| Önce — ham bayrak (tema) | 0,72 / 0,76 | 189 / 191 | 0,20 / 0,22 | **0,91 / 1,08** | 0,66 / 0,82 |
| Sonra — kapılı bayrak | 0,18 / 0,21 | 47 / 53 | 0,36 / 0,38 | **1,65 / 1,85** | 0,29 / 0,39 |

Öğrenilen eşikler iki yarıda da aynı çıktı: önsel ≥ 0,30 ve ≥ 2 destekleyici
sinyal (A için 250, B için 264 tikten öğrenildi). Hüküm: **seçici**
(kabul eşiği: iki yarıda da kaldırma ≥ 1,25).

**Permütasyon sınavı.** Etiketler karıştırılıp kapı sıfırdan kuruldu, 400
deneme: karıştırılmış veri gerçeğin isabetini A yarısında 2/400, B yarısında
0/400 kez yakaladı (p = 0,005 / 0,000). Kaldırma tesadüf değil.

**Bedel açıkça yazılır:** yakalama 0,74'ten 0,35'e düşüyor. Kapı, gerçek
diziliş değişimlerinin üçte ikisini kaçırıyor. Seçicilik ile kapsama arasındaki
bu takas koçun kararıdır; karne ikisini de gösterir, birini ötekinin arkasına
saklamaz.

## Ölçüm sınırları

- **Hedef zayıf vekil.** StatsBomb "Tactical Shift" etiketi kadro değişince de
  yeniden yazılıyor: bu külliyatta diziliş olaylarının **%89'u** aynı pencerede
  bir oyuncu değişikliğiyle birlikte. Yani kapı kısmen "değişiklik anı"nı
  öğreniyor olabilir. Bağımsız diziliş etiketi olmadan bu ayrılamaz.
- **Tek takım, tek külliyat.** 100 maç, takım 217, 514 tik, 109 pozitif. Kapılı
  bayrak yarı başına 47–53 tik; küçük sayı.
- **Destek eşiğinin payı ayrı kanıtlanmadı.** Yalnız önselle kaldırma 1,45/1,63,
  destek eşiği eklenince 1,65/1,85. İki yarıda da aynı yönde ama fark küçük;
  "destekleyici sinyal sayısı bağımsız bilgi taşıyor" iddiası bu ölçümle
  kanıtlanmış sayılmaz. Kapı bütünü permütasyon sınavını geçti, bileşeni değil.
- **Motorun canlı çıktısı değişmedi.** Kapı karnenin ölçüm katmanındadır.
  Gerçek öneriyi %19 bayrağa kısmak, yakalamayı üçte ikiye düşürmek demek ve
  hedef zayıf vekil — bu, ölçümle değil pilot kararıyla verilir.
- Kalibrasyon, cetvel kontrolü ve "kim çıkar" boyutları bu çalışmanın ölçümü
  değildir; karnenin o satırları değişmedi.

## Tekrar üretim

Komutlar repo kökünden. `--events-dir` ham StatsBomb `events/<match_id>.json`
klasörüdür (100 maç; diziliş değişimi yalnız ham olayda var, DB olay tablosunda
pas/şut/müdahale tutulur). Girdi tablosunun SHA-256'sı ölçüm JSON'unda.

```powershell
.\venv\Scripts\python.exe -m scripts.measure_shape_selectivity --tenant t-default --team 217 --events-dir C:\sb --out docs/measurements/karne-sekil-seciciligi-2026-09-14.json
.\venv\Scripts\python.exe -m scripts.coach_iq --tenant t-default --team 217 --events-dir C:\sb
```

Karnenin "ŞEKİL ÖNERİSİ SEÇİCİLİĞİ" bloğu aynı kapıyı aynı ayrık yarılarla
yeniden kurar; iki komutun sayıları eşleşmelidir.

Kontroller: **2498 test geçti, 1 atlandı**; ruff temiz; mypy 483 kaynak
dosyasında temiz.
