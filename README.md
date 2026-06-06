# football-intelligence

Spor zekası platformu — futbol teknik ekiplerine veriyle karar desteği veren sistem.
Bugün: futbol verisi (API-Football) çek, doğrula, depola, sun.
Yarın: tracking, tahmin, otomasyon. Sonra: diğer sporlar.

> **Production state:**
> [`PILOT_ENGINES.md`](PILOT_ENGINES.md) — **19 production-grade engine**
> gerçek La Liga 2018/19 (34 maç, 85k event) ile sinyal/gürültü auditten geçti.
> 36 engine niche/spesifik kullanım için. VAEP 68k event üzerinde tabular
> trained.

> **Frontend yol haritası:**
> [`DESIGN.md`](DESIGN.md) — tasarım sistemi (FM 2010-15 koyu tema, token, komponent spec).
> [`PROMPT_FRONTEND_FAZ2.md`](PROMPT_FRONTEND_FAZ2.md) ✅ **tamamlandı** (commit `ad69e2b`) — layout shell + 4 komponent + 4 sayfa.
> [`PROMPT_FRONTEND_FAZ3.md`](PROMPT_FRONTEND_FAZ3.md) ✅ **tamamlandı** (commit `9b34166`) — auth refresh + WS reconnect + observability + E2E.
> [`PROMPT_FRONTEND_FAZ4.md`](PROMPT_FRONTEND_FAZ4.md) ✅ **tamamlandı** (commit `b8f01b9`) — 4 saha-içi sayfa + MiniPitch + SetPieceZoneMap.
> [`PROMPT_BACKEND_LOAD_THRESHOLD.md`](PROMPT_BACKEND_LOAD_THRESHOLD.md) ✅ **tamamlandı** (commit `2fa05a8`) — engine.load eşik parametrikleşmesi.

## Mimari prensipler
- **Gevşek bağlı katmanlar.** Bağımlılık tek yönlü: `api → ai → engine → domain`.
  `engine/` saf hesap; API/DB/LLM bilmez.
- **Veri kaynakları soyut.** Her kaynak `DataSource` arayüzüne uyan bir adapter.
  Yeni kaynak = yeni adapter, çekirdek değişmez.
- **Sporlar parametrik.** `"football"` stringi koda gömülmez; `sports/football.py`
  sportif sabitleri tutar.
- **Hiçbir veri doğrulanmadan DB'ye girmez.** `data/validation/` kapı bekçisi.
- **Açıklanabilirlik baştan.** Her motor çıktısı `audit/` üzerinden gerekçesini taşır.
- **İleriye hazır, ama bugün over-engineer yok.** Boş iskeletler yer tutar,
  içleri ilgili faz gelince dolar.

## Klasörler — bir bakışta
| Klasör | Faz | Görev |
|---|---|---|
| `app/core/` | 1 | config, logging, ortak yardımcılar |
| `app/core/usage/` | 1 | API çağrı / token sayacı, kota koruması |
| `app/domain/` | 1 | spordan bağımsız temel modeller |
| `app/db/` | 1 | SQLAlchemy modelleri + Alembic |
| `app/data/sources/` | 1 | veri kaynağı adapter'ları (api_football) |
| `app/data/cache/` | 1 | API yakmamak için cache |
| `app/data/validation/` | 1 | DB'ye yazmadan önce kontrol |
| `app/data/ingest/` | 1 | çek → doğrula → normalize → yaz |
| `app/snapshot/` | 1 | zaman içinde durum kaydı (tahmin yakıtı) |
| `app/api/` | 1 | FastAPI endpoint'leri |
| `app/sports/` | 1 (football) | spor tanımları, parametrik sabitler |
| `app/engine/form\|load\|rating\|opponent/` | 2 | saf analiz fonksiyonları |
| `app/audit/` | 2 | "neden bunu önerdi" izi |
| `app/ai/` | 3 | Claude yorum katmanı |
| `app/scheduler/` | ileri | zamanlanmış sync |
| `app/engine/tracking/` | 6 | tracking analizi |
| `app/data/sources/tracking.py` | 6 | tracking adapter |
| `app/engine/predict/` | ufuk 3 | ML tahmin |
| `app/agents/` | ufuk 3 | otomasyon |
| `app/sports/<diğer>` | ufuk 4 | basketbol/voleybol |

