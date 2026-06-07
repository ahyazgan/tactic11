# manager2 — API Endpoint Referansı

Otomatik üretildi (2026-06-07). `app/api/*.py` router'larından.
Toplam **121** endpoint. Ekran/sözlük
bağlamı için `SCREEN_INVENTORY.md` ve `FOOTBALL_GLOSSARY.md`.

> Tüm uçlar (`/health*` hariç) JWT/X-API-Key korumalı (`protected` router).

## Admin / observability / scout / KVKK  
`app/api/admin.py`

| Method | Path | Açıklama |
|--------|------|----------|
| `GET` | `/admin/jobs` |  |
| `GET` | `/admin/usage` |  |
| `GET` | `/admin/quota-status` |  |
| `GET` | `/admin/snapshots` |  |
| `GET` | `/admin/snapshots/diff` |  |
| `GET` | `/admin/metrics` |  |
| `GET` | `/admin/predict-accuracy` |  |
| `GET` | `/admin/leagues-summary` |  |
| `GET` | `/admin/agent-outputs` |  |
| `GET` | `/admin/ml-model-status` |  |
| `GET` | `/admin/db-stats` |  |
| `GET` | `/admin/manager-performance` | TD performans değerlendirmesi — xPts vs actual points |
| `GET` | `/admin/scout/watchlist` | Scout izleme listesi |
| `POST` | `/admin/scout/watchlist` | Scout izleme listesine oyuncu ekle (idempotent) |
| `DELETE` | `/admin/scout/watchlist/{player_external_id}` | Scout izleme listesinden oyuncu çıkar |
| `GET` | `/admin/scout/similar/{player_external_id}` | Hedef oyuncuya benzer top-N oyuncu (cosine similarity) |
| `GET` | `/admin/xg-model-status` | xG modeli artifact durumu (trained/untrained + metrikler) |
| `POST` | `/admin/trigger-daily-brief` | Daily decision brief job'unu manuel tetikle (test için) |
| `GET` | `/admin/scout/player-role/{player_id}` | Oyuncu rol typology (engine.player_role v1) |
| `GET` | `/admin/teams/{team_id}/xg-difference` | Sezon xG farkı + overperformance (engine.xg_match_graph) |
| `GET` | `/admin/tactical/xt-info` | xT engine bilgisi (Karun Singh 2019 grid) |
| `GET` | `/admin/tactical/ppda-info` | PPDA engine bilgisi (pres zone + literatür referans) |
| `GET` | `/admin/tactical/match-phase/{match_id}` | Maç phase analizi (1H/2H/ET split — engine.match_phase) |
| `GET` | `/admin/teams/{team_id}/tactical-profile` | Takım taktiksel profil (20+ engine birleşik) |
| `POST` | `/admin/tactical-cache/clear` | Tactical profile/trend cache temizle (event ingest sonrası) |
| `GET` | `/admin/players/{player_id}/tactical-profile` | Oyuncu taktiksel profil (8 engine birleşik) |
| `GET` | `/admin/teams/{team_id}/tactical-trend` | Takım sezon-boyu trend (PPDA, field_tilt, dominance, xT, possession) |
| `POST` | `/admin/matches/{match_id}/decisions` | TD hamlesi kaydet (substitution / formation_change / tactical_instruction) |
| `GET` | `/admin/matches/{match_id}/decisions` | Bir maçtaki kayıtlı TD kararlarını listele |
| `POST` | `/admin/decisions/{decision_id}/outcome` | Karar sonucunu kaydet (Faz 8 #4 — feedback loop) |
| `GET` | `/admin/teams/{team_id}/decisions/feedback` | Karar tipine göre geçmiş isabet oranı (Faz 8 #4 → güven skoru) |
| `GET` | `/admin/matches/{match_id}/decisions/learning` | Post-match learning: TD kararının sonuca etkisi (causal proxy) |
| `GET` | `/admin/teams/{team_id}/set-piece-pattern-history` | Rakibin geçmiş set-piece pattern'leri (canlı maç alert için) |
| `GET` | `/admin/matches/{match_id}/live-sub-recommendation` | Canlı maç oyuncu değişikliği önerisi (retrospective demo da) |
| `GET` | `/admin/players/{player_id}/tactical-trend` | Oyuncu sezon-boyu trend (xT, xA, VAEP, prog_passes, press_resistance) |
| `GET` | `/admin/matches/{match_id}/halftime-brief` | Devre arası analiz brief (1. yarı event'leri üzerinde 7 engine + AI) |
| `GET` | `/admin/halftime-brief-history` | Kaydedilmiş devre arası brief'lerin listesi |
| `POST` | `/admin/vaep/train` | VAEP tabular model train (events tablosundan zone-bin lookup öğren) |
| `GET` | `/admin/matches/{match_id}/dominance` | Tek maç dominance + match_phase (composite + split) |
| `GET` | `/admin/matches/{match_id}/players/{player_id}/feedback` | Bireysel oyuncu maç-sonu coach feedback (sınıf 2) |
| `GET` | `/admin/teams/{team_id}/training-plan` | Haftalık antrenman planı — rakip profilinden (sınıf 3) |
| `GET` | `/admin/matches/{match_id}/substitution-chess` | Sub kombinasyonları forward projection (sınıf 1) |
| `GET` | `/admin/teams/{team_id}/set-piece-routine` | Set-piece routine builder — rakibin zayıf zone'una göre (sınıf 4) |
| `GET` | `/admin/teams/{team_id}/matchup-grid` | Rakip zaaf × bizim güç eşleştirme (3 kanal) — Faz 5 #21 |
| `POST` | `/admin/teams/{team_id}/game-plan` | Birleşik maç-hazırlık game-plan dokümanı — Faz 5 #22/#25/#27/#29 |
| `POST` | `/admin/teams/{team_id}/available-squad` | Müsait kadro ön-filtre (sakat/cezalı/yük) — Faz 5 #23 |
| `GET` | `/admin/teams/{team_id}/proactive-alerts` | Yük/risk/fikstür uyarı listesi — Faz 5 #14 |
| `GET` | `/admin/daily-briefing` | Rol bazlı 'bugün ne yapmalıyım' özeti — Faz 5 #15 |
| `GET` | `/admin/players/{player_id}/injury-risk` | Sakatlık risk skoru (yük + yaş + sıklık) — Faz 5 #42 |
| `POST` | `/admin/teams/{team_id}/squad-depth` | Pozisyon bazlı kadro derinliği + yaşlanma — Faz 5 #33 |
| `GET` | `/admin/teams/{team_id}/rotation-plan` | Yük periyotlama / rotasyon önerisi — Faz 5 #31 |
| `GET` | `/admin/teams/{team_id}/season-calendar` | Sezon takvimi + fikstür zorluğu — Faz 5 #30 |
| `GET` | `/admin/players/{player_id}/transfer-targets` | Benzer profilde transfer hedefleri — Faz 5 #35 |
| `GET` | `/admin/teams/{team_id}/decision-dashboard` | Karar geçmişi + isabet özeti (tüm maçlar) — Faz 5 #39 |
| `GET` | `/admin/matches/{match_id}/live-decision` | Maç-içi karar paneli (momentum/sub/tactical/risk + spatial/matchup/score-time) — Faz 6+7 |
| `POST` | `/admin/matches/{match_id}/opponent-reaction` | Rakip sub okuma + momentum kırma önerisi — Faz 6 #13/#14 |
| `POST` | `/admin/matches/{match_id}/live-risk` | Canlı kart/sakatlık/zaman riski — Faz 6 #10/#11/#12 |
| `POST` | `/admin/matches/{match_id}/set-piece` | Duran top fırsatı + penaltı atıcı durumu — Faz 7 #7/#8 |
| `POST` | `/admin/matches/{match_id}/game-friction` | Faul biriktirme + ofsayt tuzağı — Faz 7 #9/#10 |
| `POST` | `/admin/matches/{match_id}/referee-context` | Hakem eğilimi + avantaj penceresi — Faz 7 #11/#12 |
| `POST` | `/admin/analysis/what-if` | Karşı-olgu: oyuncu çıkarınca takım metriği nasıl değişir (A) |
| `POST` | `/admin/analysis/backtest` | Olasılıksal motor değerlendirme: hit-rate + Brier + kalibrasyon (B) |
| `POST` | `/admin/analysis/anomaly` | Metrik serisinde aykırı değer + form kırılması (C) |
| `POST` | `/admin/analysis/development-curve` | Gelişim eğimi + oynaklık + projeksiyon (E) |
| `GET` | `/admin/performance/protocols` | Performans test protokol kütüphanesi (nasıl yapılır + normlar) ⚠️_deprecated_ |
| `POST` | `/admin/performance/score` | Tek test sonucunu norm + kadro yüzdeliğiyle skorla ⚠️_deprecated_ |
| `POST` | `/admin/performance/battery` | Bir test gününün tüm sonuçları → atlet profili (güçlü/zayıf) ⚠️_deprecated_ |
| `POST` | `/admin/performance/progression` | Bir protokolün tarihsel serisi → gelişim + regresyon uyarısı ⚠️_deprecated_ |
| `POST` | `/admin/performance/workload` | ACWR (sakatlık riski) + monotony/strain — günlük yük serisinden ⚠️_deprecated_ |
| `POST` | `/admin/performance/assess-change` | Yeni ölçüm bireysel baseline'a göre ANLAMLI mı (SWC) — gürültü filtresi |
| `POST` | `/admin/performance/gps-load` | GPS/wearable seansı → iç-yük (AU, ACWR'ye beslenir) — sports science |
| `POST` | `/admin/performance/wellness` | Subjektif wellness anketi → readiness skoru — sports science |
| `GET` | `/admin/compliance/access-log` | KVKK denetim izi — bir oyuncunun verisine kim erişti (DPO için) |
| `GET` | `/admin/compliance/audit` | Olağandışı toplu hassas-veri erişimi (olası sızıntı) tespiti |

## Auth (login/refresh/me)  
`app/api/auth.py`

| Method | Path | Açıklama |
|--------|------|----------|
| `POST` | `/auth/login` |  |
| `POST` | `/auth/refresh` |  |
| `POST` | `/auth/logout` |  |
| `GET` | `/auth/me` |  |

## HTML görünümler  
`app/api/html_views.py`

| Method | Path | Açıklama |
|--------|------|----------|
| `GET` | `/matches/{match_id}/game-plan` | Birleşik game-plan ekranı (Faz 5 #29) |
| `GET` | `/matches/{match_id}/warmup` | Kickoff -60 dk hazırlık checklist (Faz 5 #26) |
| `GET` | `/matches/{match_id}/live` | Canlı maç izleyici (WebSocket-tüketici sayfa) |
| `GET` | `/matches/{match_id}/voice-notes` | Maç-içi sesli not + hızlı tag (Faz 5 #20) |
| `GET` | `/teams/{team_id}/dashboard` | Takım merkezli landing sayfası (Faz 5 #15) |
| `GET` | `/players/{player_id}/dashboard` | Oyuncu gelişim trendi sayfası (Faz 5 #36) |
| `GET` | `/teams/{team_id}/decisions-dashboard` | Karar geçmişi + isabet dashboard'u (Faz 5 #39, Faz 8 #4) |
| `GET` | `/roles/{role}/dashboard` | Rol bazlı landing dashboard composer (Faz 5 #17) |

## Canlı maç  
`app/api/live.py`

| Method | Path | Açıklama |
|--------|------|----------|
| `GET` | `/ws/active-connections` |  |

## Canlı VAEP  
`app/api/live_vaep.py`

| Method | Path | Açıklama |
|--------|------|----------|
| `GET` | `/matches/{match_id}/live-vaep` |  |

## Notlar  
`app/api/notes.py`

| Method | Path | Açıklama |
|--------|------|----------|
| `POST` | `/notes` |  |
| `GET` | `/notes` |  |
| `GET` | `/notes/{note_id}/replies` |  |
| `DELETE` | `/notes/{note_id}` |  |

## Bildirimler  
`app/api/notifications.py`

| Method | Path | Açıklama |
|--------|------|----------|
| `GET` | `/admin/notifications/status` |  |
| `POST` | `/admin/notifications/test` |  |

## Fiziksel test / yük riski (B)  
`app/api/physical_tests.py`

| Method | Path | Açıklama |
|--------|------|----------|
| `POST` | `/physical-tests/` |  |
| `GET` | `/physical-tests/players` |  |
| `GET` | `/physical-tests/{player_id}` |  |
| `GET` | `/physical-tests/{player_id}/risk` |  |
| `GET` | `/physical-tests/{player_id}/trend` |  |
| `GET` | `/physical-tests/{player_id}/pdf` |  |
| `DELETE` | `/physical-tests/{test_id}` |  |

## Maç planı  
`app/api/plan.py`

| Method | Path | Açıklama |
|--------|------|----------|
| `POST` | `/matches/{match_id}/plan` |  |
| `GET` | `/matches/{match_id}/plan/vs-live` |  |

## Raporlar (PDF/paylaşım)  
`app/api/reports.py`

| Method | Path | Açıklama |
|--------|------|----------|
| `GET` | `/reports/agent-outputs/{output_id}/pdf` |  |
| `GET` | `/reports/agents/{agent_name}/{subject_type}/{subject_id}/pdf` |  |
| `POST` | `/reports/performance/pdf` |  ⚠️_deprecated_ |
| `POST` | `/reports/agent-outputs/{output_id}/share` |  |

## Paylaşılan  
`app/api/shared.py`

| Method | Path | Açıklama |
|--------|------|----------|
| `GET` | `/shared/reports/{token}` |  |

## Sözleşme/rehab  
`app/api/sprint3.py`

| Method | Path | Açıklama |
|--------|------|----------|
| `GET` | `/players/contract-alerts` |  |
| `GET` | `/players/transfer-targets` |  |
| `POST` | `/players/{player_id}/rehab` |  |
| `GET` | `/players/{player_id}/rehab/active` |  |

## Sprint 4  
`app/api/sprint4.py`

| Method | Path | Açıklama |
|--------|------|----------|
| `GET` | `/players/youth` |  |
| `POST` | `/players/{player_id}/goals` |  |
| `GET` | `/players/{player_id}/goals` |  |
| `PATCH` | `/players/{player_id}/goals/{goal_id}` |  |

## Sprint 5  
`app/api/sprint5.py`

| Method | Path | Açıklama |
|--------|------|----------|
| `POST` | `/formations/matchup` |  |
| `POST` | `/formations/best-against` |  |
| `POST` | `/teams/{team_id}/goals` |  |
| `GET` | `/teams/{team_id}/goals` |  |
| `PATCH` | `/teams/{team_id}/goals/{goal_id}` |  |
