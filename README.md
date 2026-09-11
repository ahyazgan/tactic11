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

## Test ve kalite kapıları

CI'daki üç kapının **hepsi yerelde koşturulabilir** — push edip beklemeye gerek yok.

```bash
pytest -q                              # 2205 test, in-memory SQLite (DB/anahtar gerekmez)
ruff check app/ scripts/ tests/        # stil + basit hatalar
mypy app/ scripts/                     # tip denetimi (~3 dk)
```

Frontend:
```bash
cd frontend
npm run typecheck                      # tsc --noEmit
npm run build && npx next start -p 3111 &
E2E_BASE_URL=http://localhost:3111 E2E_BACKEND=false npx playwright test
```
Tarayıcı yoksa bir kez `npx playwright install chromium`. e2e'yi **üretim
derlemesine** karşı koşturun (CI öyle yapıyor); sunucuyu yeniden başlatırken
portu gerçekten kapatın, yoksa eski derleme sunulmaya devam eder.

> **mypy sürümü 1.18.2'de sabit, yükseltmeyin.** 1.19+ `librt`'ye (yalnızca
> derlenmiş .pyd) zorunlu bağımlı; Windows 11'de Smart App Control bunu
> engellediği için mypy hiç başlamıyor ve kapı yerelde koşturulamaz hale
> geliyor. Gerekçe `requirements-dev.txt` içinde yazılı.

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

POST /admin/decisions/{decision_id}/applied
    → Koç işareti: öneri sahada uygulandı mı? payload: {"applied": true|false|null}
      false = karşı-olgu kaydı (aynı durumda öneri uygulanmayınca ne oldu);
      geri besleme YALNIZ applied=true kararlardan öğrenir, null uydurulmaz

GET /admin/teams/{id}/decisions/feedback
    → decision_type bazlı geçmiş isabet oranı → güven skorunu kalibre eder
      (yalnız koçun uyguladığı kararlar; `excluded` dışarıda kalanları sayar)

GET /admin/teams/{id}/decisions/uplift
    → Öneri etkisi: uygulanan vs uygulanmayan öneri, karar öncesi duruma göre
      katmanlı isabet farkı (engine.decision_uplift). Karşı-olgu yoksa
      hüküm vermez — 502 uygulanmamış öneride ölçüldü: "sonra ne oldu" ile
      "öneri yüzünden ne oldu" karşı-olgu olmadan ayrılamıyor
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
# İsteğe bağlı yedek arka uç (torch'un yüklenemediği / GPU'suz makine): ONNX Runtime
venv-cv\Scripts\python.exe -m pip install onnxruntime-gpu "onnx>=1.16,<2" onnx_graphsurgeon polygraphy ^
    "nvidia-cuda-runtime>=13,<14" "nvidia-cublas>=13,<14" "nvidia-cufft>=12,<13" nvidia-cudnn-cu13 "nvidia-cuda-nvrtc>=13,<14" nvidia-curand
