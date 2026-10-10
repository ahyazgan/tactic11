# Birleşik kimlik adayı: yeni zaman aralıklarında kontrol planı

10 Ekim 2026. Bu plan seçilen görüntüler açılmadan hazırlanmıştır. Tek başına
dondurma kaydı değildir: video/canlı entegrasyonu doğrulandıktan sonra aday,
edinim ve değerlendirme araçları, model, ayarlar, ortam sürümleri ve bu plan
birlikte hash'lenip Git'e kaydedilmelidir. Bu kapı geçmeden yeni görüntüler
açılmaz. Kontrolde algoritma veya eşik seçilmez.

## Önceden ayrılan aralıklar

| Kaynak | Kesit | Başlangıç | Süre |
|---|---:|---:|---:|
| 117093 ilk yarı, gündüz | 68 | 2040 sn | 30 sn |
| 117093 ilk yarı, gündüz | 72 | 2160 sn | 30 sn |
| 117092 ilk yarı, gece | 74 | 2220 sn | 30 sn |
| 117092 ilk yarı, gece | 76 | 2280 sn | 30 sn |

Kaynak başlıkları 25 fps; gündüz 67.625, gece 67.375 kare gösterir.
Bu aralıklar kaynak süresinin içindedir. Başlık incelemesinde görüntü
çözülmedi. Mevcut 19 kimlik kesiti artık geliştirme verisidir. Gündüz
2100–2110 / 2220–2250 ve gece 2580–2590 / 2640–2670 saniyeleri önceki
Torch/ROI kontrollerinde kullanıldığından bu seçimden çıkarılmıştır.

Bunlar aynı iki maçın yeni zamanlarıdır; bağımsız maç genellemesi sayılmaz.
Eksik kaynak veya başarısız edinim başarılı kontrol sayılamaz. Görüntü
açıldıktan sonra başarısız sonucu gizlemek için aralık değiştirilmez.

## Sabit aday ve karşılaştırma

`bytetrack-osnet-guarded-identity-v2`: özgün ByteTrack, kısa kopma onarımı ve
bağımsız OSNet desteği. Palet geçişi için önceki sabit geliştirme çapaları;
görünüş uzlaşısı için kesitin özgün ByteTrack takım merkezleri kullanılır.
Başlangıç kutusu kaybı onarımı tüm kesitte geri çeker. Ek gerçek kaynak
tespitlerinin takımı belirsiz kalır. Karar segment sonunda geçmişe uygulanır.

Üç karşılaştırma kolu aynı ham tespitleri kullanır: varsayılan `supervision`,
önceki palet destekli uzlaşı ve yeni `guarded`. Dedektör Torch RF-DETR,
tek görüntülü top ROI gruplaması kapalı; ayarlar, kalibrasyon ve sabit
çapalar ilgili geliştirme kayıtlarından aynen alınır. Kaynak RGB ve OSNet
üretim yolunda yeniden hesaplanır. Bu kişi kontrolünde top/olay doğruluğu
ve performans için ayrı başarı iddiası üretilmez.

## Edinim, kör etiket ve değerlendirme sırası

1. Entegrasyon doğrulaması ve dondurma tamamlanır; bütün kod/model/girdi
   hashleri çalışmadan önce ve sonra kontrol edilir. Eski donmuş belgeler
   ve deney araçları değiştirilmez.
2. Dört kesit yeni klasöre çıkarılır. Kaynak başına 750 kare, 25 fps ve
   özgün boyutlar doğrulanır. Tek çözücü iş parçacığı fiilen denetlenir.
   Ham edinimde kesit başına beklenen 375 örneğin sıra/zaman/tespit kapsamı
   doğrulanmadan etiketlemeye geçilmez; sadece dosya/hash bulunması yetmez.
3. Eski kör kaynak protokolü korunur: kaynak 374 ve 686. karede bütün kişi
   kutuları, 30 kare sonraki uçlar ve sabit ara bağlam. Forma, tam/kısmi/
   karışık/mükerrer/kişi olmayan kutu ve aynı/farklı kişi ilişkileri, takip
   numarası veya takım tahmini gösterilmeden etiketlenir. Belirsiz gözlem
   kesin ilişkiye dönüştürülmez. Bütün etiketler tahminler açılmadan mühürlenir.
4. Üç kol çalıştırılır; her kaynak grubu ayrı puanlanır. Toplamlar bir
   kaynaktaki gerilemeyi diğer kaynağın kazanımıyla örtemez. Önceden doğru
   uç ilişkilerinin kaybı, yanlış birleşme, kopma, forma ve kapsam izlenir.