## Kurulum
```bash
python -m venv venv
source venv/bin/activate            # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                # DATABASE_URL'i doldur
alembic upgrade head                # tabloları oluştur
```

`.env` notları:
- `DATABASE_URL` zorunlu (yerel: Postgres ya da test için `sqlite:///./dev.db`).
- `API_FOOTBALL_KEY` boşsa `USE_FIXTURES=true` yap; adapter
  `tests/fixtures/*.json` üzerinden okur, API'ye dokunmaz.
- `API_FOOTBALL_DAILY_LIMIT` / `MONTHLY_LIMIT` ile kota koruması;
  `core/usage` her gerçek HTTP çağrısını sayar, eşiğe yaklaşınca uyarır,
  aşınca `QuotaExceeded` fırlatır.
- `API_AUTH_KEY` production'da set edilmeli. İstemciler `X-API-Key: <değer>`
  header'ında gönderir. Boş ise auth devre dışı (dev). `/health` her zaman açık.

## Auth — JWT + multi-tenant (Ufuk 1)

**İki kulüp aynı deploy'da yan yana**, veri izole. JWT bearer token + tenant ContextVar
loader_criteria ile her ORM query otomatik tenant_id'ye filtrelenir.

```bash
# 1) Login → token pair
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@konyaspor.com","password":"...","tenant_slug":"konyaspor"}'
# → {"access_token":"eyJ...","refresh_token":"abc...","token_type":"bearer"}

# 2) Korumalı endpoint'lere Authorization header'ı
curl http://localhost:8000/teams -H "Authorization: Bearer eyJ..."

# 3) Token expired → refresh
curl -X POST http://localhost:8000/auth/refresh \
  -d '{"refresh_token":"abc..."}'
# → yeni token pair. Eski refresh REVOKED (rotation güvenlik).

# 4) Logout (refresh revoke)
curl -X POST http://localhost:8000/auth/logout -d '{"refresh_token":"abc..."}'

# 5) Current user info
curl http://localhost:8000/auth/me -H "Authorization: Bearer eyJ..."
```

**Roller:** `admin | analyst | coach | viewer`. Admin tüm endpoint'lere erişir;
analyst/coach/viewer'a `require_role(["admin"])` korumalı endpoint'ler 403 döner.

**Backward-compat:** `BACKWARD_COMPAT_API_KEY` set'liyse `X-API-Key: <değer>` hâlâ
kabul edilir ve default tenant + admin user'a map edilir — eski entegrasyonlar
kırılmaz.

## Çalıştırma
```bash
# 0) Uçtan uca demo (fixture; anahtar gerekmez) — her şey nasıl çalışıyor?
python scripts/demo.py --reset

# 1) Bir lig + sezonu çek, doğrula, DB'ye yaz, snapshot al
python scripts/sync_league.py --league 203 --season 2024

# 2) API'yi ayağa kaldır
uvicorn app.api.main:app --reload
# Okuma (Faz 1):
#   GET /health
#   GET /leagues
#   GET /teams/{league_id}                      # liglerde görünen takımlar
#   GET /teams/{team_id}/matches                # takım maçları
# Analiz (Faz 5; ?explain=true ile Claude yorumu — ANTHROPIC_API_KEY yoksa stub):
#   GET /teams/{team_id}/form?last_n=5
#   GET /teams/{team_id}/rating?last_n=10
#   GET /teams/{a}/vs/{b}                       # head-to-head
#   GET /matches/{match_id}/preview?last_n=5    # ev+dep form + H2H, kickoff öncesi
# Operasyonel (admin):
#   GET /admin/jobs?since_hours=24&status=failed
#   GET /admin/usage                            # source başına call + token
#   GET /admin/snapshots?scope=...
#   GET /admin/db-stats                         # tablo boyutları

# 3) Scheduler — kayıtlı bir job'u çalıştır (dış cron buradan tetikler)
python scripts/run_job.py --list
python scripts/run_job.py sync_league --league 203 --season 2024
# Cron örneği: 0 6 * * * cd /opt/manager2 && venv/bin/python scripts/run_job.py sync_league --league 203 --season 2024
```

