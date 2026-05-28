# PROMPT — manager2 Frontend Faz 2

> Bu dosya Claude Code (veya başka bir agent) için **tek seferlik talimat**dır.
> Repo kökünde aç, içeriği bir Claude Code session'ına yapıştır. Beklenen
> sonuç: 4 komponent + 4 sayfa + layout shell, **mevcut yapı kırılmadan**.

-----

## Rol

Sen `ahyazgan/manager2` reposunda çalışan senior frontend mühendisisin.
Stack: **Next.js 14 App Router + Tailwind + TypeScript**. Backend FastAPI
(Python). Sen sadece `frontend/` katmanına dokunursun; backend kontratı
**dokunulmaz**.

## Mutlak kurallar

1. **`DESIGN.md`'yi oku, kurallarına harfiyen uy.** Renk, tipografi, layout,
   komponent spesifikasyonları orada. Inline hex, inline tablo markup,
   sayfaya özel renk **yasak**. Token kullan: `bg-surface`, `text-textmut`,
   `border-border`, `bg-win/15` vb.
2. **Mevcut komponentleri yeniden yazma.** Şunlar zaten var, kullan:
   - `@/components/ui` → `Panel`, `Pill`, `ResultDot`, `FormStrip`, `RatingBar`
   - `@/lib/cn` → `cn()` className merge
   - `@/lib/rating` → `ratingColor(value)`, `normalize10to100(value)`
   - `@/lib/format` → `ppg`, `goalDiff`, `pct`, `minute`
   - `@/lib/api` → `apiFetch<T>()`, `login()`, `getAccessToken()`, `clearTokens()`
3. **Mevcut sayfaları kırma.** Şu sayfalar canlı ve çalışıyor; sadece
   DESIGN.md token'larına geçir (minimal refactor), JSX yapısını bozma:
   - `/login`, `/matches`, `/matches/[id]`, `/teams/[id]`, `/calibration`,
     `/decisions`, `/chat`, `/teams/[id]/tactical`, `/players/[id]/tactical`,
     `/matches/[id]/halftime`, `/matches/[id]/live`, `/teams/[id]/trend`
4. **Backend kontratını değiştirme.** Sadece mevcut endpoint'leri tüket.
5. **Eksik veri uydurma.** Endpoint yoksa veya schema belirsizse `AskUserQuestion`
   ile sor; mock data ile sahte UI yapma.
6. **Bağımlılık ekleme.** `package.json`'da olan paketler yeterli (`next`,
   `react`, `swr`, `recharts`, `clsx`, `tailwind-merge`, `lucide-react`).
   Yenisi gerekirse gerekçe yaz.

## Tüketilecek backend endpoint'leri (auth: `Authorization: Bearer <JWT>`)

```
POST  /auth/login      {email, password, tenant_slug}
POST  /auth/refresh
POST  /auth/logout
GET   /auth/me                                 → {email, tenant_id, role}

GET   /leagues                                 → liste
GET   /teams/{league_id}                       → ligdeki takımlar
GET   /teams/{team_id}/matches                 → maç listesi
GET   /teams/{team_id}/form?last_n=N&explain   → form raporu (+Claude yorum)
GET   /teams/{team_id}/rating?last_n=N&explain → rating
GET   /teams/{a}/vs/{b}?explain                → H2H

GET   /matches/{match_id}/preview?last_n=N     → maç önizleme

GET   /admin/jobs                              → job geçmişi
GET   /admin/usage                             → API kullanımı
GET   /admin/db-stats                          → satır sayıları
GET   /admin/snapshots                         → snapshot listesi
GET   /admin/snapshots/diff                    → snapshot fark
```

`explain=true` paramı pahalı (LLM + kota) — **daima lazy + cache**.

## Görev — kesin teslimat

### A. Layout shell (`frontend/src/app/layout.tsx`)

Mevcut layout'a **sidebar + topbar** ekle:

- TopBar (`h-12 bg-surface border-b border-border`):
  - Sol: tenant slug + sezon `<select>` (UI bileşeni; sezon listesi sabit
    `[2024, 2023]` bugünlük — gelecekte `/leagues`'ten çıkartılır)
  - Sağ: `/auth/me`'den email + role pill + logout butonu
  - Kullanıcı giriş yapmamışsa TopBar gizli
- Sidebar (`w-56 bg-surface border-r border-border`, sayfa boyu sticky):
  - Nav grupları: **Ligler · Takımlar · H2H · Maçlar · Canlı · Admin**
  - Aktif item: `bg-surface2 text-text border-l-2 border-accent`
  - Pasif item: `text-textmut hover:text-text hover:bg-surface2`
  - **Admin sadece `role==='admin'`** için görünür
  - Bunun altı: küçük "DESIGN.md • v1" footer
- İçerik: `pl-56 pt-12 p-4 bg-bg` — full-bleed (max-w yok).

`/login` sayfası shell'in dışında kalmalı (layout login'i sarmasın ya da
shell sadece `pathname !== "/login"` için render etsin).

