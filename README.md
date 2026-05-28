# football-intelligence

Spor zekası platformu — futbol teknik ekiplerine veriyle karar desteği veren sistem.
Bugün: futbol verisi (API-Football) çek, doğrula, depola, sun.
Yarın: tracking, tahmin, otomasyon. Sonra: diğer sporlar.

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

## Taktiksel Engine Envanteri (47 modül)

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
```

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
