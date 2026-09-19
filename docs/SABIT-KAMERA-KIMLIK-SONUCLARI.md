# Sabit kamera kimliği: üretim düzeltmeleri ve dondurulmuş deney

14 Eylül 2026. Canlı kesit kimliklerinin birbirine karışması, bu kimliklerin
PostgreSQL sınırını aşması, uzun maçlarda eşleme panelinden kaybolması ve canlı
yeniden başlatmada forma çapasının kaybolması düzeltildi. Deneysel kişi
bölme/birleştirme yöntemi ise kabul edilmedi: gündüz forma ataması iyileşirken
aynı kişiyi takip etme sonucu geriledi. Yeni otomatik kamera profili açılmadı.

## Üretim davranışı

- Bağımsız işlenen kesitler artık periyot ve milisaniye hassasiyetindeki
  başlangıç zamanı ile ayrı anonim kimlik alanları kullanır. Aynı kesit tekrar
  işlendiğinde kimliği değişmez. İlk periyot, sıfır başlangıç için eski kimlikler
  korunur. Farklı kesitlerdeki aynı kişi otomatik tanınmış sayılmaz.
  Eski, sıfırdan farklı başlangıçlı kesitlerin elle yapılmış eşlemeleri yeniden
  işleme sonrası yeni kimliklere otomatik taşınmaz; görüntüyle yeniden eşlenir.
- Sıfırdan 30 saniye sonraki kesitin ilk oyuncusu `30000030001` olabilir.
  Oyuncu kimliği taşıyan 13 sütun `BigInteger` oldu; satır anahtarları ve maç/takım
  kimlikleri genişletilmedi. `0034_player_external_ids_bigint` geri geçişi bütün
  sütunları önceden kontrol eder; int32'ye sığmayan veri varsa hiçbir sütunu
  daraltmadan durur. Canlı veritabanına bu çalışma sırasında yazılmadı.
- Pas ve top kazanımı kayıtlarının tekil anahtarı maç ve periyodu içerir.
  Aynı kimlik/zaman başka maçta çakışmaz; eski kayıt tekrar içe alındığında
  aynı maç ve periyottaki olay çiftlenmez.
- Eşleme panelindeki görünürlük oranı kişinin bulunduğu kesitlerin kareleri
  üzerinden hesaplanır; boş kareler de paydaya dahildir. Sekiz kısa kesitin
  oyuncuları bütün maça göre yüzde 20 filtresinde kaybolmaz. Eski, kesit bilgisi
  olmayan verilerde maç kapsamı kullanılır. Saha ile panel aynı anonim etiketi
  gösterir; gerçek kadro eşlemesi ayrı ve açık bir işlemdir.
- Canlı işçi ilk geçerli, birbirinden ayrılabilen takım paletini atomik durum
  dosyasında saklar. Sıcak model, ayrı süreç ve yeniden başlatma bu çapayı taşır.
  Maç/takım/kalibrasyon/kimlik yöntemi/kamera ayarı uyuşmazlığı reddedilir.
  Göreli model yolları çağıranın klasörüne göre çözülür; süreç değiştirmek
  farklı model seçmez. Tek operatörlü kamerada kesme/tekrar süzgeçleri kapalıdır.

## Deneysel yöntem ve sınırı

`--refine-identities on`, sabit kalibrasyonlu `video_tracking` kaynağında şu
ortak yolu çalıştırır: ham tespitlerde desteklenen küçük vücut parçalarını
ayırma; gövde, parlak forma ve doygun renk kanıtı toplama; doğrulanan renk/temas
çelişkisinde anonim izi bölme; kısa izlerden forma öğrenme; iki yönlü hareket
ve renk kanıtıyla temkinli bağlantı. Forma, bağlantıdan sonra yeniden öğrenilmez.
Belirsiz kareye sonradan bütün izin çoğunluk takımı zorla yazılmaz. Bölünmüş
kimlik sınırı daha sonra yeniden birleştirilemez.

Varsayılan `auto`, ancak kalibrasyonda kabul edilmiş `fixed_camera_identity_v1`
profili varsa bu yolu açabilir. **Bu çalışmada hiçbir kaynağa bu profil
eklenmedi.** Hareketli/yayın kaynağı, kare başına kalibrasyon veya normalleştirilmiş
renk ile açık seçim reddedilir. `off` eski forma/takip yöntemini kullanır;
kesit kimliği, veri tipi ve kullanıcı arayüzü düzeltmeleri yine geçerlidir.

