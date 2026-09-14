# Maç içi yük: ön-kayıtlı sınav planı — 14 Eylül 2026

Bu doküman **veri gelmeden önce** yazıldı. Amacı tek: GPS verisi eline geçtiğinde
hangi sınavın yapılacağı, hangi eşiğin aranacağı ve neyin başarı sayılacağı
önceden sabitlensin.

Gerekçe deneyimle sabit. Aynı projede üç kez, veriye baktıktan **sonra** ölçüt
seçmenin sonucu şişirdiğini gördük:

1. Beraberlikleri oyuncu kimliğine göre çözmek isabet@1'i 0,093'ten 0,181'e
   çıkardı — bu veri kümesinde küçük kimlik daha eski oyuncu demek.
2. `set` yineleme sırası "saf önsel iki kat iyi" görüntüsü verdi.
3. Altı sinyal × iki yönün en iyisi, ortada hiçbir şey yokken bile tabanın
   0,056 üstünde çıktı (`docs/KARNE-GRUP-ICI-SINYAL.md`).

Veri geldikten sonra plan yazılırsa dördüncüsü olur. Bu yüzden şimdi yazılıyor.

## Cevaplanacak soru

Karnenin ölçülmüş tek zayıflığı: motor doğru **mevki grubunu** buluyor
(isabet@3 %47, rastgele %28) ama grubun **içinden** doğru kişiyi seçemiyor
(%11, rastgele %9). Olay verisinden türetilen altı sinyal iki yönde de sınandı,
hiçbiri geçmedi (ayrık yarıda +0,001, permütasyon p = 0,62).

**Soru:** gerçek koşu yükü grup içindeki seçimi açıklıyor mu?

## Gereken veri

`POST /admin/matches/{id}/load-samples` — maç içi, **kümülatif**, dakika
çözünürlüklü. Bir maç için en az:

- ilk 11 + oyuna giren her oyuncu,
- 5 dakikada bir örnek (daha sık olabilir),
- `total_distance_m` **zorunlu**; `high_speed_m`, `sprint_m`, `accelerations`
  varsa çok daha iyi,
- `speed_thresholds` — hangi hız eşiğiyle "yüksek hız" sayıldığı. Kulüpten
  kulübe değişir; yazılmazsa kümeler arası kıyas geçersizdir.

**Asgari hacim:** 60 maç / ~200 taktik değişiklik. Gerekçe: mevcut ölçüm 329
değişiklikle çalışıyor ve grup içi ortalama 3,6 aday var; 200 değişiklikte
0,05'lik bir farkın standart hatası ≈ 0,032, yani ancak 1,5σ. Daha azıyla
"bulduk" demek dürüst olmaz.

## Sınanacak sinyaller — liste ŞİMDİ kapatılıyor

Her biri, çıkan oyuncunun hamle anındaki durumu, **aynı mevki grubundaki**
takım arkadaşlarına göre:

1. `toplam_mesafe` — o ana kadarki kümülatif mesafe
2. `mesafe_dakika_basina` — kümülatif mesafe / oynadığı dakika
3. `yuksek_hiz_mesafesi` — kümülatif HSR
4. `son10_mesafe_dususu` — son 10 dk hızı, önceki döneme göre
5. `son10_yuksek_hiz_dususu` — aynısı HSR için
6. `ivmelenme_sayisi` — kümülatif accel + decel
7. `cihaz_yuku` — cihazın kendi bileşik AU değeri (varsa)
8. `azami_hiz_dususu` — son 10 dk azami hızı, maçın en yükseğine göre

**Sekiz sinyal, iki yön = on altı aday.** Liste bu kadar; veri görüldükten
sonra sinyal EKLENMEZ. Eklenirse bu doküman geçersiz olur ve yeni bir
ön-kayıtla baştan başlanır.

## Sınavın kuralları

Mevcut `scripts/measure_within_group_signal.py` ile **aynı** — o script olay
sinyalleri için yazıldı, yük sinyalleri aynı boru hattından geçecek:

- **Grup içi.** Adaylar yalnız çıkan oyuncuyla aynı mevki grubunda.
- **Beraberlik tarafsız.** Eşit değerli t aday ilk sırayı paylaşır → 1/t.
- **Seçim ayrık yarıda, MAÇ bazında.** On altı adayın en iyisi bir yarıda
  seçilir, öteki yarıda ölçülür; iki yön de raporlanır.
- **Permütasyon.** Çıkan oyuncu grup içinden rastgele seçilerek 400 deneme;
  p = (yakalama + 1) / (deneme + 1).

## Kabul ölçütü — şimdi sabitleniyor

Yük sinyali motora **ancak şu üçü birden** sağlanırsa bağlanır:

1. Ayrık yarı ortalaması rastgele tabanı **en az 0,05** geçecek.
2. Permütasyon **p ≤ 0,05**.
3. İki yarı **aynı sinyali ve aynı yönü** seçecek. (Grup içi ölçümde iki yarı
   farklı sinyal seçmişti; bu tek başına sonucun gürültü olduğunun işaretiydi.)

Üçü birden sağlanmazsa sonuç **"yük de bilmiyor"** diye yazılır ve sinyal
bağlanmaz. Eşikler burada, veriden önce duruyor.

## Bağlanırsa nasıl bağlanır

`compute_live_sub_recommendation` zaten dışarıdan önsel alabiliyor
(`off_prior`). Yük sinyali de aynı kapıdan, ayrı bir parametre olarak girer;
tablo gibi donmuş bir sabite gömülmez. Sebebi: yük eşikleri kulüp ve cihazla
değişir, tek bir global sayı yanlış olur — `ELITE_OFF_PRIOR`'ın tek kulüpten
fit edilip her kulübe uygulanmasıyla aynı hata olurdu
(`docs/KARNE-KIM-BAGIMSIZ.md`).

## Takipten türetilen yük ayrı değerlendirilir

Video takibi de konum üretir, dolayısıyla mesafe hesaplanabilir
(`source="tracking"`). Ama oyuncu kimliği elle eşleniyor ve takım ataması şu an
%80 civarı. Bu yüzden:

- GPS ve takip kaynaklı örnekler **ayrı ayrı** ölçülür, karıştırılmaz.
- Takip kaynaklı veri kabul ölçütünü geçse bile, kimlik eşlemesinin doğruluğu
  ayrıca raporlanmadan öneriye bağlanmaz.

## Şu an ne var, ne yok

| | Durum |
|---|---|
| Tablo (`match_load_samples`) | var — kümülatif, dakika çözünürlüklü |
| Göç (0033) | var |
| Giriş uç noktası | var — `POST /admin/matches/{id}/load-samples` |
| Ölçüm boru hattı | var — `measure_within_group_signal` |
| **Veri** | **yok** |
| Öneriye bağlantı | **yok** ve ölçülene kadar olmayacak |

Bu, boş bir boru döşemek değil: sınav planı yazılı olduğu için veri geldiği gün
tek komutla cevap alınır, ve cevabın "evet" çıkması için önceden ne gerektiği
belli.

## Kulüpten istenecek şey — tek cümle

*"60 maç boyunca, her oyuncu için 5 dakikada bir kümülatif koşu mesafesi ve
yüksek-hız mesafesi; hangi hız eşiğini kullandığınızı da yazın."*

Bu, GPS yeleği kullanan her kulübün zaten sahip olduğu ve dışa aktarabildiği
bir çıktıdır.

Kontroller: **2633 test geçti, 1 atlandı**; ruff temiz; mypy 509 kaynak
dosyasında temiz; göç zinciri `0033_match_load_samples`'a kadar uçtan uca
çalışıyor.
