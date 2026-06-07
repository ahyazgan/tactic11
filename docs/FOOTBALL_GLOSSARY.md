# manager2 — Futbol Zekâsı Sözlüğü

Platformun ekranlarında, raporlarında ve AI asistanında kullanılan ortak
taktik/analitik dil. Her terim: kısa tanım → platformdaki veri/motor karşılığı →
hangi ekranda görünür. Sayısal metrikler arayüzde **JetBrains Mono** ile gösterilir.

> Amaç: Scout, Maç Planı, Canlı Maç ve Form ekranları aynı dili konuşsun;
> teknik direktöre "veriyle karar" hissi tutarlı verilsin.

---

## Analitik metrikler

### xG — Beklenen Gol (Expected Goals)
Bir şutun gole dönme **olasılığı** (0.0–1.0); pozisyonun mesafesi, açısı, tipi
(ayak/kafa), asist türü ve baskı bağlamından kestirilir. Bir maçta yüzlerce
pozisyon değerlendirildiğinden, sezon ölçeğinde milyonlarca veri noktası üretir —
"şanslı/şanssız" skoru ayıklayıp gerçek üretkenliği ölçer.
- **Motor:** `app/engine/xg/`, `app/engine/xg_match_graph/`
- **Ekran:** Form & Rating, Maç Planı, Canlı Maç (momentum)

### xGA — Beklenen Gol (Karşı) (Expected Goals Against)
Takımın **yediği** xG; savunma kalitesinin proxy'si. Her takımın her maçında
takımsal düzeyde üretilir. Düşük xGA + yüksek xG = sürdürülebilir üstünlük.
- **Türev:** xG motorunun rakip-perspektifi
- **Ekran:** Form & Rating, Scout (rakip dosyası)

### CCA — Topla İlerleme / Dokunuş Eylemi (carry/touch)
Oyuncunun topu ayağında taşıyarak ilerlettiği eylem metriği; bir maçta onlarca
kez gerçekleşen, dokunuş-temelli ilerleme istatistiği. Pas-dışı ilerlemeyi ve
final üçte-bire taşımayı ölçer.
- **Motor:** `app/engine/carries_into_final_third/`, `app/engine/final_third_entries/`
- **Ekran:** Scout, Maç Planı (eşleşme grid)

### OP — Açık Oyun (Open Play)
Duran toplar (korner, faul, taç, penaltı) dışındaki akan oyun fazı; bir futbol
maçının yaklaşık **%85'ini** oluşturur. Metrikler genelde "OP" ve "duran top"
diye ayrıştırılır; analiz çoğunlukla OP üzerinedir.
- **Karşıtı:** Duran top (set-piece) — ayrı motor: `app/engine/set_piece_*`
- **Ekran:** Maç Planı (duran top vs OP ayrımı), Canlı Maç

---

## Saha bölgeleri & yapı

### Yarı Alan (Half-space)
Sahanın merkez koridoru ile kanat koridoru arasındaki iki dikey şerit; standart
bir sahada tam **2 adet** bulunur (sol ve sağ yarı alan). Ters ayaklı kanatların,
derin oyun kurucuların ve sahte 9'ların alan bulduğu kritik bölge — modern
hücumun büyük kısmı buradan kurulur.
- **Motor:** `app/engine/channel_preference/` (koridor tercihi),
  `app/engine/build_up_pattern/`
- **Ekran:** Scout (zayıf bölge haritası), Maç Planı (eşleşme grid)

### Savunma Hattı & Kompaktlık
Savunma hattının yüksekliği ve hatlar arası mesafe (kompaktlık); presleme ve
ofsayt tuzağıyla doğrudan ilişkili.
- **Motor:** `app/engine/defensive_line/`, `app/engine/compactness/`
- **Ekran:** Maç Planı, Canlı Maç

---

## Presleme sistemleri

### Gegenpress — Karşı-Baskı (Counter-press)
Top kaybedilir kaybedilmez (genelde ilk 5 saniye) topu **hemen** geri kazanmak
için yapılan koordineli baskı. Dünyada elit seviyede 15–20 takımın ana felsefesi;
yüksek fiziksel maliyet → fiziksel test/yük modülüyle (yük riski) doğrudan bağlı.
- **Motor:** `app/engine/counter_press_triggers/`, `app/engine/pressing_trigger/`,
  `app/engine/press_resistance/`
- **Ekran:** Maç Planı, Canlı Maç; **yük** bağlantısı: `/physical-tests` (Yük Riski)

---

## Oyuncu rolleri

### Ters Ayaklı Kanat (Inverted Winger)
Doğal ayağının tersi kanatta oynayan kanat oyuncusu (örn. sol ayaklı oyuncu sağ
kanatta) — içeri kesip şut/ara pas için yarı alana girer. Modern kanatların
yaklaşık **%70'i** bu profilde; binlerce oyuncuyu kapsar.
- **İlişki:** Yarı alan + xG (içeri kesiş şutları)
- **Ekran:** Scout (oyuncu benzerliği), Maç Planı

### Derin Oyun Kurucu (Deep-lying Playmaker / Regista)
Savunmanın hemen önünden oyunu yönlendiren, derinden tempo ve yön veren nadir
orta saha rolü; dünya çapında elit seviyede 40–50 temsilcisi olan az bulunur bir
profil. Pres direnci ve ilk-pas kalitesi belirleyici.
- **Motor:** `app/engine/press_resistance/`, `app/engine/build_up_pattern/`
- **Ekran:** Scout, Maç Planı (önerilen 11)

### Sahte 9 (False 9)
Numara 9 pozisyonundan orta sahaya inerek savunmayı çeken, boşalttığı alanı
kanat/yarı alan koşularına açan forvet rolü; dünyada aktif olarak en fazla 5–10
elit oyuncunun gerçekten uygulayabildiği **en nadir** forvet profili.
- **İlişki:** Yarı alan + CCA (orta sahaya iniş + topla ilerleme)
- **Ekran:** Maç Planı (önerilen 11 + rakip brifing)

---

## Notlar
- Bu sözlük ekranların ve AI asistanının **tek dil kaynağıdır**; yeni metin
  yazarken buradaki terimleri kullan.
- Metrik değerleri her zaman monospace; rol/sistem adları normal metin.
- CCA'nın tam tanımı kulüp veri sağlayıcısına göre rafine edilebilir; motor
  karşılığı `carries_into_final_third`.
