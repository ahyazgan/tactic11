# ROADMAP

Mimari uzun vadeli vizyona göre baştan kurulur, ama her faz sadece o fazın
kodunu yazar. Boş iskeletler yer tutar; sırası gelince doldurulur.

---

## Faz 1 — Veri katmanı çalışır (BUGÜN)
**Hedef:** API-Football'dan veri çekip doğrulayıp DB'ye yazmak ve okumak.

- [x] `app/core/config.py` — pydantic-settings ile `.env` okuma
- [x] `app/core/logging.py` — yapılandırılmış log
- [ ] `app/core/usage/` — API çağrı sayacı + eşik kontrolü
- [x] `app/domain/` — League, Team, Match, Player (pydantic)
- [x] `app/db/` — SQLAlchemy modelleri + Alembic ilk migration
- [x] `app/data/sources/base.py` — `DataSource` arayüzü
- [x] `app/data/sources/api_football.py` — adapter (fixture modlu; cache/rate-limit sonraki tur)
- [ ] `app/data/cache/` — basit cache (DB veya bellek)
- [x] `app/data/validation/` — kural listesi + çalıştırıcı
- [x] `app/data/ingest/` — çek + doğrula + normalize + yaz
- [ ] `app/snapshot/` — her sync'te durum özeti, üzerine yazmadan
- [x] `app/api/main.py` — FastAPI app + `/health`, `/leagues`, `/teams/...`
- [x] `app/sports/football.py` — futbol sabitleri
- [x] `scripts/sync_league.py` — uçtan uca CLI
- [x] `tests/fixtures/` — örnek JSON + fixture modu

**Faz 1 bitiş kriteri:** `.env` doldur → `alembic upgrade head` →
`python scripts/sync_league.py --league 203 --season 2024` → DB'de takımlar
görünür → `GET /teams/203` boş değil.

---

## Faz 2 — Analiz motoru
- `engine/form/` — son N maç trendi, ev/deplasman, gol farkı
- `engine/load/` — oyuncu yük/rotasyon (dakika, maç sıklığı)
- `engine/rating/` — basit takım/oyuncu skoru
- `engine/opponent/` — rakip örüntü analizi
- `audit/` doldurulmaya başlar: her motor çıktısı gerekçeli

**Kural:** engine fonksiyonları saf. İçeri veri (pydantic model / DataFrame),
dışarı hesap. DB/API/LLM bilmez.

---

## Faz 3 — AI yorum katmanı
- `ai/` — engine çıktısını Claude'a verip insan diline çevirir
- Prompt'lar şablonlu, motor sayıları üzerinden açıklama üretir
- `core/usage/` Claude token'larını da sayar

---

## Faz 4 — Scheduler
- `scheduler/` — günlük otomatik sync (Faz 1'deki CLI'yi tetikler)
- Görev kaydı, başarısız çalıştırma yeniden deneme

---

## Faz 5 — API olgunlaşır
- Analiz endpoint'leri (`/teams/{id}/form`, `/matches/{id}/preview`)
- Auth (kullanıcı/rol)

---

## Faz 6 — Tracking entegrasyonu
- `data/sources/tracking.py` — kulüp tracking adapter'ı (`DataSource`'a uyar)
- `engine/tracking/` — yerleşim, pres, yük çıkarımı

---

## Ufuk 1 — Çok-kulüp (multi-tenant)
- DB modellerine `tenant_id` eklenir (bugün varsayım gömülmedi, kolay olacak)

## Ufuk 2 — Görselleştirme/ön yüz
## Ufuk 3 — ML tahmin (`engine/predict/`) + otomasyon (`agents/`)
- Maç sonucu, sakatlık riski, oyuncu değeri
- Otomatik rapor, sürekli scout tarama, uyarılar
- `scheduler/` `agents/`'ı tetikler

## Ufuk 4 — Diğer sporlar
- `sports/basketball.py`, `sports/volleyball.py`
- `football.py`'yi şablon al
