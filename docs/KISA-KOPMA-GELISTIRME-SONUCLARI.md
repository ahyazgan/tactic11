# Kısa kopma ve kimlik devri: geliştirme ölçümü

9 Ekim 2026. Bu çalışma ilk 11 geliştirme kesiti ve son palet kontrolünden
dört kesit, toplam 15 tüketilmiş kesitte araştırmadır.
Yeni kör kontrol açılmadı; uygulamanın takip varsayılanı değiştirilmedi.
Kişi ilişkileri seyrek kaynak etiketlerine dayanır. Tam maç HOTA/IDF1,
gerçek kadro kimliği veya bağımsız insan hakem doğrulaması değildir.

## Kaynakta yeniden üretilen sorun

117092 gece, kesit 84: mavi top taşıyıcısının 374. karedeki kutusu ile
404. karedeki kutusu aynı kişiyi gösterir. ByteTrack'in 16 numaralı takibi
382'den sonra kesilir, 392'de yeni 52 numarası oluşur. 386 ve 390'da kaynak
tespitleri vardır; güvenleri sırasıyla 0,4033 ve 0,4150'dir. 386'da eski
hareket kestirimi ile tespit arasındaki IoU 0,2955; güvenle birleştirilmiş
maliyet 0,8808 olur ve 0,8 eşleştirme kapısını geçemez. İz henüz zaman
aşımına uğramamıştır. Sadece kayıp bekleme süresini artırmak bu nedeni çözmez.

Son beş gerçek kutunun hareketiyle kısa boşluğu onarmak 16 kimliğini korur.
Ancak aynı takip daha sonra 472'de beyaz oyuncuya devredilir. Gece formaları
RGB oranlarında birbirine yakın göründüğünden yalnız renk tonu değişimi
bu devri yakalayamaz. Sabit palet sınıfı ile bağımsız Deep OC-SORT desteği
birlikte değiştiğinde kimliği ayıran ikinci adım bu vakayı ele alır.

## Adayın sınırları

- Hareket önerisi beş ardışık kaynak gözlemi ve en fazla dört örneklik
  boşluk ister; özgün kutu/güven, eşleştirme eşiği ve Kalman kovaryansı korunur.
- Eski kestirimin zaten geçerli bir eşleşmesi varsa müdahale edilmez.
  Birden fazla makul tespit veya rakip kimlik varsa onarım yapılmaz.
  Yeni konumdaki gerçek güven/IoU maliyeti de yalnız hedef kutuyu kabul
  etmelidir; renk açısından reddedilen yüksek güvenli komşu kutu yine takip
  motorunun eşleştirmesine girdiği için ayrıca denetlenir.
  Rakip merkezinin uzaklığı, iki kutunun büyük olan yüksekliğinin 0,75 katını
  aşmalıdır. Bu eşik geliştirmede seçildi: 1,0 katı kalabalık vakayı durdururken
  bilinen gece kopmasının onarımını da engelledi. Genelleme kanıtı değildir.
- Palet ve bağımsız takip desteği birlikte değişmelidir. Sonraki üç ardışık
  gözlem onay verir; ayrım ilk değişim anına geriye dönük uygulanır.
  Dolayısıyla bu sürüm çevrimdışı araştırma adayıdır.
- Forma kararı kaynak kutusundaki eski atamadan taşınır. Önceden bulunmayan
  gözleme takım uydurulmaz. Kimlikler değiştikten sonra genel renk kümelemesini
  yeniden yapmak gündüz/gece forma puanlarını bozduğu için reddedilmiştir.
- Bozuk/eksik renk olumlu kanıt sayılmaz; mükerrer kutu, değiştirilmiş güven,
  zaman/sıra ve kaynak dışı çıktı değerlendirmeyi durdurur. Kamera kimlik
  alanları ayrıdır; eski hareket geçmişi sona eren takiplerle temizlenir.
