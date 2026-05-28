# PROMPT — manager2 Frontend Faz 4 (Saha-içi Uygulanabilir)

> FAZ2 + FAZ3 tamamlandıktan sonra çalıştırılır. Bu turda backend'in
> 4 saha-içi sınıfı (player_feedback, training_plan, substitution_chess,
> set_piece_routine) UI'da görünür hale getirilir.
>
> Repo kökünde aç → içeriği bir Claude Code session'ına yapıştır.

-----

## Rol

`ahyazgan/manager2` frontend mühendisisin. Stack: **Next.js 14 App Router
+ Tailwind + TypeScript**. Backend dokunulmaz.

## Mutlak kurallar

1. **DESIGN.md hâkim.** Tüm renk/spacing/komponent → DESIGN.md.
2. **Mevcut komponentleri yeniden yazma.** Tüket:
   - `@/components/ui` → `Panel`, `Pill`, `ResultDot`, `FormStrip`,
     `RatingBar`, `DataTable`, `Sparkline`, `StatTile`, `ExplainPanel`,
     `ExplainButton`
   - `@/lib/cn`, `@/lib/rating`, `@/lib/format`, `@/lib/api`, `@/lib/auth`
3. **Backend dokunma.** Yeni endpoint gerekirse `AskUserQuestion`.
4. **Mock data yasak.** Empty state ve loading skeleton şart.
5. **Yeni dep yok.** recharts var; gerekirse SVG kendin çiz.

## Tüketilecek 4 yeni endpoint

```
GET  /admin/matches/{id}/players/{pid}/feedback     → PlayerFeedbackAgent
       Output: metrics{xt/xa/vaep/prog/press_resistance/overperformance}
                + pass_alternatives_summary{top_suboptimal[]} + ai_brief

GET  /admin/teams/{id}/training-plan?opponent_id=N  → TrainingPlanAgent
       Output: opponent_profile + drills[{name, focus, rationale, duration_min}]
                + ai_brief

GET  /admin/matches/{id}/substitution-chess?my_team_id&current_minute
       Output: scenarios[{out_player_id, projected_dominance_delta,
                          confidence, minutes_remaining}] + best_scenario_index

GET  /admin/teams/{id}/set-piece-routine?opponent_id&set_piece_type
       Output: top_recommendations[{target_zone, technique, rationale,
                                    opponent_weakness_score, our_strength_score,
                                    routine_score}] + avoid_zone
```

## Görev — kesin teslimat

### A. 4 yeni sayfa

#### A1. `/matches/[id]/players/[pid]/feedback`

Bireysel oyuncu maç-sonu feedback raporu.

**Layout:**
- Üst: oyuncu adı + maç skoru + dakika (StatTile grid)
- Orta: 6 metric StatTile (xT/90, xA/90, VAEP/90, prog/90, press_resistance,
  overperformance) + delta (varsa)
- Alt: "Alt-optimal pas örnekleri" Panel — top 3 frame:
  - Her frame için saha mini-map (100×100 SVG, başlangıç + actual end +
    önerilen end nokta gösterimi, ok işaretli)
  - Yan tarafa: "32. dk: actual (78,40), önerilen (62,18) → xT Δ +0.18"
- En alt: AI brief Panel (whitespace-pre-wrap)

**Saha mini-map SVG komponenti** (`@/components/charts/MiniPitch.tsx`):
- 200×130 SVG, koyu yeşil zemin, beyaz çizgi
- Props: `start: [x,y], actualEnd: [x,y], suggestedEnd: [x,y]`
- Actual = kırmızı kesik çizgi; suggested = yeşil düz çizgi; başlangıç dot

#### A2. `/teams/[id]/training-plan?opponent_id=N`

Haftalık antrenman planı.

**Layout:**
- Üst: rakip profili Panel — 5 StatTile (PPDA, pressing_style,
  recovery_style, archetype, dominant_channel)
- Orta: drill listesi (DataTable):
  - Kolonlar: drill name, focus, duration_min, rationale (uzun text, max 80
    karakter truncate)
- Alt: AI brief Panel

**Pre-fetch UX:**
- İki team selector kullanılsın gibi olabilir ama `?opponent_id=N` zaten
  query'de — yoksa "Rakip seç" placeholder (mevcut /h2h pattern'i)

#### A3. `/matches/[id]/sub-chess?my_team_id=N&current_minute=M`

Substitution chess viewer.

**Layout:**
- Üst: maç bilgisi + dakika sayacı + skor
- Orta: 3 senaryo card grid (top 3):
  - Kart başlığı: "Senaryo {idx}: Player #N → boş slot"
  - StatTile içinde projected_dominance_delta + confidence pill
  - "Out player fatigue 0.45 → kalan 30 dk'da 0.66 olur"
  - "In player fresh 0.05 → kalan 30 dk'da 0.26 olur"