venv-cv\Scripts\python.exe -m scripts.export_detector_onnx --weights data/tracking/models/rfdetr_top_small   # ONNX + parite
```

> **Windows Smart App Control (SAC) açık makinede — imza değil, bulut itibarı.** Ölçüldü
> (2026-09-11): SAC ikili dosyayı imzasına göre değil hash'inin Microsoft bulutundaki
> itibarına göre engelliyor. **Yeni çıkan tekerlekler engellenir, eski/yaygınlar geçer**:
> torch 2.11 (cu128 ve cpu), 2.7.1+cu128, numpy 2.5.3, regex 2026.9, onnx 1.22, onnxsim
> 0.7, ml_dtypes 0.6 engelli; torch 2.5.1+cpu, numpy 2.3.5, onnx 1.17, onnxruntime 1.30
> (Microsoft imzalı) geçiyor. Böyle bir makinede (ör. bir alıcının kulüp bilgisayarı) **torch
> ile GPU yok**; çalışan reçete: `"torch==2.5.1" "torchvision==0.20.1"` (cpu index),
> `"numpy==2.3.5" "regex<2026" "onnx==1.17.0" "ml_dtypes<0.5"`, `onnxsim` yok (aktarım
> scripti sadeleştirmeyi atlar, doğruluğu pariteyle ölçer) ve çıkarım **ONNX Runtime**'da
> (`CUDAExecutionProvider` doğrulandı). SAC bir kez kapatılırsa Windows yeniden kurulmadan
> açılamaz — kararı makinenin sahibi verir; kod iki durumda da çalışır.

**Dedektör arka ucu** (`--backend auto|torch|onnx`): `auto` sırayla — CUDA'lı torch varsa
**torch**; yoksa ONNX modeli varsa **ONNX**; yoksa torch CPU. Ölçüldü (ince ayarlı small,
1080p, aynı kare, RTX 5060):

| tiles | dilim | torch GPU fp16 | ONNX GPU | torch CPU | bulunan oyuncu |
|---|---|---|---|---|---|
| 1 | 1 | 45 ms | **18–41 ms** | 165 ms | 1 (üstten çekimde oyuncu çok küçük) |
| 2 | 9 | **88 ms → 11 fps** | 153–244 ms | — | 15 |
| 4 | 25 | **156 ms → 6.4 fps** | 423–600 ms | ~3 sn | 23 |

Dilimli çıkarımda torch'un fp16 derlenmiş batch'i ONNX'ten 3-4 kat hızlı; tek dilimde başa
baş. **Gerçek zaman (15 fps): tiles=1, ya da torch GPU ile tiles=2'ye yakın.** Yayın
karesinde oyuncular büyük olduğu için tiles=1 yeter (COCO medium, 4K yayın karesi: 16 kutu,
85 ms ONNX); üstten/drone geniş açıda tiles ≥ 3 gerekir → o kaynak çevrimdışı işlenir.
ONNX ölçümlerindeki aralık: torch cu128 ile aynı süreçte CUDA 12/13 kütüphaneleri
karışınca ORT yavaşlıyor (uyarı basar) — ONNX yedeğini torch'suz makinede kullan.

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

**Ölçülen doğruluk.** Sayılar `scripts/bench_calibration.py` ile üretilir —
iddiaların hepsi tekrar koşturulabilir:

```bash
# 1) Ölçüm videosu + saha gerçeği üret (bir kez)
venv-cv\Scripts\python.exe -m scripts.bench_calibration make ^
    --source data/tracking/live/seg_0000.mp4 ^
    --calibration data/tracking/calibrations/saha.json ^
    --out-dir data/tracking/bench

# 2) Tabloyu üret
venv-cv\Scripts\python.exe -m scripts.bench_calibration table ^
    --bench-dir data/tracking/bench --frames 50
