# Klipli maç raporu: insan incelemesiyle teslim

Bu akış, bir analistin gerçek videodan seçtiği pozisyonları kulübe PDF ve
oynatılabilir kliplerle teslim etmesini sağlar. Ekran: `/match-reports`
(menüde **Zekâ & Rapor → Klipli Maç Raporu**).

## Analistin işi

1. Kulübün hesabıyla giriş yap; H.264, 8 bit MP4 video yükle.
2. Başlık, kulüp, rakip, tarih ve inceleme kapsamını gir.
3. Her pozisyon için başlangıç/bitiş, konu, gözlem ve çalışma önerisi yaz.
   Oyuncu adı ve bir sonraki maçta kontrol edilecek davranış isteğe bağlıdır.
4. Maç değerlendirmesi, iyi yapılanlar ve en fazla üç antrenman odağını yaz.
5. Kaydet. Görüntüleri, isimleri ve yorumları gerçekten kontrol ettikten sonra
   inceleme kutusunu işaretleyip onayla.
6. PDF indir veya klipli teslim paketini hazırla. ZIP'i klasöre çıkarıp
   `index.html` dosyasını aç; klipler internet olmadan oynatılır.

Yeni maç öncesinde **Önceki raporlardan gelişim takibi** bölümünü aç. En güncel
100 rapordaki onaylı “Sonraki maçta neye bakacağız?” notları oyuncu veya konuya
göre aranabilir. Her notun önceki çalışma önerisi, kaynak raporu ve sürümü
görünür. Aynı adlı oyuncuların notları birleştirilmez. Açık taslak kaydedilmeden
kaynak rapora geçilmez. Analist yeni maçta gördüklerini yeni rapora kaydeder;
bu liste kendi başına iyileşme veya kötüleşme skoru üretmez.

Önerilen ilk hizmet kapsamı: tek maç incelemesi, seçilmiş kritik pozisyonlar,
oyuncuya özgü gözlemler ve üçe kadar antrenman odağı. Gerçek müşteriyle süre,
revizyon ihtiyacı ve antrenörün raporu kullanıp kullanmadığı ölçülmeden sabit
teslim süresi veya kârlılık iddiası yapılmaz.

## Teslimdeki bilgiler

| Alan | Kaynak |
| --- | --- |
| Maç ve kapsam | Analistin girdiği kulüp, rakip, tarih, tam maç/seçilmiş bölüm beyanı |
| Pozisyon | Kaynak videonun başlangıcına göre saniye; hücum, savunma, geçiş, duran top veya oyuncu gelişimi |
| Gözlem | Analistin görüntüden doğruladığı açıklama |
| Çalışma | Antrenman önerisi ve sonraki incelemede aranacak davranış |
| Onay | Oturum açmış inceleyenin kimliği, UTC zamanı, rapor sürümü |
| İzlenebilirlik | Kaynak dosya adı ve SHA-256; ZIP manifestinde pozisyonlar ve klip hash'leri |

Her pakette `report.pdf`, `index.html`, `manifest.json` ve `clips/*.mp4` bulunur.
Klipler H.264/AAC olarak, en fazla 1280 piksel genişlikte yeniden kodlanır.
Kaynak video korunur. PDF'deki zamanlar yayın saati veya maç dakikası değildir.

## Kayıt, onay ve veri ayrımı

- Giriş zorunlu. Admin, analyst ve coach oluşturur/düzenler/onaylar; viewer okur
  ve hazır teslimi indirir. Yeni rapor, video ve paket sorguları kulüple sınırlıdır.
- Bir değişiklik kaydedildiğinde önceki onay kalkar. Özet, en az bir pozisyon ve
  bir antrenman odağı olmadan onay verilemez. Kaydedilmemiş değişiklik veya açık
  pozisyon formu varken teslim düğmeleri kapalıdır.
- Sürüm çakışmasında başka oturumun kaydı ezilmez. Analist kendi notlarını ayrı
  rapora kopyalayabilir; kopya yeniden inceleme gerektirir.
