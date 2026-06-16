# PILOT_ENGINES.md — Production-Grade Engine Listesi

> Bu dosya, gerçek La Liga 2018/19 sezonu (34 maç, 85k event) üzerinde
> sinyal/gürültü auditine dayalı **pilot kulübe sunulabilir 19 engine**'i
> listeler. Kalan engine'ler ya niche kullanım için, ya tracking gerektiriyor,
> ya da audit sonrası tasarımı gözden geçirilmeli.
>
> Kaynak: `full_season_audit.md` + `full_season_audit.json` (commit `720f23e`
> sonrası re-audit).

-----

## Audit metodolojisi

- 34 maç × 2 takım = **68 sample** per engine
- Verdict eşikleri:
  - **STRONG_SIGNAL**: CV ≥ 0.30 veya team_spread/|mean| ≥ 0.30 (mean≈0 case'inde
    stdev > 0.5 veya spread > 1.0)
  - **MODERATE**: 0.05 < CV < 0.30
  - **NO_SIGNAL**: CV < 0.05 ve düşük team_spread
- Barca sanity check (Pep-tarz beklenti): field_tilt > 0.6, direct_play < 0.5,
  tempo > 6, dominance > 1.5, team_xt > 1.5

## 19 Pilot-Ready Engine

Pilot kulübün TD'sine hafta hafta somut karar verecek engine'ler.

| # | Engine | CV | Team Spread | n | Açıklama |
|---|---|---|---|---|---|
| 1 | `team_xt` | 2.07 | 2.55 | 68 | Karun Singh xT 12×8 grid — yaratıcılık |
| 2 | `set_piece_zones` | 0.75 | 4.00 | 68 | Duran top 5 zone heatmap |
| 3 | `ppda` | 0.62 | 6.52 | 68 | Pres yoğunluğu (Liverpool ~8, City ~10) |
| 4 | `cutback_frequency` | 0.60 | 13.50 | 68 | Cit-tarz yan-çizgi geri pas |
| 5 | `pressing_trigger` | 0.54 | 0.26 | 68 | Top kaybından kazanım süresi |
| 6 | `field_tilt` | 0.49 | 0.56 | 68 | Hücum yarısı pas dominance |
| 7 | `cross_effectiveness` | 0.48 | 21.50 | 68 | Orta tipi × varış zone × şut |
| 8 | `transition` (v2) | 0.44 | 0.21 | 68 | Recovery → şut conversion (v2 fix) |
| 9 | `recovery_zone_heat` | 0.43 | 0.35 | 68 | Yüksek/orta/düşük blok |
| 10 | `tempo` | 0.35 | 5.05 | 68 | Pas/dakika (fast/medium/slow) |
| 11 | `possession_quality` | 0.34 | 3.66 | 68 | Possession başına pas + ilerleme |
| 12 | `final_third_entries` | 0.34 | 51.68 | 68 | Pas vs carry, kanal dağılımı |
| 13 | `counter_press_triggers` | 0.26 | 45.50 | 68 | Top kaybı sonrası ilk reaksiyon |
| 14 | `channel_preference` | 0.22 | 0.28 | 68 | Sol/orta/sağ koridor |
| 15 | `defensive_line` | 0.20 | 22.55 | 68 | Avg x defansif aksiyon |
| 16 | `defensive_duels` | 0.17 | 0.50 | 68 | Yer düellosu kazanma % |
| 17 | `direct_play` | 0.16 | 0.17 | 68 | Sumpter directness index |
| 18 | `press_resistance` | 0.10 | 0.33 | 68 | Pres altında pas tamamlama |
| 19 | `match_dominance` | inf | 11.75 | 68 | 5-bileşen composite (zero-sum metrik) |

**Barca sanity** (5 metric, 4 OK 1 MISS):
- ✅ field_tilt 0.69 (Pep-tarz hücum hakimiyeti)
- ✅ direct_play 0.31 (possession-ağırlık)
- ✅ tempo 7.86 (yüksek pas hızı)
- ✅ match_dominance 3.42 (dominant takım)
- ❌ team_xt 1.35 (eşik 1.5, sınırda kaçtı — yine yüksek)

