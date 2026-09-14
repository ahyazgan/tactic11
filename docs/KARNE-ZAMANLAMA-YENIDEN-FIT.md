# Zamanlama önseli yeniden fit edildi: yedi küme, hak-farkındalıklı — 14 Eylül 2026

Önceki adım hak-bitti kapısını ekledi ama tablonun kendisi hâlâ tek kulübün 100
maçından ve 3-hak/5-hak **karışımından** geliyordu. Bu çalışma tabloyu yeniden
kurdu.

**Sonuç:** hiç kullanılmamış bir kümede (Dünya Kupası 2022) F1 **0,669 → 0,733**,
yakalama **0,707 → 0,795**. Yeni tablo o kümenin kendi içinde öğrenilebilecek
tavana oturuyor (0,736 / 0,725).

Ölçümler:
[yeniden fit](measurements/timing-prior-fit-2026-09-14.json) ·
[dışarıda-kalan sınav](measurements/karne-zamanlama-holdout-wc2022.json).
Sabit kamera / takip dosyalarına dokunulmadı.

## Kuralları aynı havuza koymayı mümkün kılan şey

Eski tabloda "3 kullanılmış" hücresi iki zıt gerçeği harmanlıyordu: 3 hakken
*bitti/imkânsız*, 5 hakken *2 hak var/çok olası*.

Yeni fit'te **hak-bitmiş tikler tabloya hiç girmiyor** (16559 tikten 1073'ü
elendi). Bu bilgi tabloda değil **kapıda** duruyor (`subs_allowed`). Elenince
"3 kullanılmış" her rejimde tek bir şeyi anlatır: *3 yaptı ve hakkı var*. Ancak
bu sayede 3-hak ve 5-hak verisi aynı havuza konabiliyor — ve konması gerekiyor,
çünkü hücrelerin çoğu (0, 1, 2 kullanılmış) iki rejimde de aynı şeydir.

Tablo ve kapı artık **tek nesne**. Kapısız ölçüm olmayan bir şeyi ölçer; ilk
denememde doğrulama scripti kapıyı atlıyordu ve yeni tabloyu haksız yere kötü
gösterdi (0,759 yerine 0,661). Script artık motorun kendi fonksiyonunu doğrudan
çağırıyor.

## Havuz

| Küme | Maç | Tik | Hak |
|---|---:|---:|---:|
| Barcelona 3-hak (< 2020-06-11) | 54 | 1728 | 3 |
| Barcelona 5-hak (≥ 2020-06-11) | 46 | 1472 | 5 |
| La Liga 2015/16 | 100 | 3200 | 3 |
| Premier League 2015/16 | 100 | 3200 | 3 |
| Indian Super League 2021/22 | 100 | 3200 | 5 |
| FA WSL 2023/24 | 100 | 3200 | 5 |
| Euro 2024 | 51 | 1632 | 5 |

Toplam 16559 kullanılabilir tik, 57 hücre — eski tablonun 3200 tikine karşı
beş katı veri. Erkek/kadın, kulüp/milli, dört ülke, üç kural dönemi **kasten**
karıştırıldı: soru "bu yapı her yerde aynı mı" idi.

Dört 5-hak havuzu birbirine çok benziyor (taban oranı 0,336–0,373; takım başına
ortalama değişiklik 4,04–4,58), yani yapı gerçekten ortak.

## Leave-one-out: her küme kendisi hariç ötekilerden

| Küme | Eski tablo | Yeni tablo |
|---|---:|---:|
| Barcelona 3-hak | 0,761 | 0,758 |
| Barcelona 5-hak | 0,701 | **0,718** |
| La Liga 2015/16 | 0,751 | **0,759** |
| Premier League 2015/16 | 0,698 | 0,699 |
| Indian Super League 2021/22 | 0,653 | **0,703** |
| FA WSL 2023/24 | 0,656 | **0,696** |
| Euro 2024 | 0,659 | **0,735** |
| **Ortalama** | 0,697 | **0,724** |
| **En kötü küme** | 0,653 | **0,696** |

