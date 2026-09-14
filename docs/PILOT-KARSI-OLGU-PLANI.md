# Pilot karşı-olgu: ön-kayıtlı sınav planı — 14 Eylül 2026

Karnenin yedi boyutundan ikisi aylardır "ölçülemez" diyor: **Kalibrasyon** ve
**Karşı-olgu**. İkisi de aynı şeye bağlı — koçun *"bu öneriyi uyguladım"*
beyanına. Ekran ve uç noktalar hazır; bu doküman **veri gelmeden önce** sınavı
sabitliyor.

Aynı disiplin maç içi yük için de uygulandı (`docs/MAC-ICI-YUK-PLANI.md`).
Gerekçe değişmedi: bu projede üç kez, veriye baktıktan sonra ölçüt seçmek
sonucu şişirdi.

## Asıl tehlike: kolların içine bakarak göremeyeceğiniz yanlılık

`decision_uplift` uygulanan kolu uygulanmayanla kıyaslar ve karar öncesi duruma
göre katmanlar — ortalamaya dönüşü böyle kontrol eder. Bu iyi bir tasarım ama
tek bir şeyi **göremez**: koç önerilerin hangisine cevap vereceğini kendi seçer.

Bir koç beğendiği önerilere "uyguladım" deyip ötekileri hiç işaretlemezse:

- uygulanan kol dolu olur,
- uygulanmayan kol da dolu görünebilir (ara sıra "uygulamadım" der),
- ve uplift **haksız yere iyi** çıkar.

İki kola bakarak bunu anlayamazsınız. Anlamanın tek yolu **paydayı** bilmektir:
kaç öneri gösterildi, kaçına cevap verildi?

Bu yüzden canlı panel artık her öneriyi belirdiği anda `applied=null` ile
kaydediyor; koç dokununca aynı satır işaretleniyor
(`GET /admin/matches/{id}/decision-coverage`).

## Kapsama kapısı — şimdi sabitleniyor

| Kapsama | Ne yapılır |
|---|---|
| < %50 | **Uplift hesaplanmaz.** Sonuç "kapsama yetersiz" diye yazılır. |
| %50–%80 | Hesaplanır ama **yalnız yanlılık analiziyle birlikte** raporlanır (aşağıda). |
| ≥ %80 | Ana analiz yapılır. |

Kapsama maç başına değil, **pilot boyunca toplam** üzerinden hesaplanır; ayrıca
maç başına dağılımı da raporlanır (bir maçta %100, ötekilerde %10 olması,
ortalamanın gizlediği bir sorundur).

## Yanlılık analizi — cevaplanan ile cevapsız aynı mı?

Kapsama %100 değilse, cevaplanan öneriler cevapsızlardan sistematik olarak
farklı olabilir. Şu üç eksende kıyaslanır ve rapora girer:

1. **Dakika dağılımı** — geç dakikadaki öneriler daha mı çok cevaplanıyor?
2. **Güven skoru** — sistem emin olduğunda mı cevap alıyoruz?
3. **Tema** — "değişiklik" önerileri "şekil ayarla"dan daha mı çok cevaplanıyor?

Bu üç eksende belirgin fark varsa (herhangi birinde cevaplanan/cevapsız oranı
1,5 katı aşarsa), uplift sonucu **"seçili örnek"** etiketiyle raporlanır ve
kabul ölçütünü geçse bile ürün iddiası yapılmaz.

## Asgari hacim

- **En az 40 cevaplanmış öneri**, her kolda **en az 15**.
- Gerekçe: `attribution.MIN_SAMPLES` zaten 15; altında `decision_uplift`
  "yetersiz veri" der. 40 toplam, katmanlama sonrası hücrelerin boş kalmaması
  için gereken en düşük sayıdır.
- Bu, tek bir pilot maçla karşılanamaz. Yaklaşık **10–15 maç** gerekir.

## Ölçülecek şey ve kabul ölçütü

Cetvel `decision_impact`: kararın önü/sonrası xG farkı, karar öncesi duruma göre
katmanlı. Uplift = uygulanan kol isabeti − uygulanmayan kol isabeti,
Mantel-Haenszel ağırlıklı.

**"Öneriler işe yarıyor" denebilmesi için üçü birden:**

1. Katmanlı fark **≥ 0,10** (`decision_uplift.MIN_EFFECT`).
2. Her iki kolda **≥ 15** örnek.
3. Kapsama **≥ %80** ya da yanlılık analizinde üç eksende de belirgin fark yok.

Üçü sağlanmazsa sonuç **"öneri etkisi ölçülemedi"** diye yazılır. Ham fark da
her hâlükârda raporlanır ki katmanlamanın ne kadarını yediği görünsün.

## Bu gözlemsel bir kıyastır, deney değil

Katmanlama yalnız **ölçülen** karıştırıcıyı (karar öncesi durum) kontrol eder.
Koçun neyi uyguladığını kendi seçmesi, ölçülmeyen karıştırıcıdır ve kapsama
kapısı bunu ancak **görünür** kılar, yok etmez.

Gerçek nedensellik için öneriyi rastgele göstermek/gizlemek gerekir. Bu teknik
olarak mümkün (paneldeki öneri kartı rastgele saklanabilir) ama **etik ve
ticari bir karardır**: koçtan bilerek bilgi saklamak demektir. Bu dokümanda
önerilmiyor, yalnız kaydediliyor — ileride gündeme gelirse kulüple açıkça
konuşulması gereken bir şeydir.

## Kalibrasyon boyutu da buradan açılır

Karnenin Kalibrasyon boyutu "kalibre olasılık yok" diyor: külliyat uygulanmamış
önerilerden oluştuğu için güven skoru bir olasılığa dönüşemedi. `applied=true`
işaretli kararların sonucu bilinince kalibrasyon kurulabilir ve boyut ölçülebilir
hale gelir. **Aynı asgari hacim ve kapsama kapısı orada da geçerlidir**; ham
kanıt skorunu olasılık gibi sunma yasağı sürüyor (`coach_benchmark` ölçüm
günlüğü).

## Şu an ne var, ne yok

| | Durum |
|---|---|
| İşaret uç noktası (`decisions/{id}/applied`) | var |
| Canlı panelde Uyguladım / Uygulamadım | var |
| Değişiklik ekranında tek soru | var |
| **Payda (gösterilen öneri kaydı)** | **var** — bu turda eklendi |
| **Kapsama ölçümü** | **var** — bu turda eklendi |
| Uplift motoru | var |
| **Pilot verisi** | **yok** |
| Ürün iddiası | **yok** ve kapılar geçilene kadar olmayacak |

## Pilotta ilk sınanacak şey

Modelin doğruluğu değil: **koç 90 dakika boyunca bu düğmelere gerçekten
dokunuyor mu?** Kapsama %50'nin altında kalırsa toplanan veri karşı-olgu
ölçümüne yetmez ve sorun modelde değil akışta demektir — çözümü de model değil,
daha az sürtünmeli bir arayüzdür.

Kontroller: **2645 test geçti, 6 atlandı**; ruff temiz; mypy 510 kaynak
dosyasında temiz; frontend `tsc --noEmit` ve `next build` temiz.