```

Yöntem: sabit kameralı bir klipten kırpma penceresi gezdirilerek pan+zoom taklidi
üretilir (1900 px gezinme + zoom salınımı). Kırpma parametreleri bilindiği için her
karenin **gerçek** homografisi analitik hesaplanır; hata metre cinsinden ölçülür.

| yöntem | ortalama hata | en kötü | kalibre kare |
|---|---|---|---|
| sabit homografi (eski davranış) | **16.11 m** | 28.87 m | — |
| kare başına, her kare | **0.12 m** | 0.29 m | %100 |
| kare başına, her 2. kare | 0.11 m | 0.24 m | %100 |
| kare başına, her 3. kare | 0.09 m | 0.24 m | %100 |
| kare başına, her 5. kare | — | — | **%2 (reddediyor)** |

> Sentetik hareket düzgündür (gerçek kameramanın ani düzeltmeleri yoktur) ve
> sıkıştırma bozulmaları azdır — bu sayılar **iyimser taraftadır** ve gerçek yayın
> görüntüsünde doğrulanması gerekir.
>
> **Tablo 60 karelik ölçümdür.** 500 karede (17 sn, aynı elle çapa) ölçüldü: hata
> ort **0.32 m**, %90 0.98 m, en kötü **1.95 m**. Kayma kadrajda az çizgi göründüğü
> (yakın zoom) anlarda birikiyor ve inlier'la ilişkili (hatası <0.5 m karelerde inlier
> 0.99, >0.5 m karelerde ~0.7); kadraj "belirleyicilik" ölçüleri (segment sayısı, yön
> çeşitliliği) ve tolerans daraltma ayırt etmiyor — denendi. Uzun koşumda güvenilirlik
> için takipte inlier tabanı + sürüklenme (aşağıda).

**Takip inlier tabanı + sürüklenme** (`PerFrameCalibrator.TRACK_MIN_INLIER`, `COAST_FRAMES`).
Oturma kabul sınırını (0.45) geçen ama takip tabanının (0.85) altındaki kare **üretilmez**;
son iyi duruş korunur ve kamera 15 kare boyunca oradan aranır (çapaya düşülmez). Kesmede
sürüklenme yok. Ölçüldü (500 kare):

| ayar | kalibre kare | hata ort | en kötü | kesmeli yayın |
|---|---|---|---|---|
| taban 0.45, sürüklenme yok (eski) | 500 | 0.32 m | 1.95 m | 146 |
| **taban 0.85, sürüklenme 15** | 396 | **0.18 m** | **1.01 m** | **179** |
| taban 0.85, sürüklenme 45, sıçrama tavansız | 382 | 13.8 m ✗ | 157 m ✗ | — |

Karelerin %21'i "veri yok" olur, kalanların hatası yarıya iner. Uzun sürüklenme tavansız
sıçrama iziniyle yanlış çizgiye kilitleniyordu → izin verilen sıçrama geçen kareyle büyür
ama 3× ile **tavanlıdır**; tavanla 45 kare de 0.18 m'de kalır.

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
- **Yeniden yakalama yalnız ÇAPADAN.** Serbest arama denendi: kesme sonrası iki
  ardışık kare AYNI yanlış çizgiye kilitlenip birbirini "doğruladı" ve hata 499 m'ye
  çıktı. Kayıpta kaymış son homografiden değil çapadan aranır ve %85 inlier istenir
  (`--reacquire`, yayında otomatik açık). Çapadan da tutmuyorsa çekim başka yere
  bakıyordur → aşağıdaki çekim başına çapa devreye girer.
- Yakın çekim/replay (saha çizgisi yok) → kare atlanır.

### Çapasız başlangıç — otomatik çapa ve TV kuralı

`--calibration` verilmezse kalibratör çapayı **görüntüden kendisi arar**
(`homography_fit.find_anchor`): makul kamera duruşlarından ~300 aday puanlanır, en
iyileri iyileştirilir, kabul kapılarından geçen varsa çapa olur. Bulunana kadar kare
üretilmez. Kesmeden sonra çapadan yakalama ~1 sn tutmazsa aynı arama **çekim başına**
yeniden yapılır.

**180° ikiliği nasıl kapanıyor — TV kuralı.** Saha çizgi modeli 180° dönme altında
birebir kendine eşittir; hangi yarıya bakıldığı çizgilerden asla çıkarılamaz. Yayın
rejisinde ise tüm canlı kameralar sahanın **aynı tarafındadır** (180° kuralı; karşı
açı yalnız tekrarda). O hâlde "görüntünün altı yakın taç (y=68), solu küçük x" bir
tahmin değil bir **çerçeve tanımıdır** ve aynı taraftaki her kamera için tutarlıdır.
Hücum yönü bu çerçeve içinde veriden çıkarılır. **Sınır:** canlı karşı açıda o
çekimin konumları aynalanır ve hiçbir kalite kapısı bunu yakalayamaz — geometri aynı
puanı verir.

**Kabul kapıları** (hepsi ölçümle bulundu): ≥%90 inlier · ayırt edici yapı (ceza
sahası/orta yuvarlak) görünür ve oturmuş · geometrik olarak farklı en iyi rakibi
%25 farkla geçmiş · **kapsama ≥ %60**. Kapsama sonradan eklendi: inlier "model →
çizgi" bakar; modelin çoğunu kadraj dışına atıp yalnız orta çizgiyi oturtan bir duruş
**%97 inlier alıp 27 m yanlış** çıktı (pan_zoom kare 300). Kapsama tersini sorar —
görünen çizgi piksellerinin ne kadarı modelle açıklanıyor — ve o çözüm %14 aldı.
Aday sıralaması da aynı sebeple kesinlik × duyarlılık ile yapılır.

**Ölçüldü** (`bench_calibration anchor` / `auto`, saha gerçeği bilinen pan_zoom, 500 kare):

| | kapsama kapısı yok | kapsama kapısı + kesinlik×duyarlılık |
|---|---|---|
| tek kareden çapa: kabul | 2/50 | 2/50 |
| kabul edilenlerde **yanlış (>3 m)** | **1/2 (26.9 m)** | **0/2** (en kötü 1.59 m) |
| arama süresi | 220 ms | ~1000 ms |

Çapasız kalibratör uçtan uca: pan_zoom'da 9. denemede çapalanıp **362/500 kare kalibre
(%72)**, hata ort **1.67 m** / %90 3.76 m; kesmeli yayında **133/500 (%27)** — elle çapayla
aynı (%29). Elle çapa **0.09 m** veriyordu: otomatik çapanın ~1.5 m'lik perspektif kusuru
takipte düzelmiyor. Bu yüzden **otomatik çapa bir yedektir**: operatör varsa
`scripts/propose_calibration.py --tv-rule` ile öneriyi önizlemede onaylayıp
`--calibration` vermek daha doğrudur. Çapasız evrede arama saniyede ~1 kez ~1 sn sürer
(gerçek zaman sınırında); çapa bulununca maliyet biter.

**Maliyet:** 88 ms/kare (720p, CPU). 25 fps gerçek zaman için 40 ms gerekir; şu an
2.2 kat yavaş. Düşürme yolları: çizgi maskesini küçültmek, model noktası sayısını
azaltmak, GPU'ya taşımak.

**Kaynak etiketi yükselir:** kamera hareketli olduğu için `broadcast_tracking`
işaretlenen kareler, kare başına kalibrasyon başarılıysa `video_tracking`'e yükseltilir
— konumlar artık gerçek saha konumu taşıdığı için şekil ve bölge analizi yeniden açılır.

#### 180° ikilik — çizgilerden çözülemeyen şey

Saha çizgi modeli **180° dönme altında birebir kendine eşittir**. Sayısal olarak
doğrulandı: modeli `(x,y) → (105-x, 68-y)` ile döndürüp orijinaliyle karşılaştırınca
fark **ortalama ve en fazla 0.0000 m**. Yani her homografinin özdeş puanlı bir "ayna
ikizi" vardır — ölçüldü, ayna oranı her karede tam **1.00**.

**Sonuç: kameranın hangi yarıya baktığı yalnız saha çizgilerinden ASLA çıkarılamaz.**
Bu bir uygulama eksiği değil, geometrinin sınırıdır. Ayrımı ancak dışarıdan bir bilgi
yapar: kaleler, tribün/reklam panoları, çim deseni, operatör bilgisi ya da kesme öncesi
bilinen homografi.

Serbest aramayla çapa denendi ve bu ikilik tam da beklendiği gibi vurdu: **%94 inlier
alan bir çapa 47 m yanlıştı**. Bu yüzden:

- `find_anchor()` ipucu verilmedikçe **kabul etmez**; iki hipotezi de döndürür
  (`homography` + `mirror_homography`), kararı bilgisi olana bırakır.
- `PerFrameCalibrator` kayıp durumda serbest arama yapmaz; `allow_reacquire` açıksa
  arama **çapadan** yapılır — çapa hangi yarı olduğunu sabitlediği için ikilik kapanır.
  TV'de ana kamera kesmeden sonra benzer görüntüye döndüğü için bu pratikte çalışır.

#### Hız — gerçek zamana ulaşıldı

| adım | süre/kare | doğruluk |
|---|---|---|
| başlangıç | 88 ms | 0.09 m |
| + kapalı form homografi (SVD yerine 8×8 çözüm) | 54 ms | 0.10 m |
| + görüntüyü 0.75 ölçekte işleme | 42 ms | 0.08 m |
| + aramada model noktası aralığı 1.5 m | **39 ms** | 0.11 m |

Son hâl `bench_calibration table` çıktısında: ölçek 1.0 → 50.6 ms, ölçek 0.75 →
**39.2 ms** (hata 0.11 m), ölçek 0.5 → 47.1 ms ama hata 1.50 m.

25 fps için bütçe 40 ms → **gerçek zamanlı kalibrasyon mümkün**. Darboğaz skorlama
değil, her denemede yapılan homografi çözümüydü: 4 nokta için genel DLT'nin (Hartley
normalizasyonu + SVD) gereği yok, `h33=1` alıp 8×8 doğrusal sistem çözmek **3.9 kat**
hızlı ve sonuç birebir aynı (fark 8e-14).

**0.5 ölçeğin altına inmeyin:** hata 0.11 m'den 1.50 m'ye (en kötü 6.59 m) çıkıyor ve
üstelik daha da yavaşlıyor (47 ms), çünkü kötü oturma daha çok iterasyon gerektiriyor.
Sebep tolerans değil (ölçeğe bağlandı, düzelmedi) — çizgi çıkarmanın morfolojik filtresi
720p'ye göre ayarlı; daha küçük görüntüde ince çizgileri kaçırıyor.

### Ölçüme bu hafta başlamak — yalnız şutlarla

Karar etkisi ölçümü koordinatlı event verisi ister (pas/taşıma/şut). Bu
StatsBomb/Opta seviyesidir; çoğu kulüpte yoktur ve tam etiketleme maç başına
**2-3 saat** sürer. Beklemeye gerek yok: **yalnız şutlarla** da ölçüm yapılır.

Bir maçta ~25 şut olur — bir analistin **15 dakikalık** işi.

```bash
# 1) Maç sonrası şutları bir CSV'ye yaz (Excel'den de kaydedilebilir)
#    dakika,takim,x,y,gol
#    12.5,biz,88,52,0
#    23,rakip,80,40,1
python -m scripts.import_shots --csv mac_sutlar.csv --tenant t-default ^
    --match-id 20260914 --our-team 217 --their-team 213 ^
    --kickoff 2026-09-14 --our-score 2 --their-score 1

