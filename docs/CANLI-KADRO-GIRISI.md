# Canlı kadro girişi: video hattı ile karar hattını bağlayan halka — 14 Eylül 2026

Hat şudur:

```
video → takip → olaylar (pas/müdahale/şut) → karar paneli
```

İlk üç halka çalışıyor. Ama karar katmanının iki tablosu videodan **çıkmayan**
bilgiye muhtaç:

| Tablo | İhtiyacı | Video verir mi? |
|---|---|---|
| Ne zaman değiştir (`sub_timing`) | o ana kadar kaç değişiklik yapıldı | **hayır** |
| Kimi çıkar (`live_sub_recommendation`) | sahada kim var, kim ilk 11'di | **hayır** |

Takip sistemi sahada 22 **anonim iz** görür. Kimin kim olduğunu bilmez — oyuncu
kimliği (`TrackingIdentity`) zaten elle girilen bir eşlemeden gelir. Kimin
sonradan girdiğini de bilmez.

Sonuç: kadro girilmezse `player_appearances` boş kalır, `subs_used` ve
`off_prior` `None` gider, iki tablo da **sessizce** devre dışı kalır ve panel
boş öneri döndürür — hata vermeden.

Bu çalışma o halkayı kapattı.

## Uç noktalar

| | Ne yapar |
|---|---|
| `PUT /admin/matches/{id}/lineup` | İlk 11'i yazar; kadro farkındalığını açar |
| `POST /admin/matches/{id}/substitution` | Çıkanı kapatır, gireni açar; `subs_used` kendiliğinden ilerler |
| `GET /admin/matches/{id}/squad-state` | Panelin geçireceği iki sayı: sahadakiler ve kullanılmış hak |

Panel zaten `player_appearances`'tan okuduğu için ayrıca bağlama gerekmedi;
kadro girildiği anda iki tablo da çalışmaya başlıyor.

## Sessizlik kaldırıldı

Canlı karar yanıtına `kadro` bloğu eklendi:

```json
"kadro": {
  "girildi": false,
  "kullanilmis_hak": null,
  "degisiklik_hakki": 5,
  "sahadaki": null,
  "uyari": "kadro girilmedi: zamanlama penceresi ve 'kim çıkar' önerisi bu maçta
            devre dışı. PUT .../lineup ile ilk 11'i, POST .../substitution ile
            değişiklikleri girin."
}
```

Boş öneri döndürüp susmak en kötü davranıştır: koç sistemin "değişiklik gerekmiyor"
dediğini sanır, oysa sistem **bakamıyordur**.

## `applied` neden otomatik işaretlenmiyor

Değişiklik girildiğinde sistem, çıkan oyuncunun son 15 dakikadaki önerilerin aday
listesinde olup olmadığını görebiliyor — ve görüyor da, yanıtta
`oneriyle_uyusma` olarak dönüyor (hangi öneri, listenin kaçıncı sırası).

Ama bundan **`applied=true` türetilmiyor.**

`applied` "koç bu öneri **yüzünden** yaptı" demektir ve karşı-olgu ölçümünün tek
dayanağıdır (`decision_uplift`, karnenin Karşı-olgu boyutu). Koçun zaten
yapacağı bir değişikliği "bizim listemizde de vardı" diye uygulanmış saymak,
ölçülmek istenen nedenselliği **uydurmaktır** — ve tam olarak eksikliğinden
şikâyet ettiğimiz veriyi sahte üretir. Karnenin bu boyutu aylardır "ölçülemez"
diyor; onu sahte veriyle "ölçülebilir" yapmak ilerleme değil, gerileme olurdu.

Uyuşma **gözlem**, işaret **koçun beyanı**. İkisi ayrı alanlarda duruyor.
Uyuşma bilgisi yalnızca panelin koça tek dokunuşla sorabilmesi için dönüyor:
`POST /admin/decisions/{id}/applied`.

Bu ayrım korunursa, bir pilotta koç işaretlemeye başladığı anda karnenin iki
ölçülemez boyutu (Kalibrasyon ve Karşı-olgu) **gerçek** veriyle açılır.

## Kurallar ölçüm tarafıyla aynı tutuldu

- **Aynı dakikadaki iki değişiklik iki hak kullanır** (tekilleştirme yok) —
  `measure_shape_selectivity` ve `validate_timing_prior` da öyle sayıyor.
