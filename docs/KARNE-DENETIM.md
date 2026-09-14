# Kod denetimi: 43 bulgu, ne çıktı — 14 Eylül 2026

Karne ve karar zekâsı hattına çok mercekli bir denetim uygulandı. Tarama fazı
bitti (8 mercek, 43 tekil bulgu); **doğrulama fazı oturum limitine takıldı**.
Yani elde sınav görmemiş ham iddialar kaldı. Bu doküman sınavın sonucudur.

Ham bulgu bir iddiadır, bulgu değil. Bu depoda ölçüm iddialarının şişmesi
tekrarlayan bir sorun oldu; denetimin kendi çıktısına da aynı şüphe uygulandı.

## Sınav nasıl yapıldı

İki aşama. Önce her iddia GÜNCEL koda karşı okundu (tarama sırasında doğru
olup sonradan düzeltilmiş olabilir). Sonra hayatta kalanların her birine iki
ayrı mercek saldırdı: biri "iddia yanlış" demeye çalıştı, öteki "doğru ama
önemsiz" demeye çalıştı. İkisini de geçen bulgu kabul edildi.

**Hayatta-kalma kuralı düzeltildi.** Önceki turda kural "çürüten sayısı < 2"
idi; iki doğrulayıcıdan biri oturum limitinde düşerse bulgu "hayatta kaldı"
sayılıyordu. Yani ölü ajan sessizce ONAY oluyordu. Yeni kural: beklenen
mercek sayısı dönmezse bulgu **doğrulanamadı** sayılır, hayatta kalmış değil.

Yüksek yakınsamalı bulgular (aynı satırı birden çok tarayıcının bulduğu)
elle sınandı; kalan 16'sı ikinci bir iş akışıyla (39 ajan, 0 hata).

## Sonuç

