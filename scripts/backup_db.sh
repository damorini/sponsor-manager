#!/bin/bash
# =============================================================================
# Backup automatico database PostgreSQL
# =============================================================================
# Da eseguire ogni notte via cron sul server di produzione.
# Comprime il dump e (se configurato) lo carica su Backblaze B2.
# Mantiene 90 giorni di retention.
#
# Setup cron (sul server, non nel container):
#   0 3 * * * /opt/sponsor_manager/scripts/backup_db.sh >> /var/log/sponsor-backup.log 2>&1
# =============================================================================

set -euo pipefail

# Config
PROJECT_DIR="${PROJECT_DIR:-/opt/sponsor_manager}"
COMPOSE_FILE="${PROJECT_DIR}/docker-compose.yml"
BACKUP_DIR="${PROJECT_DIR}/deploy/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="sponsor_manager_${TIMESTAMP}.sql.gz"
RETENTION_DAYS=90

# Credenziali DB: valori letterali della docker-compose.yml (servizio db),
# sovrascrivibili via ambiente. NON letti da .env (lì non ci sono).
DB_NAME="${DB_NAME:-sponsor_manager}"
DB_USER="${DB_USER:-sponsor}"

mkdir -p "${BACKUP_DIR}"
DEST="${BACKUP_DIR}/${BACKUP_FILE}"

echo "[$(date)] Avvio backup (${DB_NAME})..."

# Dump dentro il container db, compresso al volo.
# pipefail fa fallire lo script se pg_dump fallisce (anche dietro la pipe).
docker compose -f "${COMPOSE_FILE}" exec -T db \
    pg_dump -U "${DB_USER}" -d "${DB_NAME}" --clean --if-exists | gzip > "${DEST}"

# Verifica anti-"backup vuoto": il file deve esistere, non essere vuoto ed
# essere un gzip valido. Altrimenti rimuovilo e fallisci rumorosamente.
if [ ! -s "${DEST}" ] || ! gzip -t "${DEST}" 2>/dev/null; then
    echo "[$(date)] ERRORE: backup non valido o vuoto. Rimuovo ${BACKUP_FILE} e fallisco." >&2
    rm -f "${DEST}"
    exit 1
fi

BACKUP_SIZE=$(du -h "${DEST}" | cut -f1)
echo "[$(date)] Backup locale OK: ${BACKUP_FILE} (${BACKUP_SIZE})"

# Upload opzionale su Backblaze B2 (solo se 'b2' installato e bucket impostato)
if command -v b2 &> /dev/null && [ -n "${B2_BUCKET_NAME:-}" ]; then
    echo "[$(date)] Upload su Backblaze B2..."
    b2 file upload "${B2_BUCKET_NAME}" "${DEST}" "backups/${BACKUP_FILE}"
    echo "[$(date)] Upload completato"
fi

# Pulizia backup locali piu' vecchi di N giorni
find "${BACKUP_DIR}" -name "sponsor_manager_*.sql.gz" -mtime +${RETENTION_DAYS} -delete
echo "[$(date)] Backup completato con successo"
