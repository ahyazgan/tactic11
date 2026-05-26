# db/

SQLAlchemy modelleri, session yönetimi, Alembic migration'ları.

**Bugün:** league, team, match, player tabloları + ilişkiler + ilk migration.
**Yarın:** snapshot, usage_log, validation_rejection, audit_record tabloları.

**Hazırlık (ufuk 1, multi-tenant):** Tablolar bugün `tenant_id` taşımıyor ama
indeks/PK tasarımı sonradan eklemeyi kolaylaştıracak şekilde basit tutulacak.

**Neye bağımlı:** `core/config` (DATABASE_URL), `domain/` (model eşlemesi).
