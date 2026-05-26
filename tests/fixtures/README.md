# tests/fixtures/

Gerçek API yanıtlarından alınmış örnek JSON veri setleri.

**Amaç:**
- Testler API'ye dokunmasın, hızlı çalışsın, kota yakmasın.
- Geliştirme sırasında "fixture modu" açılırsa adapter API yerine buradan okur.

**Fixture modu:** `.env` içinde `USE_FIXTURES=true` → `data/sources/api_football.py`
gerçek HTTP yerine bu klasördeki dosyaları döndürür.

**Beklenen dosyalar (Faz 1):**
- `leagues.json`
- `teams_<league_id>.json`
- `matches_<team_id>.json`

Dosyalar API'nin ham yanıtının küçük örnekleri olur; adapter yine bunları
`domain/` modeline çevirir.