### B. 4 reusable komponent

Hepsi `frontend/src/components/ui/` altına; `index.ts`'e re-export ekle.

#### B1. `Table` / `DataTable` (`table.tsx`)

DESIGN.md §4.Table.

```ts
type Column<T> = {
  key: keyof T | string;
  header: string;
  align?: "left" | "right" | "center";
  sortable?: boolean;
  render?: (row: T) => React.ReactNode;
  width?: string;
};

<DataTable
  columns={cols}
  rows={data}
  rowKey={(r) => r.id}
  selectedKey?
  onRowClick?
/>
```

- Satır `h-7`, hücre `px-2 text-[12px]`. Zebra: tek `bg-surface`, çift `bg-surface2`.
- Hover `hover:bg-elevated`. Seçili `bg-accent/15 border-l-2 border-accent`.
- Header sticky `top-0 bg-surface border-b border-border text-[11px] uppercase
  tracking-wide text-textmut`. Tıklanınca sort indicator (▲▼).
- Sayısal kolon (`align="right"`) → `text-right tabular-nums`.

#### B2. `Sparkline` (`sparkline.tsx`)

DESIGN.md §4.Sparkline.

```ts
<Sparkline data={[1, 1.2, 0.9, 1.4]} width={64} height={18} color?={string} />
```

- SVG polyline. Eksen/grid YOK. Son nokta `<circle r="2">` vurgulu.
- Color verilmezse yön tabanlı: `data[last] > data[0]` → `win`, `<` → `loss`,
  eşit → `textmut`.

#### B3. `ExplainPanel` + `ExplainButton` (`explain-panel.tsx`)

DESIGN.md §4.ExplainPanel.

```ts
<ExplainButton onClick={open} loading={loading} />
<ExplainPanel
  open={open}
  onClose={...}
  fetchExplain={() => apiFetch(`/teams/${id}/form?last_n=5&explain=true`)}
/>
```

- Sağdan slide-in panel (`fixed right-0 top-12 w-80 h-[calc(100vh-3rem)]
  bg-elevated border-l border-border z-50`).
- İçerik: Claude yorumu `text-[13px] prose` + altta collapsible "audit gerekçesi"
  (`text-[11px] text-textmut`).
- **Lazy**: `open=true` olunca ilk fetch, sonuç state'te cache.
- 4 state: loading (skeleton), error (text-danger + retry), empty, data.

#### B4. `StatTile` (`stat-tile.tsx`)

DESIGN.md §4.StatTile.

```ts
<StatTile
  label="PPG"
  value="2.14"
  delta="+0.3"   // opsiyonel; pozitif win, negatif loss renkte
  sparkData?={number[]}
/>
```

- `bg-surface border border-border rounded-md p-3`.
- Label `text-[10px] uppercase tracking-wider text-textdim`.
- Value `text-xl font-semibold tabular-nums text-text`.
- Delta `text-[11px] tabular-nums` + win/loss renk.
- Sparkline varsa label'ın sağında küçük (`w-16 h-4`).

### C. 4 eksik sayfa

#### C1. `/leagues` (`app/leagues/page.tsx`)

- `GET /leagues` çağrısı.
- DataTable: kolonlar `code`, `name`, `season` (varsa), `team_count` (eğer
  endpoint vermiyorsa kolonu gösterme — uydurma!).
- Satır tıklanınca `/leagues/[id]/teams`'e navigate.
- Empty state: "Henüz lig sync edilmemiş."

#### C2. `/leagues/[id]/teams` (`app/leagues/[id]/teams/page.tsx`)

- `GET /teams/{league_id}` çağrısı.
- Breadcrumb: `Ligler / {league.name} / Takımlar`.
- DataTable: `external_id`, `name`, opsiyonel ek metric (eğer API döndürürse:
  `wins`, `draws`, `losses`, `ppg`, `rating`). Eksik alanları **gösterme**.
- Sortable kolonlar (DataTable native).
- Satır tıklanınca `/teams/[id]` (mevcut detay sayfası).

#### C3. `/h2h` (`app/h2h/page.tsx`)

- İki adet team selector (önce `/leagues` listesinden, sonra her lig için
  `/teams/{league_id}`). SWR ile.
