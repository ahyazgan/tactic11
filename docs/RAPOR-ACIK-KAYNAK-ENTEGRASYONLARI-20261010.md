# Rapor iş akışındaki açık kaynak entegrasyonları

10 Ekim 2026. Amaç, analistin gerçek videodan onaylı ve taşınabilir rapor hazırlamasını hızlandırmak. Yeni bileşenler kendi sunucumuzda çalışır; müşteri videosu üçüncü taraf hizmetlere gönderilmez.

| Bileşen | Sabit sürüm / lisans | Uygulamada kullanımı |
|---|---|---|
| [tus-js-client](https://github.com/tus/tus-js-client) | 4.3.1 / MIT | 2 MiB parçalar, duraklat/devam, sayfa yenileme sonrası aynı dosyayla devam, bağlantı ve oturum yenileme |
| [Portalocker](https://github.com/wolph/portalocker) | 4.4.0 / BSD-3-Clause | Aynı yüklemeye birden fazla işlemden yazmayı engelleyen Windows/Linux dosya kilidi |
| [Hotkeys.js](https://github.com/jaywcjlove/hotkeys-js) | 4.0.8 / MIT | Video alanında boşluk, yön tuşları, N/I/O; metin ve yerel kontrol alanlarını koruma |
| [Konva](https://github.com/konvajs/konva) / [React Konva](https://github.com/konvajs/react-konva) | 10.7.1 / 18.2.16 / MIT | Seçilen kaynak karesine ok ve alan ekleme, üç renk, geri alma, düzenleme, kayıt |

React Konva'nın React 18 sürümü seçildi. Lisansların tam metinleri `frontend/public/review-third-party-notices.txt` dosyasında dağıtılır. Bu tablo eklenen doğrudan bağımlılıkları kapsar; tüm ürün bağımlılıklarının lisans envanteri değildir.

## Yükleme ve saklama sınırları

- `/match-reports/uploads` rotaları JWT, aktif kulüp ve düzenleyici rolü ister. Yükleme makbuzları kulüp **ve kullanıcı** alanına aittir. Tamamlanan videolar mevcut kulüp video kütüphanesine girer.
- [tus 1.0](https://tus.io/protocols/resumable-upload) core/creation/expiration/termination iş akışı uygulanır. Concatenation, deferred-length, creation-with-upload ve method-override uygulanmaz. Genel amaçlı tam tus sunucusu iddiası yoktur.
- Varsayılan video sınırı 2 GiB, istek parçası sınırı 4 MiB, kullanıcı başına üç yarım yükleme ve oluşturulduktan itibaren 24 saat devam süresi vardır. Dosya tamamlanana kadar oynatılabilir video kaydı oluşturulmaz.
- Makbuzlar ve parçalar `REVIEW_DATA_DIR/<kulüp-hash>/uploads/<kullanıcı-hash>` içinde tutulur. Baytlar diske senkronlandıktan sonra makbuz atomik değiştirilir. Kesinti sonrası onaylanmamış kuyruk baytları atılır; taşınmış kaynak ve DB kaydı idempotent tamamlanır. İşlem ölünce işletim sistemi kilidi serbest bırakır.
- Tarayıcı devam kimliği hesap, token kullanıcı kimliği, dosya adı/boyutu/tarihi ve baş/orta/son örneklerinin SHA-256 değerine bağlıdır. Bu örnek hash'i tüm dosya eşitliği kanıtı değildir; kullanıcı aynı dosyayı seçmelidir. Tam dosyanın SHA-256 değeri sunucuda hesaplanır.
- Süresi dolmuş veya geçersiz makbuz/parçalar aynı kullanıcı yeni yükleme açtığında temizlenir. Süre dolunca devam reddedilir; zamanlanmış genel disk temizleyicisi yoktur. Kilit dosyaları yarış koşulunu önlemek için tutulur. Tamamlanmış MP4 kaynakları makbuz temizliğinde/iptalinde silinmez.
- Bir API makinesi veya aynı kalıcı yerel medya birimini kullanan işlemler içindir. Ayrı diskli çoklu sunucu, S3 multipart, kota/faturalama ve tüm 90 dakikalık maç yükü doğrulanmış değildir. Reverse proxy zaman aşımı ve istek sınırları en az 2 MiB parçayı desteklemelidir. API 429 yanıtı verirse istemci gecikmeli yeniden dener.

## Çizim, onay ve teslim

Kaynak kare sunucunun FFmpeg aracıyla çıkarılır. Her çizimin kaynak zamanı ve 0–1 arası koordinatları rapor belgesinde saklanır. En fazla 20 ok/alan ve 12 pozisyon kabul edilir. Kare zamanı pozisyon aralığında olmalıdır. Eski raporlar çizimsiz açılabilir.

Çizim değişikliği normal rapor sürümüne dahildir; kaydetme eski onayı kaldırır ve çakışmada başka oturumun üzerine yazılmaz. Teslimde kaynak hash'i doğrulanır. PDF gerçek kaynak karesiyle işaretleri içerir; ZIP içinde aynı kareler `drawings/NN.png` olarak, hash ve zamanları manifestte bulunur. Çevrimdışı HTML bu PNG'leri ve özgün kesilmiş klipleri gösterir. İşaretler analistin anlatımıdır; otomatik oyuncu ölçümü veya hareket boyunca takip eden telestrasyon değildir.

## Önceki dış takip araştırmasıyla ilişki

[15 proje karşılaştırması](HARICI-TAKIP-PROJELERI-KARSILASTIRMA-20261010.md) ve [mevcut takip entegrasyon durumu](TAKIP-ENTEGRASYON-DURUMU.md) geçerlidir. Bu değişiklik RF-DETR/ByteTrack tabanını veya dondurulmuş kontrol adayını değiştirmez. McByte kimlik önerileri bağımsız doğruluk kapısından geçmeden otomatik üretim kararı olmaz. Kapalı model erişimi, belirsiz lisans ve yerel ölçüm eksikliği dış projeleri topluca üretime eklememek için somut sınırlardır.

## Bağımlılık denetimi

`npm audit` (10 Ekim 2026) yeni dört ön yüz paketinde bildirim göstermedi. Mevcut ağaç toplam 19 bildirim içeriyor: 2 orta, 15 yüksek, 2 kritik; kritik bildirimler mevcut Next.js ve geliştirme zincirindeki shell-quote ile ilişkili. Bu entegrasyon güvenlik borcunu kapatmaz. Desteklenen Next.js sürümüne geçiş ve eski geliştirme bağımlılıklarının güncellenmesi ayrıca tüm uygulama/dağıtım testlerini gerektirir; `npm audit fix --force` uygulanmadı. “Tüm bağımlılıklar güvenli” veya “internete açık ücretli kullanıma hazır” sonucu çıkarılamaz.

## Tekrar üretme

```powershell
venv/Scripts/python.exe -m pytest tests/test_review_uploads.py tests/test_review_drawing.py tests/test_match_reports.py -q
cd frontend
npm run typecheck
# E2E_REVIEW_BACKEND=true ve scripts.review_e2e_setup ile hazırlanmış ayrı API/DB gerekir.
npx playwright test e2e/match_reports.spec.ts e2e/review_uploads.spec.ts e2e/review_followups.spec.ts --workers=1
```

API testleri yanlış offset/başlık/boyut, hesap ve rol ayrımı, sürenin dolması, iptal, süreç kilidi, disk yazımı/DB kaydı arasında kesinti, gerçek hash, çizim doğrulama ve PDF görüntüsünü kapsar. Tarayıcı testi gerçek yüklemeyi ikinci parçada keser, duraklatır, sayfayı yeniler, aynı dosyayı doğru offsetten sürdürür ve gerçek refresh isteğini doğrular. Teslim testi kısayolla pozisyon açıp çizim yapar, PDF/ZIP indirir ve çevrimdışı görüntü/klipleri açar.
