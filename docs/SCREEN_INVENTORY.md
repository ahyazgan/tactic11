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

## Gece çalışma sırası (öneri)
1. Scout (7) ve Tıbbi Merkez (9) — referans gerekmez, FM primitifleriyle, gerçek
   endpoint'lere bağlı. (Görsel onay sabah.)
2. Mevcut ekranlara `EndpointTag` + monospace + `RiskPill` kademeli uygula.
3. Ana Konsol / Canlı Maç / Maç Planı — kullanıcı referans HTML'leri verince.

## Endpoint backend desteği — doğrulanacak
Scout/Tıbbi ekranları üretmeden önce backend uçlarının (`next_opponent_brief`,
`return_to_play`, `minutes_management`, `similarity_engine`) gerçekten expose
edilip edilmediği kontrol edilmeli; yoksa önce backend uç + test (mergeable).
