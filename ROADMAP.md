# ROADMAP

Mimari uzun vadeli vizyona göre baştan kurulur, ama her faz sadece o fazın
kodunu yazar. Boş iskeletler yer tutar; sırası gelince doldurulur.

---

## Faz 1 — Veri katmanı çalışır ✓
**Hedef:** API-Football'dan veri çekip doğrulayıp DB'ye yazmak ve okumak.

- [x] `app/core/config.py` — pydantic-settings ile `.env` okuma
- [x] `app/core/logging.py` — yapılandırılmış log
- [x] `app/core/usage/` — API çağrı sayacı + eşik kontrolü
- [x] `app/domain/` — League, Team, Match, Player (pydantic)
- [x] `app/db/` — SQLAlchemy modelleri + Alembic ilk migration
- [x] `app/data/sources/base.py` — `DataSource` arayüzü
- [x] `app/data/sources/api_football.py` — adapter (cache + kota guard)
- [x] `app/data/cache/` — DB-destekli TTL cache
- [x] `app/data/validation/` — kural listesi + çalıştırıcı
- [x] `app/data/ingest/` — çek + doğrula + normalize + yaz + snapshot
- [x] `app/snapshot/` — her sync'te durum özeti, üzerine yazmadan
- [x] `app/api/main.py` — FastAPI app + `/health`, `/leagues`, `/teams/...`
- [x] `app/sports/football.py` — futbol sabitleri
- [x] `scripts/sync_league.py` — uçtan uca CLI
- [x] `tests/fixtures/` — örnek JSON + fixture modu

**Faz 1 bitiş kriteri:** `.env` doldur → `alembic upgrade head` →
`python scripts/sync_league.py --league 203 --season 2024` → DB'de takımlar
görünür → `GET /teams/203` boş değil.

---

## Faz 2 — Analiz motoru ✓
- [x] `engine/form/` — son N maç trendi, W/D/L, ev/deplasman, gol farkı, ppg
- [x] `engine/load/` — pencere içi dakika/maç, yüksek yük bayrağı.
      Veri akışı uçtan uca BAĞLANDI: `PlayerAppearance` tablosu (alembic
      0005 + 0013), `APIFootball.get_fixture_player_stats`,
      `ingest_appearances_for_match` (idempotent + quota-guard),
      `GET /players/{id}/load?window_days=N&threshold_minutes_per_week=N&explain=bool`
      endpoint, 22 + 7 = 29 test.
      Eşik artık parametrik: default `football.DEFAULT_HIGH_LOAD_MINUTES_PER_WEEK`
      (270 dk/hafta), caller `threshold_minutes_per_week` ile override eder
      (PROMPT_BACKEND_LOAD_THRESHOLD.md kapandı). Lig/pozisyon bazlı default
      seçimi caller (agent/scheduler) sorumluluğunda.
- [x] `engine/rating/` — ppg+gd_per_match kompoziti, açıklanabilir
- [x] `engine/opponent/` — head-to-head özet
- [x] `audit/record.py` — `AuditRecord` + `EngineResult[T]` (engine sonuç +
      gerekçeyi birlikte taşır); kalıcı yazma orkestrasyon işi

**Kural:** engine fonksiyonları saf. İçeri veri (pydantic model / DataFrame),
dışarı hesap. DB/API/LLM bilmez.

---

## Faz 3 — AI yorum katmanı ✓
- [x] `ai/anthropic_client.py` — `claude-opus-4-7` çağrısı + stub mod (anahtar yok)
- [x] `ai/prompts.py` — sabit sistem promptu (caching uyumlu) + EngineResult → JSON gövdesi
- [x] `ai/commentator.py` — `Commentator` arayüzünün somut implementasyonu;
      anthropic kotasını `guard_quota`/`record_call` ile sayar

---

