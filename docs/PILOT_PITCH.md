# tactic11 — Pilot Kulüp Pitch (TR)

> Tek sayfalık satış brief'i. TD/Analiz Şefi/GM toplantısında 5 dakikada
> ne sunduğumuzu anlatmak için.

---

## Problem

Maç boyunca TD'nin kafasında 12+ paralel sinyal var:
yorgunluk + skor + dakika + momentum + rakip dizilim + kart riski + duran top
+ hakem eğilimi + yıldız beslemesi + faul ritmi + …

Şu an bu sinyalleri **birleştiren ve önceliklendiren** bir araç yok.
Hudl/Wyscout maç **sonrası** analiz yapar; canlı maçta TD yalnız.

## Çözüm — tek ekran "ŞİMDİ şunu yap"

13 saf-hesap engine (pure compute, audit'li) bir orkestra şefi'nde birleşir
(`context_engine`). Ekran üst kısmında **tek primary aksiyon** + güven
yüzdesi + gerekçe. Altında 7 engine kartı (Neden bu? tooltip'li).

```
ŞİMDİ ŞUNU YAP                                    güven: yüksek %78
Berabere · son 15 dk → tempo: yükselt, ikame: hücumcu
80. dk, berabere — closing_strategy primary; aynı anda:
foul_pressure (rakip ritim kırıyor), star_feed (yıldız aç) → karar net
   [✓ Bu kararı uygula & yansıt]   [▶ İzle]
```

## Diferansiyasyon

| Konu | Hudl/Wyscout | StatsBomb IQ | **tactic11** |
|---|---|---|---|
| Canlı "şimdi şunu yap" karar | ❌ analiz sonrası | ❌ takım, opak | ✅ |
| Açıklanabilir gerekçe (Neden?) | ❌ | ❌ kapalı | ✅ her engine tooltip + audit |
| Karar kayıt → isabet trend döngüsü | ❌ | ❌ | ✅ pending → ✓/✗ → hit_rate sparkline |
| TR dil + Süper Lig odak | ❌ | ❌ | ✅ |
| Multi-tenant + B2B SaaS hazır | ⚠ enterprise | ⚠ enterprise | ✅ JWT + tenant scope |
| Pure-compute audit'li engine | ❌ | ⚠ kısmi | ✅ EngineResult.audit.formula |

## 4 ekran (DEMO_MODE ile hemen gezilebilir)

1. **`/decisions`** — hub, 2 büyük tile + son karar kartları
2. **`/decisions/live`** — canlı panel: Scoreboard (skor+dakika+momentum tilt)
   + ŞİMDİ banner + 7 engine kart + Timeline (▶ Replay 60→95) +
   Canlı mod (5sn refresh) + Bildirim (critical → push)
3. **`/decisions/track`** — isabet sparkline + karar tablosu +
   inline ✓/✗/○ pending mark
4. **`/scout`, `/medical`, `/physical-tests`** — yan ekranlar

## Canlı demo akışı (2 dakika)

1. `/decisions/live` aç → **▶ Replay** tıkla (60→95 otomatik)
2. 80. dk'da ŞİMDİ banner: "tempo: yükselt, ikame: hücumcu" + güven %78
3. **▶ İzle** tıkla → karar anı klibi modal (CMS bağlandığında video oynar)
4. **✓ Bu kararı uygula & yansıt** tıkla → `/decisions/track`'e geçer
5. Track'te ✓ tıkla → isabet sparkline güncellenir
6. Tooltip'leri göster: "Neden Kapanış reçetesi? (skor_diff, dakika) →
   tempo+ikame matrisi"

## 13 engine — sinyal envanteri

**Faz 6 (maç-içi karar):** momentum_tracker, sub_timing,
live_tactical_trigger, live_risk_monitor, opponent_reaction

**Faz 7 (mekânsal/bireysel):** spatial_control, live_matchup,
score_time_matrix

**Faz 8 (orkestra):** context_engine, signal_quality, confidence,
match_memory

**Yeni (F-K kategorisi):** closing_strategy (K), foul_pressure (I.1),
star_feed (G.3), hot_hand (G.2), set_piece_opportunity (H.1),
referee_tendency (J.1), clip_assembler (video)

## Teknik mimari (kısa)

- **Backend:** FastAPI + SQLAlchemy + Alembic + JWT + multi-tenant
- **Frontend:** Next.js 14 App Router + SWR + PWA (offline shell)
- **Engine kuralı:** pure compute (DB/HTTP yok), audit'li, EngineResult
- **Veri:** StatsBomb Open (production'da Sportmonks/Opta adapter)
- **Test:** 1770+ backend test + 6 E2E + ruff temiz
- **Deploy:** Docker compose; tek-bin kullanıma hazır

## Pilot teklif (örnek)

- **6 ay ücretsiz** — gerçek 1 sezon Süper Lig maçında çalışsın
- **Karşılığında:**
  - Pilot kulüp video CMS (broadcast feed) bizim adapter'a bağlanır
  - Kart/sub/faul/oyuncu durum stream'i bizim ingest pipeline'ından geçer
  - Kulüp logosu "Galatasaray bizi kullanıyor" referansı olarak gösterilir
- **6 ay sonra:**
  - Aylık SaaS lisans (3 user × 3 panel)
  - Custom engine (kulübün stil sözlüğüne göre tunable)

## Kim, ne kadar?

- 1 geliştirici (ben) — ~12 ay; ~30K satır kod, 1770+ test, 13 engine
- Replacement cost: **$80-180K** (codebase olarak)
- Acqui-hire: **$150-400K** (ben + codebase + 1-2 yıl bağlanma)
- 6 ay pilot sonrası SaaS: **$300K-1M ARR** olası (5-7 kulüp + 1 medya partneri)

## İletişim

[buraya kulüp temsilcisi bilgileri]

---

_Hazırlık: tactic11 — `feat/closing-strategy` branch · 2026-06-14_
_Demo: https://tactic11.com/decisions/live (DEMO_MODE on)_
