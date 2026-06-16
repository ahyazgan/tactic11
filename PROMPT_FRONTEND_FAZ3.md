# PROMPT — tactic11 Frontend Faz 3

> Faz 2 tamamlandıktan sonra çalıştırılır. Faz 2'nin teslimatına ek olarak
> bu turda **dayanıklılık + güvenlik + gözlem** katmanı eklenir. Yeni sayfa
> ya da yeni veri görünümü YOK; mevcut ekranların production-ready olması.
>
> Repo kökünde aç → içeriği bir Claude Code session'ına yapıştır.

-----

## Rol

`ahyazgan/tactic11` frontend mühendisisin. Stack: **Next.js 14 App Router
+ Tailwind + TypeScript**. Backend dokunulmaz.

## Mutlak kurallar

1. **DESIGN.md hâkim.** Yeni renk/token/komponent eklenmez; mevcut sistemden
   tüketilir. Faz 2 komponentleri (Panel, DataTable, Sparkline, ExplainPanel,
   StatTile, RatingBar, Pill, FormStrip) yeniden yazılmaz.
2. **Backend dokunma.** Sadece mevcut endpoint'leri tüket. Yeni endpoint
   gerekirse `AskUserQuestion` ile sor — sahte bypass yok.
3. **Yeni sayfa rotası yok.** Sadece mevcut sayfaları sertleştir, layout
   shell'i zenginleştir.
4. **Mock data yasak.** Veri yoksa empty state göster.
5. **Bağımlılık eklemek için gerekçe.** Bu fazda **Playwright** (E2E için)
   ve **idle-timer** (oturum süresi için) eklenmesi gerekçeli kabul. Başka
   yeni dep için sor.

## Görev — kesin teslimat

### A. Auth hardening (`frontend/src/lib/api.ts` + `auth.tsx`)

#### A1. Gerçek refresh flow

Şu an `lib/api.ts` 401'de `clearTokens() + redirect /login`. Bunu gerçek
refresh ile değiştir:

- 401 alındığında **önce** `POST /auth/refresh` çağrısı (refresh_token ile)
- Başarılı → yeni access_token sakla + orijinal isteği **bir kez** retry et
- Başarısız → mevcut flow (`clearTokens` + redirect)
- Aynı anda birden çok 401 gelirse **tek refresh kuyruğu** (race condition yok).
  Pattern: in-flight `refreshPromise` singleton; tüm isteklerin awaited.
- Refresh response: `{access_token, refresh_token}` (rotation — eski refresh revoke).

Test edilebilir senaryolar:
- Access token süresi dolmuş + refresh valid → otomatik yenilenir, kullanıcı görmez
- Refresh de invalid → login'e gider (mevcut flow)
- 3 paralel istek aynı anda 401 alır → 1 refresh çağrısı yapılır, hepsi retry edilir

#### A2. Idle logout

15 dakika kullanıcı etkileşimi yoksa otomatik logout:

- `useIdleTimer` hook'u (kendi yaz ya da `react-idle-timer` paketini gerekçeli
  ekle).
- 14 dk'da TopBar'da uyarı pill: `Pill variant="warn"` "1 dakikada otomatik
  çıkış".
- 15 dk'da `clearTokens()` + `/login` redirect.
- Hareketler: mousemove, keydown, click, scroll, touchstart.

#### A3. Role-based route guard

Faz 2'de `/admin` için yaptın — şimdi merkezi bir HOC veya middleware:

- `frontend/src/lib/auth.tsx` → `<RequireRole roles={['admin']}>` wrapper
- `viewer` rolü görmemesi gereken rotalar:
  - `/admin/*` (zaten gizli)
  - `/decisions` (TD-only)
  - `/players/[id]/tactical` (analyst+)
- Sayfanın en üstünde wrapper kullanılır; rolünü `/auth/me`'den SWR ile çek
  (cache 5 dk).
- Yetkisiz → `/` redirect + TopBar'da 3 sn flash mesaj "Bu sayfaya erişimin
  yok".

