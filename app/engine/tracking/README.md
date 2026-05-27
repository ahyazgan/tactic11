# engine/tracking/

**Faz 6: kulüp tracking verisi gelince doldurulacak.**
Şimdi: sözleşme + stub. Çağrılırsa `NotImplementedError`.

Tracking verisinden (oyuncu konumları, hız) anlamlı sinyaller çıkaran saf
algoritmalar. Diğer engine modülleriyle aynı kural: girdi
`Iterable[TrackingFrame]`, çıktı `EngineResult[T]` (value + AuditRecord).
DB/HTTP/LLM yok.

**Planlanan üretimler:**
- `compute_formation()` — kümeleme ile yerleşim ('4-3-3', '4-2-3-1', ...)
- `compute_pressure()` — top sahibine yakın rakip oyuncu sayısı / sürede
- (daha sonra) defansif blok yüksekliği, tracking-tabanlı oyuncu yükü

**Bağımlılıklar (hazır):**
- `app/domain/tracking.py` → `TrackingFrame`, `PlayerPosition`
- `app/data/sources/tracking.py` → `TrackingDataSource` ABC (somut adapter yok)

**Faz 6 için gerekenler:**
1. En az bir somut adapter (`SecondSpectrumAdapter`, `HawkEyeAdapter` vb.)
2. `data/ingest/tracking_sync.py` — frame batch upsert
3. `db/models.py` → `TrackingFrame` tablosu + migration
4. Bu modülün gerçek implementasyonu (stub'ları doldur)
