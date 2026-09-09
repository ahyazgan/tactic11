# tactic11 — başlatıcılar

Beş dosyaya çift tıklayarak siteyi yönetirsin.

| Dosya | Ne yapar |
|---|---|
| **BASLAT.bat** | Siteyi açar (`npm run dev` de bunu çalıştırır). Kod değişmişse önce derler. |
| **DURDUR.bat** | Çalışan siteyi ve API'yi kapatır. |
| **DURUM.bat** | Ne çalışıyor, güncel mi, otomatik açılış kurulu mu — hepsini söyler. |
| **ACILISA-EKLE.bat** | Bilgisayar her açıldığında site hazır olsun. Bir kez tıklaman yeter. |
| **ACILISTAN-KALDIR.bat** | Otomatik açılışı geri alır. |

Adres: <http://localhost:3000> (eski yer imleri için `:3001` de çalışır).

## Nerede duruyorlar

Gerçek betikler **repoda**: `football-intelligence/launcher/`. Böylece
sürümleniyorlar ve satışta ürünle birlikte gidiyorlar.

Bir üst klasördeki (kurulum klasörü) aynı adlı dosyalar **yönlendiricidir** —
tek satır, buradaki gerçek dosyayı çağırır. `KUR.bat` onları üretir:

```
football-intelligence\launcher\KUR.bat          → bir üst klasöre kurar
football-intelligence\launcher\KUR.bat "D:\yol" → verilen klasöre kurar
```

Yol **kurulum anında gömülür**. Proje klasörünü taşırsan `KUR.bat`'ı yeniden
çalıştır. İki kopya tutmak yerine tek kaynak + ince yönlendirici: kopyalar
zamanla birbirinden ayrılır, yönlendirici ayrılamaz.

`SUNUCU.bat` ve `.ps1` yardımcıları yönlendirilmez — onlar iç dosyalardır,
doğrudan çalıştırılmaz.

---

## Neden gizli çalışıyor

Sunucu, başlattığın pencereden **bağımsız** çalışır: terminali ya da başlatıcı
penceresini kapatmak siteyi kapatmaz. Bu bilinçli bir tercih — koç maç günü
yanlışlıkla bir pencere kapattı diye sistem düşmemeli.

Bedeli: Görev Yöneticisi'nde yalnız `node.exe` / `python.exe` görürsün, hangisi
olduğu belli olmaz. Bu yüzden **DURDUR.bat** ve **DURUM.bat** var.

## Bayatlık koruması (2026-09-09'da eklendi)

**Yaşanan sorun:** Başlatıcı, 3000 portu dinleniyorsa hiç dokunmuyordu ve
yalnız `.next/BUILD_ID` *yoksa* derliyordu. Sonuç: kod değişse bile eski
derleme sunulmaya devam etti. Ölçüldü — hem site hem API **16 saat boyunca**
bir önceki günün kodunu sundu. `/video-tracking` 404, `/decisions/track` 500
veriyordu ve bunun sebebini anlamanın hiçbir yolu yoktu.

**Çözüm:** Her başlangıçta *kaynak dosyaların değişme zamanı* ile *derlemenin /
çalışan sürecin* zamanı karşılaştırılır. Kaynak daha yeniyse yeniden derlenip
başlatılır.

- Git commit'i değil **dosya zamanı** kullanılır: commit edilmemiş bir
  değişiklik de bayatlıktır, SHA onu kaçırır.
- `tsconfig.tsbuildinfo` bilerek kaynak sayılmaz — o bir derleme çıktısıdır;
  sayılsaydı her kontrol "bayat" der, sonsuz derleme olurdu.
- Backend derleme gerektirmediği için bayatsa koşulsuz yeniden başlatılır (ucuz).
- Kendin sormak için: `DURUM.bat`, ya da
  `powershell -ExecutionPolicy Bypass -File guncel-mi.ps1 -Bilesen frontend`
  (çıkış kodu: `0` güncel, `1` bayat, `2` bilinmiyor).

