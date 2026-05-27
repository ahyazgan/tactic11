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

Logları izle:
```bash
docker compose logs -f api
```

Kapatmak için:
```bash
docker compose down            # container'ları durdur, volume kalır
docker compose down -v         # volume da silinir — veri kaybı!
```

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
# Her sabah 06:00 UTC — Süper Lig sync
0 6 * * * cd /opt/manager2 && venv/bin/python scripts/run_job.py sync_league --league 203 --season 2024 >> /var/log/manager2-cron.log 2>&1
```
`run_job.py` başarısızsa exit 1 döner — cron MAILTO ile uyarı gönderir.

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
