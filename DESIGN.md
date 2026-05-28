# DESIGN.md — football-intelligence frontend tasarım sistemi

> Bu dosya tek doğruluk kaynağıdır. Yeni sayfa/komponent yazarken veya
> mevcutları refactor ederken buradaki token, renk ve komponentleri kullan.
> Inline stil veya sayfaya özel renk **yasak** — her şey buradaki Tailwind
> utility'leri ve reusable komponentler üzerinden.

Stack: **Next.js 14 App Router + Tailwind CSS + TypeScript**.
Estetik hedefi: **Football Manager 2010–2015** — koyu, veri-yoğun, masaüstü-öncelikli,
süssüz. Boşluk değil bilgi yoğunluğu; her piksel veri taşır.

-----

## 1. Renk paleti (hex)

Tailwind `tailwind.config.ts` → `theme.extend.colors` altına ekle. Hardcode hex kullanma, token adıyla çağır.

```ts
colors: {
  // Zeminler (koyu → açık)
  bg:        '#14171c',  // sayfa zemini
  surface:   '#1a1d24',  // kart / panel zemini
  surface2:  '#21252e',  // iç panel, hover öncesi
  elevated:  '#272c37',  // dropdown, modal, tooltip
  // Çizgiler
  border:    '#2c3038',  // varsayılan ayraç
  borderlt:  '#3a3f4a',  // vurgulu ayraç / focus ring öncesi
  // Metin
  text:      '#e4e7ec',  // birincil
  textmut:   '#9aa1ad',  // ikincil / label
  textdim:   '#6b7280',  // üçüncül / disabled
  // Marka / aksiyon
  accent:    '#3d7eff',  // birincil aksiyon, link, seçili satır
  accenthov: '#5a92ff',
  // Durum
  win:       '#3fb950',  // W
  draw:      '#d4a72c',  // D
  loss:      '#e5534b',  // L
  warn:      '#d4a72c',  // kota uyarısı
  danger:    '#e5534b',  // failed job, hata
  ok:        '#3fb950',
}
```

### Rating gradyanı (kırmızı → sarı → yeşil)

Sayısal rating'i (0–100 veya 0–10 normalize) renge map'le. 5 durak:

| Aralık (0–100) | Renk       | Hex       |
|----------------|------------|-----------|
| 0–39           | loss       | `#e5534b` |
| 40–54          | turuncu    | `#d97742` |
| 55–69          | draw       | `#d4a72c` |
| 70–84          | açık yeşil | `#7bc96f` |
| 85–100         | win        | `#3fb950` |

`ratingColor(value: number): string` util'i `lib/rating.ts` içinde tek yerde tanımlanır.

-----

## 2. Tipografi

- Font: sistem sans (`ui-sans-serif, system-ui`) — süs yok. İstersen `Inter`.
- Sayısal kolonlar (ppg, gd, rating): `font-variant-numeric: tabular-nums` (Tailwind `tabular-nums`).

| Rol             | Boyut / satır | Tailwind                                            |
|-----------------|---------------|-----------------------------------------------------|
| Tablo hücresi   | 12px / 16     | `text-[12px] leading-4`                             |
| Tablo başlığı   | 11px / 14     | `text-[11px] uppercase tracking-wide text-textmut`  |
| Body / paragraf | 13px / 18     | `text-[13px] leading-[18px]`                        |
| Sayfa başlığı   | 18px / 24     | `text-lg font-semibold`                             |
| Bölüm başlığı   | 14px / 20     | `text-sm font-semibold`                             |
| Mini etiket     | 10px          | `text-[10px] uppercase tracking-wider text-textdim` |

Kural: tablo metni **asla** 13px üstü. Yoğunluk FM'in imzası.

-----

## 3. Layout

```
┌─────────────────────────────────────────────┐
│ TopBar: tenant seçici · sezon · /auth/me · ⏻ │  h-12, bg-surface, border-b
├──────────┬──────────────────────────────────┤
│ Sidebar  │  İçerik (max-w yok, full-bleed)   │
│ w-56     │  p-4, bg-bg                        │
│ bg-      │  ┌ Breadcrumb (text-[11px])       │
│ surface  │  └ Sayfa                           │
│ Nav      │                                    │
└──────────┴──────────────────────────────────┘
```

- **Sidebar (`w-56`, `bg-surface`, `border-r border-border`)**: dikey nav.
  Aktif item `bg-surface2 text-text border-l-2 border-accent`, pasif `text-textmut`.
  Gruplar: *Ligler · Takımlar · H2H · Maçlar · Canlı · Admin*. Admin item'ı sadece `role==='admin'`.
- **TopBar (`h-12`)**: solda tenant + sezon `<select>` (bg-surface2), sağda kullanıcı email + logout.
- İçerik full-bleed; merkezleme yok. FM gibi ekranı doldur.
- Density: section'lar arası `gap-3`, kart içi padding `p-3`. Cömert boşluk yok.

-----

## 4. Reusable komponentler (`frontend/src/components/ui/`)