**Bunun anlamı:** Normal açılışta kaynak değişmediği için derleme yapılmaz,
site saniyeler içinde gelir. Sadece kod değiştiyse birkaç dakika derler.

Ölçülen süreler (2026-09-09, bu makine):

| Durum | Süre |
|---|---|
| Site zaten çalışıyor ve güncel | ~5 sn |
| Kapalıydı, derleme güncel | ~20 sn |
| Kod değişmiş — yeniden derleme | ~2 dk |
| Güncellik kontrolünün kendi maliyeti | 0,4 sn |

## `DURUM.bat` neden sayfa da açar

Port dinlemek yetmez. 2026-09-09 arızasında port gayet açıktı; sorun
`/video-tracking` sayfasının 404 vermesiydi. Bu yüzden `DURUM.bat` yalnız
porta bakmaz, gerçekten iki sayfa ister ve HTTP kodunu gösterir. Backend için
de aynısı: `/health` çağrılır, `db` durumu okunur.

## Taşınabilirlik

`ACILISA-EKLE.bat` artık hazır bir dosyayı Başlangıç klasörüne *kopyalamıyor*;
kurulum anındaki **gerçek proje yolunu** içine yazarak yeni bir kayıt
**üretiyor**. Öncesinde yol dosyanın içine sabit gömülüydü: proje klasörü
taşınırsa ya da başka bir bilgisayara kurulursa otomatik açılış sessizce
kırılıyordu — pencere gizli olduğu için hata bile görünmüyordu.

Başlangıç klasörünün yeri de sabit yazılmaz; OneDrive veya kurumsal profil
yönlendirmesi bu yolu değiştirebildiği için Windows'a sorulur.
`DURUM.bat`, kaydın hâlâ doğru klasörü gösterip göstermediğini denetler.

## Günlükler

Hepsi `football-intelligence/` kökünde, her biri tek bir işe bakar:

| Dosya | İçerik |
|---|---|
| `baslat-hata.log` | **Olay günlüğü** — ne zaman ne oldu. Önce buraya bak. |
| `derleme.log` | Son derlemenin çıktısı. |
| `sunucu-cikti.log` | Çalışan sunucunun kendi çıktısı. |
| `api.log` | Backend API çıktısı. |

Neden ayrı: hepsi tek dosyaya yazılırken `next start` o dosyayı **çalıştığı
sürece açık tutuyordu**; ikinci bir başlatma olay satırını yazamayıp
"dosya başka bir işlem tarafından kullanılıyor" hatası veriyor ve **satır
kayboluyordu** — tanı kaydı tam ihtiyaç anında eksiliyordu. Ölçüldü ve
düzeltildi (2026-09-09). Olay günlüğü artık her zaman yazılabilir.

## Sorun çıkarsa

- **Site açılmıyor** → `baslat-hata.log` son satırlar; oradan `derleme.log`.
- **API çalışmıyor** → `api.log`. Site yine açılır, demo veriye düşer — bu
  bilinçli: API opsiyoneldir.
- **Üst klasördeki kısayol çalışmıyor** → proje taşınmış olabilir;
  `launcher\KUR.bat`'ı yeniden çalıştır.
- **3000 portunu başka program tutuyor** → `BASLAT.bat` o programın adını ve
  PID'ini söyler ve derleme yapmaz.
- **Eski sayfayı görüyorum** → `DURUM.bat` çalıştır. "BAYAT" diyorsa
  `BASLAT.bat`; "güncel" diyorsa tarayıcı önbelleği (Ctrl+F5).

## Notlar

- `.bat` ve `.ps1` dosyaları **yalnız ASCII** içerir. Türkçe karakter ve uzun
  tire `cmd`'yi bozuyor; PowerShell 5.1 de BOM'suz `.ps1` dosyalarını ANSI
  okuduğu için çıktı bozuluyor.
- `-ExecutionPolicy Bypass` yalnız o sürece özeldir; **sistem güvenlik ayarını
  değiştirmez**.
- Gerçek geliştirme modu (hot reload) ayrı: `npm run gelistirme`.