- "Karşılaştır" butonuna basınca `GET /teams/{a}/vs/{b}` çağrı.
- Yan yana iki StatTile sütunu (Takım A | Takım B):
  - W/D/L (FormStrip ile)
  - PPG, gol farkı (StatTile)
  - Rating (RatingBar)
- Altta DataTable: geçmiş karşılaşmalar (response'tan gelen matches[] varsa).
- "Açıkla" butonu → ExplainPanel ile `?explain=true` çağrısı.

#### C4. `/admin` (`app/admin/page.tsx`)

- **Route guard**: `/auth/me`'den `role !== 'admin'` ise `/` redirect.
- 3 Panel:
  - **Jobs** (`/admin/jobs`): DataTable `started_at`, `job_name`, `status`
    (Pill ile: success/failed/running), `attempts`, `error`. Failed satırlar
    `text-danger` ekstra vurgu.
  - **API usage** (`/admin/usage`): bugünkü call/token sayaçları StatTile + 
    kotaya yaklaşma uyarısı (eşik %80 → warn Pill).
  - **DB stats** (`/admin/db-stats`): kompakt 2-kolon grid (label + sayı).

### D. Mevcut sayfa minimal refactor

Aşağıdaki sayfalarda **JSX yapısını bozma**, sadece:
- `bg-panel` → `bg-surface`
- `text-fg` → `text-text`
- `text-muted` → `text-textmut`
- `bg-good` → `bg-win`, `bg-bad` → `bg-loss`
- `.card` class kullanan div'leri `<Panel>` ile sar (header yoksa
  `<Panel>{children}</Panel>` formu)

Dosyalar: `/login/page.tsx`, `/matches/page.tsx`, `/teams/[id]/page.tsx`,
`/calibration/page.tsx`, `/decisions/page.tsx`, `/chat/page.tsx`,
`/teams/[id]/tactical/page.tsx`, `/players/[id]/tactical/page.tsx`,
`/matches/[id]/halftime/page.tsx`, `/matches/[id]/live/page.tsx`,
`/teams/[id]/trend/page.tsx`.

Form/ResultDot render eden inline div'leri **`ResultDot`/`FormStrip`** ile
değiştir.

## Kabul kriterleri

Bitirdiğinde şunlar çalışmalı:

- [ ] `npm run typecheck` (frontend/) hatasız geçer
- [ ] `npm run build` (frontend/) hatasız geçer
- [ ] Login → sidebar görünür → `/leagues` → lig tıkla → takım listesi →
      takım tıkla → mevcut detay sayfası çalışır
- [ ] `role!=='admin'` user `/admin` URL'i yazınca `/`'e redirect olur
- [ ] H2H sayfasında iki takım seçimi + explain panel açma sorunsuz
- [ ] Mevcut tactical/halftime/live/trend sayfaları DESIGN.md token'larıyla
      görsel olarak tutarlı (renk farkı yok, font yoğunluğu eşit)
- [ ] DataTable hover/select/sort hepsi etkileşimde
- [ ] `git diff frontend/` ~3000-5000 satır arasında (over-engineer yok)

## Çıktı sırası

1. **Önce** `frontend/` mevcut yapısını incele ve özetle (hangi sayfalar var,
   hangi pattern'lar kullanılmış)
2. **Sonra** eklenecek dosya listesini ver (komponent ağacı + sayfa rotası)
3. **Implement et** — sıra: layout shell → 4 komponent → 4 sayfa → minimal
   refactor
4. **Her ekran için** "nasıl test edilir" notu (URL + beklenen davranış)
5. **Belirsizlikte** `AskUserQuestion` — uydurma

## Anti-pattern (DESIGN.md §6 + ek)

- Açık tema, beyaz zemin, pastel
- Büyük hero, dekoratif gradient
- Inline `<table>` markup veya inline hex
- 13px üstü tablo metni
- `explain` otomatik tetikleme
- Sayfa-spesifik renk token'ı
- `useEffect` içinde fetch döngüsü — SWR kullan
- "Test için" mock data — boş state göster

-----

## Notlar (referans için)

- Backend kontratı 835 backend test ile korunuyor; sen frontend yazarken
  tipler için `app/api/schemas.py`'den TypeScript karşılığını manuel yaz.
- Mevcut `apiFetch` 401'de `/login`'e atıyor; tekrar yazma.
- Token'lar `localStorage`'da (`manager2_access_token`, `manager2_refresh_token`).
- Refresh flow `lib/api.ts`'te şu an stub — production'da gelecek (Faz 3).
- `tailwind.config.ts`'te DESIGN.md tokenları + legacy alias'lar var; legacy
  alias'lara dokunma (mevcut sayfalar bozulur).

İyi çalışmalar.
