# Deployment

Bu doküman yerel Docker Compose ve production VPS senaryolarını kapsar.

## Yerel (Docker Compose)

```bash
cp .env.example .env
# .env içinde mutlaka set et:
#   POSTGRES_PASSWORD=<güçlü>
#   API_AUTH_KEY=<rastgele 32+ byte>
#   API_FOOTBALL_KEY=<api-football anahtarın>   (yoksa USE_FIXTURES=true)
#   ANTHROPIC_API_KEY=<varsa>                   (yoksa Claude stub mod)

docker compose up -d --build
# migrate servisi alembic upgrade head'i çalıştırır ve exit eder.
# api servisi uvicorn ile :8000'de dinler.

curl -H "X-API-Key: $API_AUTH_KEY" http://localhost:8000/leagues
```

İlk veri yükleme:
```bash
docker compose exec api python scripts/run_job.py sync_league --league 203 --season 2024
```

## İlk gerçek sync — api-football production smoke

`USE_FIXTURES=true` ile sentetik veri yeterli; ama prod'a çıkmadan önce
`API_FOOTBALL_KEY`'in çalıştığını, kotanın yeterli olduğunu ve adapter'ın
gerçek response şeklini parse edebildiğini doğrulamak gerek.

### 1) API anahtarı edin
- [api-football](https://www.api-sports.io/documentation/football/v3) — RapidAPI
  veya doğrudan abonelik (Free plan: 100 req/gün; Pro: 7500/gün).
- Anahtarı `.env` içine yaz: `API_FOOTBALL_KEY=...`
- `API_FOOTBALL_DAILY_LIMIT` (default 100) planınla uyumlu olsun;
  yoksa `app/core/usage.py:consume_quota` kotayı boşa harcayıp 429 fırlatır.

### 2) Smoke (sync'ten ÖNCE — ~3 request harcar)
```bash
python scripts/api_football_smoke.py --key $API_FOOTBALL_KEY --league 203 --season 2024
# beklenen çıktı:
#   [1/3] /leagues   ✔ leagues   id=203 name='Süper Lig' seasons=N
#   [2/3] /teams     ✔ teams     count=20 sample=611:'Galatasaray'
#   [3/3] /fixtures  ✔ fixtures  count=5  sample=... 'Galatasaray' vs 'X' status=FT
#   OK — 3/3 endpoint passed.
```
Smoke geçmezse sync denemeden problemi izole et:
- HTTP 401/403 → anahtar yanlış veya plan kapsamı dışı endpoint
- `api errors → {requests: ...}` → günlük kota dolmuş, ertesi gün dene
- `response anahtarı eksik` → api-football tarafında schema değişikliği
  olmuş; issue aç ve adapter'ı güncelle (`app/data/sources/api_football.py`)

### 3) Kota durumunu kontrol et
```bash
curl -H "X-API-Key: $API_AUTH_KEY" http://localhost:8000/admin/quota-status
# api_football: { used: 3, limit: 100, fraction: 0.03 }
# warn fraction (default 0.80) altındaysa rahat; üstündeyse cron öncesi
# limit artır ya da daha az takım/sezon sync et.
```

### 4) İlk gerçek sync (~ 1 league + N team × 1 fixtures call)
```bash
# USE_FIXTURES=false olduğundan emin ol — yoksa gerçek API'a hiç dokunmaz
docker compose exec api env USE_FIXTURES=false python scripts/run_job.py sync_league --league 203 --season 2024 --last 10
# log çıktısında:
#   sync tamam: leagues=1 teams=20 matches=200 rejected=0 snapshot=<id>
```
Sync'ten sonra kotayı tekrar kontrol et (`/admin/quota-status`); 20 takım ×
1 fixtures call ≈ 22 request (1 leagues + 1 teams + 20 fixtures).

### 5) Veri akışını doğrula
```bash
curl -H "X-API-Key: $API_AUTH_KEY" http://localhost:8000/admin/db-stats
# matches > 0, teams > 0, leagues > 0 görmelisiniz
curl -H "X-API-Key: $API_AUTH_KEY" http://localhost:8000/admin/leagues-summary
# 203 / Süper Lig: teams_count=20, matches_count=200, last_snapshot=...
```

Logları izle:
```bash
docker compose logs -f api
```

Kapatmak için:
```bash
docker compose down            # container'ları durdur, volume kalır
docker compose down -v         # volume da silinir — veri kaybı!
```

## Multi-tenant migration (0011 + 0012) — production rollout

Tek-kulüp deploy'dan multi-tenant'a geçiş **2 aşamalı, zero-downtime** path:

### Önce: backup
```bash
DATABASE_URL=$DATABASE_URL ./scripts/backup_db.sh /var/backups/manager2-pre-multitenant
# → manager2-pre-multitenant-YYYY-MM-DD-HHMMSS.sql.gz
```
Roll-back için bu yedek kritik. Multi-tenant migration zorlu downgrade içerir.

### Aşama 1: alembic 0011 (NULLABLE + backfill)
```bash
# DB'ye tenants/users/refresh_tokens tabloları + tenant_id NULLABLE + default tenant seed
alembic upgrade 0011_tenants_and_tenant_id_nullable
```
Bu noktada:
- Eski uygulama hâlâ çalışır (tenant_id NULLABLE, app tenant filter kapalı)
- Yeni uygulama deploy edilebilir (session.info["tenant_id"] yazıyor)

### Yeni app deploy
```bash
# JWT_SECRET_KEY üret + .env'e yaz
python -c "import secrets; print(secrets.token_hex(32))"
# BACKWARD_COMPAT_API_KEY = eski API_AUTH_KEY değeri (kırılma yok)
systemctl restart manager2-api  # yeni binary, JWT auth aktif
```

### İlk admin user'ı yarat (default tenant'a)
```bash
python -c "
from app.db.session import SessionLocal
from app.db.tenant_context import DEFAULT_TENANT_ID
from app.auth.service import create_user
with SessionLocal() as s:
    u = create_user(s, tenant_id=DEFAULT_TENANT_ID,
                    email='admin@firma.com', password='YYYstrong-...',
                    role='admin')
    s.commit()
    print('user_id:', u.id)
"
```

### Aşama 2: alembic 0012 (NOT NULL + scoped uniques)
```bash
# Tüm satırlar tenant'a backfill'lendi, kod tenant_id yazıyor → NOT NULL güvenli
alembic upgrade 0012_tenant_id_not_null_and_scoped_uniques
```
Bu migration aynı external_id'nin farklı tenant'larda yaşamasını sağlar
(uq_teams_sport_extid → sport+external_id+tenant_id).

### Yeni tenant ekleme (Konyaspor + Antalyaspor pilot)
```bash
python -c "
from datetime import datetime, UTC
import uuid
from app.db.session import SessionLocal
from app.db import models
from app.auth.service import create_user
with SessionLocal() as s:
    for slug, name in [('konyaspor','Konyaspor'),('antalyaspor','Antalyaspor')]:
        t = models.Tenant(id=str(uuid.uuid4()), slug=slug, name=name,
                          settings_json='{}', active=True,
                          created_at=datetime.now(UTC))
        s.add(t); s.flush()
        create_user(s, tenant_id=t.id, email=f'admin@{slug}.com',
                    password='change-me-' + slug, role='admin')
    s.commit()
"
```

### Sync per-tenant
```bash
# Tenant context'i set ederek sync — her tenant kendi verisini çeker
# (Sync job tenant_id'yi context'e yazmalı; bu otomatize edilecek — Prompt 3)
```

### Roll-back (0011'e dön)
```bash
alembic downgrade 0011_tenants_and_tenant_id_nullable
# Sonra eski app version'a geri dön → tenant_id NULLABLE, eski davranış
```
0011'in altına (`0010`) dönmek tenants tablosunu DROP eder — sadece backup'tan
restore mümkün, normal downgrade VERİ KAYBI riski içerir.

## Production VPS (systemd + cron + Postgres)

Compose dışı, daha klasik kurulum.

### 1) Bağımlılıklar
```bash
sudo apt update && sudo apt install -y python3.11 python3.11-venv postgresql postgresql-contrib
sudo -u postgres createuser --pwprompt manager2
sudo -u postgres createdb -O manager2 manager2
```

### 2) Kod + venv
```bash
sudo mkdir -p /opt/manager2 && sudo chown $USER /opt/manager2
git clone <repo> /opt/manager2 && cd /opt/manager2
python3.11 -m venv venv
venv/bin/pip install -r requirements.txt
cp .env.example .env  # düzenle
venv/bin/alembic upgrade head
```

### 3) systemd unit (`/etc/systemd/system/manager2-api.service`)
```ini
[Unit]
Description=football-intelligence API
After=network.target postgresql.service

[Service]
Type=exec
User=manager2
WorkingDirectory=/opt/manager2
EnvironmentFile=/opt/manager2/.env
ExecStart=/opt/manager2/venv/bin/uvicorn app.api.main:app --host 127.0.0.1 --port 8000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now manager2-api
sudo systemctl status manager2-api
```

Nginx önünde reverse proxy + TLS önerilir (`proxy_pass http://127.0.0.1:8000`).

### 4) Cron (`crontab -e` — manager2 kullanıcısı)
```cron
# 06:00 UTC — Süper Lig sync (1. iş — veri tazele)
0 6 * * * cd /opt/manager2 && venv/bin/python scripts/run_job.py sync_league --league 203 --season 2024 >> /var/log/manager2-cron.log 2>&1

# 06:15 UTC — Morning brief (Faz 5 #18): bugün maçı olan takımların
# PreMatchReportAgent çıktıları tazelenir. sync_league'ten 15 dk sonra
# tetiklenmeli — fresh verilerle çalışsın.
15 6 * * * cd /opt/manager2 && venv/bin/python scripts/run_job.py morning_brief >> /var/log/manager2-cron.log 2>&1

# 03:00 UTC — Geçen günkü maçların tahmin sonuçlarını uzlaştır (kalibrasyon)
0 3 * * * cd /opt/manager2 && venv/bin/python scripts/run_job.py reconcile_predictions >> /var/log/manager2-cron.log 2>&1

# Pazartesi 04:00 UTC — predict_ml haftalık retrain
0 4 * * 1 cd /opt/manager2 && venv/bin/python scripts/run_job.py train_predict_ml >> /var/log/manager2-cron.log 2>&1
```
`run_job.py` başarısızsa exit 1 döner — cron MAILTO ile uyarı gönderir.

#### Cron zinciri mantığı
- **sync_league (06:00)** → API-Football'dan günün maç + sonuç verisi.
- **morning_brief (06:15)** → fresh veriler üstünden bugün maçı olan
  takımlar için PreMatchReportAgent çıktısı; `run_pre_match_reports`
  job'unu `horizon_days=1` ile çağıran kabuk. Idempotent: aynı maçın
  output'u tazelenir (`save_agent_output` upsert).
- **reconcile_predictions (03:00 gece)** → dünkü maçların actual sonucunu
  predictions tablosuna yazar; ML retrain için lazım.
- **train_predict_ml (Pzt 04:00)** → haftalık best ρ retrain; cache_entries
  içine 30 gün TTL ile yazar.

Saat dilimi: cron expression'ları **UTC** kabul edilir (server timezone).
Lokal saatte istersen crontab'in başına `TZ=Europe/Istanbul` ekle.

## Production checklist

- [ ] `API_AUTH_KEY` set edildi (uvicorn startup'ta uyarı varsa unutuldu demektir)
- [ ] `DATABASE_URL` Postgres (SQLite production için değil)
- [ ] `USE_FIXTURES=false` (sadece dev/test için true)
- [ ] `API_FOOTBALL_KEY` valid; `API_FOOTBALL_DAILY_LIMIT` kotanıza uygun
- [ ] `ANTHROPIC_API_KEY` set ise `ANTHROPIC_DAILY_TOKEN_LIMIT` makul (default 200k)
- [ ] `.env` dosyası repo'ya commit edilmedi (`.gitignore` zaten engelliyor)
- [ ] Alembic migrasyonları uygulandı (`alembic current` head'i göstermeli)
- [ ] Cron çalıştığını ilk çağrıdan sonra `job_runs` tablosundan doğrula:
      `SELECT job_name, status, attempts, started_at FROM job_runs ORDER BY started_at DESC LIMIT 5;`
- [ ] `/health` endpoint'i 200 dönüyor; load balancer probe'a uygun
- [ ] DB yedeği zamanlı (`scripts/backup_db.sh` cron'da, günlük; aylık restore drill — bkz. Backup & Recovery bölümü)

## Backup & Recovery

Postgres üretiminde günlük yedek + aylık restore drill önerilir. Repo'da
hazır script'ler var:

### Manuel yedek
```bash
DATABASE_URL=$DATABASE_URL ./scripts/backup_db.sh /var/backups/manager2
# → /var/backups/manager2/manager2-2026-05-27-030000.sql.gz
```

Plain SQL dump + gzip; `--no-owner --no-privileges` ile restore'da
owner uyumsuzluğu önlenir.

### Cron (günlük 03:00 UTC)
```cron
0 3 * * * cd /opt/manager2 && DATABASE_URL=$(grep ^DATABASE_URL .env | cut -d= -f2-) ./scripts/backup_db.sh /var/backups/manager2 >> /var/log/manager2-backup.log 2>&1
```

### Restore drill (ayrı bir DB üzerinde, ayda bir)
```bash
# Test DB oluştur
createdb manager2_restore_test

# Restore
DATABASE_URL=postgresql://user:pw@localhost/manager2_restore_test \
  ./scripts/restore_db.sh /var/backups/manager2/manager2-2026-05-27-030000.sql.gz

# Doğrula
psql manager2_restore_test -c "SELECT version_num FROM alembic_version;"
psql manager2_restore_test -c "SELECT COUNT(*) FROM matches;"

# Bitince temizle
dropdb manager2_restore_test
```

### Eski yedekleri temizle
`backup_db.sh`'in altındaki `find ... -mtime +30 -delete` satırını yorum dışına
al (default opt-in; veri retention politikanız net oluncaya kadar saklamak
daha güvenli).

### S3 / external storage (opsiyonel)
```cron
# Her sabah yedek aldıktan sonra S3'e yükle
5 3 * * * aws s3 sync /var/backups/manager2 s3://my-bucket/manager2-backups/ --no-progress
```
Yerel disk yangını riskini azaltır; AWS region farkı (multi-region) için S3
Cross-Region Replication kullan.

### RTO / RPO
- **RPO** (Recovery Point Objective): 24 saat — günlük yedek penceresi
- **RTO** (Recovery Time Objective): ~15 dk (küçük DB, ~50MB)
- Daha sıkı RPO için Postgres WAL archiving + Point-in-Time-Recovery (PITR)
  ayrı bir RFC; bu repo'nun kapsamı dışında

## Sağlık kontrolü

Operasyonel sorular için iki yol var: `/admin/*` HTTP uçları (auth gerekli)
ya da doğrudan psql. HTTP daha pratik, psql ise debug için.

```bash
# API canlı mı?
curl http://localhost:8000/health  # → {"status":"ok"}

# Auth doğru mu?
curl -H "X-API-Key: $API_AUTH_KEY" http://localhost:8000/leagues

# Sync ne durumda? — son 24 saatin job run'ları
curl -H "X-API-Key: $API_AUTH_KEY" "http://localhost:8000/admin/jobs?since_hours=24"

# Sadece başarısızları gör
curl -H "X-API-Key: $API_AUTH_KEY" "http://localhost:8000/admin/jobs?status=failed&since_hours=168"

# Bugün ve bu ay kota tüketimi (source başına call + token)
curl -H "X-API-Key: $API_AUTH_KEY" http://localhost:8000/admin/usage

# Bir lig için snapshot tarihçesi (tahmin yakıtı)
curl -H "X-API-Key: $API_AUTH_KEY" "http://localhost:8000/admin/snapshots?scope=league:203:season:2024"

# Tablo boyutları — sync ilerlemesi hızlı bakış
curl -H "X-API-Key: $API_AUTH_KEY" http://localhost:8000/admin/db-stats

# --- Doğrudan psql (debug için) ---
psql $DATABASE_URL -c "SELECT job_name, status, attempts, error FROM job_runs ORDER BY started_at DESC LIMIT 5;"
psql $DATABASE_URL -c "SELECT source, COUNT(*) FROM usage_events WHERE created_at > now() - interval '1 day' GROUP BY source;"
psql $DATABASE_URL -c "SELECT scope, leagues_count, teams_count, matches_count, created_at FROM snapshots ORDER BY created_at DESC LIMIT 10;"
```
