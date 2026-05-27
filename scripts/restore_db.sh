#!/usr/bin/env bash
# Postgres DB restore — backup_db.sh çıktısından geri yükler
#
# Kullanım:
#   DATABASE_URL=postgresql://... ./scripts/restore_db.sh <backup_file.sql.gz>
#
# UYARI: Hedef DB'deki tüm tabloları DROP+RECREATE eder (pg_dump plain SQL).
# Drill için ayrı bir DB üzerinde çalıştırın.

set -euo pipefail

if [[ $# -lt 1 ]]; then
    echo "Kullanım: DATABASE_URL=postgresql://... $0 <backup_file.sql.gz>" >&2
    exit 1
fi

BACKUP_FILE="$1"

if [[ ! -f "$BACKUP_FILE" ]]; then
    echo "ERROR: dosya bulunamadı: $BACKUP_FILE" >&2
    exit 1
fi

if [[ -z "${DATABASE_URL:-}" ]]; then
    echo "ERROR: DATABASE_URL set edilmedi" >&2
    exit 1
fi

if [[ "$DATABASE_URL" != postgresql* ]]; then
    echo "ERROR: DATABASE_URL postgres olmalı" >&2
    exit 1
fi

echo "UYARI: $DATABASE_URL üzerindeki veriler $BACKUP_FILE ile değiştirilecek."
read -p "Devam etmek için 'evet' yaz: " CONFIRM
if [[ "$CONFIRM" != "evet" ]]; then
    echo "İptal."
    exit 1
fi

echo "Restore başlıyor..."
gunzip -c "$BACKUP_FILE" | psql "$DATABASE_URL"
echo "Tamam."

# Restore sonrası alembic_version doğru mu?
echo
echo "Alembic durum:"
psql "$DATABASE_URL" -c "SELECT version_num FROM alembic_version;" || true
