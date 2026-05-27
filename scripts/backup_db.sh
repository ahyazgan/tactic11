#!/usr/bin/env bash
# Postgres DB yedeği (pg_dump custom format + gzip)
#
# Kullanım:
#   DATABASE_URL=postgresql://user:pw@host:5432/db ./scripts/backup_db.sh [output_dir]
#
# Output: <output_dir>/manager2-<YYYY-MM-DD-HHMMSS>.sql.gz
# Default output_dir: ./backups
#
# Cron örneği (her gece 03:00 UTC):
#   0 3 * * * cd /opt/manager2 && DATABASE_URL=... ./scripts/backup_db.sh /var/backups/manager2

set -euo pipefail

OUTPUT_DIR="${1:-./backups}"

if [[ -z "${DATABASE_URL:-}" ]]; then
    echo "ERROR: DATABASE_URL set edilmedi" >&2
    exit 1
fi

if [[ "$DATABASE_URL" != postgresql* ]]; then
    echo "ERROR: DATABASE_URL postgres olmalı (geldiği: $DATABASE_URL)" >&2
    echo "SQLite için yedek doğrudan dosya kopyasıdır:" >&2
    echo "  cp manager2.db ${OUTPUT_DIR}/manager2-\$(date +%Y-%m-%d).db" >&2
    exit 1
fi

mkdir -p "$OUTPUT_DIR"
TIMESTAMP="$(date -u +%Y-%m-%d-%H%M%S)"
OUT_FILE="${OUTPUT_DIR}/manager2-${TIMESTAMP}.sql.gz"

# pg_dump:
#   -F p : plain SQL (restore_db.sh psql ile geri yükler)
#   --no-owner : restore'da owner uyumsuzluğu olmasın
#   --no-privileges : grants restore'da çakışmasın
echo "Yedek alınıyor → $OUT_FILE"
pg_dump "$DATABASE_URL" \
    -F p \
    --no-owner \
    --no-privileges \
    | gzip -9 > "$OUT_FILE"

SIZE=$(du -h "$OUT_FILE" | cut -f1)
echo "Tamam — $OUT_FILE ($SIZE)"

# Eski yedekleri temizle (>30 gün) — opsiyonel, comment'i kaldır:
# find "$OUTPUT_DIR" -name 'manager2-*.sql.gz' -mtime +30 -delete
