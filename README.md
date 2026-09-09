# football-intelligence

Spor zekası platformu — futbol teknik ekiplerine veriyle karar desteği veren sistem.
Bugün: futbol verisi (API-Football) çek, doğrula, depola, sun.
Yarın: tracking, tahmin, otomasyon. Sonra: diğer sporlar.

## 🚀 Canlıya alma (~3 dakika)

Frontend (ekranlar) Vercel'de canlı. Backend'i (veri sunucusu + DB) açmak için:

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/ahyazgan/tactic11)

1. **Render:** Yukarıdaki düğmeye bas → Render'a giriş yap → repoyu seç → **Apply**.
   `render.yaml` blueprint'i Postgres + API servisini kurar; migration + demo seed
   **otomatik** çalışır. Servis "Live" olunca URL'i kopyala
   (`https://tactic11-api-xxxx.onrender.com`).
2. **Vercel:** Projen → **Settings → Environment Variables** → ekle:
   `API_BASE_URL = <Render URL'i>` *(sonunda `/` YOK)* → **Deployments → Redeploy**.
3. **Giriş:** `admin@besiktas-demo` / `demo-password-1234` → ekranlar gerçek veriyle dolar.

> Düğme repoyu Render'a bağlamak için GitHub yetkisi isteyebilir. Detay:
> [`DEPLOYMENT.md`](DEPLOYMENT.md).

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
# Cron örneği: 0 6 * * * cd /opt/tactic11 && venv/bin/python scripts/run_job.py sync_league --league 203 --season 2024
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
progression,workload,assess-change,gps-load}`.

**KVKK / hassas veri uyumu (1 modül):**
Oyuncu sağlık/performans/GPS/wellness verisi KVKK'da **özel nitelikli kişisel
veri**. `engine/compliance` (saf): `classify_sensitivity`
(ozel_nitelikli/kisisel/genel) + `detect_access_anomalies` (sliding-window;
kısa pencerede çok sayıda özneye toplu erişim → olası sızıntı). Persistans:
`DataAccessLog` tablosu (multi-tenant, auto-fill) + `record_data_access`
helper. API: `/admin/compliance/{access-log,audit}` (DPO denetimi).

**Teslim — PDF rapor + tablet veri-girişi:**
`reports/build_performance_report_pdf` → `POST /reports/performance/pdf`:
batarya skorları (renk-kodlu norm), güçlü/zayıf alan, gelişim eğilimi +
regresyon uyarısı, KVKK dipnotu (reportlab yoksa 503; export erişim loguna
`action=export_pdf` ile yazılır). Frontend `/performance`: saha/lab için büyük
dokunma hedefli veri-giriş ekranı — protokol seçimi + nasıl-yapılır, anlık
değerlendirme, tek dokunuşla PDF indir.

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

## Karar Etkisi (post-match learning)

Koçun maç-içi hamleleri `decisions` tablosuna yazılıyor; `engine.decision_impact`
her kararın **öncesi/sonrası** penceresini ölçüp etkiyi sayıya döker:

- Pencereler maç sonuna kırpılır ve metrikler **dakika başına** normalize edilir
  (88. dk kararının 2 dakikalık "sonrası"ı 15 dakikayla kıyaslanmasın).
- Ölçülenler: xG farkı, xT, şut, gol, saha eğimi (hücum üçte-biri pas payı).
- Hüküm: `positive` / `negative` / `neutral` / `insufficient_data`; güven pencere
  uzunluğu ve olay yoğunluğundan gelir.

| Uç | İş |
|---|---|
| `GET /admin/matches/{id}/decisions/learning` | maçtaki her kararın ölçümü |
| `POST /admin/matches/{id}/decisions/auto-outcome` | ölçümü `outcome` alanına yazar (elle girilenleri ezmez) |
| `GET /admin/teams/{id}/decisions/track-record` | karar defteri: tip + dakika bandı kırılımı, en iyi/en kötü |

Yazılan sonuçlar `decisions/feedback` üzerinden `context_engine` güven skorunu
kalibre eder: sistem bu koçun hangi tip hamlesinin işe yaradığını öğrenir.
Arayüz: **Karar Takip** sayfasında "Ölçülen Etki" bölümü (`Ölç ve kaydet` düğmesi).

Ölçüm vekildir, nedensellik kanıtı değil — skor durumu, kart ve rakip hamlesi de
aynı pencerede etkilidir; arayüz bunu açıkça yazar.

## Video Takibi (saha overlay için ikinci kaynak)

Klip → RF-DETR (Apache-2.0) tespit → ByteTrack takip → forma rengi takım ataması → saha
homografisi → `TrackingFrame`. Çıktı StatsBomb 360 ile **aynı şemaya** yazılır; `/tracking`
API'si ve Saha Overlay kaynağı ayırt etmez.

**Ortam:** ağır bağımlılıklar ayrı bir yorumlayıcıda (`venv-cv`, Python 3.12):

```bash
py -3.12 -m venv venv-cv
venv-cv\Scripts\python.exe -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
venv-cv\Scripts\python.exe -m pip install rfdetr supervision opencv-python-headless "scipy==1.15.3"
venv-cv\Scripts\python.exe -m pip install "rfdetr[train]"   # yalnız ince ayar için
```

> Windows Smart App Control açıkken çok yeni scipy derlemeleri engellenebilir; `scipy==1.15.3` sabit tutuldu.

**Akış (arayüz):** `/video-tracking` → klip yükle → `/video-tracking/calibrate` ile karede 4+ saha
işaretine tıkla (çizgiler kareye geri-izdüşülür, hata metre cinsinden) → "Video işle" → iş
bitince maç listeye düşer. Backend: `app/api/tracking_jobs.py` (`venv-cv` alt süreç + ingest).

**Akış (CLI):**

```bash
venv-cv\Scripts\python.exe -m scripts.track_video --video clip.mp4 \
  --calibration data/tracking/calibrations/saha.json --out data/tracking/out/frames.json \
  --match-id 990001 --home-team 9001 --away-team 9002 --fps 5 --track-fps 15 \
  --weights data/tracking/models/rfdetr_top_small --tiles 6 --threshold 0.3 --ball-threshold 0.3 \
  --preview data/tracking/out/preview.mp4
