# tactic11 — Ekran Envanteri (tasarım promptu ↔ gerçek repo)

Tasarım promptundaki 10 ekranın repodaki **gerçek** durumu. Amaç: neyin zaten
var olduğunu (yeniden yazma!), neyin gerçekten eksik olduğunu netleştirmek.
Her ekran: route → ana endpoint(ler) → kullandığı/kullanması gereken sözlük
kavramları (bkz. `FOOTBALL_GLOSSARY.md`).

> Tasarım dili: `DESIGN.md` token'ları + `FOOTBALL_GLOSSARY.md` + FM primitifleri
> (`EndpointTag`, `RiskPill`, `ConditionBar`, `ProbBar`). Sayılar monospace.

---

## "Tasarlanmış" 5 ekran (referans HTML gerekir)

| # | Ekran | Route | Durum | Not |
|---|-------|-------|-------|-----|
| 1 | Tanıtım/Landing | `/` | **Kısmî** | `page.tsx` bir dashboard; pitch/landing değil. Referans HTML ile yenilenebilir. |
| 2 | Ana Konsol (Genel Bakış) | — | **EKSİK** | 3-kolon FM konsol (nav + KPI/risk + sağ bilgi) yok. Referans HTML bekliyor. |
| 3 | Performans Paneli | `/physical-tests` | **VAR** | Konsolide B paneli (risk halkası + kadro + test + PDF). Eski `/performance` (batarya) deprecated, banner ile yönlendiriyor. |
| 4 | Canlı Maç Konsolu | — | **EKSİK** | `/live` route yok (5 canlı motor + saha + momentum + audit). Referans HTML bekliyor. |
| 5 | Maç Planı | — | **EKSİK** | `/match-plan` yok (önerilen 11 + rakip brifing + eşleşme grid + duran top). `matches` yalnız fikstür. Referans HTML bekliyor. |

## "Üretilecek" 5 ekran

| # | Ekran | Route | Durum | Not |
|---|-------|-------|-------|-----|
| 6 | Login / Kulüp Girişi | `/login` | **VAR** | Multi-tenant JWT giriş mevcut. |
| 7 | Scout / Rakip Dosyası | — | **EKSİK** | `next_opponent_brief` + zayıf bölge haritası + form trendi + `similarity_engine`. Referans gerekmez — aynı dilde üretilebilir. |
| 8 | AI Asistan Sohbet | `/chat` | **VAR** | `/assistant/chat`, tool-call'lar. FM-leştirme (EndpointTag, mono) eklenebilir. |
| 9 | Tıbbi Merkez | — | **EKSİK** | `return_to_play` + `minutes_management` + sağlık kartları + dönüş takvimi + yük geçmişi. Referans gerekmez. |
| 10 | Form & Rating | `/teams/[id]` | **VAR** | `/teams/{id}/form` + `/rating`, ConfidenceBadge + FormStrip + monospace. |

---

## Özet

- **Zaten var (dokunma / kademeli FM-leştir):** Performans (3), Login (6), Chat (8), Form&Rating (10).
- **Gerçekten eksik, referans GEREKMEZ (gece üretilebilir):** **Scout (7)**, **Tıbbi Merkez (9)**.
- **Gerçekten eksik, referans HTML GEREKİR (kullanıcı verecek):** Ana Konsol (2), Canlı Maç (4), Maç Planı (5).
- **Kısmî:** Landing (1).

## Diğer mevcut ekranlar (envanterde yok ama repoda var)
`/leagues`, `/matches`, `/h2h`, `/decisions`, `/calibration`, `/admin`, `/players`,
`/training` — hepsi mevcut DESIGN.md sistemiyle.

## Karar Merkezi (Haziran 2026 — feat/closing-strategy)

`/decisions` altı tam dolu üçlü ekran seti — orkestra şefi (context_engine)
10 sinyali tek karara indirgiyor; canlı + geçmiş + isabet döngüsü kapalı.

| # | Ekran | Route | Durum | Not |
|---|-------|-------|-------|-----|
| 11 | Kararlar (Hub) | `/decisions` | **VAR** | 2 büyük tile (Maç-içi + Takip) + demo karar kartları |
| 12 | Maç-içi Karar | `/decisions/live` | **VAR** | Scoreboard (skor+dakika+momentum tilt bar) → ŞİMDİ banner (critical pulse) → 7 engine kart (Momentum/Kapanış/İkame/Trigger/Risk/Yıldız/Faul) + tooltips + Timeline (▶ Replay 60→95) + Canlı mod (5sn refresh) + Bildirim (Notification API) + Karar Yansıt (POST decision) |
| 13 | Karar Takip | `/decisions/track` | **VAR** | İsabet (SVG rolling-N sparkline) + 4 summary kart + tablo (Tarih/Maç/Dk/Tip/Not/Güven/Öneri/Sonuç pill) + inline ✓/✗/○ pending mark |

**Yeni endpointler:**
- `GET /admin/matches/{id}/live-decision?my_team_id=...&current_minute=...&star_player_id=...` — 13 engine birleşik panel + context_engine primary/secondary
- `GET /admin/matches/{id}/closing-strategy` — K kategorisi standalone
- `GET /admin/matches/{id}/star-feed?star_player_id=X` — G.3 standalone
- `POST /admin/matches/{id}/foul-pressure` — I.1 payload OR DB-fed
- `GET /admin/matches/{id}/hot-hand` — G.2 sıcak el (loaded.shots × baseline)
- `GET /admin/matches/{id}/set-piece-opportunity` — H.1 (corners+FK+fouls)
- `POST /admin/referee/tendency` — J.1 hakem eğilimi (prior_matches payload)
- `GET /admin/matches/with-events?limit=N` — match selector için ingest'li maçlar
- `GET /admin/decisions/recent?limit=N&team_external_id=X` — track sayfası için summary + decisions
- `POST /admin/decisions/{id}/outcome` — inline outcome mark

**Yeni engine'ler:** `closing_strategy` (K), `foul_pressure` (I.1), `star_feed` (G.3), `hot_hand` (G.2), `set_piece_opportunity` (H.1), `referee_tendency` (J.1) — hepsi pure compute + audit + EngineResult.

**Veri ingest:** StatsBomb event type=22 (Foul Committed) + type=24 (Bad Behaviour) artık parse'lanıyor. dev_seed eski demo.db'lerde foul backfill yapıyor (idempotent re-ingest).

---

## Gece çalışma sırası (öneri)
1. Scout (7) ve Tıbbi Merkez (9) — referans gerekmez, FM primitifleriyle, gerçek
   endpoint'lere bağlı. (Görsel onay sabah.)
2. Mevcut ekranlara `EndpointTag` + monospace + `RiskPill` kademeli uygula.
3. Ana Konsol / Canlı Maç / Maç Planı — kullanıcı referans HTML'leri verince.

## Endpoint backend desteği — doğrulanacak
Scout/Tıbbi ekranları üretmeden önce backend uçlarının (`next_opponent_brief`,
`return_to_play`, `minutes_management`, `similarity_engine`) gerçekten expose
edilip edilmediği kontrol edilmeli; yoksa önce backend uç + test (mergeable).
