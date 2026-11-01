# Video takip ve otomatik telestrasyon: doğruluk karnesi (2026-11-01)

Kulübe "bu ne kadar güvenilir?" sorusunun cevabı. Her satır ölçülmüş bir sayıdır;
nasıl ölçüldüğü ve tekrar üretimi bağlantılı belgede. Ölçülmemiş olan "ölçülmedi"
diye yazılır.

## Ne gerekiyor

- **Sabit kamera** (stadyum çatısı, direk ya da panorama). Telestrasyon TV yayınında
  çalışmaz; yayında yalnız takip var (`docs/CANLI-MOD-KILAVUZU.md`).
- **Saha kalibrasyonu**: stadyum başına bir kez, en az 5 saha işareti; bağımsız
  doğrulama hatası ≤ 2,0 m olmazsa çizgi ve etiket çizilmez (`canli_mac` bunu
  başlamadan denetler ve geçmeyen kalibrasyonla başlamaz).
- **GPU**: ölçümler RTX 5060 (8 GB) dizüstünde.

## Koçun gördüğü çıktılar

İki maç, ikisi de ön kayıtlı ve sistemin karar verirken görmediği 10'ar dakika:
**gece** SoccerTrack v2 117092 (1800–2400 sn, 7500 kare) ve **gündüz** 132877
(600–1200 sn, hiç kullanılmamış test maçı). Referans olay kayıtları; gecede GSR
oyuncu konumları da.

| Çıktı | Gece (117092) | Gündüz (132877) | Not |
|---|---|---|---|
| Hangi takım savunuyor (çizilen karelerde) | %68,1 | %81,3 | gece önceki top seçimiyle %46,1 |
| Blok etiketi (alçak/orta/yüksek) | dengeli %63,7, tam isabet %67,6 (uçtan uca, sahiplik olaylardan) | dengeli %84,0, tam isabet %86,2 (sahiplik takipten) | gündüz: referans saha işaretlerine göre düzeltilmiş GSR |
| Savunma hattı hatası (referansa karşı) | medyan 1,9 m | medyan 1,0 m, p90 10,4 m | gece referansı düzeltilemedi (farklı görüntü uzayı) |
| Çizim kapsaması | %86 | %100 | gece kalanında savunandan < 6 oyuncu görünür |
| Pres işareti uyumu | %96,7 | %94,8 | |
| Oyuncu takım rengi | %76 | %93,4 | eşleşen oyuncu, 118 794 eşleşme |
| Top, dokunuş anında 5 m içinde | %19,1 | %73,2 | gece ayak dibindeki top çoğunlukla bulunamıyor |
| Top, pas uçuşunda 5 m içinde | %50 (42 pas) | %91,1 (79 pas) | |

Gündüz ve aydınlık sahada sistem belirgin biçimde daha güvenilir; gece ışıklarla
sahte top adayları en zor durum.

**Şekil bekçisi (blok/genişlik/hat aralığı/boy uyarıları):** dakikalık medyan ölçüm
gürültüsü blok derinliğinde 0,8–2,1 m ve hat aralığında 0,6–2,0 m (eşikler 6 ve 4 m:
gündüz güvenilir, gecede sınırda); genişlikte 2,4–5,8 m (6 m eşik gürültü içinde:
güvenilmez) ve boyda yeni sahada 10 m (güvenilmez). Ayrıntı ve öneri: `docs/SEKIL-BEKCISI-OLCUMU.md`.

**Başka stadyum (132831, gündüz, düzeltilmiş referansa karşı 10 dk):** takım rengi
%92,6, blok etiketi dengeli %68,4 / tam %74,6, savunma hattı medyan 3,2 m, pres %97,7,
kapsama %97, karede eşleşen oyuncu 14,0; top dokunuşta %42,2, pas uçuşunda %71,4.
Oyuncu tespiti bu sahada iyi: MOT etiketli klipte v2 tespit oranı %96,1, kesinlik
%91,6. (Ham GSR referansıyla ilk ölçüm takım %76,7 / hat 5,2 m göstermişti; fark
referansın kendi 2–3 m en kaymasından, `docs/measurements/gsr-corrected-telestration.json`.)
Göz etiketli net renkli kutularda takım ataması %93–97
(`docs/TAKIM-AYRIMI-GUNES.md`; renk oranıyla yeniden atama ön kayıtlı kontrolde geçmedi).
Ayrıntı: `docs/measurements/venue-132831-detector-and-geometry.json`, `docs/TOP-TESPITI-OLAY-OLCUMU.md` §6.