venv\Scripts\python.exe -m scripts.ingest_tracking_json --json data/tracking/out/frames.json --tenant t-default
```

**İnce ayar:** `scripts/build_topview_dataset.py` (TeamTrack klipleri → dilimli COCO; kamera başına
farklı `--tiles` ile `--append`) + `scripts/train_topview_detector.py` (RF-DETR small, 8 epoch).
Varsayılan ağırlık `data/tracking/models/rfdetr_mixed_small` (drone + yan açı karma, 39 dk RTX 5060);
yoksa `rfdetr_top_small`. Ağırlıklar repoya girmez.

Tespit ölçümü (TeamTrack, eğitim dışı klipler, 5 kare/kamera, eşik 0.3):

| Model | Drone 4K recall/prec | Yan açı 6500×1000 recall/prec |
|---|---|---|
| COCO ön-eğitimli | 0.77 / 0.85 | 1.00 / 0.61 (saha dışı insanlar) |
| Yalnız drone ince ayar | 1.00 / 0.96 | 0.63 / 0.70 |
| **Karma (drone + yan açı)** | **1.00 / 0.96** | **0.97 / 0.94** |

Tam hat (drone klibi, GT'ye karşı, karma model): oyuncu recall 0.995 / precision 0.995,
konum hatası 0.20 m, kare başına 22.0/22 oyuncu, top 3 m içinde 0.83, 30 sn klip ≈ 224 sn.

Ortam değişkenleri: `TRACKING_DATA_DIR`, `TRACKING_WORKER_PYTHON`, `TRACKING_WEIGHTS`
(`TRACKING_WORKER_CMD` testler için işçi stub'ı).

**Kimlik eşleme:** video takibinde oyuncular `30000+track_id` sentetik id'siyle gelir.
Video Analiz sayfasındaki *Kimlik eşleme* tablosunda takibi oyuncuya bağlarsın
(`PUT /tracking/matches/{id}/identities`); kareler servis edilirken isim/forma uygulanır
ve overlay'de `identity_estimated=false` olarak görünür. Takip listesi:
`GET /tracking/matches/{id}/tracks` (kare sayısı, süre aralığı, ortalama hız, topla geçen
kare, ortalama bölge — hangi takibin kim olduğunu ayırt etmeye yarar).

**Kamera tipi ve dilimleme:** `--tiles` yükseklik ekseninde dilim sayısıdır; sütun
sayısı görüntü oranından hesaplanır (dilimler eğitim oranına yakın kalır). 16:9 drone/
taktik kamerada `--tiles 6` (dilim 640×360), panoramik yan-açıda (örn. 6500×1000)
`--tiles 4` (dilim ~433×250) iyi sonuç verir. Panoramik **fisheye birleştirme** uyarısı:
tek düzlemsel homografi bu görüntülerde tam oturmayabilir (yakın taç çizgisi kadraj
dışındaysa daha da zor) — kalibrasyon ekranındaki geri-izdüşüm hatası bunun ölçüsüdür;
2 m üstündeyse ya daha çok/yayılmış nokta seç ya da distorsiyonu giderilmiş akış kullan.

**Takım şekli & pres:** `GET /tracking/matches/{id}/shape?minute=&window=` — `engine.tracking`
(v2) pozisyon karelerinden genişlik / derinlik / kompaktlık / hat konumları / yerleşim
tahmini ve rakip topa sahipken pres endeksi üretir. Kaynak ayırt edilmez (360 ya da video);
kamera dışı oyuncular sayılmaz, bu yüzden yerleşim yalnız kadro görünür + tutarlıyken yazılır.

### Canlı maç: segment akışı → maç-içi karar paneli

Klip sonrası işlemeye ek olarak video **maç sırasında** okunabilir. Kamera/encoder
klasöre segment yazar, `scripts/track_live.py` klasörü izler; her yeni segmenti takip
hattından geçirip kareleri **aynı maça ekler** (`ingest_tracking_json --append`).
Canlı karar paneli o kareleri okuyup pozisyon sinyali üretir.

```bash
# kulüp tarafında (kamera → segment)
ffmpeg -i rtsp://kamera -c copy -f segment -segment_time 30 -reset_timestamps 1 \
  data/tracking/live/seg_%04d.mp4