RGB geçmişi 32 gözlem, en az 5 örnek ve 3 ardışık çelişki kullanır. Bağlantıda
iki yöndeki hareket artığı gövde yüksekliğinin 0,75'ini aşamaz; temas, karşıt
yön, belirsiz aday ve eksik kanıt bağlantıyı engeller. Bütün parametreler ve
kod özetleri [dondurma kaydında](measurements/joint-identity-frozen-decision.json)
yer alır; kontrol görüldükten sonra değiştirilmedi.

## Geliştirme ölçümleri

Karşılaştırmalar aynı ham tespitler, aynı kaynak pikselleri ve aynı kalibrasyonla
üretim fonksiyonları üzerinden yapıldı. Kutular, değişebilen takip numarasıyla
değil kaynak kare ve koordinatlarıyla eşleştirildi. Önceki yolun 9 geliştirme
kesitindeki 3.375 örnek karesi yeniden üretildi.

| Geliştirme kümesi | Doğru forma | Yanlış forma | Atanamayan | Başka giysiye takım ataması |
|---|---:|---:|---:|---:|
| Gündüz 117093, düzeltilmiş tekil kişi etiketleri | 195 → 204 | 20 → 11 | 1 → 1 | 16 → 10 |
| Gece 117092, kesit 0/3/6/9 | 95 → 96 | 13 → 12 | 15 → 15 | 4 → 4 |
| Gece 117092, ek kesit 20/30 | 50 → 52 | 12 → 10 | 5 → 5 | **3 → 5** |

Gündüzde özgün ham forma etiketi skoru 195/22/1 → 204/12/2; özgün tekil kişi
skoru 194/22/1 → 204/12/1'dir. İki kaynak etiketi ikinci görüntü incelemesiyle
düzeltildi; özgün belgeler korundu. Yukarıdaki düzeltilmiş 216 forma örneği
bu ayrı katmanı kullanır. 11 bağımsız doğrulanmış parça kutusu kaldırılırken
destekleyen gerçek kişi kutuları korundu. Ham ve tekil paydalar sonuç JSON'unda
ayrıdır; kaldırılan parça doğru oyuncu kazanımı sayılmadı.

Kişi bağlantısı geliştirme grubunda aynı kişi doğrusu 15/22 → 16/22,
farklı kişi doğrusu 1/7 → 7/7 oldu. Ayrı bağlantı denetiminde aynı kişi
**2/5 → 1/5 geriledi**, farklı kişi 2/2 kaldı. Birleşik aynı kişi sonucu
17/27 → 17/27; farklı kişi 3/9 → 9/9'dur. Alt gruptaki kayıp ortalamada
gizlenmedi. Gece ek kümesindeki başka giysiye atama artışı da kabul hatasıdır.

Kaynaklar: [gündüz](measurements/joint-identity-development-day-results.json),
[gece](measurements/joint-identity-development-night-results.json),
[ek gece](measurements/joint-identity-development-night-extra-results.json),
[kişi etiketleri](measurements/identity-person-development-labels.json),
[bağlantı denetimi](measurements/identity-link-audit-development-labels.json).

## Dondurulmuş kontrol

Kod, model, kalibrasyon, paletler ve kabul kuralları **12:09:25 UTC**'de
donduruldu. Gece etiketleri **12:31:37**, gündüz etiketleri **12:40:54 UTC**'de
sonlandırıldı; kontrol skorları bundan sonra açıldı. Tüm saatler 14 Eylül 2026.
Etiketleri farklı ajanlar kaynak görüntüden hazırladı ve çapraz inceledi;
insan hakem incelemesi yapılmadı.

Gece kontrolü yeni 40/50 kesitleri, maçın 1800–1830 ve 2100–2130 saniyeleridir.
Gündüz kontrolü geliştirmede kullanılan 0/3/6 kesitlerinin başka zamanlarıdır;
bağımsız maç testi değildir. Başlangıç kareleri 374/686, karşılıkları 404/716;
arada 1,2 saniye vardır. Kapsama bütün ham başlangıç kutuları alınmıştır.