Kaynaklar: `docs/TOP-TESPITI-OLAY-OLCUMU.md` (ön kayıt + kontrol),
`docs/measurements/ball-track-control.json`, `docs/measurements/daylight-132877-gsr-telestration.json`,
`docs/OTOMATIK-TELESTRASYON.md`, `docs/DEDEKTOR-INCE-AYAR-SONUCLARI.md`.

## Altyapı ölçümleri

| | Ölçülen | Kaynak |
|---|---|---|
| Panoramada oyuncu tespiti (v2) | GT oyuncularının %61,9'u, hayalet payı %33,9 | `docs/DEDEKTOR-INCE-AYAR-SONUCLARI.md` |
| Takip konumu, en yakın GT oyuncusuna | medyan ~2,4–3 m (hayaletler dahil) | `docs/TOP-TESPITI-OLAY-OLCUMU.md` |
| Saha kalibrasyonu (65 işaret, TPS) | bir-dışarıda doğrulama 1,76 m (gece), 1,43 m (gündüz) | `docs/TOP-SECIMI-SONUCLARI.md`, `docs/GUNDUZ-MACI-SONUCLARI.md` |
| 30 sn segment işleme süresi | 89–102 sn (gerçek zamanın ~3,2 katı) | `docs/CANLI-HIZ-VE-PROVA.md` |
| `--keep-up` ile gecikme | ~2 dk sabit, maçın ~%42'si işlenir | `docs/CANLI-HIZ-VE-PROVA.md` |

## Ne zaman kullanılır

- **Devre arası ve 60–80. dakika kararları**: ~2 dakika geriden gelen resim yeterli.
- **Maç sonu**: atlanan segmentler silinmez, maçın tamamı çizimli işlenebilir.
- **Son saniye kararı için değil**: gerçek zamana bu donanımda ulaşılmadı.

## Bilinen sınırlar

- Üç maç: iki maç aynı üniversite sahasında (bir gece, bir gündüz); üçüncü,
  başka bir stadyum (132831). Düzeltilmiş referansla üçüncü saha ilkine yakın
  (takım %92,6, blok dengeli %68,4, hat 3,2 m).
- GSR referansı ile saha işareti kalibrasyonumuz arasında, iki gündüz maçında da,
  sahanın eni boyunca sistemli 2–3 m kayma ölçüldü. Resmî saha işaretlerine karşı
  sınandığında kaymanın GSR tarafında olduğu görüldü: GSR'nin piksel→saha dönüşümü
  işaretleri 5–9 m yanlış yere koyuyor, bizim kalibrasyonumuz 1,5 m içinde
  (`docs/measurements/gsr-reference-geometry.json`). Bu yüzden GSR'ye karşı
  "eşleşen oyuncu" ve "savunma hattı hatası" sayıları gerçek doğruluğumuzu OLDUĞUNDAN
  KÖTÜ gösterir. Gündüz sütunu ve üçüncü saha paragrafı referans saha işaretlerine
  göre DÜZELTİLEREK yeniden hesaplandı (`gsr-corrected-telestration.json`); gece
  referansı düzeltilemedi (GSR görüntüsü panoramanın kırpımı değil), oradaki hat
  hatası ve takım rengi sayıları ham referansa aittir.
- Savunan takım üç karenin birinde hâlâ yanlış olabilir; çıktı bir ikinci göz olarak
  okunmalı, kesin hüküm olarak değil.
- Takipten çıkarılan pas listesi ham topla hesaplanır; top düzeltmesi yalnız kare
  konumlarına ve telestrasyona yansır.
- Ölçümler kendi ekibimizce yapıldı; ön kayıtlı kontroller sonuçtan önce commit
  edildi (ör. 7a577b2), ama bağımsız bir denetimden geçmedi.