# bizim tarafta (izleyici)
venv-cv\Scripts\python.exe -m scripts.track_live --watch data/tracking/live \
  --calibration data/tracking/calibrations/saha.json \
  --match-id 990100 --home-team 611 --away-team 612 --tenant t-default \
  --segment-seconds 30 --weights data/tracking/models/rfdetr_mixed_small \
  --database-url "postgresql+psycopg://..."
```

Segment → dakika eşlemesi ada göre sırayla yapılır (`--start-minute` ile kaydır,
ya da dosya adından `--minute-from-name 'min_(\d+)'` ile oku). İşlenen segmentler
`<watch>/.track_live_state.json` içinde tutulur → yeniden başlatınca kaldığı yerden
devam eder. **Ingest başarısız olursa segment "işlendi" sayılmaz**, 3 kez yeniden
denenir (DB geçici düşerse kare kaybı olmasın). CV `venv-cv`'de, DB yazımı ana
`venv`'de koşar (`--ingest-python`); `--database-url` ingest alt sürecine geçirilir.

**Sıcak model:** izleyici varsayılan olarak modeli bir kez yükleyip segmentleri
aynı süreçte işler (`--isolate` eski davranışa döner). Dedektör ilk karede batch'ini
sabitleyip fp16 derlediği için sıcak model yalnız aynı çözünürlükte geçerlidir;
kaynak çözünürlük değişirse model otomatik yeniden kurulur.

**Takım kimliği çapası:** her segment ayrı fit edildiğinden, takım kimliği "en
kalabalık küme" kuralıyla verilirse segmentler arası **yer değiştirebilir** (kadraja
giren oyuncu sayısı değişir) — o zaman "rakip daraldı" sinyali yanlış takımı gösterir.
İlk segmentte bulunan forma renkleri çapa olarak sabitlenir, sonraki segmentler
kimliği renge göre eşler (`TeamAssigner.fit(anchor_colors)`).

**Gerçek zaman: henüz yetişmiyor (ölçüldü, RTX 5060, 4K 3840×2160).** Aynı 3 segment,
`--threshold 0.3`, ince ayarlı `rfdetr_mixed_small`:

| girdi | ayar | süre (8.4/5.0 sn video) | gerçek zaman katı | oyuncu/kare |
|---|---|---|---|---|
| 4K | `tiles 6`, `track-fps 15`, ayrı süreç | 63 / 43 sn | ~7.5–8.6× | **22.0** |
| 4K | `tiles 6`, `track-fps 15`, sıcak model | 50 / 29 sn | ~5.8–6.0× | **22.0** |
| 4K | `tiles 4`, `track-fps 15`, sıcak model | 50 / 32 sn | ~6.0–6.4× | **22.1** |
| 4K | `tiles 6`, `track-fps 5`, sıcak model | 32 / 19 sn | ~3.8× | 9.9–13.2 ✗ |
| 4K | `tiles 4`, `track-fps 5`, sıcak model | 19 / 15 sn | ~2.3–3.0× | 11.5–14.3 ✗ |
| **1080p** | **`tiles 4`, `track-fps 15`, sıcak model** | **35 / 22 sn** | **~4.2–4.4×** | **21.7** |

**Önerilen canlı ön ayar: 1080p girdi + `--tiles 4 --track-fps 15`.** Başlangıç
noktasına göre **~2 kat hızlı, tespit kalitesi aynı** (22.0 → 21.7 oyuncu/kare).
1080p'ye inerken kalibrasyon piksel noktaları da yarıya bölünmeli.

Ölçümden çıkan sonuçlar:

1. **Sıcak model kararlı durumda %21–33 kazandırıyor** (segment başına ~30-40 sn'lik
   model yükleme/derleme gidiyor) — ama tek başına gerçek zamanı çözmüyor.
2. **`track-fps` kaliteyi belirleyen ayar, ona dokunma.** 15 → 5 düşürmek kare başına
   22 oyuncudan ~11'e indiriyor, yani takımın yarısı kayboluyor. Sebep filtre değil
   (`min_track_seconds` düşük fps'te daha gevşek): 0.2 sn'de oyuncu çok yol aldığı
   için ByteTrack'in IoU eşleşmesi kopuyor, takipler tek karelik parçalara bölünüp
   gürültü olarak eleniyor. `engine.tracking_signals` en az 8 oyuncu istediğinden
   şekil sinyalleri bu ayarda anlamsızlaşır.
3. **`tiles` darboğaz değil.** 6 → 4 ne kaliteyi düşürdü (22.0 → 22.1) ne de hızı
   değiştirdi — `tiles 6` bu görüntü için fazlaydı, `tiles 4` bedavaya kullanılabilir.
4. **Çözünürlük düşürmek serbest kazanç:** 4K → 1080p %30 hızlandırıyor ve oyuncu
   tespiti düşmüyor (21.7). Demek ki 4K'nın fazladan pikselleri bu model için bilgi
   taşımıyor, sadece çözme/kırpma maliyeti getiriyor.

Yine de gerçek zamanın ~4 katı yavaş. Kalan yollar: TensorRT/ONNX çıkarım, daha güçlü
GPU, segmentleri paralel işlemek. Şu an pratik kullanım: **maç sonrası / devre arası
analiz**, ya da kabul edilen gecikmeyle (birkaç dakika geriden) canlı takip — koç
kararları dakika ölçeğinde alındığı için bu çoğu senaryoda yeterli. Script her
segmentte `✓ gerçek zamana yetişiyor` / `⚠ segmentten yavaş` yazar; kurulumda bu
satıra bak.

**Event beslemesi olmayan kulüp senaryosu:** `/admin/matches/{id}/live-decision` eskiden
event yoksa boş dönüyordu. Artık event yok ama kare varsa panel yalnız pozisyon
verisiyle çalışır: `engine.tracking_signals` ardışık iki pencerenin şekil/pres farkından
sinyal üretir (blok açıldı/sıkıştı, hat yükseldi/düştü, rakip daraldı, pres düştü) ve
bunlar `context_pipeline` üzerinden birincil karara dönüşür. Doğrulandı: sıfır event'li
video maçında panel *"Rakip 6 m daraldı — kanatlar boş, oyunu genişlet"* birincil
kararını üretiyor (`tests/test_api_live_decision_tracking_only.py`).

**Dürüstlük kuralı:** şekil sinyalleri yalnız **sürekli takipte** (video) üretilir.
StatsBomb 360 kareleri event-çapalı ve topun çevresini gösterdiği için orada
`continuous=False` geçilir → yalnız topa göreli pres sinyalleri çıkar. Aksi halde
"hat 22 m yükseldi" gibi sahte sinyaller üretiliyordu. İki pencere arasında görünen
oyuncu sayısı 2'den çok oynarsa şekil kıyaslanmaz.

## Koç Karar Zekâsı (karar → ölçüm → kalibrasyon)

Koçun maç-içi hamlesi işe yaradı mı, ve sistemin kendi güveni dürüst mü?

**1. Karar etkisi** — `engine.decision_impact`: her kararın öncesi/sonrası penceresi
(varsayılan 15 dk) xG farkı, xT, şut, gol ve saha eğimi üzerinden kıyaslanır. Pencereler
maç sonuna kırpılır ve metrikler **dakika başına** normalize edilir (88. dakikadaki
kararın 2 dakikalık sonrası, 15 dakikalık öncesiyle haksız kıyaslanmasın). Hüküm
positive/negative/neutral/insufficient_data — ve **xG ile xT'nin aynı yöne gitmesi
şartı** vardır, tek metrik yeter sayılmaz.

- `GET /admin/matches/{id}/decisions/learning` — maçtaki kararların ölçümü
- `POST /admin/matches/{id}/decisions/auto-outcome` — ölçümü `Decision.outcome`'a yazıp
  geri besleme döngüsünü kapatır. Elle girilmiş sonuçlar korunur (oto kayıtlar `[oto]`
  önekiyle ayrılır); `?overwrite_manual=true` ile ezilebilir.
- `GET /admin/teams/{id}/decisions/track-record` — takım defteri, tip ve dakika bandı kırılımı

**2. Karar kalitesi** — `GET /admin/teams/{id}/decisions/quality`: `engine.backtest`
kalibrasyonu + öneri/koç kıyası. İki soruya bakar: sistem "%70 güvenle öner" dediğinde
gerçekten %70 tutuyor mu, ve sistemin önerdiği kararlar koçun kendi aldıklarından iyi mi.

> **Yanıttaki iki "isabet" karıştırılmamalı:** `confidence_calibration.accuracy` =
> 0.5 eşiğinde sınıflandırma doğruluğu; `recommended_vs_own.*.hit_rate` = pozitif
> çıkan karar oranı. Bu yüzden kalibrasyon tarafında `hit_rate` adı bilinçli
> kullanılmıyor.

Arayüz: **Karar Takip** sayfası (`/decisions/track`) → "Ölçülen Etki" bölümü.
`DecisionTrackRecordCard` (defter), `DecisionQualityCard` (kalibrasyon çubukları +
öneri vs koç), `MatchDecisionImpactCard` (maç kırılımı + "Ölç ve kaydet").

**Sınır:** ölçüm vekildir, nedensellik kanıtı değil — karar sonrası pencerede skor
durumu, kartlar ve rakibin hamlesi de etkilidir. Öneri/koç kıyası gözlemseldir (iki
grup farklı maç durumlarında oluşur). Kalibrasyon n<20 iken yön göstergesi sayılmalı;
kart bunu "yön göstergesi / anlamlı" etiketiyle açıkça yazar.

### Boşluk haritası — "nerede üstünlük var, nereye oyna"

`engine.tracking` takımın **şeklini** ölçer, `engine.tracking_signals` iki pencere
arasındaki **değişimi** yakalar. İkisi de takım geneli ortalamadır: koça "rakip
daraldı" der ama **nerede** boşluk açıldığını söylemez. `engine.space_map` o boşluğu
sahanın üstüne yerleştirir:

- **Bölgesel sayısal üstünlük** — saha 3 koridor × 3 üçte bire bölünür, her hücrede
  kare başına ortalama oyuncu farkı (biz − rakip) hesaplanır
- **Hatlar arası boşluk** — rakip geri hattı ile önündeki hat arası mesafe + o cepte
  kaç oyuncumuz var ("cebe gir")
- **Zayıf taraf** — rakibin terk ettiği koridor ("kanat değiştir")

Bulgular `context_pipeline` üzerinden `space:*` anahtarlı `spatial` sinyal olarak
karar motoruna girer; arayüzde `_console/space-map-card.tsx` 3×3 ızgarayı çizer
(sağ kenar hep bizim hücum ettiğimiz kale).

**Hücum yönü bu motorun ön koşulu.** "Hücum üçte biri" yön bilinmeden anlamsızdır ve
takımlar ikinci yarıda taraf değiştirir. Veride yön bilgisi yok; kalecinin konumundan
(yoksa en derin oyuncudan) çıkarılır. Yön ters ise saha **180° döndürülür** — yani
`x → 100-x` ile birlikte `y → 100-y`. Sadece x'i aynalamak koridorları ters çevirir
("sol" derken sağı gösterir); testler bunu açıkça kovalar.

**Üretmediği zaman sebebini söyler** — boş kart koçu "veri mi yok, sinyal mi yok"
ikileminde bırakıyordu:

| durum | davranış |
|---|---|
| event-çapalı kareler (StatsBomb 360) | bölge sayımı yapılmaz — freeze-frame topun çevresini gösterir |
| görünür oyuncu < 8 | sayım güvenilmez |
| oyuncuların x yayılımı < %45 | "kamera sahanın yalnız ~%X'ini görüyor" |
| hücum yönü çıkarılamadı | "kaleci görünmüyor, iki takımın derinliği yakın" |

**Yanlış sinyalden kaçınma:** bir koridorda hiç oyuncu yoksa (ne biz ne rakip) orası
kameranın görmediği yerdir; "rakip o kanadı boşalttı" demek uydurma olur, bu yüzden
zayıf-taraf sinyali koridorun gözlendiğine dair kanıt ister. Aciliyet üçte bire göre
ağırlıklıdır: hücum üçte birindeki üstünlük doğrudan gol şansıdır, orta sahadaki aynı
fark şekil sinyallerini ezmemelidir.

**Mevcut demo klibinde çalışmaz** — TeamTrack drone klibi sahanın orta bandını
gösteriyor, kaleciler kadraja girmiyor, yön çıkarılamıyor. Motor bunu sessizce
uydurmak yerine sebebi yazıyor. Kulübün tam saha gören taktik kamerasında çalışır.

### Yayın kamerası (TV) — neden ayrı bir sorun, ne yapılıyor

Takip hattı **tek ve sabit** bir homografi kullanır: kalibrasyon bir kez yapılır, her
karede aynı matrisle piksel → saha metresi çevrilir. Bu yalnız kamera hiç oynamıyorsa
doğrudur. Ölçüldü (4K, gerçek kalibrasyon):

| kamera kayması | oyuncunun sahada kayması |
|---|---|
| 30 px | 1.1 m |
| 100 px | 3.6 m |

`engine.tracking_signals` eşikleri 2.5–4 m. Yani **kamera hareketi tek başına sahte
taktik sinyal üretir**: "geri hat 4 m yükseldi" der, oysa hat yerinde durmuş, kamera
kaymıştır. Yayın kamerası saniyede yüzlerce piksel çevirir.

**Koruma:** `app/tracking/camera.py` videoyu işlemeden önce kameraya bakar. İki ardışık
örnek kare arasında faz korelasyonu global kaymayı ve tutarlılığını, histogram uzaklığı
içerik değişimini verir. Ayrım şu: hızlı bir **çevirme** de histogramı çok değiştirir
ama kayması tutarlıdır; **kesmede** tutarlılık yoktur.

| hüküm | kaynak etiketi | sonuç |
|---|---|---|
| `static` | `video_tracking` | sabit homografi geçerli → tam analiz (şekil + bölge) açık |
| `panning` | `broadcast_tracking` | tek çekim ama kamera çeviriyor → top-merkezli |
| `broadcast` | `broadcast_tracking` | kesme + hareket → top-merkezli |
| `unknown` | `broadcast_tracking` | analiz yapılamadı → güvenli tarafta kısıtlı |

Etiket kareye yazılır, ingest'te `meta_json.source` olarak saklanır ve motorlara kadar
gider: `broadcast_tracking` kareler **StatsBomb 360 freeze-frame'lerle aynı sınıf**
sayılır (top-merkezli), şekil ve bölge analizi kapanır, yalnız topa göreli sinyaller
üretilir. `scripts/track_video.py --camera auto|static|broadcast` ile elle de verilebilir.

Gerçek veriyle doğrulandı: TeamTrack drone klibi → `static` (ortalama 0.02 px hareket);
aynı klipten üretilen çevirmeli/zoomlu yayın taklidi → `panning` (%96 hareket, ortalama
36.7 px) → tam analiz kapatıldı.

**Bilinen sınır:** kesme tespiti sahne değişimine (kalabalık, yakın çekim, replay)
göre ayarlıdır; aynı sahneye sert zoom "hareket" olarak okunur. Sonuç yine güvenli
taraftır (kısıtlı mod), ama kesme sayısı olduğundan az raporlanabilir. Eşikler gerçek
yayın görüntüsüyle ayarlanmalıdır.

**TV yayınından tam saha analizi istiyorsanız** gereken şey bellidir ve bu sürümde
YOKTUR: **kare başına kalibrasyon** — her karede saha çizgilerini (taç, ceza sahası,
orta yuvarlak) tespit edip homografiyi yeniden hesaplamak; ayrıca kesme tespiti,
replay ayıklama ve çekim sınıflandırma (ana kamera mı, yakın çekim mi). Bunlar
olmadan TV yayınından çıkarılabilecek dürüst sonuç **topun çevresiyle sınırlıdır**.

### Kare başına kalibrasyon — hareketli kamerada gerçek konum

Sabit homografi yalnız sabit kamerada doğrudur. Yayın kamerası çevirdiğinde
oyuncular sahada kaymış görünür ve sahte taktik sinyal çıkar. `--per-frame-calibration`
homografiyi **her karede yeniden bulur**: modelin saha çizgileri görüntüdeki gerçek
çizgilere oturtulur.

**Nasıl:** sıfırdan çözmek yerine önceki karenin homografisinden başlanıp iyileştirilir
(kamera bir karede az oynar). Parametre olarak matris elemanları değil **sahanın dört
köşesinin görüntüdeki konumu** kullanılır — hepsi piksel biriminde, geometrik olarak
anlamlı. Arama hamleleri gerçek kamera hareketlerine karşılık gelir: öteleme (pan),
ölçek (zoom), tek köşe (perspektif).

**Ölçülen doğruluk** (gerçek 4K klipten üretilmiş pan+zoom, 1900 px gezinme, saha
gerçeği bilinen):

| yöntem | ortalama hata | en kötü | kalibre kare |
|---|---|---|---|
| sabit homografi (eski) | **~21 m** | 34 m | — |
| kare başına, her kare | **0.09 m** | 0.27 m | %100 |
| kare başına, her 2. kare | 0.12 m | 0.79 m | %100 |
| kare başına, her 3. kare | 0.19 m | 0.89 m | %100 |
| kare başına, her 5. kare | — | — | %1 (reddediyor) |

**`--track-fps 15` şart.** Kalibrasyon kamerayı ancak ardışık örnekler yakınsa takip
eder; 30 fps kaynakta her 3. kareye kadar sorunsuz, her 5. karede kopuyor. `track-fps 5`
denendiğinde 30 karenin yalnız 1'i kalibre oldu. Zaten tespit/takip kalitesi de 15
istiyor (bkz. yukarıdaki performans tablosu) — iki kısıt aynı yeri gösteriyor. Script
düşük değerde uyarır.

**Bulamadığında susar.** Bu motorun işi doğru homografiyi bulmak kadar, bulamadığında
konum üretmemektir:

- Oturma kalitesi (inlier) **tek başına yetmez**: sahanın paralel çizgileri birbirine
  benzediği için homografi yanlış çizgiye kilitlenebilir. Ölçüldü — böyle oturmalar
  %55 inlier alıyor, doğru oturmalardan biri %58. Ayıran şey fizik: yanlış çözüm bir
  karede 36 m sıçrıyor, ki bu imkânsızdır. Bu yüzden süreklilik kapısı var.
- **Otomatik yeniden yakalama kapalı.** Denendi: kesme sonrası iki ardışık kare AYNI
  yanlış çizgiye kilitlenip birbirini "doğruladı" ve hata 499 m'ye çıktı. Artık takip
  kaybolunca kare üretilmiyor, dışarıdan çapa bekleniyor — **TV yayınında bu, çekim
  başına çapa gerektiği anlamına gelir**.
- Yakın çekim/replay (saha çizgisi yok) → kare atlanır.

**Maliyet:** 88 ms/kare (720p, CPU). 25 fps gerçek zaman için 40 ms gerekir; şu an
2.2 kat yavaş. Düşürme yolları: çizgi maskesini küçültmek, model noktası sayısını
azaltmak, GPU'ya taşımak.

**Kaynak etiketi yükselir:** kamera hareketli olduğu için `broadcast_tracking`
işaretlenen kareler, kare başına kalibrasyon başarılıysa `video_tracking`'e yükseltilir
— konumlar artık gerçek saha konumu taşıdığı için şekil ve bölge analizi yeniden açılır.
