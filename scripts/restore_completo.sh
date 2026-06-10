#!/bin/bash
# =============================================================================
# RESTORE COMPLETO PER TRASFERIMENTO
# =============================================================================
# Ripristina .env + database + media da un archivio creato con
# backup_completo.sh. Da lanciare sul NUOVO server, dalla cartella del progetto
# (dopo aver fatto: git clone + docker compose up -d almeno di db e web):
#   ./scripts/restore_completo.sh trasferimento_sponsor_AAAAMMGG_HHMMSS.tgz
#
# ATTENZIONE: sovrascrive .env, il database e i media del server corrente.
# =============================================================================
set -euo pipefail

ARCHIVE="${1:-}"
if [ -z "$ARCHIVE" ]; then
    echo "Uso: $0 <trasferimento_....tgz>"
    exit 1
fi

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

if [ ! -f "$ARCHIVE" ]; then
    echo "ERRORE: archivio non trovato: $ARCHIVE"
    exit 1
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
tar xzf "$ARCHIVE" -C "$WORK"

echo "ATTENZIONE: sto per SOVRASCRIVERE .env, database e media su questo server."
read -p "Continuare? (yes/no): " CONFIRM
[ "$CONFIRM" = "yes" ] || { echo "Annullato."; exit 0; }

# 1) .env (serve PRIMA, per avere DB_PASSWORD ecc.)
if [ -f "$WORK/.env" ]; then
    [ -f .env ] && cp .env ".env.prima_del_restore_$(date +%Y%m%d_%H%M%S)"
    cp "$WORK/.env" .env
    echo "[1/3] .env ripristinato (il precedente è salvato come .env.prima_del_restore_*)"
fi

get_env() { grep -E "^$1=" .env 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"'; }
DB_USER="$(get_env DB_USER)";  DB_USER="${DB_USER:-sponsor}"
DB_NAME="$(get_env DB_NAME)";  DB_NAME="${DB_NAME:-sponsor_manager}"

# Assicura che db e web siano su
docker compose up -d db web
echo "    attendo che il database sia pronto..."
sleep 5

# 2) database
if [ -f "$WORK/database.sql.gz" ]; then
    echo "[2/3] ripristino database ($DB_NAME)..."
    gunzip -c "$WORK/database.sql.gz" \
        | docker compose exec -T db psql -U "$DB_USER" -d "$DB_NAME" >/dev/null
    echo "    database ripristinato"
fi

# 3) media
if [ -f "$WORK/media.tgz" ]; then
    echo "[3/3] ripristino media/..."
    docker compose exec -T web sh -c 'mkdir -p /app/media && tar xzf - -C /app/media' \
        < "$WORK/media.tgz"
    echo "    media ripristinati"
fi

echo
echo "FATTO. Ora applica codice e riavvia tutto:"
echo "   git pull && docker compose build web && docker compose up -d"