## Faz 4 — Scheduler ✓
- [x] `scheduler/registry.py` — `JobSpec` katalog, ad ile çözüm
- [x] `scheduler/jobs.py` — `sync_league` job kaydı (modül import'unda otomatik)
- [x] `scheduler/runner.py` — `run_job(name, **kwargs)` retry + exponential backoff;
      bir çağrı = bir `job_runs` satırı; status/attempts/error denetlenebilir
- [x] `scripts/run_job.py` — dış cron buradan tetikler (`--list`, `--max-attempts`)
- Cron örneği: `0 6 * * * cd /opt/manager2 && venv/bin/python scripts/run_job.py sync_league --league 203 --season 2024`

---

## Faz 5 — API olgunlaşır (auth dışında ✓)
- [x] `GET /teams/{id}/form?last_n=N&explain=bool` — engine/form sonucu + audit
- [x] `GET /teams/{id}/rating?last_n=N&explain=bool` — engine/rating
- [x] `GET /teams/{a}/vs/{b}?explain=bool` — engine/opponent head-to-head
- [x] `GET /matches/{id}/preview?last_n=N` — ev/dep form + H2H; kickoff'tan
      önceki maçlar üzerinden (sızıntı yok)
- [x] `api/serialize.py` — EngineResult → dict adaptörü (engine pure kalsın)
- [x] `?explain=true` → `ClaudeCommentator.explain` (anahtar yoksa stub)
- [x] Auth (`X-API-Key`); `API_AUTH_KEY` boş ise dev modu (auth devre dışı).
      JWT/OAuth ve kullanıcı/rol modeli multi-tenant (Ufuk 1) ile birlikte.

---

## Maç-içi karar mekanizması — Faz 6 ✓
Canlı maç-içi 14 karar özelliği, 5 engine (event-window proxy; gerçek feed
gelince adapter swap):
- [x] `engine/momentum_tracker/` — momentum meter + pres kırılma + xG swing (#1/2/3)
- [x] `engine/sub_timing/` — optimal timing + etki + paket (#4/5/6)
- [x] `engine/live_tactical_trigger/` — formation switch + press height + kanal (#7/8/9)
- [x] `engine/live_risk_monitor/` — kart + sakatlık + zaman yönetimi (#10/11/12)
- [x] `engine/opponent_reaction/` — rakip sub tepkisi + momentum kırma (#13/14)
- [x] `GET /admin/matches/{id}/live-decision` (birleşik panel) + 2 POST endpoint
- [x] WebSocket live snapshot'a 3 canlı sinyal eklendi
- PR #68 (`4a1415f`)

## Maç-içi karar mekanizması — Faz 7 ✓
Mekânsal/bireysel/bağlam katmanı, 14 özellik, 6 engine (F–K grupları):
- [x] `engine/spatial_control/` — boşluk haritası + sayısal üstünlük + genişlik (F)
- [x] `engine/live_matchup/` — düello kaybeden + sıcak el + yıldız besle (G)
- [x] `engine/set_piece_timing/` — köşe/faul fırsat rutini + penaltı atıcı (H)
- [x] `engine/game_friction/` — faul biriktirme + ofsayt tuzağı (I)
- [x] `engine/referee_context/` — hakem eğilimi + avantaj penceresi (J)
- [x] `engine/score_time_matrix/` — kapanış reçetesi + risk/getiri eşiği (K)
- [x] `live-decision` 8-engine birleşik'e genişledi + 3 POST endpoint (set-piece,
      game-friction, referee-context)
- [x] WebSocket live snapshot'a 3 Faz 7 sinyali eklendi
- PR #69 (`ea497e8`)

## Bağlam & güven katmanı — Faz 8 ✓ (orkestra şefi)
Her engine ayrı sinyal veriyordu; kullanıcı 5 ayrı uyarı görüp hangisine
bakacağını bilemiyordu. Bu faz sinyalleri tek karara indirger:
- [x] `engine/context_engine/` — tüm aktif sinyalleri okuyup tek "şimdi şunu
      yap" önceliği üretir (#1, en kritik)
- [x] `engine/confidence/` — her öneriye 0-1 güven skoru + "neden?" sürücüleri (#2)
- [x] `engine/match_memory/` — maç-içi hafıza: momentum dönüşü + kanat düşüşü +
      rakip değişimi bağlantısı; sistemi reaktiften proaktife geçirir (#3)
- [x] `engine/signal_quality/` — gürültü/yetersiz-örnek/ısınma filtresi; yanlış
      alarmı context'ten önce eler (#5)
- [x] Karar audit trail (#4): `decisions` tablosu outcome/confidence/recommended
      + `match_snapshots` tablosu (hafıza kalıcılığı) — migration 0016
- [x] `live-decision` + WebSocket'e `context` başlığı; `POST /decisions/{id}/outcome`
      + `GET /teams/{id}/decisions/feedback` (feedback loop → güven kalibrasyonu)
- [x] `app/api/context_pipeline.py` — pipeline orkestrasyonu (engine'ler saf kalır)

## Faz 9 — Dayanıklılık & ölçek (kısmen ✓)
Sistem dayanıklılık eksiklerinin kapatılması. Şimdi yapılanlar additive +
bağımlılıksız; kalanlar harici bağımlılık/altyapı gerektirdiği için ertelendi.

Yapıldı:
- [x] **#1 Retry + circuit breaker** — `data/sources/_resilience.py`
      (`CircuitBreaker` + `call_with_retry`); `api_football._http_get` geçici
      hata/timeout/5xx'te backoff ile retry, eşik aşılınca fail-fast.
- [x] **#2 Liveness/readiness ayrımı** — `/healthz` (DB'siz liveness) +
      `/readyz` (DB ping readiness, 503); `/health` legacy birleşik kaldı.
- [x] **#5 Güvenlik header'ları** — middleware: X-Content-Type-Options,
      X-Frame-Options, Referrer-Policy, Permissions-Policy + prod'da HSTS.
      (CSP hariç — `/dashboard` inline JS kullanıyor; ayrı ele alınacak.)
- [x] **#6 Login'e özel rate limit** — `/auth/login` IP başına ayrı sıkı
      limiter (`LOGIN_RATE_LIMIT_PER_MINUTE`, default 10).
- [x] **#8 DB pool ayarları** — `pool_size`/`max_overflow`/`pool_recycle`
      (SQLite dışı backend'lerde; settings'ten).
- [x] **#11 Graceful shutdown** — FastAPI `lifespan`; SIGTERM/deploy'da
      `engine.dispose()` ile havuz temiz kapanır.
- [x] **#3 Sentry** — `core/monitoring.init_sentry()` opsiyonel/graceful
      (`SENTRY_DSN` boş ya da lib yoksa no-op); requirements'a eklendi.
- [x] **#4 Prometheus `/metrics`** — `observability.py` guarded Counter/Histogram
      (method+status, düşük kardinalite) + `/metrics` endpoint; lib yoksa no-op.

Ertelendi (gerçek altyapı gerektirir — Redis sunucusu / çok-replica DB,
sandbox'ta doğrulanamaz):
- [ ] **#7 Kota aşımında graceful degradation** — `QuotaExceeded`'de stale
      cache'ten "degraded" servis. Cache katmanına `cache_get_stale` (TTL
      yoksay) eklemeyi gerektirir; davranış riski → ayrı PR.
- [ ] **#9 Redis cache** — DB-destekli TTL cache yerine; ölçekte. Cache
      arayüzü (`cache_get/cache_set`) stabil, backend swap.
- [ ] **#10 Dağıtık lock / leader election** — çok-replica scheduler için
      Postgres advisory lock; job çift-tetiklenmesini önler.

## Faz 10 — canlı güven + zeka + proaktif uyarı ✓
Saf, lokalde doğrulanabilir engine'ler (altyapısız):
- [x] `engine/live_confidence/` — canlı sinyal güven skoru + `summarize_trend`
      zamansal yön; live snapshot'a `confidence`/`trend` anahtarları.
- [x] `engine/data_quality/` — event-akışı kalite skoru (D); snapshot `data_quality`.
- [x] `engine/what_if/` — karşı-olgu simülatörü (A).
- [x] `engine/backtest/` — olasılıksal motor değerlendirme harness'ı (B).
- [x] `engine/anomaly/` — z-skor aykırı + form kırılması (C).
- [x] `engine/development_curve/` — gelişim eğimi + projeksiyon (E).
- [x] `engine/live_alerts/` — maç-içi proaktif uyarı (J); snapshot `live_alerts`.
- [x] `confidence` 5 motora bağlandı (form/rating/predict/matchup/opponent_weakness).

## Zeka derinleştirme & ürün backlog (A–K)
**A. Karar/senaryo:** ✓ what-if simülatörü (`engine/what_if/`); canlı karar
(Faz 6/7/8); sezon rotasyon/load opt — kısmi.
**B. Güven/açıklanabilirlik:** ✓ motor güven skoru (Faz 8 + ürüne yayım) + ✓
backtest harness'ı (`engine/backtest/`); kalibrasyon izleme — backtest ile mümkün.
**C. Karşılaştırmalı/benchmark:** benzerlik motoru (var: `player_similarity`) +
✓ anomali/kırılma (`engine/anomaly/`); lig yüzdelik benchmark — bekliyor.
**D. Veri kalitesi:** ✓ event-akışı kalite skoru (`engine/data_quality/`);
çapraz-kaynak doğrulama — bekliyor.
**E. Zaman/trend:** ✓ gelişim eğrisi + momentum projeksiyonu
(`engine/development_curve/`); sakatlık sonrası dönüş — bekliyor.
**F. Çıktı/teslim:** ✓ AgentOutput PDF + paylaşılabilir link; ✓ performans test
PDF raporu (`reports/build_performance_report_pdf`, `POST
/reports/performance/pdf` — renk-kodlu norm + regresyon uyarısı + KVKK dipnotu).
**G. i18n:** UI İngilizce — bekliyor (frontend).
**H. Rol derinliği:** rol-bazlı görünümler, not/yorum — bekliyor.
**I. Mobil/saha-içi:** ✓ tablet veri-giriş ekranı (`/performance` — büyük
dokunma hedefleri, protokol seçimi, anlık değerlendirme, PDF indir).
**J. Proaktif uyarı:** ✓ maç-içi uyarı motoru (`engine/live_alerts/`);
push/e-posta GÖNDERİMİ — bekliyor (infra).
**K. Performans/hız:** caching/asenkron — bekliyor (#9 Redis ile bağlantılı).
**L. KVKK / hassas veri uyumu:** ✓ `engine/compliance` (sınıflandırma + toplu
erişim anomali tespiti) + `DataAccessLog` + `/admin/compliance/{access-log,
audit}` (DPO denetimi); sağlık/performans verisi özel nitelikli olarak işlenir.

> Kalan (G/H/K + #7/#9/#10) gerçek altyapı (Redis/Postgres-replica) ya da
> frontend i18n çalışması gerektirir; deps-kurulu ortamda yapılmalı.

> Not: Auth (refresh sha256 + rotation, bcrypt 12-round) audit'te sağlam
> bulundu — tekrar ele alınmayacak.

## Tracking entegrasyonu (ertelendi — gerçek tracking feed bekliyor)
- `data/sources/tracking.py` — kulüp tracking adapter'ı (`DataSource`'a uyar)
- `engine/tracking/` — yerleşim, pres, yük çıkarımı

---

## Ufuk 1 — Çok-kulüp (multi-tenant) ✓
- [x] `tenants` + `users` + `refresh_tokens` tabloları (alembic 0011)
- [x] 16 domain tablosuna `tenant_id` NOT NULL FK (0011 NULLABLE + 0012 NOT NULL)
- [x] JWT auth (HS256, access 15dk + refresh 7g rotation)
- [x] 4 rol: admin | analyst | coach | viewer (`require_role` factory)
- [x] SQLAlchemy `with_loader_criteria` + `session.info["tenant_id"]` —
      her ORM query otomatik tenant'a filtre
- [x] Cross-tenant 404 (403 değil — exist'i bile gizle)
- [x] Backward-compat `BACKWARD_COMPAT_API_KEY` — eski X-API-Key entegrasyonu
- [x] 73 yeni test (login/JWT/refresh/role/isolation)

## Ufuk 2 — Görselleştirme/ön yüz
## Ufuk 3 — ML tahmin (`engine/predict/`) + otomasyon (`agents/`)
- Maç sonucu, sakatlık riski, oyuncu değeri
- Otomatik rapor, sürekli scout tarama, uyarılar
- `scheduler/` `agents/`'ı tetikler

## Ufuk 4 — Diğer sporlar
- `sports/basketball.py`, `sports/volleyball.py`
- `football.py`'yi şablon al
