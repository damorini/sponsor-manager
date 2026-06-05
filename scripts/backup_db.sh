#!/bin/bash
# =============================================================================
# Backup automatico database PostgreSQL
# =============================================================================
# Da eseguire ogni notte via cron sul server di produzione.
# Comprime il dump e lo carica su Backblaze B2 (storage economico per backup).
# Mantiene 90 giorni di retention.
#
# Setup cron (sul server, non nel container):
#   0 3 * * * /opt/sponsor_manager/scripts/backup_db.sh >> /var/log/sponsor-backup.log 2>&1
# =============================================================================

set -euo pipefail

# Config
PROJECT_DIR="/opt/sponsor_manager"
BACKUP_DIR="${PROJECT_DIR}/deploy/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="sponsor_manager_${TIMESTAMP}.sql.gz"
RETENTION_DAYS=90

# Carica variabili d'ambiente
if [ -f "${PROJECT_DIR}/.env" ]; then
    export $(grep -v '^#' "${PROJECT_DIR}/.env" | xargs)
fi

mkdir -p "${BACKUP_DIR}"

echo "[$(date)] Avvio backup..."

# Esegue pg_dump dentro il container db, compresso al volo
docker compose -f "${PROJECT_DIR}/docker-compose.prod.yml" exec -T db \
    pg_dump -U "${DB_USER}" -d "${DB_NAME}" --clean --if-exists | gzip > "${BACKUP_DIR}/${BACKUP_FILE}"

BACKUP_SIZE=$(du -h "${BACKUP_DIR}/${BACKUP_FILE}" | cut -f1)
echo "[$(date)] Backup locale completato: ${BACKUP_FILE} (${BACKUP_SIZE})"

# Upload su Backblaze B2 (richiede tool b2 installato sul server)
# Se non hai B2, commenta questa sezione e usa solo backup locali
if command -v b2 &> /dev/null && [ -n "${B2_BUCKET_NAME:-}" ]; then
    echo "[$(date)] Upload su Backblaze B2..."
    b2 file upload "${B2_BUCKET_NAME}" "${BACKUP_DIR}/${BACKUP_FILE}" "backups/${BACKUP_FILE}"
    echo "[$(date)] Upload completato"
fi

# Pulizia backup locali vecchi (mantieni N giorni)
find "${BACKUP_DIR}" -name "sponsor_manager_*.sql.gz" -mtime +${RETENTION_DAYS} -delete
echo "[$(date)] Pulizia backup vecchi (>${RETENTION_DAYS} giorni) completata"

echo "[$(date)] Backup completato con successo"
