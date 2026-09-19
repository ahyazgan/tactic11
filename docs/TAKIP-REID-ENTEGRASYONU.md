# Deep OC-SORT + OSNet

RF-DETR tespitlerini kullanan görünüş destekli takip, sabit kalibre kameralar
için açıkça seçilebilir. Model ağırlıkları uygulamaya gömülmez ve takip sırasında
indirilmez. Varsayılan `supervision` motoru önceki doğrulanmış ByteTrack yoludur.
`deepocsort` deneysel profildir; geliştirme/kontrol kapıları geçilmeden otomatik
seçilmez. Genel futbol kişi kimliği doğruluğu veya "en iyi motor" iddiası yoktur.

`--tracker consensus` aynı OSNet kurulumu ile mevcut ByteTrack'i koruyup
kimlik ayrımlarını ikinci akış ve renk kanıtıyla doğrulayan ayrı deneysel
seçenektir. Ayrıntı: [KIMLIK-UZLASISI-SONUCLARI.md](KIMLIK-UZLASISI-SONUCLARI.md).

## Kurulum

Mevcut `venv-cv` ortamında çalışan CUDA Torch kurulumu gerekir. Bu makinede
Torch `2.11.0+cu128`, CUDA ve RTX 5060 Laptop doğrulandı. Model FP32 çalışır.
Uygulamanın web/API ortamının bu bağımlılıklara ihtiyacı yoktur.

```powershell
venv-cv\Scripts\python.exe -m pip install -r requirements-tracking-reid.txt
venv-cv\Scripts\python.exe -m scripts.setup_tracking_reid
```

Model SHA-256: `2f38acc25e28cb29407635db2be315edc08d5457a904b72a9a11e427f41f3242`.
Farklı veya bozuk ağırlık reddedilir. İndirme mevcut dosyanın üzerine yazmaz.
Model değişikliği yeni profil, ölçüm ve onaylı hash gerektirir.

## Kullanım

Mevcut `scripts.track_video` veya `scripts.track_live` komutuna ekleyin:

```text
--tracker deepocsort --camera static --calibration <sabit-kamera.json>
```

Özel konum için `--reid-model <osnet_ain_ms_d_c.pth.tar>` kullanılır. Canlı sıcak
işçide ağ bellekte tutulur; her segmentin kişi kimliği ve görünüş geçmişi ayrı
başlar. `--isolate` aynı motoru/modeli alt sürece geçirir. Takım çapası motor/model
bağlamına bağlıdır; farklı deney için ayrı izleme klasörü kullanılır. Segmentler
arası insan kimliği eşleştirmesi bu değişikliğin kapsamı değildir.

Hareketli/kare başına kalibrasyonlu kamera profili desteklenmez. Eksik model,
CUDA veya hatalı girdi açık hata verir; sessiz motor değişimi yapılmaz.
Takipte yalnız orijinal tespit satırları dışarı çıkar. Kesintiler geçmişi sıfırlar.
Görünüş çıkarımında upstream'in dosya/pickle cache'i kullanılmadığından eski
kutuya ait özelliklerin yeni kutuda yeniden kullanılması mümkün değildir.

## Kaynak ve değerlendirme

[Resmî Deep OC-SORT](https://github.com/GerardMaggiolino/Deep-OC-SORT),
`6bb51d027b137233f5c520b6fcc4f2ae387a6ba9`; MIT lisansları ve uyarlamalar
`app/tracking/_vendor/deepocsort/NOTICE.md` içinde. Yazarların genel OSNet
modeli kullanılır; resmî README'nin MOT skorları futbol başarımı olarak alınmaz.
CMС kapalı, bütün gövde 128×256 RGB, ImageNet normalizasyonu ve sabit parametreler
`TAKIP-REID-ENTEGRASYON-PLANI.md` içinde kayıtlıdır.

Geliştirme tekrarı:

```powershell
venv-cv\Scripts\python.exe -m scripts.soccertrack_v2.benchmark_deepocsort --out .cache/<yeni-klasor>
```

Önceden görülen 11 kesit, üç kol: mevcut ByteTrack, Deep OC-SORT hareket ve
Deep OC-SORT+OSNet. Tespit/etiket eşleşmesi kaynak kutuyla yapılır; üretilen ID
etiket eşleştirmesinde kullanılmaz. Süre ReID dahil takip güncellemesidir;
dedektör, model yükleme ve video çözme dahil uçtan uca FPS değildir.
