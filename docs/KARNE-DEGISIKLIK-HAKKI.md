# Değişiklik hakkı: "3 kullanılmış" hücresi iki zıt gerçeği harmanlıyordu — 14 Eylül 2026

Zamanlama önselinin doküstringi bir uyarı taşıyordu: *"2018-21'de hak 3'tü;
5-hak kuralıyla yeniden fit gerekir."* Bu çalışma o boşluğu ölçtü.

Önselin hücresi `(dakika bandı, skor durumu, kullanılmış hak ≤ 3)`. Kural 3
hakken "3 kullanılmış" = **hak bitti, değişiklik imkânsız**. Kural 5 hakken aynı
hücre = **2 hak var, değişiklik çok olası**. Tablo bu iki dünyanın karışımından
fit edilmişti.

**Bulgu doğrulandı ve giderildi.** Motora *hak-bitti kapısı* eklendi: hak
bittiyse olasılık öğrenilmez, **0'dır**. Bu öğrenilmiş bir tahmin değil, kuralın
kendisi.

Ölçüm: [sub-allowance-2026-09-14.json](measurements/sub-allowance-2026-09-14.json).
Sabit kamera / takip dosyalarına dokunulmadı.

## Doğal deney: aynı kulüp, aynı lig, değişen kural

Külliyat kural değişimini içeriyor: La Liga COVID sonrası **2020-06-11**'de 5
hakla yeniden başladı. Maçlar tarihe göre ayrıldı — **sezona göre ayırmak
yanlış olurdu**, çünkü 2019/20 sezonunun son çeyreği de 5 haklıdır. İlk denemede
sezona göre ayırıp kirli bir küme elde ettim; tarih ayrımı bunu düzeltti.

| Küme | Maç | Takım başına ort. değişiklik | 4+ değişiklik yapan takım oranı |
|---|---:|---:|---:|
| 3-hak (< 2020-06-11) | 54 | 2,93 | **%0** |
| 5-hak (≥ 2020-06-11) | 46 | 4,32 | **%80** |
| La Liga 2015/16 | 100 | 2,90 | %0 |
| Premier League 2015/16 | 100 | 2,79 | %0 |

Ayrım gerçek ve keskin: 3-hak döneminde hiçbir takım 4 değişiklik yapmamış.

## Harmanlanan hücre

"3 kullanılmış" hücresinde, sonraki 12 dakikada değişiklik olma oranı:

| Küme | Oran | n |
|---|---:|---:|
| 3-hak (< 2020-06-11) | **0,000** | 169 |
| La Liga 2015/16 (3 hak) | **0,000** | 335 |
| Premier League 2015/16 (3 hak) | **0,000** | 228 |
| 5-hak (≥ 2020-06-11) | **0,672** | 125 |

Üç bağımsız 3-hak kümesinde de tam sıfır — tesadüf değil, kuralın kendisi.
5-hak döneminde aynı hücre 0,672. Üretim tablosu karışımdan öğrendiği için
ikisinin arasında bir yerde duruyor ve her iki dünyaya da yanlış cevap veriyor.

Sonucu 5-hak döneminde görülüyor: yakalama 0,898'den **0,753'e** düşüyor. Motor,
hakkı olan takıma "değişiklik penceresi kapalı" diyor.

## Çözüm: öğrenilen değil, mantıksal

Hak bittiyse değişiklik kural gereği imkânsızdır. Dolayısıyla oradaki her bayrak
zaten **yanlış pozitifti** ve kapı yalnız onları siler — yakalamaya matematiksel
olarak dokunamaz. Ölçüm bunu doğruluyor:

| Küme | F1 (kapısız → kapılı) | Yakalama |
|---|---:|---:|
| 3-hak (< 2020-06-11) | 0,749 → **0,761** | 0,898 → 0,898 |
| 5-hak (≥ 2020-06-11) | 0,697 → **0,701** | 0,753 → 0,753 |
| La Liga 2015/16 | 0,741 → **0,751** | 0,900 → 0,900 |
| Premier League 2015/16 | 0,693 → **0,698** | 0,884 → 0,884 |

Dört kümede de iyileşiyor, hiçbirinde bozulmuyor, yakalama sabit.

Çapraz dönem matrisinde de kapı her hücreyi iyileştiriyor: kapısız F1 aralığı
0,600–0,766 iken kapılı 0,704–0,766. En büyük kazanç tam beklendiği yerde —
3-hak döneminden öğrenip 5-hak dönemine taşırken **0,635 → 0,726**.

## Kodda ne değişti

- `elite_sub_window_probability(..., subs_allowed=5)`: hak bittiyse `0.0` döner.
- `compute_sub_timing(..., subs_allowed=5)` ve canlı karar uç noktası bu
  parametreyi geçirir.
- Varsayılan **5** (IFAB kuralı 2022'den beri). Bu varsayılan **güvenli
  yöndedir**: 3-hak bir maçta kapı hiç ateşlenmez, yani yanlışlıkla öneri
  bastırmaz — yalnız düzeltmeyi kaçırır. Eski maçları yeniden oynatırken o
  dönemin hakkı verilmelidir.

## Yapılmayan: tabloyu yeniden fit etmek

Kapı, harmanın yarısını mantıkla kesiyor ama **tablonun kendisi hâlâ karışımdan
geliyor**. Kapıyla birlikte yeniden fit ölçüldü: 5-hak döneminde F1 0,719'dan
**0,746**'ya çıkıyor.

Yeniden fit **edilmedi**, çünkü elimizdeki 5-hak örneği yalnız 46 maç / 1472 tik
ve hepsi tek kulübün maçları. Hangi veriyle fit edileceği ayrı bir karardır:
StatsBomb'da 5-hak döneminden başka lig verisi var (Euro 2024, Dünya Kupası
2022, kadın ligleri 2023/24), ama rekabet düzeyi ve turnuva formatı farklı.
Bu, bir sonraki adımın konusu.

## Ölçüm sınırları

- **"Üç oturumda" kuralı modellenmedi.** 5 hak, en fazla 3 oyun durmasında
  kullanılabilir. Bu kısıt tabloya da kapıya da girmiyor.
- **Devre arası sayılmıyor.** Devre arasındaki değişiklik oturumdan sayılmaz;
  ızgara bunu ayırmıyor.
- **Uzatma hakkı yok.** 90 dakikayı aşan maçlarda ek hak verilir; ızgara 85'te
  bitiyor, bu yüzden sorun oluşturmuyor ama modellenmiş de değil.
- **5-hak örneği tek kulüp.** 46 maç, Barcelona. Kapının kendisi mantıksal
  olduğu için bundan etkilenmez; yeniden fit kararı etkilenir.

## Tekrar üretim

```powershell
.\venv\Scripts\python.exe -m scripts.measure_sub_allowance --events-dir C:\sb --match-index C:\sb-idx --extra-set "La Liga 2015/16|C:\sb-laliga1516|3" --extra-set "Premier League 2015/16|C:\sb-pl1516|3" --out docs/measurements/sub-allowance-2026-09-14.json
```

`--match-index` StatsBomb `matches/<comp>/<season>.json` klasörüdür; maç
tarihleri oradan gelir. Ayırıcı `|`, çünkü Windows sürücü harfi `:` içerir.

Kontroller: **2557 test geçti, 1 atlandı**; ruff temiz; mypy 498 kaynak
dosyasında temiz. Külliyat veritabanına ve ham maç dosyalarına yazılmadı.