Gündüz körlük sınırı: ana ajan önizleme hazırlarken üçüncü geliştirme kesitinin
anonim bölünme numaralarını/zamanlarını konsola yazdırdı; bu bilgiler bazı
kontrol zamanlarını da kapsıyordu. O aşamada kontrol kutusu ile tahmin
kimliği/takımı eşleşmeleri veya kontrol skorları açılmadı. Bu nedenle gündüz
çalışması tam bağımsız kör doğrulama olarak sunulmaz. Ayrıntı
[inceleme kaydında](measurements/joint-identity-control-day-review.json).

| Kontrol ölçümü | Gündüz önce → sonra | Gece önce → sonra |
|---|---:|---:|
| Tekil kişi doğru forma | 90 → 95 | 52 → 52 |
| Yanlış forma | 8 → 2 | 9 → 9 |
| Atanamayan (kayıp kutu dahil) | 1 → 2 | 4 → 4 |
| Forma kutusu kaybı, üsttekinin alt kümesi | 1 → 1 | 0 → 0 |
| Başka giysiye takım ataması | 11 → 7 | 1 → 1 |
| Açıkça tekil gerçek kişi başlangıç kapsamı | 121/164 → 121/164 | 69/69 → 69/69 |
| Aynı kişi bağlantısı doğru | **92/134 → 90/134** | 59/63 → 59/63 |
| Farklı kişi bağlantısı doğru | 84/134 → 84/134 | 61/63 → 61/63 |

Gündüz 250 başlangıç etiketi ve başlangıç/son toplam 493 ham kutu vardır.
Tekil bağlantı skoru, etiketlenmiş 9 parça uç noktasını dışlar: 134 aynı kişi,
134 farklı kişi; belirsiz 21 ilişki dışarıda tutulur. Ham kutu bağlantı skorunda
143'er ilişki, aynı kişi 92 → 90, farklı kişi 86 → 85'tir. Tekil ilişkilerin
referans verdiği gözlem kapsamı 231/313 → 230/313'tür; bu payda gerçek kişi
başlangıç kapsamıyla aynı değildir.

Gündüz net iki bağlantı kaybı, **üç yeni yanlış bölünme ve bir düzelme** içerir.
Yeni kayıplar `0-374-d14 → 0-404-d22`, `0-686-d17 → 0-716-d16`,
`6-374-d17 → 6-404-d17`; düzelen bağlantı `0-686-d11 → 0-716-d7`'dir.
İki kayıp forma çelişkisi, biri temas sonrası görünüş çelişkisi bölmesinden
geldi. Bu tanıdan sonra kontrol üzerinde eşik ayarı veya etiket değişikliği
yapılmadı. Gündüz kabul edilmedi.

Gece 83 başlangıç etiketi (65 forma, 4 başka giysi, 8 kişi olmayan, 6 belirsiz)
ve 164 ham başlangıç/son kutusu vardır. İlişkilerin kullandığı 138 gözlemin
136'sı iki yöntemde de kapsandı. Altı kabul kapısı aynı skorla geçti; doğruluk
artışı gösterilmedi. İki yanlış bölünme ve iki kapsanmayan aynı kişi ilişkisi
sürer. Önceki ek gece kümesindeki gerilemeyle birlikte gece de otomatik açılmaz.

Tam sonuçlar: [gündüz](measurements/joint-identity-control-day-results.json),
[gece](measurements/joint-identity-control-night-results.json).
Takip sayısı veya sahada 11'den çok kişi görülmesi tanısal sayımdır; kimlik
başarı metriği değildir. Resmî kimlik verisinin 3840×1504 görüntüsü ile mevcut
3840×1906 kaynak hizası doğrulanamadı; IDF1/HOTA, forma numarası veya kadro
oyuncusu doğruluğu iddiası yapılmaz. Modelin tam ön eğitim bağımsızlığı da
kanıtlanmış değildir.

## Dondurma sonrası entegrasyon ve tekrar üretim

Kontrol sonuçları ve ilk dondurma kaydı değiştirilmedi. Entegrasyonda yalnız
donmuş üç dosyanın kodu değişti: `pipeline.py` kaynak güvenlik koşulu;
`track_video.py` palet aktarımı ve operatörlü kamera bayrakları;
`track_live.py` kalıcı palet, ayar doğrulama ve göreli dosya yolları.
Diğer 13 donmuş dosya ve bütün sınıflandırıcı parametreleri aynıdır.

