#!/bin/bash
# =============================================================================
# Restore database da backup
# =============================================================================
# Uso: ./restore_db.sh <path-al-backup.sql.gz>
#
# ATTENZIONE: questo sovrascrive il database corrente. Usalo con coscienza.
# Lo script fa SEMPRE un backup di sicurezza del db attuale prima di procedere.
# =============================================================================

set -euo pipefail

if [ $# -eq 0 ]; then
    echo "Uso: $0 <backup.sql.gz>"
    exit 1
fi

BACKUP_FILE="$1"
PROJECT_DIR="${PROJECT_DIR:-/opt/sponsor_manager}"
COMPOSE_FILE="${PROJECT_DIR}/docker-compose.yml"

# Credenziali DB: valori letterali della docker-compose.yml, override via env.
DB_NAME="${DB_NAME:-sponsor_manager}"
DB_USER="${DB_USER:-sponsor}"

if [ ! -f "${BACKUP_FILE}" ]; then
    echo "ERRORE: file di backup non trovato: ${BACKUP_FILE}"
    exit 1
fi
if ! gzip -t "${BACKUP_FILE}" 2>/dev/null; then
    echo "ERRORE: ${BACKUP_FILE} non e' un gzip valido."
    exit 1
fi

# Conferma
echo "ATTENZIONE: questa operazione sovrascrivera' il database corrente."
echo "Database: ${DB_NAME}"
echo "Backup:   ${BACKUP_FILE}"
read -p "Continuare? (yes/no): " CONFIRM
if [ "${CONFIRM}" != "yes" ]; then
    echo "Annullato."
    exit 0
fi

echo "[$(date)] Backup di sicurezza del db corrente..."
SAFETY_BACKUP="/tmp/safety_backup_$(date +%Y%m%d_%H%M%S).sql.gz"
docker compose -f "${COMPOSE_FILE}" exec -T db \
    pg_dump -U "${DB_USER}" -d "${DB_NAME}" | gzip > "${SAFETY_BACKUP}"
if [ ! -s "${SAFETY_BACKUP}" ] || ! gzip -t "${SAFETY_BACKUP}" 2>/dev/null; then
    echo "ERRORE: il backup di sicurezza e' fallito. Annullo il restore." >&2
    exit 1
fi
echo "[$(date)] Backup di sicurezza salvato: ${SAFETY_BACKUP}"

echo "[$(date)] Restore in corso..."
gunzip -c "${BACKUP_FILE}" | docker compose -f "${COMPOSE_FILE}" exec -T db \
    psql -U "${DB_USER}" -d "${DB_NAME}"

echo "[$(date)] Restore completato"
echo "Backup di sicurezza disponibile in: ${SAFETY_BACKUP}"
