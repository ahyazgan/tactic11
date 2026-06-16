# PROMPT_FAZ5_BACKLOG.md — Önceliklendirilmiş 47 Geliştirme

> Konuşmadan üretilen tam liste. Her item için **efor** (S/M/L/XL) +
> **değer** (★1-5) + **durum** notu. ROI sıralaması en üstte.

**Efor ölçeği**:
- S = 0.5-2 saat (mevcut altyapı + ufak wiring)
- M = 2-6 saat (yeni endpoint/sayfa, mevcut motor kullanımı)
- L = 6-12 saat (yeni motor + endpoint + sayfa + test)
- XL = 12+ saat (yeni veri akışı, ML, tracking entegrasyonu)

**Değer ölçeği**: TD/analist/kulüpe hafta hafta sağladığı somut karar
desteği. ★1 = ürün cilası, ★5 = pilot kulüp için kritik.

-----

## Sprint 1 — Quick Wins (S + ★4-5, ilk hafta)

Mevcut altyapı üzerine ince wiring; her biri 1-2 saat.

| # | İş | Efor | Değer | Mevcut altyapı |
|---|---|---|---|---|
| 1 | get_lineup_recommendation chat tool | S | ★4 | LineupRecommendationAgent ✓ |
| 2 | get_opponent_scout chat tool | S | ★5 | OpponentScoutAgent v3 ✓ |
| 3 | get_substitution_advice chat tool | S | ★4 | SubstitutionAdviceAgent ✓ |
| 4 | get_tactical_adjustment chat tool | S | ★4 | TacticalAdjustmentAgent ✓ |
| 5 | get_training_plan chat tool | S | ★5 | TrainingPlanAgent ✓ |
| 6 | get_injury_load / get_fatigue_signal chat tool | S | ★4 | InjuryLoadAgent + fatigue_signal ✓ |
| 7 | get_set_piece_routine chat tool | S | ★3 | engine.set_piece_routine ✓ |
| 8 | get_player_feedback chat tool | S | ★5 | PlayerFeedbackAgent ✓ |
| 9 | get_pre_match_report chat tool | S | ★4 | PreMatchReportAgent ✓ |
| 10 | get_post_match_report chat tool | S | ★4 | PostMatchReportAgent ✓ |
| 11 | get_weekly_digest chat tool | S | ★3 | WeeklyDigestAgent ✓ |
| 12 | get_team_tactical chat tool | S | ★4 | tactical-profile endpoint ✓ |
| 13 | compare_players chat tool | S | ★4 | player_similarity ✓ |

**Sprint 1 toplam**: 13 chat tool × ~1 saat = **bir oturum bitiyor**.

-----

## Sprint 2 — Yapısal feature'lar (M + ★4-5)

Yeni endpoint + frontend sayfa, mevcut motor kullanımı.

| # | İş | Efor | Değer | Notlar |
|---|---|---|---|---|
| 14 | Proaktif uyarı motoru | M | ★5 | Yük/zaaf/sözleşme alert engine + Notification model |
| 15 | "Bugün ne yapmalıyım" landing | M | ★5 | Role-based dashboard composer (4 rol) |
| 21 | Rakip zayıflık ↔ bizim güç eşleştirme | M | ★5 | opponent_weakness + matchup mevcut |
| 25 | Duran top hazırlık brief | M | ★4 | set_piece_routine + pattern_history ✓ |
| 22 | Maç planı (game-plan) dokümanı | M | ★5 | Mevcut agent'ları compose eden plan agent |
| 23 | Müsait kadro ön-filtre | M | ★4 | injury + cards + load → available squad |
| 27 | Senaryo planı (Plan B-C) | M | ★4 | Skor durumuna göre alternatif lineup öneri |
| 28 | Plan ↔ canlı köprü | M | ★4 | Pre-match plan store + live comparison |
| 29 | Birleşik game-plan ekranı | M | ★5 | Sprint 2'nin diğerlerini tek sayfada toplar |

**Sprint 2 toplam**: ~9 iş × 3-5 saat = **~30-45 saat agent işi**.

-----

## Sprint 3 — Sezon/uzun vade (M-L + ★3-4)

| # | İş | Efor | Değer | Notlar |
|---|---|---|---|---|
| 30 | Sezon takvimi + fixture zorluğu | M | ★4 | fixture_difficulty + schedule mevcut |
| 31 | Rotasyon/yük periyotlama | L | ★4 | load engine + planlama agent (yeni) |
| 32 | Sezon hedef takibi | M | ★3 | Hedef tablosu + xG aggregate + projeksiyon |
| 33 | Kadro derinlik haritası | M | ★4 | Pozisyon bazlı yaşlanma + yetersizlik |
| 34 | Sözleşme/yaş uyarıları | S | ★3 | Tablo + cron alert (basit) |
| 35 | Transfer hedef havuzu | M | ★4 | player_similarity + filtre UI |