- En iyi senaryo `border-l-2 border-win` vurgu
- `current_minute` slider (5-90 arası) → SWR yeniden çağrı

#### A4. `/teams/[id]/set-piece-routine?opponent_id=N`

Set-piece routine builder.

**Layout:**
- Üst: takım bilgisi + rakip + set_piece_type select
  (corner_kick / free_kick / all)
- Orta: top 3 routine card:
  - Zone label (kale ağzı / yakın direk vs) — büyük başlık
  - Technique pill (in_swinger / out_swinger / kısa korner)
  - routine_score progress bar
  - "Rakip %50 conv yiyor; biz %40 üretiyoruz"
- Alt: "Avoid zone" uyarı bandı: "Rakip bu bölgeyi bekliyor — yığınak yapar"
- Saha mini-map: 5 zone renkli (en yüksek score = win, en düşük = textmut)

**Yeni komponent** (`@/components/charts/SetPieceZoneMap.tsx`):
- Kale önü mini saha (kale + ceza sahası + 5 zone overlay)
- Her zone'a tıklanınca o zone'un detayı sağda
- Avoid zone üstünde × işareti

### B. Mevcut sayfalara entegrasyon

- `/teams/[id]/tactical`: "Training Plan" butonu (rakip seçici modal) →
  `/teams/[id]/training-plan?opponent_id=X`'a navigate
- `/matches/[id]/live`: "Sub Chess" linki → `/matches/[id]/sub-chess?
  my_team_id=N&current_minute=<snapshot.current_minute>`'a navigate
- `/players/[id]/tactical`: "Maç-sonu feedback" listesi (son 5 maç) →
  her satır `/matches/[mid]/players/[id]/feedback`'a link
- Sidebar nav'ına yeni item: **Antrenman Planı** (`/training` index sayfası)

### C. Yeni sidebar nav item ve `/training` index

`/training/page.tsx` — takım seçici + son N training_plan history (varsa,
`/admin/agent-outputs?agent_name=training_plan`).

### D. Frontend testleri (Playwright)

`frontend/e2e/saha_ici.spec.ts`:

1. `/training/page` smoke render
2. `/teams/X/training-plan?opponent_id=Y` → drill DataTable görünür
3. `/matches/X/players/Y/feedback` → 6 metric StatTile + brief görünür
4. `/matches/X/sub-chess?...` → senaryo card grid + slider çalışır
5. `/teams/X/set-piece-routine` → routine card + avoid uyarısı görünür

Backend-bağımlı testler `E2E_BACKEND=true` ile.

## Kabul kriterleri

- [ ] `npm run typecheck` clean
- [ ] `npm run build` 19 → 23 sayfa
- [ ] 4 yeni sayfa hata olmadan render olur (boş state dahil)
- [ ] MiniPitch + SetPieceZoneMap komponentleri saha mini-map çizebiliyor
- [ ] Saha-içi sınıf endpoint'leri tükenilir (curl ile aynı JSON UI'da)
- [ ] DESIGN.md token'larına uyumlu (inline hex yok)
- [ ] Mobile responsive değil (desktop-first)

## Çıktı sırası

1. Mevcut `/players/[id]/tactical` + `/teams/[id]/tactical` + 
   `/matches/[id]/live` sayfalarını incele — entegrasyon noktası belirle
2. Yeni dosya listesi: 4 sayfa + 2 komponent (MiniPitch, SetPieceZoneMap)
3. Implement: komponentler önce (MiniPitch + SetPieceZoneMap),
   sonra 4 sayfa, en son entegrasyonlar
4. E2E test
5. Belirsizlikte AskUserQuestion

## Anti-pattern

- Saha mini-map için canvas/p5.js — saf SVG yeterli
- Drill rationale'i 100+ karakter göstermek — truncate + tooltip
- Slider için 3rd-party — native `<input type="range">` yeterli
- Modal kütüphanesi — mevcut shell pattern'i tut
- 4 sayfa için ortak abstraction yazmak — over-engineer; her sayfa
  spesifik

-----

## Notlar

- Backend 4 endpoint zaten persist=true ile agent_outputs'a yazıyor;
  history endpoint `/admin/agent-outputs?agent_name=player_feedback`
  (eğer varsa) ile son feedback'leri çekebilirsin
- `subject_type="player"` ve `subject_id=player_id` ile filtre
- Saha-içi sınıf en yüksek pilot demo değeri — bu turun çıktısı kulüp
  pitch'inin canlı parçası
- FAZ5+ için aklımda: in-game heatmap annotator (tablet stylus desteği),
  decision audit dashboard (TD'nin geçmiş kararları + verdict trendi),
  StatsBomb 360 tracking adapter

Toplam **~6-8 saatlik agent işi**. Mevcut frontend mimarisini bozmaz.
