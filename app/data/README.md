# data/

Dış dünyadan veri çekme, doğrulama, normalize etme, DB'ye yazma katmanı.

Alt klasörler:
- `sources/` — her veri kaynağı bir adapter (api_football, ileride tracking)
- `cache/` — API yakmamak için cache
- `validation/` — DB'ye yazmadan önce kural kontrolü
- `ingest/` — orkestrasyon: çek → doğrula → normalize → yaz

**Neye bağımlı:** `core/`, `domain/`, `db/`.
**Bağımlı olmayan:** `engine/`, `ai/`, `agents/`, `api/`.
