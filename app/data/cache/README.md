# data/cache/

API'yi gereksiz yere yakmamak için cache katmanı.

**Ne yapar:** Adapter çağrılarını anahtarlayıp (provider + endpoint + parametre)
süreli olarak saklar. Önce cache'e bakılır, yoksa kaynağa gidilir.

**Ne zaman dolacak:** Faz 1 (basit DB tabanlı cache yeterli; in-memory de olur).
**Neye bağımlı:** `db/` veya bellek; başka katmana bağımlı değil.
