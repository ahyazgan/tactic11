# data/ingest/

Orkestrasyon katmanı: bir kaynaktan veri çek → doğrula → normalize et → DB'ye yaz
→ snapshot al.

**Ne yapar:** Adapter'ı çağırır, sonucu `validation/`'a verir, geçenleri DB'ye
yazar, `snapshot/`'a son durumu kaydeder. Hatalı kayıtları işaretler.

**Ne zaman dolacak:** Faz 1.
**Neye bağımlı:** `data/sources/`, `data/validation/`, `db/`, `snapshot/`.
