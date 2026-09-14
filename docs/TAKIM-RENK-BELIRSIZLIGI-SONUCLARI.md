# Tek forma renginden iki takım çıkarılmasını önleme

14 Eylül 2026, başlangıç `937c31b`, dal `codex-work`.

Kamera takım atamasındaki tek renk uç durumu düzeltildi. Mevcut SoccerTrack
kontrolünde doğruluk **%81,11 olarak kaldı**; bu çalışma genel oyuncu kimliği
veya takım doğruluğunda artış göstermiyor.

## Hata ve davranış

`k=2` kümeleme, görüntüde tek forma rengi varken de iki merkez döndürüyordu.
İki aynı renkli takip veya sekiz aynı renkli takip, bir takım kesin biliniyormuş
gibi etiketleniyordu. Küçük parlaklık farkları eklendiğinde aynı forma iki
takıma bölünüyordu. Canlı işçi de bu geçersiz renkleri ilk çapa olarak tüm
maç boyunca saklayabiliyordu.

Artık iki dolu küme yoksa veya merkezlerin Öklid RGB uzaklığı 30'dan büyük
değilse takiplerin takımı belirsiz kalır. 30, mevcut RGB aykırılık filtresindeki
alt toleranstır; bu görevde yeni bir kontrol verisi taramasıyla seçilmedi.
Bu toleransın iki farklı formanın ayrımı için genel geçerliliği kanıtlanmadı.
Birbirine yakın gerçek forma renklerinde kullanılabilir atamalar da kaybolabilir.

Belirsiz sonucun renkleri sıfır olarak döner ve neden video kalite özetine
yazılır. Canlı işçi ayrı renkleri bekler; daha önce edinilmiş geçerli çapayı
belirsiz bir segmentle değiştirmez. Ölçüm aracı da aynı çapa kuralını kullanır
ve `--development-only` ile kontrol metriklerini hesaplamadan çalışabilir.

## Aynı kayıt üzerinde karşılaştırma

Geliştirme: 600–630 ve 690–720 sn; kontrol: 780–810 ve 870–900 sn.
1500 önbelleklenmiş takip örneği, her 10. örnekte 3 m içinde birebir GT eşleme.
Önceden sabitlenen +9 kare hizalaması korundu. Önce geliştirme, sonra kontrol
çalıştırıldı; sonuç görüldükten sonra eşik değiştirilmedi.

| Gözlem | Önce | Sonra |
|---|---:|---:|
| Geliştirme doğru / yanlış / belirsiz | 350 / 58 / 17 | 350 / 58 / 17 |
| Kontrol doğru / yanlış / belirsiz | 511 / 119 / 16 | 511 / 119 / 16 |
| Kontrol atanmış gözlemlerde doğruluk | %81,11 | %81,11 |
| Kontrol bir takımda 12+ kişi oranı | %36,40 | %36,40 |

Bu dört segmentte korumayı gerektiren renk çökmesi yok; doğru atama kaybı da
yok. Kalan 119 yanlış gözlem çözülmedi. Bunlar konumsal eşleşmeye koşullu
ölçümlerdir; gerçek oyuncu adı/kimliği veya bağımsız kalibrasyon doğruluğu değildir.
Yalnız bir takımın görüldüğü geniş parlaklık değişimleri bu korumayı aşabilir.

Makine raporu ve altı girdi dosyasının SHA-256 değerleri:
[team-palette-2026-09-14.json](measurements/team-palette-2026-09-14.json).

## Regresyon kanıtı ve tekrar

Yeni yedi test durumunun altısı eski kodda başarısız oldu; sıfır paletle canlı
başlangıç senaryosu zaten geçiyordu. Düzeltme sonrası yedisi de geçti.
İlgili video/canlı dosyalarında toplam **44 test geçti**.
Tam proje koşusu: **2529 geçti, 1 atlandı, 15 mevcut uyarı** (262,91 sn).
Ruff temiz; mypy 490 kaynak dosyasında hatasız. Test veritabanı izole SQLite.

```powershell
.\venv\Scripts\python.exe -m scripts.soccertrack_v2.evaluate_teams --cache data/tracking/bench/signal_quality_v1 --gt data/tracking/bench/signal_quality_gt.npy --alignment data/tracking/bench/signal_quality_alignment.json --out data/tracking/bench/palette_recheck_dev.json --development-only
.\venv\Scripts\python.exe -m scripts.soccertrack_v2.evaluate_teams --cache data/tracking/bench/signal_quality_v1 --gt data/tracking/bench/signal_quality_gt.npy --alignment data/tracking/bench/signal_quality_alignment.json --out data/tracking/bench/palette_recheck_all.json
```

Önce ölçümünü yeniden üretmek için `937c31b` kodunu ayrı bir checkout'ta aynı
girdi dosyalarıyla çalıştırın; `--baseline` daha eski kısa-takip/renk filtresini
temsil eder, bu düzeltmenin öncesini temsil etmez.