| | Sayı |
|---|---:|
| Tekil bulgu | 43 |
| Elle sınanan (yüksek yakınsama) | 27 |
| İş akışıyla sınanan | 16 |
| **Gerçek çıkan ve düzeltilen** | **15** |
| Zaten düzeltilmiş (önceki PR'larda) | 3 |
| Çürütülen | 5 |

### Çürütülenler — neyin bulgu OLMADIĞI da kayda değer

- **`decision_corpus.py:319` sıralaması `measure_sub_ranking`'i bozuyor.**
  Bozmuyor: o script külliyatın kayıtlı `sub_candidates` sırasını hiç okumuyor,
  adayları olaylardan kendisi kuruyor.
- **`measure_sub_ranking.py:209` aday eşiği paydayı bozuyor.** Yapısal kusur
  gerçek ama ölçülen sonuca etkisi gösterilemedi.
- **`coach_iq.py:85` plasebo penceresi çakışıyor.** Etki var ama mevcut
  yayımlanmış sonucun ALEYHİNE, lehine değil — yani sonucu şişirmiyor.
- **`decision_corpus.py:169` külliyat kapısız üretildi.** Doğru, ama etkisi
  tek yönlü ve küçük.
- **`coach_iq.py:442` kadro kaydı eksik değişiklikler.** Yön doğru, pratik
  büyüklüğü kanıtlanamadı.

## Düzeltilenler ve her birinin yayımlanmış sayıya etkisi

### Motor davranışını DEĞİŞTİRENLER (ölçümler yeniden koşulmalı)

**1. Yorgunluk skorunun yarısı bilgi taşımıyordu.**
`action_drop` ham eylem SAYIMINDAN hesaplanıyordu, oysa erken ve geç pencereler
eşit uzunlukta değil. Varsayılan pencerelerde bile erken (0,30) 30 dakika, geç
(30,45) 15 dakika: tempo hiç düşmese bile sayım yarıya iner, `raw_drop` = 0,5
ve `/0,5` normalizasyonuyla bileşen **tam 1,0**. Canlı yolda daha beter —
75. dakikada erken 60 dk, geç 15 dk; doyuma girmemek için oyuncunun son 15
dakikada temposunu İKİYE KATLAMASI gerekiyordu. **45. dakikadan sonra her
oyuncuda 1,0'a kilitliydi.** Artık dakika başına tempodan hesaplanıyor.

**2. Önsel normalizasyonu motorunkinden farklıydı.**
`measure_sub_ranking` tepe önseli eylem eşiğinden SONRAKİ aday listesinden
alıyordu; motor onu eşikten ÖNCEKİ havuzdan alır. En yüksek önselli oyuncu
eşikte elenirse tepe çöker ve modellenen sıralayıcı motorunki olmaktan çıkar.

→ `docs/KARNE-SIRALAMA.md` sayıları **yeniden koşulmalı** ve o sayfa böyle
işaretlendi. Ana bulgunun ("grubu buluyor, kişiyi bulmuyor") ayakta kalması
bekleniyor — ters kontrol zaten yorgunluk sıralamasının bilgi taşımadığını
söylüyordu ve birinci kusur bunun bir sebebini açıklıyor.

### Ölçüm CETVELİNİ düzeltenler

**3. İki motor tanımının en iyisi sabit tabana karşı raporlanıyordu**
(`docs/KARNE-TANIM-SECIMI.md`). Seçim bedeli artık ödeniyor.

**4. Grup içi ölçümde taban ile isabet farklı paydalardan geliyordu.**
Yayımlanmış +0,001 sonucu etkilenmedi (seçilen iki sinyal 329 vakanın hepsinde
tanımlıydı, kollar 168 + 161 = 329) ama hata canlıydı: pas isabeti sinyalleri
321 ve 318 vakada tanımlıydı.

**5. Öncü süre taban çizgisi olmadan raporlanıyordu.** Ölçüt penceredeki EN
ERKEN bayrak olduğu için her tikte bayrak yakan bir kural azami öncü süreyi
alır — sayı öngörüden değil tik ızgarasının geometrisinden gelir. Doygun taban
artık yanında basılıyor; eşitse not bunu söylüyor.

**6. Kalibrasyonun beceri sütunu kendi tabanını kullanmıyordu.**
`1 − ECE/0,25` sabit ölçeği, saf tabanla EŞİT bir sistemi bile ödüllendiriyordu.
`Dimension.skill` sözleşmesi "taban = 0" der; `skill_from_error` bunu sağlıyor.

### Canlı yol ile ölçülen yolu ayıranlar

**7. WebSocket paneli `subs_used` ve `off_prior` geçirmiyordu.** Hak-bitti
kapısı hiç ateşlenmiyordu: hakkı bitmiş takıma "şimdi değiştir" denmeye devam
ediyordu. Panelde çalışan motor, karnenin ölçtüğü motor değildi.

**8. Karşı-olgu paydası eksik sayıyordu.** Mükerrer anahtarı konu oyuncuyu
içermiyordu; 62'de "Ali'yi çıkar" ile 64'te "Veli'yi çıkar" tek satıra çöküyor,
kapsama olduğundan yüksek görünüyordu.

**9. Koç cevapladıktan sonra güven ve bağlam eziliyordu.** Kalibrasyon "bu
güvenle söylendiğinde ne oldu" sorusunu cevaplar; koçun görmediği bir sayıyı
onun beyanına iliştirmek onu bozar. Artık cevaptan sonra donuyor.

### Kayıtların söylediğiyle ölçtüğü aynı olmayanlar

**10. Yeniden fit kendini ölçüyordu.** `fit_timing_prior`'ın "eski tablo"
sütunu canlı sabitten okuyordu — refit o sabiti değiştirdiği için kıyas
tekrarlanamaz hâle gelmişti. Refit öncesi tablo (50 hücre, `c0527cd`)
`docs/measurements/timing-prior-baseline.json` olarak donduruldu.

**11. Docstring üç yerde kendisiyle çelişiyordu.** "Yedi kümeden yeniden fit
edildi" ile "yeniden fit EDİLMEDİ" aynı dosyadaydı.

**12. "Bağımsız doğrulama" bağımsız olmaktan çıkmıştı.** Alıntıladığı La Liga
2015/16 ve Premier League 2015/16, aynı gün yapılan refit'le fit havuzuna
alınmıştı. Sayılar yazıldığında dürüsttü; bölüm ÖNCEKİ tabloya ait diye
etiketlendi.

**13. Tablo durum uzayını kaplamıyordu.** 57 hücre var, uzay 60. Eksik üçü
(45 dk öncesi, herhangi bir skor, 3 hak kullanılmış) 5-hak dünyasında mümkün.
`UNKNOWN_CELL` 0,5 > eşik 0,35 olduğu için böyle bir tik **bayrak yakar** —
"bilmiyorum" sessizlik değil "evet" demek. Açık uç olarak belgelendi ve testle
sabitlendi.

**14. Ölçüm JSON'ları yanlış kaynak damgalıyordu.** Yedi kümeli refit'ten sonra
"Barcelona'nın 100 maçı, 3200 tik" yazmaya devam ediyordu. Künye tek yere
taşındı (`PRIOR_SOURCE`).

**15. `ELITE_OFF_PRIOR` yorumundaki tablo iki kez bayatladı.** Taban 0,243'ten
0,273'e düzeltildiğinde yorum "%24" demeye devam etti; puanlama
beraberlik-tarafsız yapıldığında sayılar değişti, kopya değişmedi. Tablo
koddan kaldırıldı, tek kaynak `docs/KARNE-KIM-BAGIMSIZ.md` oldu — o dokümanın
kendi içindeki iki bayat satır da düzeltildi.

Ayrıca **leave-one-out kümesi sızdırıyordu**: "Barcelona 3-hak" dışarı
çıkarılırken "Barcelona 5-hak" eğitimde kalıyordu. Grup bazlı LOO eklendi;
ikisi de raporlanıyor.

## Örüntü

Denetimden çıkan tek cümlelik ders, bu oturumda daha önce beş kez görülenin
aynısı: **bir sayı düzeltildiğinde onu anlatan metin düzeltilmiyor.** 15
gerçek bulgunun 6'sı tam olarak bu. Bunun panzehiri disiplin değil, TEK
KAYNAK: aynı tablo iki yerde duruyorsa biri er geç yalan söyler. Bu turda üç
kopya kaldırıldı (`PRIOR_SOURCE`, kıyas tabanı dosyası, LOO tablosu).

## Kapılar

2661 test geçti, 6 atlandı; ruff `app/`, `scripts/`, `tests/` temiz; mypy temiz.