5. Bütün hareket önerileri, uygulanan/reddedilen onarımlar, tüm-kesit geri
   dönüşleri, bütün yeni/kaldırılmış ayrımlar ve ek kutular kaynakta incelenir.
   Yalnız olumlu örnekler seçilmez. Bu ikinci inceleme tahmin sonrası tanıdır;
   kör kaynak etiketlerinden ayrı kaydedilir. Etiket hatası bulunursa özgün
   mühür korunur, düzeltme açıkça tahmin sonrası olarak raporlanır.

## Kabul koşulları ve sınır

- Her kaynakta her iki karşılaştırmaya göre doğru kişi ilişkisi, eski doğru
  bağların korunması, yanlış birleşme, forma doğruluğu ve kapsam gerilemez.
  Çelişkili forma taşıyan kimlik ve takipte kalan kişi olmayan kutu artmaz.
- Bütün eski kaynak kutuları, güvenleri, zaman/süreklilik ve gözlem takım
  kararları aynen korunur. Ek gözlem yalnız gerçek ham tespit olabilir;
  ona takım uydurulmaz. Geometri üretmek veya eski gözlemi silmek ret nedenidir.
- Yanlış yeni birleşme/ayrım veya doğru eski ayrımın kaybı kabul edilmez.
  Belirsiz değişiklik kazanç sayılmaz. Bağımsız olumlu kişi düzeltmesi yoksa
  yalnız eşit çıktı genel doğruluk artışı olarak sunulmaz.
- Edinim, etiket, kaynak/kod bütünlüğü veya gerileme kapısı eksikse terfi yok.
  Kontrol üzerinde ayar değiştirilmez; başarısız adayın verisi daha sonra
  geliştirmede kullanılabilir, fakat yeniden bağımsız kontrol sayılamaz.

Tek AI kaynak incelemesi insan hakem doğrulaması değildir. Seyrek ilişkiler
tam maç HOTA/IDF1, forma numarası/kadro eşlemesi veya segmentler arası kişi
sürekliliğini kanıtlamaz. Başarılı kontrol bile varsayılan takip motorunu
otomatik değiştirmez; gerçek zaman kapasitesi ayrıca ölçülmelidir.

## Uygulama araçları ve mühür sırası

`scripts.soccertrack_v2.guarded_control` eski edinim/aday dosyalarına dokunmadan
bu kontrolün yeni dizinlerini kullanır. `freeze`, önce tamamlanmış 19 kesit,
22 varsayılan çıktı ve gerçek video/canlı kanıtlarının kaynak/kod/çıktı
hashlerini denetler; ardından `identity-guarded-frozen-decision.json` yazar.
Bu karar ve kod Git'e kaydedilip normal PR kontrollerinden geçirilir.
`verify`, hem dosya hashlerini hem kararın ve kodun HEAD'de kayıtlı olduğunu
denetler. Bu doğrulamadan önce hiçbir `extract/capture/prepare/replay` adımı
çalıştırılmaz.

```powershell
.\venv-cv\Scripts\python.exe -m scripts.soccertrack_v2.guarded_control freeze
# Karar ve kod commit/PR ile kaydedildikten sonra:
.\venv-cv\Scripts\python.exe -m scripts.soccertrack_v2.guarded_control verify
.\venv-cv\Scripts\python.exe -m scripts.soccertrack_v2.guarded_control extract --group day
.\venv-cv\Scripts\python.exe -m scripts.soccertrack_v2.guarded_control capture --group day
.\venv-cv\Scripts\python.exe -m scripts.soccertrack_v2.guarded_control validate --group day
.\venv-cv\Scripts\python.exe -m scripts.soccertrack_v2.guarded_control prepare --group day
```

Aynı sıra gece için `--group night` ile uygulanır. Yeni ham veri dizini
`data/tracking/bench/guarded_control_v1` altındadır. Tamamlanmamış eski deneme
başarı manifesti olarak kullanılamaz; önceki dosyalar korunur.

Etiketler bütün başlangıç ve bitiş kutularını, kaynak kapsamını ve her açık
aynı-kişi bağının farklı-kişi karşılaştırmasını içerir. `seal --group ...
--labels ... --pairs ...`, ancak etiket dosyaları Git'e kaydedildikten ve
kör görüntü paketinin hashleri doğrulandıktan sonra grup mührünü yazar.
İki grup mührü de Git'e kaydedilmeden hiçbir grubun `replay` adımı çalışmaz.
`scripts.soccertrack_v2.score_guarded_control --group ... --out ...` özgün
kaynak kutusu puanlayıcılarını kullanır; eksik/değişmiş tahmin manifestini
reddeder. Puan toplamları eşit olsa bile eski doğru bir kişi bağının kaybı
ret nedenidir. Rapor her öneri/ayrım/geri dönüşü kaynak incelemesine bırakır;
bu inceleme bitmeden otomatik olumlu doğruluk veya varsayılan terfisi yazmaz.
