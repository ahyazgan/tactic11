# Video takip ve otomatik telestrasyon: doğruluk karnesi (2026-11-01)

Kulübe "bu ne kadar güvenilir?" sorusunun cevabı. Her satır ölçülmüş bir sayıdır;
nasıl ölçüldüğü ve tekrar üretimi bağlantılı belgede. Ölçülmemiş olan "ölçülmedi"
diye yazılır.

## Ne gerekiyor

- **Sabit kamera** (stadyum çatısı, direk ya da panorama). Telestrasyon TV yayınında
  çalışmaz; yayında yalnız takip var (`docs/CANLI-MOD-KILAVUZU.md`).
- **Saha kalibrasyonu**: stadyum başına bir kez, en az 5 saha işareti; bağımsız
  doğrulama hatası ≤ 2,0 m olmazsa çizgi ve etiket çizilmez.
- **GPU**: ölçümler RTX 5060 (8 GB) dizüstünde.

## Koçun gördüğü çıktılar

İki maç, ikisi de ön kayıtlı ve sistemin karar verirken görmediği 10'ar dakika:
**gece** SoccerTrack v2 117092 (1800–2400 sn, 7500 kare) ve **gündüz** 132877
(600–1200 sn, hiç kullanılmamış test maçı). Referans olay kayıtları; gecede GSR
oyuncu konumları da.

| Çıktı | Gece (117092) | Gündüz (132877) | Not |
|---|---|---|---|
| Hangi takım savunuyor (çizilen karelerde) | %68,1 | %81,3 | gece önceki top seçimiyle %46,1 |
| Blok etiketi (alçak/orta/yüksek), uçtan uca | dengeli %63,7, tam isabet %67,6 | ölçülmedi | gündüz GSR yok |
| Çizim kapsaması | %86 | %100 | gece kalanında savunandan < 6 oyuncu görünür |
| Pres işareti uyumu | %96,7 | ölçülmedi | |
| Oyuncu takım rengi | %76 | ölçülmedi | |
| Top, dokunuş anında 5 m içinde | %19,1 | %73,2 | gece ayak dibindeki top çoğunlukla bulunamıyor |
| Top, pas uçuşunda 5 m içinde | %50 (42 pas) | %91,1 (79 pas) | |

Gündüz ve aydınlık sahada sistem belirgin biçimde daha güvenilir; gece ışıklarla
sahte top adayları en zor durum.

**Başka stadyum (132831, gündüz, ön kayıtlı, sınav geçmedi):** top dokunuşta %42,2,
pas uçuşunda %71,4 doğru yerde. Takım ataması net renkli oyuncularda %97 doğru,
ama güneşte beyaza dönen uzak oyuncular sistematik olarak tek takıma yazılıyor
(göz etiketli ölçüm, `docs/TAKIM-AYRIMI-GUNES.md`); savunan takım bu sahada olay
kayıtlarıyla ölçülemedi. Ayrıntı: `docs/TOP-TESPITI-OLAY-OLCUMU.md` §6.

Kaynaklar: `docs/TOP-TESPITI-OLAY-OLCUMU.md` (ön kayıt + kontrol),
`docs/measurements/ball-track-control.json`, `docs/OTOMATIK-TELESTRASYON.md`,
`docs/DEDEKTOR-INCE-AYAR-SONUCLARI.md`.

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
  başka bir stadyum (132831), takım ayrımında başarısız oldu.
- Savunan takım üç karenin birinde hâlâ yanlış olabilir; çıktı bir ikinci göz olarak
  okunmalı, kesin hüküm olarak değil.
- Takipten çıkarılan pas listesi ham topla hesaplanır; top düzeltmesi yalnız kare
  konumlarına ve telestrasyona yansır.
- Ölçümler kendi ekibimizce yapıldı; ön kayıtlı kontroller sonuçtan önce commit
  edildi (ör. 7a577b2), ama bağımsız bir denetimden geçmedi.