[Ek değişiklik kaydı](measurements/joint-identity-integration-amendment.json),
eski/yeni SHA-256 değerlerini ve [eşitlik kanıtını](measurements/joint-identity-integration-parity.json)
bağlar. 11 farklı kesitin 22 önce/sonra dosyası, toplam 164.772 kişi gözlemi
bayt düzeyinde eşittir. Eski/yeni üretim koduyla 2.750 normal çıktı karesi ve
8.250 yoğun olay karesi aynı JSON'u üretir. Gündüz zaman kontrolü aynı üç
kesiti tekrar kullanır; ayrıca yeni kesit olarak sayılmadı. Bu kanıt sabit
kamera içindir; hareketli canlı işçinin kalıcı kalibratörü ile her kesitte
yeniden başlayan ayrı süreç arasında genel eşitlik iddiası değildir.

Girdi video/model/tam tespit önbellekleri büyüklükleri nedeniyle yerel
`data/tracking/bench`, `data/tracking/models` ve `.cache` altındadır.
Kaynak özetleri sonuç JSON'larında ve dondurma kaydındadır. Etiketler, seçilmiş
inceleme görüntüleri ve sonuçlar repodadır. Tekrar çalıştırma bu aynı yerel
girdileri gerektirir; eksik önbellekle yeni sonuç uydurulmaz.

Gündüz tekrar komutu, repo kökünden (yeni çıktı klasörü seçilir):

```powershell
venv-cv\Scripts\python.exe -m scripts.soccertrack_v2.benchmark_joint_identity `
  --cache data/tracking/bench/identity_day_detections `
  --features '.cache/kit_joint_agent/raw_features_day_{segment:04d}.json' `
  --segments 0 3 6 --outdir .cache/joint_identity_day_reproduction `
  --kit-labels docs/measurements/daylight-117093-labels.json docs/measurements/perimeter-control-day-labels.json `
  --adjudicated-labels docs/measurements/identity-kit-label-adjudication.json `
  --pair-labels docs/measurements/identity-person-development-labels.json docs/measurements/identity-link-audit-development-labels.json `
  --duplicate-labels docs/measurements/duplicate-part-development-labels.json
```

Kontrolde yeni palet öğrenilmez; `--anchor-report` ile ilgili dondurulmuş
geliştirme raporu geçirilir. Kaynak, etiket, dokuz renk özelliği ve üretim kodu
özetleri işlem öncesi/sonrası kontrol edilir.

Kontrol skorlaması ve entegrasyon eşitliği için kullanılan tarihsel tariflerin
bayt kopyaları [tarif manifestiyle](measurements/joint-identity-evaluation-recipes.json)
saklandı. Bunlar özgün dosya yollarını ve yeni çıktı şartını koruyan denetim
kayıtlarıdır; mevcut donmuş sonuçların üzerine çalıştırılmaz.

## İzlenebilir önizleme ve doğrulama

Aydınlık 117093 maçının 11:30–12:00 aralığı:
[önce/sonra videosu](../data/tracking/bench/joint_identity_export_v1/comparison.mp4).
30 saniye, 375 kare, 12,5 fps; iki tam panorama 2048×1292 alanda karşılaştırılır.
Yeşil/kırmızı anonim takımlar, sarı atanamayan kişilerdir. H.264/yuv420p ve
faststart, iki bağımsız çözücüde tüm kareler, kaynak 124/500 karelerinde görsel
okunabilirlik kontrol edildi. Görsel kontrol kimlik doğruluğu testi değildir.
Top ve tahmin işaretleri miras alınmıştır; bu deneyde yeniden değerlendirilmedi.

[Önizleme manifesti](measurements/joint-identity-preview-manifest.json) ilk
donmuş kodla üretilmiştir. Güncel tekrar için dışa aktarıcı dondurma belgesi,
izinli entegrasyon değişiklikleri ve başarılı eşitlik kanıtını birlikte doğrular:

```powershell
venv-cv\Scripts\python.exe -m scripts.soccertrack_v2.export_joint_identity `
  --out data/tracking/bench/joint_identity_export_reproduction
```