### B. Resilience

#### B1. WebSocket auto-reconnect

`frontend/src/app/matches/[id]/live/page.tsx` şu an WebSocket bağlanır;
bağlantı koptuğunda ne yapıyor? Şimdi sertleştir:

- `onclose` handler'a exponential backoff reconnect (2s, 4s, 8s, max 30s, max 10
  deneme).
- Connection state'i 4 değer: `connecting | open | reconnecting | closed`.
- TopBar'da değil sayfa içinde küçük status badge (`Pill`):
  - open → win
  - reconnecting → warn (sayaç: "5 sn sonra tekrar denenecek")
  - closed → danger (manuel "Yeniden bağlan" butonu)
- Reconnect başarılıysa snapshot history korunur; sayfa yeniden render etmez.

#### B2. Offline detection

Tarayıcı offline event'leriyle banner:

- `window.addEventListener('offline')` → TopBar altına strip:
  `bg-danger/20 text-danger text-[11px] text-center py-1`:
  "Çevrimdışı — gösterilen veriler güncel olmayabilir"
- `online` event'inde banner kaybolur + SWR `mutate()` ile aktif tüm
  istekler revalidate.

#### B3. SWR error retry tuning

`lib/api.ts`'te SWR config global:

- `errorRetryCount: 3`
- `errorRetryInterval: 2000` (linear, exponential değil)
- 5xx için retry, 4xx için no retry (kullanıcı hatası).
- `focus revalidation` açık (default).
- `refreshInterval` ekran-bazlı override (tactical: 0, live: WebSocket
  zaten halleder, halftime: 60sn).

### C. Observability in UI

#### C1. Kota uyarı badge (TopBar)

- TopBar'da sağda, kullanıcı email'inin yanında `Pill` (sadece varsa):
- `/admin/usage` SWR ile 60 sn'de bir poll (yalnızca admin/analyst için —
  viewer'a görünmez).
- Eşik: kullanım/limit ≥ 0.80 → `Pill variant="warn"` "Kota %X"
- ≥ 0.95 → `Pill variant="danger"` "Kota %X — duracak"
- < 0.80 → gizli.

#### C2. Last-sync timestamp (Sidebar footer)

- Sidebar'ın altına `text-[10px] text-textdim`:
  - "Son sync: 2 dk önce" (göreceli)
  - `/admin/jobs` SWR ile son başarılı `sync_league` job'ının `ended_at`'i
- Tıklanınca `/admin/jobs`'a navigate.

#### C3. Build version footer

- Sidebar'ın en altında en küçük yazı:
  `"v" + process.env.NEXT_PUBLIC_BUILD_SHA?.slice(0,7) ?? "dev"`
- `next.config.js`'e ekle: build sırasında `process.env.GITHUB_SHA` (veya
  `git rev-parse HEAD`) → `NEXT_PUBLIC_BUILD_SHA`.

### D. E2E smoke tests (Playwright)

`frontend/package.json`'a `@playwright/test` ekle. `frontend/e2e/` klasörü:

- `playwright.config.ts`: baseURL `http://localhost:3000`, single project
  (Chromium), retries 1, fully parallel.
- 5 senaryo:

#### D1. `login.spec.ts`

- Geçersiz şifre → error mesajı görünür, hala `/login`'de
- Geçerli login → `/` redirect, TopBar'da email görünür
- Logout → token'lar temizlenir, `/login`'e döner

#### D2. `leagues_navigation.spec.ts`

- Login → sidebar'da "Ligler" → `/leagues` → DataTable görünür
- Bir lig tıkla → `/leagues/[id]/teams` → takım listesi
- Bir takım tıkla → `/teams/[id]` → form/rating görünür

#### D3. `halftime_brief.spec.ts`

- Login → `/matches/16029/halftime?my_team_id=217`
- "1. Yarı Sayılar" başlığı görünür
- "Açıkla" butonuna tıkla → ExplainPanel açılır
- (LLM stub mode olduğu için brief sahte içerik olabilir; sadece panel
  açılma test edilir)

