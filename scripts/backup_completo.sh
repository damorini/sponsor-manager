#!/bin/bash
# =============================================================================
# BACKUP COMPLETO PER TRASFERIMENTO
# =============================================================================
# Crea UN SOLO file .tgz che contiene tutto cio' che NON sta su GitHub e che
# va portato a mano su un nuovo server:
#   1) .env          (segreti e configurazione: chiavi, password, IBAN, ...)
#   2) database      (pg_dump completo)
#   3) media/        (file caricati: logo segreteria, header eventi, loghi
#                     sponsor, PDF/DOCX generati)
#
# Da lanciare sul server ATTUALE (sorgente), dalla cartella del progetto:
#   ./scripts/backup_completo.sh
# Poi copia il .tgz risultante sul nuovo server e lancia restore_completo.sh.
# =============================================================================
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

# Legge nome/utente DB dal .env, con default coerenti col docker-compose.yml
get_env() { grep -E "^$1=" .env 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"'; }
DB_USER="$(get_env DB_USER)";  DB_USER="${DB_USER:-sponsor}"
DB_NAME="$(get_env DB_NAME)";  DB_NAME="${DB_NAME:-sponsor_manager}"

TS="$(date +%Y%m%d_%H%M%S)"
OUT="${PROJECT_DIR}/trasferimento_sponsor_${TS}.tgz"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

if [ ! -f .env ]; then
    echo "ERRORE: .env non trovato in $PROJECT_DIR — sei nella cartella giusta?"
    exit 1
fi

echo "[1/3] copio .env"
cp .env "$WORK/.env"

echo "[2/3] dump database ($DB_NAME)..."
docker compose exec -T db pg_dump -U "$DB_USER" -d "$DB_NAME" --clean --if-exists \
    | gzip > "$WORK/database.sql.gz"

echo "[3/3] archivio media/ dal container..."
docker compose exec -T web tar czf - -C /app/media . > "$WORK/media.tgz"

tar czf "$OUT" -C "$WORK" .

echo
echo "FATTO -> $OUT"
du -h "$OUT" | cut -f1 | sed 's/^/   dimensione: /'
echo "Copialo sul nuovo server (es. scp) e lancia: ./scripts/restore_completo.sh <file.tgz>"
