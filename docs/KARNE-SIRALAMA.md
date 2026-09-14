# Değişiklik önerisi sıralaması: doğru grup, yanlış kişi — 14 Eylül 2026

Motor bir değişiklik önerirken üç isim veriyor ve bunları sıralıyor. İki ayrı
soru var ve bugüne kadar tek sayıda karışıyorlardı:

- **Doğru grubu mu buluyor?** Antrenörün çıkardığı oyuncu ilk üçte mi?
- **Doğru kişiyi mi seçiyor?** İlk sıradaki gerçekten o mu?

**Cevap: grubu buluyor, kişiyi bulmuyor.** İlk üçte %47 isabet (rastgele %28),
ama ilk sırada %11 (rastgele %9). Ters kontrol bunu doğruluyor: yorgunluk
sıralamasını TERS çevirmek sonucu kötüleştirmiyor, hatta ilk sırada hafifçe
iyileştiriyor. Yani grup içindeki sıralama bilgi taşımıyor.

Ayrıca bir kusur bulundu ve giderildi: eşit aday puanlarında sıralama `set`
yineleme sırasına düşüyordu — koça gösterilen 1. öneri oyuncu kimliğinin
hash'ine bağlıydı.

Ölçüm: [sub-ranking-2026-09-14.json](measurements/sub-ranking-2026-09-14.json).
Sabit kamera / takip dosyalarına dokunulmadı.

## Sonuçlar

Külliyat: 331 gerçek taktik değişiklik, ortalama 10,8 aday.

| Sıralama kuralı | isabet@1 | isabet@3 |
|---|---:|---:|
| Motor harmanı (w = 0,6) — bugünkü | 0,114 | **0,466** |
| Saf yorgunluk bileşiği (w = 0) | 0,125 | 0,357 |
| Saf önsel (w = 1) | 0,125 | 0,442 |
| Önsel, eşitlikte bileşik | 0,114 | **0,466** |
| **TERS KONTROL: önsel, eşitlikte TERS bileşik** | **0,126** | 0,434 |
| Rastgele | 0,093 | 0,279 |

n = 331, standart hata ≈ 0,018. isabet@1 sütunundaki bütün değerler birbirinin
ve rastgelenin 1–2 standart hatası içinde.

## Ters kontrol neden belirleyici

Bir sinyalin bilgi taşıyıp taşımadığını anlamanın en ucuz yolu yönünü ters
çevirmektir. Yorgunluk grup içindeki sırayı gerçekten belirliyorsa, "en az yorgun
önce" kuralının "en yorgun önce"den **kötü** olması gerekir.

Olmuyor: ters yön ilk sırada 0,126, doğru yön 0,114. Fark gürültü bandında ama
yön yanlış. Yorgunluk bileşiği grup içinde hangi oyuncunun çıkacağını
**bilmiyor**; `ROLE_PRIOR_WEIGHT` ağırlığını ayarlamak bu kararı düzeltmez.

Harman ağırlığının isabet@3'e etkisi de yok: w ≥ 0,2 için 0,466'da sabit. Grubu
belirleyen önseldir; bileşik yalnız grup içini karıştırır.

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
.\venv\Scripts\python.exe -m scripts.measure_sub_ranking --tenant t-default --team 217 --events-dir C:\sb --out docs/measurements/sub-ranking-2026-09-14.json
```

Aday tablosunun SHA-256'sı ölçüm JSON'unda (`kaynak.girdi_sha256`).

Kontroller: **2538 test geçti, 1 atlandı**; ruff temiz; mypy 492 kaynak
dosyasında temiz. Külliyat veritabanına ve ham maç dosyalarına yazılmadı.