#### D4. `live_ws.spec.ts`

- Login → `/matches/16029/live?my_team_id=217&interval_seconds=5&max_minute=10`
- 15 sn bekle → status badge "open"
- En az 2 snapshot history kaydı olmalı (counter ≥ 2)
- WebSocket'i tarayıcı düzeyinde kapat (server stop simulate edilemez burada
  — bunu skip et veya manuel test notuyla bırak)

#### D5. `decision_log.spec.ts`

- Login → `/matches/16029/live?...`
- DecisionPanel'de form'u doldur (substitution, player 100 → 200)
- "Kaydet" tıkla → "Bu oturumda 1 karar kaydedildi" mesajı görünür
- `/admin/matches/16029/decisions` listesinde yeni satır olduğunu
  `apiFetch` ile doğrula

#### D6. CI

`.github/workflows/frontend-e2e.yml` ekle:
- Backend test job'ından sonra çalışır
- `cd frontend && npm ci && npx playwright install --with-deps chromium`
- Backend'i `python -m uvicorn app.api.main:app --port 8000` ile start
- `npm run dev -- --port 3000` ile frontend start
- `npx playwright test`
- Artifacts: screenshot + trace failure'da

## Kabul kriterleri

- [ ] `npm run typecheck`, `npm run build` hatasız
- [ ] `npx playwright test` lokal'de 5/5 yeşil (D4 hariç — skip OK)
- [ ] Access token expire et (manuel: localStorage'dan sil access_token,
      bir API çağrısı yap) → refresh ile şeffaf yenilenir
- [ ] WebSocket'i devtools'ta öldür → status "reconnecting" → backoff sonrası
      "open"
- [ ] DevTools network throttle "Offline" → banner görünür → "Online" → banner
      kaybolur
- [ ] Viewer rolü ile `/admin` URL'ine git → `/`'e redirect + flash mesaj
- [ ] Kota %85'e çekilse (manuel: `/admin/usage` mock) → TopBar warn pill
- [ ] CI workflow yeşil (backend + frontend E2E)

## Çıktı sırası

1. Faz 2'nin teslimatını taramayla doğrula (bütün referans dosyalar var mı)
2. Yeni dosya listesi + değişen dosya listesi
3. **Implement**: A (auth) → B (resilience) → C (observability) → D (E2E)
4. Her bölüm sonrası `npm run typecheck` pass kontrol
5. **Belirsizlikte** AskUserQuestion. Sessiz uydurmak yasak.

## Anti-pattern

- Refresh için manuel polling (token expire kontrolü) — interceptor pattern
  şart.
- Idle logout sırasında zorla `window.location` — Next.js router kullan.
- SWR config'i sayfa-bazlı override (global olmalı, override sadece gerekli
  sayfada).
- WebSocket reconnect'te sonsuz deneme — max 10 + manuel reconnect butonu.
- E2E'de `sleep(N)` — Playwright'in built-in `waitFor` API'sini kullan.
- Build SHA olmadan production'a çıkmak.
- Role-based gizlemeyi sadece UI'da yapmak (backend zaten 403 atıyor; UI
  guard kullanıcı deneyimi için, güvenlik için değil).

-----

## Faz 4+ için ileriye notlar (bu turda YAPILMAZ)

- Internationalization (i18n) — en/tr toggle
- Virtualization (`react-window`) — 1000+ satırlı tablolarda
- Accessibility audit (axe-core + Lighthouse CI)
- Dark/light theme toggle (şu an dark-only)
- Push notification permission UX iyileştirmesi (modal ile sor, sessizce
  değil)
- Service worker / PWA — touch-line tablet offline-first

Bu Faz 3 prompt'u toplam **~6-8 saatlik agent işi**. Faz 2'den sonra
çalıştırılır. Backend kontratı değişmez; 835 test korunur.
