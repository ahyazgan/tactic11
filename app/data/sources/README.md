# data/sources/

Veri kaynağı adapter'ları. Her dış kaynak `DataSource` arayüzüne uyan bir sınıftır.

**Bugün:**
- `base.py` — `DataSource` arayüzü (Faz 1; league/team/match için)
- `api_football.py` — API-Football adapter (Faz 1)
- `tracking.py` — `TrackingDataSource` ABC (Faz 6 sözleşmesi; somut adapter
  henüz yok). `DataSource` ile aynı interface'i kullanmaz — tracking verisi
  yüksek-frekans zaman serisidir, ayrı sözleşme daha doğru.

**İleride:**
- `tracking.py` somut implementasyon (örn. `SecondSpectrumAdapter`)
- `transfermarkt.py`, `understat.py` vb. — istenirse `DataSource`'a uyan adapter.

**Tasarım kuralı:** Adapter'lar API'nin ham yanıtını döndürmez; `domain/`
modellerine eşler. Böylece üst katmanlar kaynağa kayıtsızdır.
