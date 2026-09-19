# Deep OC-SORT entegrasyonu ve ölçümü

19 Eylül 2026. Deep OC-SORT + resmî OSNet modeli sabit kamera video/canlı
hattına açık seçimle entegre edildi. Doğrulanmış Supervision ByteTrack varsayılan
kaldı: yeni motor kişi bağlantılarının bir bölümünü iyileştirse de tüm doğruluk
kapılarını geçmedi. Yeni kontrol görüntüleri açılmadı; başarısız adaya göre
parametre ayarlanmadı. Bu sonuç "futbol için en iyi motor bulundu" anlamına gelmez.

## Gerçek veri

Önceden görülen 11 kesit, her kolda 4.125 kare; aynı RF-DETR kutuları, güvenleri,
saha süzgeci, renkler ve başlangıç çapaları. Supervision, Deep OC-SORT hareket
ve Deep OC-SORT+OSNet olmak üzere 33 çıktı. Önceki etiketler/sonuçlar korunur.

| Grup | ByteTrack doğru/yanlış/atanamayan forma | Deep OC-SORT+OSNet |
|---|---:|---:|
| Gündüz | 285 / 28 / 2 | 285 / 29 / 1 |
| Gece | 95 / 13 / 15 | 100 / 17 / 6 |
| Ek gece | 50 / 12 / 5 | 52 / 12 / 3 |
| Eski gece kontrolü (artık geliştirme) | 52 / 9 / 4 | 51 / 10 / 4 |

| Kişi çiftleri | ByteTrack aynı / farklı doğru | Deep OC-SORT+OSNet |
|---|---:|---:|
| Gündüz başlangıç, 22 aynı + 7 farklı | 15 / 1 | 15 / 3 |
| Gündüz bağlantı denetimi, 5 + 2 | 2 / 2 | 3 / 2 |
| Eski gündüz kontrolü, 134 + 134 | 92 / 84 | 96 / 85 |
| Eski gece kontrolü, 63 + 63 | 59 / 61 | 60 / 61 |

Toplam iyileşme, önceden doğru iki gündüz bağlantısının kaybını gizlememeli:
`0-280-d20→0-310-d18`, `3-440-d10→3-460-d10`. Ayrıca gündüz başka-forma ataması
27→32, ek gecede 3→5. Eksik forma kutusu gündüzde her iki kolda 1; diğer
gruplarda 0. Tam kişi/kapsam/çift sonuçları ve reddedilme nedenleri
`measurements/deepocsort-development-results.json` içinde.

Modelin katkısı da ayrıldı: hareket kolunda gündüz doğru forma 278 iken OSNet
ile 285; aynı başlangıç kişi çifti 14→15, farklı kişi 1→3. Görünüş katkı sağlar,
ancak aynı forma, küçük oyuncu kırpımları ve tespit kaybını tek başına çözmez.

Ortalama takip güncellemesi ByteTrack 1,98 ms, Deep OC-SORT hareket 3,47 ms,
OSNet dahil 41,48 ms. Bu süreler model yükleme, dedektör ve video çözmeyi içermez;
canlı uçtan uca FPS iddiası değildir. Ölçüm sırasında kısa bir ayrı GPU model
eşitlik kontrolü de çalıştı; süreler betimleyicidir, kesin performans kıyaslaması
olarak alınmamalıdır.

## Entegrasyon ve kanıt

- `--tracker deepocsort` video, sıcak canlı ve izole canlı işçiye taşınır.
  Model yolu alt süreç çalışma dizininden önce çözülür; çapa bağlamı motor/model
  hash'ini içerir. Varsayılan eski canlı durumları uyumlu kalır.
- Üretim modeli SHA-256 ile doğrulanır; çalışma sırasında indirilmez. Güvenli
  ağırlık yükleme kullanılır. RF-DETR değişmez; kutu/güven/metadata yalnız özgün
  tespitten alınır. Akış sayaçları bağımsız, boş kare ve kesinti resetleri testlidir.
- Gerçek görüntüde 16 kırpım × 512 özellik, resmî `EmbeddingComputer` ile
  **birebir aynı**, en büyük mutlak fark **0**. Ayrıntı:
  `measurements/deepocsort-model-parity.json`.
- Önceki 22 üretim çıktısı yeniden karşılaştırıldı ve 164.772 kişi gözlemi korundu. Yalnız eklenen iki varsayılan
  yapılandırma alanı (`tracker_backend`, `reid_model`) çıkarılarak bütün çıktı
  byte'ları birebir eşleşti. Özgün dondurma, eski ek belge ve eski eşitlik kanıtı
  değişmez; yeni kanıt ayrı sürümlü entegrasyon belgesine bağlıdır.
- Kaynak MIT lisansları, sabit commit ve yerel değişiklikler vendor dizininde;
  görünüş modelinin ağırlıkları Git'e eklenmez. Karşılaştırma sonrası yalnız
  vendor satır sonu boşlukları temizlendi; ilgili önce/sonra hash'leri
  `measurements/deepocsort-formatting-amendment.json` içinde.

Kurulum ve kullanım: [TAKIP-REID-ENTEGRASYONU.md](TAKIP-REID-ENTEGRASYONU.md).
Doğruluk kararı: yeni motor deneysel/açık seçim; varsayılan ByteTrack. Aynı
oyuncuyu segmentler arasında veya tüm maç boyunca doğru tanıma hedefi hâlâ açık.

## Doğrulama

95 ilgili gerçek CV/entegrasyon/dondurma testi geçti. İzole SQLite ile tam
uygulama koşusunda 2.893 test geçti, CV bağımlılıkları bulunmayan uygulama
ortamında 43 test atlandı; ayrı CV koşusu bu motorun gerçek algoritmasını çalıştırır.
Ruff ve mypy temiz. Tam koşudan sonra vendor dosyasının yalnız boş son satırı
temizlendi (AST aynı); ilgili testler ve eşitlik kanıtı yeniden çalıştırıldı.

Aydınlık 30 saniyelik kesit üretim `process_video` yolunda 125 TrackingFrame ve
1920×506 önizleme üretti; kaynak çözme/renk/OSNet CUDA/çıktı üretimi gerçek,
RF-DETR kişi tespitleri değişmez önbellekten geldi. Dedektör yeniden çalıştırılmadı,
top girdisi ve DB ingest yapılmadı. Kanıt: `measurements/deepocsort-pipeline-smoke.json`.