**Sprint 3 toplam**: ~6 iş × 3-8 saat = **~25-40 saat**.

-----

## Sprint 4 — Oyuncu gelişimi + operasyon (M + ★3-4)

| # | İş | Efor | Değer | Notlar |
|---|---|---|---|---|
| 36 | Bireysel gelişim trendi sayfası | M | ★4 | player tactical-trend ✓ — UI cilası |
| 37 | Genç/akademi takibi | M | ★3 | Yaş < 21 filter + bireysel rapor |
| 38 | Oyuncu hedef/feedback döngü takibi | M | ★3 | Hedef tablosu + PlayerFeedback geçmişi |
| 39 | Karar geçmişi + isabet takibi | M | ★4 | decisions_audit ✓ + verdict dashboard |
| 40 | Rapor paylaş/dışa aktar | M | ★3 | PDF export + WhatsApp link |
| 41 | Çoklu kullanıcı not/yorum | L | ★3 | Yeni `notes` tablosu + UI thread |

-----

## Sprint 5 — Sağlık/risk (M-L + ★4)

| # | İş | Efor | Değer | Notlar |
|---|---|---|---|---|
| 42 | Sakatlık riski tahmini | L | ★5 | load + frequency + age → risk score motor |
| 43 | Dönüş/rehab takibi | M | ★3 | Rehabilitation status table + UI |

-----

## Sprint 6 — Dağıtım/entegrasyon (M-XL + ★3)

| # | İş | Efor | Değer | Notlar |
|---|---|---|---|---|
| 16 | NL rapor PDF üretici | M | ★3 | Mevcut briefe LaTeX/reportlab wrapper |
| 17 | Rol bazlı landing dashboard | M | ★4 | TopBar/dashboard composer |
| 18 | Sabah otomatik brief | M | ★3 | scheduler + email job |
| 19 | WhatsApp/Telegram brief | L | ★3 | Bot API + signed link |
| 20 | Maç-içi sesli not / hızlı tag | L | ★2 | Web Audio API + tagging UI |
| 24 | Rakibe göre formasyon önerisi | M | ★4 | formation_matcher ✓ → öneri sarmalı |
| 26 | Isınma/son kontrol ekranı | M | ★2 | Kickoff -30 sn checklist |

-----

## Sprint 7 — Teknik derinleştirme (L-XL + ★3-5)

| # | İş | Efor | Değer | Notlar |
|---|---|---|---|---|
| 44 | predict_ml → gerçek multinomial GBM | XL | ★4 | Feature matrisi + sklearn-free gradient boost veya basit logistic |
| 45 | Tracking entegrasyonu | XL | ★5 | StatsBomb 360 / Hawk-Eye adapter + compute_pressure + compute_formation |
| 46 | 36 pilot-dışı motor audit | M | ★3 | full_season_audit pattern'ini ikinci grupla çalıştır |
| 47 | Player-level VAEP canlı momentum | L | ★4 | VAEP per-action stream → WebSocket push |

-----

## Toplam matriks

| Sprint | İş sayısı | Toplam efor | Çıkış değeri |
|---|---|---|---|
| Sprint 1 | 13 chat tool | ~12-15 saat | ★4 ort. (kolay zafer) |
| Sprint 2 | 9 yapısal feature | ~30-45 saat | ★4.5 ort. (en yüksek değer) |
| Sprint 3 | 6 sezon/uzun vade | ~25-40 saat | ★3.5 ort. |
| Sprint 4 | 6 oyuncu/operasyon | ~20-30 saat | ★3.5 ort. |
| Sprint 5 | 2 sağlık/risk | ~10-15 saat | ★4 ort. |
| Sprint 6 | 7 dağıtım | ~25-50 saat | ★3 ort. |
| Sprint 7 | 4 teknik derin | ~40-60 saat | ★4 ort. |
| **Toplam** | **47** | **~160-255 saat** | — |

## Önerilen pilot sıralaması

1. **Sprint 1 (bu PR)** — Chat tools, 1 oturum
2. **Sprint 2** — Game-plan ekranı odaklı, 2-3 oturum
3. **Sprint 4 #39 + Sprint 5 #42** — Risk skoru + decision dashboard
4. **Sprint 6 #16, #17, #24** — Dağıtım cilası
5. **Sprint 3** — Sezon yönetimi
6. **Sprint 7** — Teknik derinleştirme (pilot kulüp imzalandıktan sonra)

Pilot demo'ya kadar Sprint 1-2 yeterli. Sprint 7 production-grade pilot
canlıya çıkınca tetiklenir.