Hiçbir kümede belirgin kötüleşme yok (en büyük düşüş Barcelona 3-hak'ta 0,003);
eski tablonun hiç görmediği üç kümede 0,04–0,08 kazanç.

## Dışarıda-kalan sınav: Dünya Kupası 2022

Bu küme fit'e de, eşik seçimine de, hiçbir ara ölçüme de **girmedi**. 64 maç,
2048 tik, taban oranı 0,367.

| | F1 | İsabet | Yakalama | Kaldırma |
|---|---:|---:|---:|---:|
| Eski tablo, kapısız | 0,667 | 0,630 | 0,708 | 1,72 |
| Eski tablo + kapı | 0,669 | 0,635 | 0,707 | 1,73 |
| **Yeni tablo + kapı** | **0,733** | **0,681** | **0,795** | **1,86** |
| Saat kuralı (≥55 dk, en iyi eşik) | 0,723 | 0,664 | 0,790 | 1,81 |
| Küme içi tavan A / B | 0,736 / 0,725 | | | |

Yeni tablo **tavana oturuyor**. Saat kuralı yine kasten avantajlı (eşiği ölçülen
kümede en iyi seçildi) ve yeni tablo onu geçiyor, ama fark (+0,010) gürültü
bandında — yani bu turnuvada zamanlama hâlâ büyük ölçüde saatin işi.

Görülmemiş hücre payı **sıfır**: 57 hücrelik tablo durum uzayını tamamen
kaplıyor.

## Eşik: plato bulundu, argmax seçilmedi

Eşik tablonun parçası olduğu için birlikte tarandı (leave-one-out ortalama F1):

| Eşik | 0,25 | 0,30 | 0,35 | 0,40 | 0,45 | 0,50 |
|---|---:|---:|---:|---:|---:|---:|
| Ortalama F1 | 0,725 | 0,725 | **0,724** | 0,727 | 0,721 | 0,712 |

0,25–0,40 arası **düz plato** (fark 0,003 = gürültü). Argmax olan 0,40
**seçilmedi**: düz bir bölgede en yüksek ortalamayı seçmek gürültüye uymaktır ve
0,40'ın en kötü kümesi daha kötü (0,689 vs 0,696). Eşik **0,35**'te bırakıldı;
böylece önce/sonra farkı yalnız **tabloya** atfedilebiliyor.

## Ölçüm sınırları

- **İki 2015/16 kümesi artık fit havuzunun içinde.** `validate_timing_prior`
  onlara uygulanırsa sonuç bağımsız değildir; scriptin doküstringi bunu uyarıyor.
  O kümelerin dürüst sayısı leave-one-out sütunudur.
- **Seyrek hücre var.** 57 hücrenin 7'sinde n < 10 (toplam 26 tik, havuzun
  binde ikisi). Laplace bunları 0,33 civarına çekiyor; eşiğin altında kaldıkları
  için bayrak üretmiyorlar, ama küçük sayıdan gelen değerlerdir.
- **"Üç oturum" kısıtı, devre arası istisnası ve uzatma hakkı hâlâ
  modellenmiyor** (önceki raporda da yazılıydı).
- **Hâlâ taklit ölçüyoruz.** "Antrenör değiştirdi mi" sorusu ölçülüyor, "iyi bir
  değişiklik miydi" değil. Bu, karar kalitesi değil takvim uyumudur.
- **Kadın futbolu havuza girdi ama ayrı ölçülmedi.** FA WSL 2023/24 fit'e
  katkıda bulunuyor ve LOO'da 0,696 alıyor; kadın futbolunun kendi yapısı olup
  olmadığı ayrı bir soru.

## Tekrar üretim

```powershell
.\venv\Scripts\python.exe -m scripts.fit_timing_prior --set "Barcelona 3-hak|C:\sb3|3" --set "Barcelona 5-hak|C:\sb5|5" --set "La Liga 2015/16|C:\sb-ll|3" --set "Premier League 2015/16|C:\sb-pl|3" --set "Indian Super League 2021/22|C:\sb-isl|5" --set "FA WSL 2023/24|C:\sb-wsl|5" --set "Euro 2024|C:\sb-euro|5" --threshold 0.35 --print-table --out docs/measurements/timing-prior-fit-2026-09-14.json
.\venv\Scripts\python.exe -m scripts.validate_timing_prior --corpus-dir C:\sb --independent-dir C:\sb-wc22 --label "Dünya Kupası 2022" --subs-allowed 5 --out docs/measurements/karne-zamanlama-holdout-wc2022.json
```

Ayırıcı `|`, çünkü Windows sürücü harfi `:` içerir. Girdi tablosunun SHA-256'sı
ölçüm JSON'unda.

Kontroller: **2560 test geçti, 1 atlandı**; ruff temiz; mypy 499 kaynak
dosyasında temiz. Külliyat veritabanına ve ham maç dosyalarına yazılmadı.