## Test
```bash
pytest -q
```
Testler in-memory SQLite ile çalışır; gerçek DB veya API anahtarı gerekmez.

## Taktiksel Engine Envanteri (88 modül)

Saf-Python pure-compute engine'ler, hepsi multi-tenant + audit'li.
Tükettiği veri: `events` tablosu (PassEvent, Carry, DefensiveAction, Shot).

**Form/predict (16 modül — pre-Faz N):**
form, rating, opponent, predict, predict_ml, schedule, matchup,
fixture_difficulty, load, tracking, calibration, formation_matcher,
set_piece, xg, player_form, player_similarity.

**Faz N — temel taktiksel (8 modül):**
xt (Karun Singh 12×8), xa, ppda, field_tilt, player_role (8-rol typoloji),
xg_match_graph, build_up_pattern, match_phase + score_state_effects.

**Wave 2 — derinleştirme (7 modül):**
pressing_trigger, defensive_line, compactness, transition,
channel_preference, press_resistance, set_piece_zones.

**Wave 3 — Opta-tarz profesyonel (13 modül):**
cross_effectiveness, cutback_frequency, off_ball_runs, final_third_entries,
defensive_duels, recovery_zone_heat, counter_press_triggers, direct_play,
possession_quality, tempo, overperformance, progressive_passes,
carries_into_final_third.

**Composite (2 modül):**
match_dominance (5-bileşen tek skor), coaching_identity (8-boyut + 5 arketip).

**VAEP — possession value (1 modül, swap-edilebilir):**
v1-baseline (xT heuristic) + v2-tabular (events tablosundan train edilmiş
zone-bin lookup). `POST /admin/vaep/train` çağrısıyla v2'ye geç.

**Faz 5 Sprint — kadro + karar destek (15 modül):**
available_squad, squad_depth, rotation_plan, injury_risk, fatigue_signal,
matchup_grid, opponent_weakness, pass_alternatives, proactive_alerts,
set_piece_pattern_history, set_piece_routine, substitution_chess,
tactical_trend, live_shape_drift, live_sub_recommendation.

**Faz 6 — maç-içi karar (5 modül):**
momentum_tracker (momentum meter + pres kırılma + xG swing),
sub_timing (optimal timing + etki + paket), live_tactical_trigger
(formation switch + press height + kanal kayması), live_risk_monitor
(kart + sakatlık + zaman yönetimi), opponent_reaction (rakip sub tepkisi +
momentum kırma).

**Faz 7 — mekânsal/bireysel/bağlam (6 modül):**
spatial_control (boşluk haritası + sayısal üstünlük + genişlik/darlık),
live_matchup (düello kaybeden + sıcak el + yıldız besle), set_piece_timing
(köşe/faul fırsat + penaltı atıcı durumu), game_friction (faul biriktirme +
ofsayt tuzağı), referee_context (hakem eğilimi + avantaj penceresi),
score_time_matrix (kapanış reçetesi + risk/getiri eşiği).

> Faz 6+7 engine'leri event-window proxy ile çalışır (replay modu); gerçek
> canlı feed gelince adapter swap edilir, engine kodu değişmez.

**Faz 8 — bağlam & güven katmanı / orkestra şefi (4 modül):**
context_engine (tüm sinyalleri tek "şimdi şunu yap" önceliğine indirger),
confidence (her öneriye 0-1 güven skoru + "neden?" sürücüleri), signal_quality
(gürültü/yetersiz-örnek/ısınma filtresi — yanlış alarmı eler), match_memory
(maç-içi hafıza: momentum dönüşü + kanat düşüşü + rakip değişimi bağlantısı).
Karar audit trail `decisions` tablosunda outcome + feedback loop ile kapanır.