# 2) Kararları ölç (panelden "Ölç ve kaydet" ya da uçtan)
#    POST /admin/matches/20260914/decisions/auto-outcome
```

**Koordinatlar:** saha 0-100 normalize, **kale (100, 50)**. Her iki takımın şutu
da kendi hücum yönünde girilir — rakip şutunu aynalamak xG'yi ters çevirir.

**Sistem sınırını söyler.** Pas verisi yokken hüküm tek metriğe dayanır; motor
bunu gizlemez:

```
45. dk Taktik ayar: positive (güven 0.45)
   xG farkı dk başına +0.029 — YALNIZ xG ile (pas verisi yok, xT doğrulaması yapılamadı)
```

Güven `SINGLE_METRIC_CONFIDENCE_FACTOR` (0.7) ile kırpılır. Pas verisi sonradan
gelirse (abonelik ya da kendi video hattımız) aynı kararlar iki metrikle
yeniden ölçülür ve güven yükselir — kayıtları baştan girmek gerekmez.

**Neden önce başlamak önemli:** güven kalibrasyonu **20+ ölçülmüş karar**
istiyor. Kayda bugün başlanmazsa kalibrasyon bir sezon gecikir.

### Replay (tekrar) tespiti

TV yayınında tekrarlar canlı akışın arasına girer. Canlı dakikayla kaydedilirse
zaman çizgisi bozulur: 68. dakikadaki atak 71'e yazılır, olay iki kez sayılır,
karar etkisi yanlış pencereyi kıyaslar.

**Kapsam.** Farklı kamera açısından gelen tekrarlar **zaten** ayıklanıyor —
kalibrasyon takibi kopuyor ve kare "kalibre edilmemiş" sayılıyor. Kalan gerçek
boşluk **ana kameradan gelen ağır çekim**: aynı açı olduğu için sorunsuz
kalibre olur. `app/tracking/replay.py` bunu hedefler.

**İki bağımsız işaret:**

1. **Ağır çekim** — kareler arası hareket, canlı oyunun kendi **medyanının**
   altına düşer. Mutlak eşik yok: "yavaş" kameraya ve sahneye göre değişir.
   Medyan kullanılır çünkü tek bir hızlı çevirme ortalamayı çeker ve sonraki
   her kareyi "yavaş" gösterir.
2. **Skorboard kayboldu** — yayıncılar tekrarda bindirmeyi gizler. Nerede
   olduğunu bilmeye gerek yok: canlı oyunda **değişmeyen** pikseller
   bindirmedir, kendi kendini bulur.

**Ağır çekim tek başına yeterli değildir** — oyun durunca da hareket düşer.
Skorboard yerindeyse kare canlı sayılır. Şüphede canlı: yanlışlıkla tekrarı
canlı saymak zaman çizgisini bozar, ama tekrar tespiti sezgiseldir ve gerçek
yayınla ayarlanmadan agresif davranmamalıdır.

**Bindirme eşiği görelidir** — sahnenin kendi varyans medyanının 0.1 katı.
Mutlak eşik taşınmıyor: ölçüldü, durgun bir drone klibinde karenin varyans
medyanı 1.5 iken sabit eşik 2.0 karenin **%65'ini** "bindirme" sanıyordu.

**Doğrulama** (skorboardlı, 120-200 arası ağır çekim tekrar içeren sentetik
yayın): **80/80 tekrar karesi yakalandı, 219 canlı karede 0 yanlış alarm.**
Gerçek drone klibinde (skorboard yok) bindirme bulunamadı ve 0 kare işaretlendi
— doğru davranış.

**Sınır:** eşikler gerçek yayın görüntüsüyle ayarlanmalı. Bindirmeyi gizlemeyen
bir yayıncıda ikinci işaret çalışmaz; o durumda ağır çekim tek başına yeterli
sayılmadığı için tekrarlar kaçar (sessizce yanlış konum üretmez, sadece ayıklamaz).
