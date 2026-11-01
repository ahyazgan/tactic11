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

Ölçüm: SoccerTrack v2 117092 (gece maçı, 4K sabit panorama), v2 dedektörü,
1800–2400 sn ön kayıtlı kontrol penceresi (20 segment, 7500 kare); referans GSR
oyuncu konumları ve olay kayıtları.

| Çıktı | Ölçülen | Not |
|---|---|---|
| Hangi takım savunuyor (çizilen karelerde) | %68,1 doğru | önceki top seçimiyle %46,1 |
| Blok etiketi (alçak/orta/yüksek), uçtan uca | dengeli doğruluk %63,7, tam isabet %67,6 | sahiplik dahil zincirin tamamı |
| Çizim kapsaması | karelerin %86'sında çizim var | kalanında savunandan < 6 oyuncu görünür |
| Pres işareti uyumu | %96,7 | referansla aynı karar |
| Oyuncu takım rengi | eşleşen oyuncuların %76'sı doğru takımda | |
| Top, dokunuş anında 5 m içinde | %19,1 | çoğunlukla ayak dibindeki top bulunamıyor |
| Top, pas uçuşunda 5 m içinde | %50 | 42 kısa pas |

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

- Tek maç (gece), tek kamera tipi. Gündüz ve başka stadyumlarda ölçülmedi.
- Savunan takım üç karenin birinde hâlâ yanlış olabilir; çıktı bir ikinci göz olarak
  okunmalı, kesin hüküm olarak değil.
- Takipten çıkarılan pas listesi ham topla hesaplanır; top düzeltmesi yalnız kare
  konumlarına ve telestrasyona yansır.
- Ölçümler kendi ekibimizce yapıldı; ön kayıtlı kontroller sonuçtan önce commit
  edildi (ör. 7a577b2), ama bağımsız bir denetimden geçmedi.