> **Pipeline:** 8 ham sinyal → signal_quality süz → confidence skorla →
> match_memory zaman-bağlamı → context_engine tek karar → decision outcome
> geri besleme. `live-decision` ve WebSocket artık tek `context` başlığı döner.

**Faz 10 — canlı güven + zeka + proaktif uyarı (7 modül):**
live_confidence (canlı sinyal güven skoru + `summarize_trend` zamansal yön),
data_quality (event-akışı kalite skoru: dropout/seyrek/bayat/eksik-tip),
what_if (karşı-olgu: oyuncu çıkarınca metrik + en güvenli/maliyetli sıralama),
backtest (olasılıksal motor değerlendirme: hit-rate + Brier + kalibrasyon),
anomaly (z-skor aykırı değer + form kırılması), development_curve (gelişim
eğimi + oynaklık + projeksiyon), live_alerts (maç-içi proaktif uyarı:
momentum kırılması/yük/kart/veri-kalitesi + dedup).

**Sports Science — performans testi (1 modül):**
performance_test (CMJ/30m sprint/YoYo IR1/T-test/RSA protokol kütüphanesi +
norm-rating + kadro yüzdeliği + gelişim/regresyon yorumu + **SWC/bireysel
baseline** ölçüm-gürültüsü filtresi), workload (**ACWR** sakatlık riski + monotony/strain), gps_load (GPS/wearable
seans → iç-yük AU, ACWR'ye beslenir), wellness (subjektif anket → readiness). API: `/admin/performance/{protocols,score,battery,
progression,workload,assess-change}`.
Ayrıca `confidence` 5 yüksek-görünürlüklü motora bağlandı (form, rating,
predict, matchup, opponent_weakness) → API yanıtlarında `confidence`.

> **Canlı snapshot anahtarları (Faz 8+10):** `context` (+`confidence_note`),
> `confidence`, `trend`, `data_quality`, `live_alerts` — hepsi additive,
> geriye uyumlu.

## Batch Tactical Endpoints

```
GET /admin/teams/{id}/tactical-profile?last_n=10[&opponent_id=22]
    → 19+ engine birleşik (PPDA, pres, hat, kompakt, transition, kanal,
      xT, build_up, vs.) + opponent_id varsa field_tilt + coaching_identity

GET /admin/players/{id}/tactical-profile?last_n=10
    → 8 engine (xT, xA, press_resistance, overperformance, prog_passes,
      carries, off_ball_runs, vaep)

GET /admin/matches/{id}/dominance
    → match_dominance + match_phases (home/away ayrı)

POST /admin/vaep/train?min_samples=100
    → events tablosundan tabular model train + cache'e yaz

GET /admin/teams/{id}/tactical-trend?last_n=10
    → 5 metric × N maç zaman serisi + slope + biggest_shift

GET /admin/players/{id}/tactical-trend?last_n=10
    → 5 oyuncu metriği zaman serisi (xT/90, xA/90, VAEP/90, prog/90, press_res)

GET /admin/matches/{id}/halftime-brief?my_team_id=N
    → Devre arası: PPDA, dominance, opponent_weakness, fatigue_alerts,
      set_piece_pattern, sub_recommendations, AI brief (200-220 kelime)

GET /admin/halftime-brief-history?match_id=N
    → Kayıtlı brief'lerin listesi (agent_outputs)

GET /admin/teams/{id}/set-piece-pattern-history?last_n=5
    → Canlı maç alert: "Son 5 maçta 8 set-piece şutunun 5'i kale ağzına gitti"

GET /admin/matches/{id}/live-sub-recommendation?my_team_id=N&current_minute=70
    → Top 3 sub önerisi (fatigue + skor + dakika), Türkçe nedenler

POST /admin/tactical-cache/clear
    → tactical_profile cache temizle (event ingest sonrası)
