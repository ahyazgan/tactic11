# api/

FastAPI uygulaması ve router'lar.

**Faz 1 endpoint'leri:** sadece DB'den okur, dış kaynağa dokunmaz.
- `GET /health`
- `GET /leagues`
- `GET /teams/{league_id}`
- `GET /teams/{team_id}/matches`

**Faz 5'te eklenecekler:** analiz endpoint'leri, auth.

**Bağımlılık yönü:** `api → ai → engine → domain`. API doğrudan adapter'lara
çağrı yapmaz; sync `scripts/sync_league.py` veya ileride `scheduler/` üzerinden olur.
