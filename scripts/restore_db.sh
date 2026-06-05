#!/bin/bash
# =============================================================================
# Restore database da backup
# =============================================================================
# Uso: ./restore_db.sh <path-al-backup.sql.gz>
#
# ATTENZIONE: questo cancella e ricrea il database. Usalo con coscienza.
# Prima fai sempre un backup del db corrente come "rete di sicurezza".
# =============================================================================

set -euo pipefail

if [ $# -eq 0 ]; then
    echo "Uso: $0 <backup.sql.gz>"
    exit 1
fi

BACKUP_FILE="$1"
PROJECT_DIR="/opt/sponsor_manager"

if [ ! -f "${BACKUP_FILE}" ]; then
    echo "ERRORE: file di backup non trovato: ${BACKUP_FILE}"
    exit 1
fi

# Carica env
if [ -f "${PROJECT_DIR}/.env" ]; then
    export $(grep -v '^#' "${PROJECT_DIR}/.env" | xargs)
fi

# Conferma
echo "ATTENZIONE: questa operazione cancellerà il database corrente."
echo "Database: ${DB_NAME}"
echo "Backup: ${BACKUP_FILE}"
read -p "Continuare? (yes/no): " CONFIRM
if [ "${CONFIRM}" != "yes" ]; then
    echo "Annullato."
    exit 0
fi

echo "[$(date)] Backup di sicurezza del db corrente..."
SAFETY_BACKUP="/tmp/safety_backup_$(date +%Y%m%d_%H%M%S).sql.gz"
docker compose -f "${PROJECT_DIR}/docker-compose.prod.yml" exec -T db \
    pg_dump -U "${DB_USER}" -d "${DB_NAME}" | gzip > "${SAFETY_BACKUP}"
echo "[$(date)] Backup di sicurezza salvato: ${SAFETY_BACKUP}"

echo "[$(date)] Restore in corso..."
gunzip -c "${BACKUP_FILE}" | docker compose -f "${PROJECT_DIR}/docker-compose.prod.yml" exec -T db \
    psql -U "${DB_USER}" -d "${DB_NAME}"

echo "[$(date)] Restore completato"
echo "Backup di sicurezza disponibile in: ${SAFETY_BACKUP}"