```

**Maç-içi karar paneli (Faz 6+7):**
```
GET /admin/matches/{id}/live-decision?my_team_id=N&current_minute=70
    [&star_player_id=N&draw_is_enough=bool&must_win=bool]
    → 8 engine birleşik tek panel: momentum + sub_timing + tactical_triggers
      + risk_monitor (Faz 6) + spatial_control + live_matchup +
      score_time_matrix (Faz 7)

POST /admin/matches/{id}/opponent-reaction?my_team_id=N&current_minute=70&momentum_score=-0.5
    → Rakip sub okuma + momentum kırma önerisi (#13/#14)
      payload: {"opponent_subs": [{position_in, minute}]}

POST /admin/matches/{id}/live-risk?my_team_id=N&current_minute=80
    → Kart + sakatlık flag + zaman yönetimi (#10/#11/#12)
      payload: {"player_states": [{player_id, yellow_card?, duel_count?, fatigue?}]}

POST /admin/matches/{id}/set-piece?my_team_id=N&current_minute=70
    → Duran top fırsat rutini + penaltı atıcı durumu (Faz 7 #7/#8)
      payload: {"set_piece_won", "opponent_weak_zones", "penalty_taker"}

POST /admin/matches/{id}/game-friction?my_team_id=N&current_minute=70
    → Faul biriktirme bölgesi + ofsayt tuzağı riski (Faz 7 #9/#10)
      payload: {"opponent_foul_zones": [...]}

POST /admin/matches/{id}/referee-context?my_team_id=N&current_minute=50
    → Hakem eğilimi + avantaj penceresi (Faz 7 #11/#12)
      payload: {"cards_per_game", "fouls_per_game", "opponent_card_edge_players"}
```

**Bağlam & feedback (Faz 8):**
```
GET /admin/matches/{id}/live-decision...
    → yanıta "context" eklendi: tek karar (primary + secondary + suppressed
      + güven skoru + birleşik gerekçe) ve "match_memory" (aktif thread'ler)

POST /admin/decisions/{decision_id}/outcome
    → Kararın sonucunu işle (positive|negative|neutral) — feedback loop
      payload: {"outcome", "outcome_value"?, "outcome_notes"?}

GET /admin/teams/{id}/decisions/feedback
    → decision_type bazlı geçmiş isabet oranı → güven skorunu kalibre eder
```

## Canlı Maç (WebSocket)

```
ws://host/ws/matches/{id}/live?my_team_id=N&interval_seconds=10&max_minute=90
    → Her N saniyede tactical snapshot push:
      PPDA + dominance + sub_recommendation + opponent_shape_drift
      + Faz 6: momentum + sub_timing + tactical_triggers
      + Faz 7: spatial_control + live_matchup + score_time_matrix
      + Faz 8: context (orkestra şefi — tek "şimdi şunu yap" başlığı)
      + Faz 10: confidence + trend + data_quality + live_alerts
    → match_ended mesajıyla kapanır

GET /ws/active-connections
    → Aktif WebSocket sayısı (observability)
```

Frontend: `/matches/{id}/live?my_team_id=N` — touch-line tablet için
canlı dashboard. WebSocket'i kullanır; 5sn'de bir güncellenir.

## Production Event Ingest (StatsBomb Open)

```bash
# Tek maç — Barcelona vs Sevilla, La Liga 2018/19
python -m scripts.ingest_statsbomb_events --tenant t-default --match 16029

# Bir takımın son 10 maçı
python -m scripts.ingest_statsbomb_events --tenant t-default --team 611 --limit 10

# Uçtan uca demo (gerçek match ingest + 14 engine analizi)
DATABASE_URL="sqlite:///demo.db" python -m scripts.demo_real_statsbomb
```

Çıktı: `events` tablosu dolu, `/admin/teams/{id}/tactical-profile` artık
gerçek sayılar döner. Frontend `/teams/{id}/tactical` sayfasında 20+ metric
+ 3 recharts grafik (kanal tercihi, recovery zone, coaching identity radar).

## Deployment
Docker Compose + Postgres ya da bare-metal systemd + cron kurulumu için
[DEPLOYMENT.md](DEPLOYMENT.md).

Detaylı yol haritası: [ROADMAP.md](ROADMAP.md).