- Hareket kolu eski gözlemlerden birini bile kaybederse o kesitte hareket
  onarımından vazgeçilir, palet ayrımı başlangıç kolunun kutularında çalışır.
  Eklenen kutular eski kutu kaybını telafi etmiş sayılmaz.

## Son ölçüm

15 kesit / 5.625 örnekte bütün seyrek kişi/forma gerileme kapıları geçti.
**114.602 eski gözlemin tamamı** kutu, güven ve mevcut forma kararıyla korundu;
51 kaynak tespitine daha takip çıktısı eklendi. Bu 51 ek gözlemin tamamı için
bağımsız gerçek-kişi etiketi olduğu iddia edilmez.

| Etiketli ilişki kümesi | Başlangıç | Son aday |
|---|---:|---:|
| Gündüz bağlantı denetimi: aynı kişi | 2/5 | 3/5 |
| Gündüz kişi geliştirme: farklı kişi | 1/7 | 2/7 |
| Son gece palet kontrolü: aynı kişi | 49/53 | 50/53 |

İyileşen kaynaklar gündüz mavi 21'in yürüyüşü, mavi 9 ile beyaz rakibin
ayrılması ve gece 84'teki top taşıyıcısının kısa kopmasıdır. Diğer etiketli
ilişkilerdeki doğrular, kapsam ve altı grubun forma puanları korunur.
Kaynak forma etiketleri çelişen gündüz takiplerinin sayısı 7'den 6'ya iner.

16 hareket önerisinin 14'ü son çıktıda kullanılır; üç palet/destek sınırı
uygulanır. Eski gece kontrolünün 50. kesitinde hareket kolu 144. karede bir
başlangıç kutusunu kaybettiğinden iki öneri o kesit için geri çekilir.
Bu kayıp seyrek etiketlerde görünmüyordu; bütün kutuları karşılaştıran kapsam
koruması yakaladı. Kaybolan kutunun sahte olduğu varsayılmadı.

İkinci motor 15 kesitin tamamında kaynak piksellerden yeniden çalıştırıldı.
Son birinci-motor/ayrım koşusu bu tamamlanmış koşunun hashleri doğrulanmış
ikinci-motor çıktılarını kullandı; ikinci bir model çıkarımı gibi sunulmaz.
Başarısız eski koşunun tamamlanabilen 13 kesitindeki ikinci-motor çıktıları,
yeni tek iş parçacıklı çözümün çıktılarıyla birebir aynıydı.

42 yeni test, gerçek kaynaktan başlangıç dahil iki takip senaryosunu, belirsiz
eşleşmeyi, farklı renkli rakibin yüksek güvenini, bozuk veriyi, kapsam geri
dönüşünü ve önbellek/model bütünlüğünü kapsıyor. İlk tam uygulama koşusunda
3.023 test geçti, 73 koşullu test atlandı. Ruff ve mypy de geçti. Bunlar
gerçek oyuncu doğruluğu yüzdesi değildir; PR'ın son başında CI ayrıca çalışır.

Makine kayıtları: [son değerlendirme](measurements/identity-short-gap-development-20261009.json),
[kaynak piksellerden ikinci motor](measurements/identity-short-gap-secondary-replay-20261009.json),
[seçim, başarısız koşu ve kapsam geri dönüşü](measurements/identity-short-gap-decision-20261009.json),
[26 önerinin kaynak incelemesi](measurements/identity-short-gap-source-review-20261009.json).

## Görüntü incelemesi neden gerekliydi?

İlk prototipin 23 hareket müdahalesi ve üç kimlik ayrımı kaynak şeritlerinde
incelendi. Gündüz mavi 9 → beyaz rakip; gecede iki mavi → beyaz geçişi
ayrım için kaynak desteği veriyor. Bir hareket müdahalesinin doğru görünmesi,
sonraki tüm kimliklerin doğru kalacağı anlamına gelmiyor.

