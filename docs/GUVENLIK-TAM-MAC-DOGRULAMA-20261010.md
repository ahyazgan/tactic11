# Güvenlik güncellemesi ve 90 dakikalık rapor doğrulaması

Tarih: 10 Ekim 2026. Kapsam: rapor arayüzü, bağımlılıklar ve uzun video
aktarımı. Dondurulmuş takip adayı, kaynak görüntüler ve canlı maç veritabanı
değiştirilmedi.

## Güncelleme

- Next.js 14.2.35 → 16.4.0; React / React DOM 18.3.1 → 19.3.0;
  React Konva 18.2.16 → 19.3.0. React 19 ref tipleri uyarlandı.
- Tailwind 3.4.19 → 4.3.3, PostCSS 8.5.29, tailwind-merge 3.7.0.
  Resmî Tailwind dönüşümüyle boyut/gölge/yuvarlama sınıfları taşındı.
  Tema değişkenleri CSS'e alındı; yerel IBM fontunun kendi değişken adı
  kullanılarak döngüsel font tanımı önlendi. PostCSS eklentisi yenilendi.
- Mevcut Webpack derleyicisi açıkça seçildi; yerel başlatıcı da aynı
  seçeneği kullanıyor. Typecheck önce Next rota tiplerini oluşturuyor.
- Kaldırılan `next lint` yerine ESLint çalışıyor. Yeni React Compiler ve
  mevcut metin uyarıları uyarı seviyesinde: 0 hata, 88 mevcut uyarı.
  Hooks sıralama kuralları hata seviyesinde; React Compiler etkin değil.
- CI, lint ve üretim bağımlılıkları için `npm audit --omit=dev
  --audit-level=moderate` çalıştırıyor. Kilit dosyası npm 12.2.0 ile üretildi;
  Linux x64 temiz kurulum çözümlemesi doğrulandı.

## Güvenlik kapsamı ve kalan bulgu

Önceki tam npm taraması: 19 bulgu (2 kritik, 15 yüksek, 2 orta).
Yeni üretim bağımlılıkları taraması: **0 bulgu**.
Yeni tam tarama: **5 yüksek**, tamamı geliştirme amaçlı aynı zincir:
`eslint-config-next → @next/eslint-plugin-next → fast-glob → micromatch → braces`.

`braces <=3.0.3` için [GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm)
yayımlanmış bir yama belirtmiyor. Bu tarama tamamen temiz değildir. Lint
yalnız depodaki dosya desenlerini işler; uygulama bu araca kullanıcı girdisi
iletmez. npm'in önerdiği eski Next lint paketine zorla dönüş uygulanmadı.
ESLint 9 son uyumlu ana sürümde tutuldu; ESLint 10 geçişi, Next lint
eklentilerinin peer uyumluluğu ile birlikte ayrıca ele alınmalıdır.

Resmî kaynaklar:

