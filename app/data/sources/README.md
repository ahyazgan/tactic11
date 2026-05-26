# data/sources/

Veri kaynağı adapter'ları. Her dış kaynak `DataSource` arayüzüne uyan bir sınıftır.

**Bugün:**
- `base.py` — `DataSource` arayüzü (Faz 1)
- `api_football.py` — API-Football adapter (Faz 1)

**İleride:**
- `tracking.py` — kulüp tracking adapter (Faz 6). Aynı arayüze uyacak.
- `transfermarkt.py`, `understat.py` vb. — istenirse aynı şekilde eklenir.

**Tasarım kuralı:** Adapter'lar API'nin ham yanıtını döndürmez; `domain/`
modellerine eşler. Böylece üst katmanlar kaynağa kayıtsızdır.
