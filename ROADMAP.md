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

## Faz 6 — Tracking entegrasyonu
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
