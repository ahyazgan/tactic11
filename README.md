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

## Çalıştırma
```bash
# 1) Bir lig + sezonu çek, doğrula, DB'ye yaz, snapshot al
python scripts/sync_league.py --league 203 --season 2024

# 2) API'yi ayağa kaldır
uvicorn app.api.main:app --reload
# GET /health
# GET /leagues
# GET /teams/{league_id}
# GET /teams/{team_id}/matches

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

Detaylı yol haritası: [ROADMAP.md](ROADMAP.md).