- [Next 16 geçiş kılavuzu](https://nextjs.org/docs/app/guides/upgrading/version-16)
- [Windows sunucularında RCE düzeltmesi](https://github.com/vercel/next.js/security/advisories/GHSA-p293-qw3h-jr36)
- [Rewrite SSRF düzeltmesi](https://github.com/vercel/next.js/security/advisories/GHSA-p9j2-gv94-2wf4)
- [Tailwind 4 geçişi](https://tailwindcss.com/docs/upgrade-guide)
- [React 19 geçişi](https://react.dev/blog/2024/04/25/react-19-upgrade-guide)

## Uzun yüklemede bulunan ve düzeltilen hata

410.355.419 baytlık denemede gerçek 120 istek/dakika sınırı devreye girdi.
tus-js-client 4.3.1, başarısız HEAD yanıtlarında yüklemeyi yeniden
oluşturabiliyordu: 239 MB ve 249 MB'de kalan iki ayrı geçici dosya oluştu.
İlk deneme 180 saniyede tamamlanamadı.

Yeni davranış:

- HEAD için yalnız kayıp/süresi dolmuş kayıt (404/410) yeniden oluşturulabilir.
- 401/429/503 gibi geçici durumlar aynı kimlik ve ofsetle yeniden denenir.
- `Retry-After` saniye/tarih değeri dikkate alınır; bekleme sırasında
  kullanıcıya otomatik devam edileceği gösterilir. Tus'un iptal edilebilir
  yeniden deneme zamanlayıcısı kullanılır.
- Yetki reddi (403) yeni bir yüklemeyle aşılmaz.
- Regresyon testi HEAD 429/401/503, PATCH 401, gerçek token yenileme,
  duraklatma/sayfa yenileme ve tek yükleme oluşturulduğunu doğrular.

## Tekrar üretme

İzole `review-e2e-*.db` veritabanı ve test API'si gerekir. Üretim verisi
üzerinde seed veya yük testi çalıştırılmamalıdır. Yerel test portları:
Next 3111 → API 8111; gerçek Next rewrite kullanılır.

```powershell
venv/Scripts/python.exe -m scripts.review_long_fixture `
  --source data/tracking/bench/daylight_117093/source/seg_0003.mp4 `
  --output .cache/review-e2e-90min-new.mp4
$env:E2E_BASE_URL='http://127.0.0.1:3111'
$env:E2E_REVIEW_BACKEND='true'
$env:E2E_REVIEW_LONG_MATCH='true'
$env:E2E_REVIEW_VIDEO='<yeni dosyanın mutlak yolu>'
# frontend dizininde:
npx playwright test e2e/match_reports.spec.ts --grep 'gerçek API:' --workers=1
```

Dosya: 5.400,08 saniye, 410.355.419 bayt, 640 piksel genişlik, 25 fps,
600 kbit/sn hedef, H.264. Aynı izinli 30 saniyelik geliştirme görüntüsü
tekrarlanır. Kaynak SHA-256:
`3e05ec8ef4f571e6cbbb20bf0922fc47334787993548ea9bcdc795ed751b149d`.
Deneme SHA-256:
`18b5393dd756be83da51fca01644f344e34ed3c64d814611b2a13f11cb41ce7b`.

Bu deney tek kullanıcı için uzun dosya yükleme, ileri sarma, seçili kareye
çizim, onaylı PDF ve iki kliplik çevrimdışı teslimi ölçer. Gerçek bir tam
maçta takip/oyuncu kimliği doğruluğunu, eşzamanlı kulüp kapasitesini, 2 GB
sınırını veya internet/Vercel aktarım performansını ölçmez. Analist onayı
gereken örnek metinler teknik deneme olarak açıkça işaretlidir.

## Sonuçlar

Gerçek istek sınırı etkin, tek kullanıcı, yerel Windows ve Next rewrite:

| Ölçüm | Sonuç |
| --- | --- |
| 410 MB yükleme; sunucunun bekleme süreleri dahil | 130,824 sn |
| 45. dakikaya atlama ve oynatma | 0,150 sn |
| 89:50'ye atlama ve oynatma | 0,158 sn |
| Çizimli PDF | 1,815 sn / 990.373 bayt |
| İki klip + çizim + PDF + çevrimdışı sayfa ZIP'i | 4,726 sn / 1.628.821 bayt |
| Kesilen zaman aralıkları | 44:59–45:02 ve 89:55–89:58 |

14 giriş/rapor/yükleme tarayıcı senaryosu ve ayrı uzun dosya senaryosu geçti.
Onay, kaydın yeniden açılması, çevrimdışı video/çizim gösterimi ve 390 px
mobil PDF indirme de bu uçtan uca senaryoya dahil. Next üretim derlemesi,
TypeScript, ESLint, yeni Python aracının Ruff/mypy kontrolleri geçti.

Yerel kanıt: `.cache/security-long-fixed-e2e/` altındaki `measurements.json`,
`report.pdf`, `delivery.zip`, ekran görüntüleri; `.cache/security-final-audit.json`
ve `.cache/security-production-audit.json`. İlk hatalı denemenin kayıtları
`.cache/security-long-e2e/` altında tutulur; yalnız onun iki yarım yüklemesi
izole test API'sinden iptal edilmiştir.