- Normal tarayıcı depolaması açıkken, kaydedilmemiş son taslak aynı sekmenin
  `sessionStorage` alanında hesap/kulüp anahtarıyla tutulur. Yenileme ve sayfaya
  dönüşte kurtarılır. Bu sunucu kaydının yerini tutmaz; sekmeyi kapatmadan kaydet.
  Başka hesapta önceki hesabın taslağı gösterilmez.
- PDF/video/JSON/ZIP yanıtları `private, no-store` taşır. PWA, API ve imzalı video
  isteklerini önbelleğe almaz; v4 eski önbelleği temizler.
- Oynatma bağlantısı dört saatlik, kullanıcı/kulüp/video kapsamlı bir erişim
  belirteci taşır. Genel paylaşım bağlantısı değildir. Süresi dolarsa raporu
  yeniden aç veya **Videoyu yeniden bağla** düğmesini kullan.
- ZIP indirme tarayıcının indirme yöneticisine aktarılır; uygulama paketin
  tamamını JavaScript belleğinde biriktirmez. Her tıklamada iki dakikalık,
  kullanıcı/kulüp/rapor/paket kapsamlı bir indirme bağlantısı üretilir. Bu süre
  indirmeyi başlatmak içindir; devam eden aktarım iki dakikada kesilmez.
  Süresi dolmuş bir indirmeyi yeniden başlatmak için **ZIP indir** düğmesine
  tekrar basılır. Bağlantı hesap girişi veya farklı dosyalara erişim sağlamaz.
- Paket onaylı sürümün sabit kopyasından üretilir. Daha sonra raporu değiştirmek,
  önceden oluşturulmuş sürümlü paketi değiştirmez. İndirmeden önce sürümü kontrol et.
- İşçi işlem boyunca 20 saniyede bir yaşam sinyali yazar. Sinyal 120 saniye
  kesilirse durum sorgusu işi başarısız sayar; kullanıcı yeniden başlatabilir.
  Eski bir işçi başarısız işin üzerine tamamlandı yazamaz.

Bu sınırlar yeni rapor akışı için doğrulanmıştır. Eski video/tracking ve diğer
uygulama modüllerinin tamamına yönelik bir güvenlik denetimi anlamına gelmez.

## Çalıştırma

- Mevcut `venv` içinde `requirements.txt` kurulmalı; `imageio-ffmpeg==0.6.0`
  video aracını sağlar. İşletim sisteminde ayrıca FFmpeg kurulması gerekmez.
- Veritabanını yedekledikten sonra `python -m alembic upgrade head` çalıştır.
  `0037_match_review_reports` üç tablo ve aktif iş için kulüp başına tekillik
  kısıtı ekler. Önceki kurulumların tüm ara göçleri de uygulanmalıdır.
- `REVIEW_DATA_DIR` varsayılanı `data/reviews`; kullanıcı videoları ve paketler
  burada tutulur. Docker/uzak sunucuda kalıcı, API tarafından yazılabilir disk
  gerekir. SQL veritabanıyla bu dizin birlikte yedeklenir.
- Docker Compose, `reviewdata` adlı kalıcı volume'ü `/app/data/reviews` yoluna
  bağlar. İmaj dizini uygulamanın normal kullanıcısına ait oluşturur; root ile
  çalıştırmak gerekmez. Konteyner yenilenmesi dosyaları korur; volume silme
  (`docker compose down -v`) yedeğin yerine geçmez ve dosyaları kaldırır.
  Eski konteynerin kendi dosya sisteminde kayıt varsa, yeniden oluşturmadan
  önce `/app/data/reviews` içeriğini yedekleyip yeni volume'e taşıyın.
  Depodaki `render.yaml` hâlâ demo kurulumu tarif eder ve medya diski tanımlamaz;
  müşteri videosunu oraya taşımadan kalıcı disk ve yedekleme yapılandırılmalıdır.