Gece kesit 3, 286–302. kareler iki mavi oyuncunun yakın hareketini içeriyor.
Onarımdan sonraki iki gözlemde başlangıçtaki ByteTrack kimliği 26 iken aday
43'ü sürdürüyor; bağımsız takip desteği de 61'den 31'e geçiyor. Kaynakta
oyuncuların yakınlığı ve örtüşmesi yüzünden bu yeni bağ güvenilir başarı
sayılmaz. Sadece palet değişimi aynı formalı bu şüpheli devri ayıramaz.
Bu nedenle rakip oyuncuya yakınlık koruması ayrıca geliştirmede ölçülür.
Eski mühürlü etiketler bu tanıya göre değiştirilmez.

## Yürütme ve tekrar

İlk tam tekrar gece 78'in çözücü okumasında 21.957.120 bayt ayıramadığı için
başarısız oldu; önce tamamlanan 13 kesit ve hata kaydı korundu. Bu koşu tamamlanmış
ölçüm sayılmadı. `OPENCV_FFMPEG_THREADS=1` isteğine rağmen gerçek çözücü 16 iş
parçacığı bildiriyordu. Yeni sürüm `CAP_PROP_N_THREADS` seçeneğini doğrudan 1
olarak verir ve açılıştaki gerçek değeri denetler. Tamamlanan her kesit için
ayrı denetim dosyası ve ilerleme manifesti yazar.

`scripts.soccertrack_v2.benchmark_short_gap_motion` gerçek Supervision ve
Deep OC-SORT/OSNet'i aynı ham kutular ve kaynak videolarında çalıştırır.
Kaynak/model/kod hashleri koşu başında ve sonunda denetlenir; örnek çıktıları
ayrı dizinde tutulur. Eski palet kontrolü artık geliştirme verisidir ve
gündüzdeki iki açık etiket düzeltmesi yalnız bu tanı puanına uygulanır.

Çalıştırmadan önce her iki `validate_palette_acquisition --group` kapısı
geçmelidir. Araştırma ortamı `venv-cv`, Supervision 0.30.2 ve trackers 2.6.0'dır.

```powershell
.\venv-cv\Scripts\python.exe -m scripts.soccertrack_v2.benchmark_short_gap_motion --out .cache/short-gap-new-run
.\venv-cv\Scripts\python.exe -m pytest --noconftest -q tests/test_short_gap_motion.py
```

Tamamlanmış bir koşunun ikinci motor çıktıları `--secondary-report` ile yeniden
kullanılabilir. Kaynak/model/kod ve sürümler aynı olmalı, her çıktı kayıtlı hash
ile eşleşmeli; eksik veya değişmiş bağımsız takip kanıtı reddedilir. Bu seçenek
yeni model çıkarımı yapılmış gibi raporlanmaz. Birinci aday ve ölçüm düzeni
değişebilir; bağımsız takip uygulaması/modeli ve kaynakları aynı kalmalıdır.
İkinci motorun özgün sürücü hashleri ve çözücü bilgisi önceki koşuya aittir;
güncellenmiş ölçüm sürücüsünün yeniden çıkarım yaptığı iddia edilmez.

## Devam koşulları

Önceki uzlaşı kontrolünün gündüz 60/62 ve gece 80/82 kesitleri bu 15'liye dahil
değildir. Canlı entegrasyon ve yeni adayın dondurulması öncesinde bunlar da
kapsanmalı; özellikle beyaz 6'nın yanlış bölünmesinin reddi ve daha önceki
altı doğru ayrım korunmalıdır. Buradaki olumlu üç seyrek ilişki bu şartların
yerine geçtiği şeklinde yorumlanmaz.

Yeni kontrol için önce son aday, bağımsız takip modeli, kaynak planı ve
kabul koşulları sabitlenmeli; canlı entegrasyonda aynı gözlem/forma kanıtını
koruyan iki akış ve gecikmeli kimlik ayrımı doğrulanmalıdır. Mevcut gece
forma hataları, kısmi kutular, top/olay doğruluğu ve tam maç gerçek zaman
hedefleri bu kısa kopma deneyinin tamamlanmış çıktıları değildir.