- **Sahada olma aralığı YARI AÇIK**: `[giriş, çıkış)`. Giriş dakikasında
  sahadadır, çıkış dakikasında değildir — motorun `live_lineup.is_on_pitch`
  kuralıyla birebir. İlk yazımda uç nokta kapalı aralık kullanıyordu ve aynı
  dakikada panelden FARKLI kadro döndürüyordu; artık bir test ikisini
  birbirine kilitliyor (`test_squad_state_matches_the_engine_on_pitch_rule`).
- **Giren oyuncu çıkanın mevkisini devralır** (açıkça verilmedikçe) —
  `coach_iq` ve `validate_who_prior` aynı kuralı kullanıyor.
- **Giriş/çıkış dakikaları tam sayı** — sağlayıcı verisi de öyle, önsel zaten
  5 dakikalık bantlarla çalışıyor.

Canlı kayıt ile ölçüm aynı dünyayı anlatmazsa, sahada toplanan veri karnede
kullanılamaz.

## Reddedilen girişler

- Kadroda olmayan oyuncuyu çıkarmak → 400, "önce lineup"
- Zaten çıkmış oyuncuyu tekrar çıkarmak → 409
- Zaten girmiş oyuncuyu tekrar sokmak → 409

## Sınırlar

- **Tek takım.** Uç noktalar `team_external_id` alıyor; rakip kadrosu ayrı
  çağrıyla girilir. Rakip kadrosu girilmezse rakip tarafı öneriler kadro-farkında
  olmaz.
- **Değişiklik hakkı panelde parametre.** `subs_allowed` canlı karar çağrısının
  sorgu parametresi (varsayılan 5); maç kaydında tutulmuyor.
- **"Üç oturum" kısıtı yok.** 5 hak en fazla 3 oyun durmasında kullanılabilir;
  ne kayıt ne öneri bunu biliyor.
- ~~Kırmızı kart yok~~ → **eklendi.** `POST /admin/matches/{id}/dismissal`
  oyuncuyu sahadan düşürür ve `red_cards` işaretini koyar ama **değişiklik hakkı
  harcamaz** — kullanılmış hak sahaya GİREN oyuncuları saydığı için kendiliğinden
  doğru kalır. Kaydedilmezse atılan oyuncu sonsuza dek sahada görünür ve motor
  onu "çıkar" diye önerebilir. Ekranda ayrı bir "Kırmızı kart" yolu var.
- **Oyuncu kimliği hâlâ elle.** Bu modül kadroyu çözüyor, takip izlerini gerçek
  oyunculara bağlamayı değil (`PUT /tracking/matches/{id}/identities`).
- **Ekran tek takım.** Rakip kadrosu için ayrı giriş gerekir.
- **Dakika panelden gelir.** Ekran kendi saatini tutmaz; canlı sayfadaki dakika
  neyse o yazılır. Yanlış dakika yanlış hücreye düşer.

## Ekran

`frontend/src/app/_console/squad-entry.tsx`, canlı karar sayfasına bağlı
(`/decisions/live`, DEMO_MODE dışında). Koçun yanındaki kişi için tasarlandı:

- Oyuncu pulları 44 px yüksekliğinde — tablette parmakla basılır.
- Kadro girilmemişse önce **ilk 11 seçimi** çıkar (11/11 olmadan kaydet düğmesi
  açılmaz), girildikten sonra ekran **çıkan / giren** seçimine döner.
- Uyarı metni panelden gelir; ekran kendi cümlesini uydurmaz.
- Havuz `GET /admin/teams/{id}/squad` ile maç kayıtlarından türetilir
  (`players` tablosunda takım bağı yok); listede olmayan oyuncu kimliğiyle
  girilebilir.

**Değişiklikten sonra tek soru:** çıkan oyuncu son 15 dakikadaki bir önerinin
listesindeyse ekran *"değişikliği bu öneri yüzünden mi yaptın?"* diye sorar ve
Evet/Hayır `POST /admin/decisions/{id}/applied` çağrısına gider. Soru
sorulmazsa Karşı-olgu boyutu ölçülemez kalır; otomatik doldurulursa sahte
ölçülebilir olur. Ekran soruyu sorar, cevabı uydurmaz.

## Sonraki adım

Ekran tek takım için çalışıyor; rakip kadrosu ayrı giriş ister. Bir pilotta
ilk sınanacak şey, 90 dakika boyunca bu ekranın gerçekten kullanılıp
kullanılmadığıdır — kullanılmıyorsa toplanan veri de olmaz.

Kontroller: **2650 test geçti, 6 atlandı**; ruff temiz; mypy 510 kaynak
dosyasında temiz; frontend typecheck ve build temiz.