shadcn/ui ruhunda ama bağımlılık şart değil — saf Tailwind + TS. Her sayfa bunları
import eder; **inline JSX kopyalamak yasak**. Hepsi `forwardRef` + className merge (`cn()` util).

### `Table` (`table.tsx`)

Dense, zebra'lı, sticky header'lı tablo primitifi.

- `<DataTable columns rows />` generic; `columns: {key, header, align, render?, sortable?}[]`.
- Satır: `h-7`, hücre `px-2`. Zebra: tek satır `bg-surface`, çift `bg-surface2`.
- Hover: `hover:bg-elevated`. Seçili: `bg-accent/15 border-l-2 border-accent`.
- Header sticky `top-0 bg-surface border-b border-border`, tıklanınca sort (▲▼).
- Sayısal kolon `text-right tabular-nums`.

### `Sparkline` (`sparkline.tsx`)

Küçük inline trend (ppg, gd, rating zaman serisi).

- Props: `data: number[]`, `width=64`, `height=18`, `color?`.
- SVG polyline; son nokta vurgulu dot. Eksen/grid yok — sadece çizgi.
- Renk verilmezse trend yönüne göre: yükseliş `win`, düşüş `loss`, düz `textmut`.

### `RatingBar` (`rating-bar.tsx`)

FM attribute bar'ı — sayı + dolu çubuk.

- Props: `value` (0–100), `label?`, `max=100`.
- Sol: değer (`tabular-nums`, `ratingColor`), sağ: track (`bg-surface2 h-1.5 rounded`)
  üzerine dolu kısım `ratingColor` arka planla.
- Kompakt varyant `<RatingBar dense />` → sadece renkli sayı, çubuk yok (tablo içi).

### `PillBadge` (`pill-badge.tsx`)

W/D/L ve durum rozetleri.

- `<Pill variant="win|draw|loss|neutral|warn|danger">{children}</Pill>`.
- W/D/L: `w-4 h-4` kare, ortalı tek harf, `text-[10px] font-bold`, ilgili renk + `/15` zemin.
- Form şeridi: `<FormStrip results={['W','D','L','W','W']} />` → yan yana 5 pill, sağdan sola en yeni.

### `ExplainPanel` (`explain-panel.tsx`)

`explain=true` Claude yorumunu gösteren yan panel.

- Tetikleyici: `<ExplainButton onClick />` (`text-[11px]`, `border border-borderlt`).
- Açılınca sağdan slide-in panel (`w-80 bg-elevated border-l border-border`).
- İçerik: Claude yorumu (prose `text-[13px]`) + altında `audit` gerekçesi (`text-[11px] text-textmut`, collapsible).
- **Lazy**: tıklanana dek fetch yok. Sonuç komponent state'inde cache'lenir (aynı paramda tekrar çağırmaz).
- Loading: skeleton; error: `text-danger` satır + retry.

### `Card` / `Panel` (`panel.tsx`)

Mevcut generic `card` class'ının yerine geçer.

- `<Panel title? actions?>` → `bg-surface border border-border rounded-md`.
- Header `h-9 px-3 border-b border-border` (başlık `text-sm font-semibold` + sağda actions slot).
- Body `p-3`.

### `StatTile` (`stat-tile.tsx`)

Tek metrik kutusu (ppg, son N W/D/L sayısı vb).

- `<StatTile label value delta? sparkData? />`. Değer büyük (`text-xl tabular-nums`),
  label `text-[10px] uppercase`, opsiyonel `Sparkline`.

### Yardımcılar

- `lib/cn.ts` — className merge (clsx + tailwind-merge).
- `lib/rating.ts` — `ratingColor(value)`.
- `lib/api.ts` — typed fetch client (auth header + refresh interception, tek yer).
- `lib/format.ts` — `ppg.toFixed(2)`, gol farkı `+/-` işaretli.

-----

## 5. Etkileşim / durum kuralları

- Her veri ekranı 4 state taşır: **loading** (skeleton), **error** (`text-danger` + retry),
  **empty** (`text-textmut` "veri yok"), **data**.
- `explain` çağrıları pahalı (LLM + kota) → daima lazy + cache. Otomatik tetikleme yok.
- Rol bazlı gizleme UI'da: `viewer` admin nav + admin sayfa görmez (route guard + nav filtre).
- Kota uyarısı: `/admin/usage` eşiğe yakınsa TopBar'da `Pill variant="warn"`.
- Failed job: admin tablosunda satır `text-danger`, status pill `danger`.

-----

## 6. Yapılmayacaklar (anti-pattern)

- Açık tema, beyaz zemin, pastel renk.
- Büyük hero, geniş boşluk, dekoratif gradient/gölge (rating bar gradyanı hariç).
- Sayfaya özel inline renk veya inline `<table>` markup — hep reusable komponent.
- 13px üstü tablo metni.
- `explain`'i sayfa yüklenince otomatik çağırmak.
- Responsive/mobil öncelik — masaüstü-öncelikli, FM gibi.