Bu komut güncel entegrasyonla ayrıca
`data/tracking/bench/joint_identity_export_integration_v1` altında çalıştırıldı.
13 medya/JSON/inceleme dosyası ilk dışa aktarımla bayt düzeyinde aynı çıktı;
8.828 önce ve 8.638 sonra kişi gözleminde yerel takım/kimlik sözleşmesi korundu.
[Güncel manifest](measurements/joint-identity-integration-preview-manifest.json)
ve [doğrulama](measurements/joint-identity-integration-preview-review.json)
entegrasyon ekini de kaydeder.

Doğrulama; gerçek Supervision takipçisiyle önbellek tekrarı, çekirdek CV
regresyonları, sıcak/kayıtlı/ayrı süreç ve yeniden başlatma testleri, büyük
kimlikli olay/eşleme/yük kayıtları, kesit kapsamlı API testleri, tam uygulama
testleri, Ruff/mypy ve frontend tip/derleme kontrolünü kapsar. PostgreSQL 16
geçiş ve veri koruyan geri geçiş testi CI'da her denemeye özel şemada çalışır;
yerel uygulama testleri izole SQLite kullanır. Son test sayıları ve PR sonucu
tamamlama kaydına eklenir.

14 Eylül birleşik kodunda yerel tam uygulama sonucu **2.837 geçti, 9 atlandı**
(262,20 saniye); ayrıca gerçek CV ortamında ilgili **164 test geçti**.
Ruff temiz, mypy 529 kaynak dosyasında hatasız. Frontend TypeScript ve Next
ESLint kuralları geçti; üretim derlemesi 55/55 statik sayfa üretti.
Derlemeden sonra yalnız anonim iz açıklaması değişti ve tip/lint kontrolü
tekrar geçti.

## 19 Eylül tamamlama kaydı

Son üretim kodu `8a66672bd7a7a577cb722ef18ace9de2d34aedf0` üzerinde tam yerel
uygulama koşusu **2.877 geçti, 15 atlandı** (136,72 saniye). İlgili gerçek CV
ortamı sonucu **164 geçti**; donmuş sınıflandırıcı ve kontrol kararları
değişmedi. Ruff temiz, mypy **532 kaynak dosyasında hatasız**. Claude'un
#253–#261 arasındaki birleşmiş değişiklikleri mevcut dalda korundu.

[CI koşusunda](https://github.com/ahyazgan/tactic11/actions/runs/35433366094)
uygulama, lint, Docker, SQLite geçişleri ve PostgreSQL kontrolü geçti.
[Tarayıcı uçtan uca testi](https://github.com/ahyazgan/tactic11/actions/runs/35433366036)
ve Vercel dağıtım kontrolü de aynı kodda başarılı.
[Gerçek PostgreSQL 16 koşusunda](https://github.com/ahyazgan/tactic11/actions/runs/35433366094/job/105871768714)
**14 test geçti**: temiz kurulum, eski Alembic sürüm tablosundan yükseltme,
büyük oyuncu kimlikleri ve UUID kayıtlarının geçiş/geri geçişte korunması.

Bu doğrulama sırasında temiz PostgreSQL kurulumunu engelleyen tarihsel geçiş
hataları da düzeltildi. `0011` gerçek boolean varsayılanı ve tipli UTC zaman
değeri kullanır. Alembic sürüm sütunu uzun revizyon adları için en az 128
karaktere hazırlanır; var olan sürüm satırları ve daha geniş sütunlar korunur.
`0020`/`0021` kullanıcı yabancı anahtarları, `users.id` ile aynı metin tipinde
kurulur. Yeni `0035_note_author_user_id_str`, önceden kurulmuş not yazarı
sütununu veri kaybetmeden dönüştürür; ORM ve not API'si UUID metnini korur,
eski sayısal API girdileri metne çevrilerek kabul edilir. `0023` ve `0035`
geri geçişleri UUID'yi daraltmaz; düzeltilmiş önceki şemaların metin tipi
korunur. Canlı veritabanına geçiş uygulanmadı; bütün geçiş testleri geçici,
izole veritabanı veya şemalarda çalıştı.

Bu kapanış, üretimdeki kesit kimliği/veritabanı/canlı palet/API/arayüz
tutarlılığını ve deneyin tamamlandığını kaydeder. Deneysel kişi bölme/bağlama
profilinin kabul kararı değişmedi: otomatik kullanım kapalıdır. Genel kişi
kimliği, forma numarası, kadro eşleşmesi veya olay doğruluğu tamamlanmış
sayılmaz.