**Coaching identity** (Barca 34 maç):
- 26 maç (%76) `high_press_possession` — Valverde-Pep ekolü ✓
- 4 maç `low_block_counter` (büyük rakipler)
- 4 maç `balanced_pragmatic`

## Sınır durumda (1)

| Engine | Sebep | Karar |
|---|---|---|
| `compactness` | CV 0.05, spread 3.80 sınırda | Gözlem altında; tracking data ile değer artar |

## Pilot-Dışı 36 Engine

Bu engine'ler iyi kod, ama pilot kulüpteki TD'nin hafta hafta karar olarak
kullanacağı şey değil. Niche/spesifik kullanım için kalıyor:

### Oyuncu-bazlı (8) — saha-içi feedback için
- `pass_alternatives` (frame-by-frame coach feedback)
- `overperformance` (G+A vs xG+xA)
- `progressive_passes` (per_90)
- `carries_into_final_third` (per_90)
- `press_resistance` (player varyantı)
- `off_ball_runs` (carry proxy)
- `player_role` (8-rol typoloji)
- `xa` (Expected Assists)

### Oyuncu form/load (5)
- `player_form` (Z-score baseline)
- `player_similarity`
- `load` (yük/rotasyon)
- `fatigue_signal` (canlı)
- `xt` (player varyantı)

### Match-level composite (5)
- `match_phase` + `score_state_effects` (split 1H/2H)
- `xg_match_graph` (zaman serisi)
- `coaching_identity` (8-boyut + arketip — full season ile %76 doğru)
- `build_up_pattern`
- `opponent_weakness`

### Canlı maç (3)
- `live_sub_recommendation`
- `live_shape_drift`
- `substitution_chess`

### Scout/strateji (4)
- `set_piece_routine` (routine builder)
- `set_piece_pattern_history`
- `set_piece` (eski)
- `formation_matcher`

### Tahmin (5)
- `form`, `rating`, `predict`, `predict_ml`, `schedule`, `matchup`,
  `fixture_difficulty`, `opponent` (h2h)

### Tracking-bağımlı (1)
- `tracking` (FixtureTrackingSource ile pilot demo, gerçek vendor swap edilecek)

### Veri agreement (3)
- `tactical_trend` (sezon serisi — pilot'a açılırken kullanılır)
- `calibration` (predict accuracy ölçer)
- `xg` (Shot xG)

### Possession value (1)
- `vaep` — full season ile train edildi (68k event):
  - Top zones P(score): zone 10 (kale önü merkez) %2.67
  - Production'da heuristic baseline + tabular trained dual mode

## Pilot pitch metni (önerilen)

> "tactic11 platform, gerçek La Liga 2018/19 sezonu üzerinde **19 production-grade
> taktiksel engine** ile pilot kulübe hizmet eder. Her engine sentetik test'te
> değil, 34 maç × 68 takım örnekleminde sinyal verir.
>
> Hafta hafta:
> - **Maç öncesi** (training plan): rakibin PPDA, pres tarzı, kanal tercihi
> - **Devre arası**: 1. yarı 7 engine + AI brief + sub önerisi + zayıf kanal
> - **Canlı maç**: WebSocket push (5 sn), shape drift, set-piece pattern alert
> - **Maç sonrası**: oyuncu-bazlı pass alternatives + post-match learning
>
> Bunun üstüne 36 niche engine (oyuncu form, player similarity, transition pattern,
> vb.) ihtiyaç oluştukça açılır."

## Audit re-run komutu

```bash
DATABASE_URL="sqlite:///full_season.db" python -m scripts.full_season_audit
```

Çıktı: `full_season_audit.json` + `full_season_audit.md`.

## Sıradaki audit konuları (Faz 5+)

- Premier League 2015/16 (StatsBomb) ile cross-league validation
- StatsBomb 360 tracking ile heuristic vs tracking-grade compare
- VAEP heuristic vs tabular ML üzerinde Brier score
- Pilot kulüp datası (StatsBomb Pro/Opta swap)