- `REVIEW_MAX_UPLOAD_BYTES` varsayılanı 2 GiB. Kabul edilen video süresi
  0,5 saniye–3 saat; rapor başına 12 pozisyon, pozisyon başına 0,5–120 saniye.
- Bir API sürecinde bir paket işçisi ve dört işlik kapasite vardır. Kulüp başına
  aynı anda tek aktif paket veritabanında uygulanır. Birden fazla API süreci
  kullanılıyorsa aynı kalıcı medya dizinini görmeleri gerekir; toplam işçi
  kapasitesi süreç sayısıyla artar.
- Yerelde `launcher/CODEX.bat`: web 3100, API 8100. Yalnız ön yüzü yayınlamak
  bu özelliği çalıştırmaz; kimlik doğrulama, veritabanı ve kalıcı medyası olan
  API'ye `API_BASE_URL` yönlendirmesi gerekir. Büyük yüklemelerde ters vekilin
  gövde/süre/disk sınırları ayrıca uyumlu olmalıdır. FastAPI multipart kabulü
  sırasında da geçici disk kullanır; yükleme ve teslim için boş alan gerekir.
- Otomatik müşteri e-postası, herkese açık paylaşım, faturalama veya dosya silme
  bu ilk sürümde yoktur. Teslim, yetkili kullanıcının indirmesiyle yapılır.

## Doğrulama ve gerçek kapasite

- API testleri: kulüp/rol ayrımı, boş/bozuk/uyumsuz video, boyut sınırı, tarih
  dilimi, sürüm çakışması, onayın kalkması, kuyruk kesintisi, kapasite, kaynak
  değişikliği, HTML kaçışları ve uzun Türkçe PDF.
- Gerçek FFmpeg testleri: klibin seçilen kareden başlaması, süre eşleşmesi ve
  **90 dakikalık sentetik** videonun sonundan kesim. Bu, 90 dakikalık gerçek maç
  analizi veya insan inceleme süresi ölçümü değildir.
- Chromium: gerçek API'de yükleme → oynatma → pozisyon → kayıt → onay → PDF/ZIP;
  oturum yenileme, başka hesaba geçiş, taslak kurtarma, çakışma kopyası ve PWA'nın
  çevrimdışı özel rapor sunmaması. GitHub `live_auth` işi de bu zinciri sentetik
  video ve ayrı SQLite veritabanıyla çalıştırır.
- Yerel görüntü denemesi, daha önce kullanılmış 30 saniyelik gündüz maç parçasıyla
  yapılır. Teknik test raporu futbol uzmanının değerlendirmesi olarak sunulmaz.
- Dondurulmuş takip adayının 103 dosyası bu çalışma sırasında değiştirilmemiştir.

Yerel şema yükseltme provası, eski 34 tablodaki 528.521 satırı koruyarak
`0032` → `0037` geçti. Provada önceden var olan bir veri sorunu da bulundu:
95 maç ve 252.678 olay `psg` kimliğine bağlı, ancak `tenants` kaydı eksikti.
Kaynak, depodaki StatsBomb araştırma ithalatıydı. `ingest_club_matches` artık
tanımsız tenant'a veri yazmadan hata verir. Yerel eski veri onarımı, aynı `psg`
kimliği için pasif araştırma tenant'ı eklemekle sınırlıdır; maç/olay satırları
silinmez, değiştirilmez ve başka müşteri hesabına taşınmaz.

Bu sürüm otomatik doğru pas sayımı, GPS doğruluğunda mesafe/hız, kesin oyuncu
kimliği veya maçlar arası sayısal gelişim skoru vaat etmez. Oyuncu gelişimi burada
kanıtlı gözlem, çalışma önerisi ve sonraki maçta kontrol edilecek davranışla
başlar. Ücretli pilotta gerçek futbol değerlendirmesi bir analist/antrenörün
incelemesini gerektirir.
