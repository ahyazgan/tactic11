# manager2 frontend — Next.js 14 App Router

**Durum:** Scaffold + giriş + maç listesi + chat widget. **Tam ürün için
~3 hafta tam zamanlı geliştirme gerekir** (Prompt 5 brief).

## Hızlı başlangıç

```bash
cd frontend
npm install
npm run dev
# → http://localhost:3000
```

Backend `http://localhost:8000`'da koşmalı. `next.config.js` `/api/*` →
backend rewrite ile JWT cookie + CORS olmadan çalışır.

## Yapılı sayfalar (scaffold)

| Sayfa | Path | Durum |
|---|---|---|
| Home | `/` | ✅ Dashboard menu |
| Login | `/login` | ✅ JWT login formu |
| Matches | `/matches` | ✅ Liste (schedule endpoint'ten) |
| Chat | `/chat` | ✅ Asistan widget (assistant/chat) |
| Match detail | `/matches/[id]` | ⬜ TODO — split-screen |
| Calibration | `/calibration` | ⬜ TODO — Recharts Brier grafiği |
| Teams | `/teams/[id]` | ⬜ TODO — form sparkline |
| Decisions | `/decisions` | ⬜ TODO — kararlar widget'ı |
| Settings | `/settings` | ⬜ TODO — branding upload |

## Tasarım — Football Manager 2010-2015 estetiği

- Dark theme (sadece)
- Yoğun veri tablo + sparkline
- Renk paleti `tailwind.config.ts`:
  - `bg #0e1116`, `panel #161b22`, `border #30363d`
  - `accent #58a6ff`, `good #3fb950`, `warn #d29922`, `bad #f85149`
- Mono font (JetBrains Mono) sayısal alanlarda

## Stack

- **Next.js 14 App Router** — SSR + RSC
- **Tailwind CSS** — utility-first
- **SWR** — data fetching + cache
- **Recharts** — kalibrasyon grafikleri (TODO)
- **TypeScript** strict mode

## RFC — Kalan iş (3 hafta tahmini)

### Hafta 1: temel sayfalar
- [x] /login JWT flow (✅ scaffold)
- [x] /matches listing (✅ scaffold)
- [ ] /matches/[id] split-screen: sol (tahmin + AI brief), sağ (form/load/H2H)
- [ ] Auth middleware — token expire → /login redirect
- [ ] Refresh token flow (cookie + auto-refresh)

### Hafta 2: analitik
- [ ] /calibration: Recharts ile Brier/log_loss/ECE grafikleri (zaman serisi)
- [ ] /teams/[id]: form sparkline + rating + son maçlar
- [ ] /decisions: bu haftaki widget'lar (yorgun oyuncu, takvim sıkışıklığı)
- [ ] Manager performance dashboard (`/admin/manager-performance` data)

### Hafta 3: özelleştirme
- [x] /chat widget (✅ scaffold)
- [ ] /chat conversation list (geçmiş konuşmalar)
- [ ] /settings/branding: logo + renk paleti upload
- [ ] /settings/webhook: tenant settings JSON editor
- [ ] /settings/xg-model: /admin/xg-model-status durum + retrain trigger
- [ ] Responsive md/lg breakpoint
- [ ] Vercel preview deploy + CI

## Backend bağlantısı

Tüm endpoint'ler `apiFetch()` üzerinden — JWT bearer otomatik.
401 → token temizle + `/login` redirect.

Backend dokümantasyonu: `../README.md` + `../DEPLOYMENT.md`.
