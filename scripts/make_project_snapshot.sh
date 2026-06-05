#!/bin/bash
# Crea uno snapshot del progetto (.tgz) da allegare a una nuova sessione.
# Esclude file inutili/pesanti (venv, cache, .git, media, backup).
# Uso: bash scripts/make_project_snapshot.sh
set -e

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT="$HOME/sponsor_manager_snapshot_${TIMESTAMP}.tgz"

cd "$(dirname "$0")/.."

tar --exclude='./.git' \
    --exclude='./venv' \
    --exclude='./.venv' \
    --exclude='*/__pycache__' \
    --exclude='*.pyc' \
    --exclude='./media' \
    --exclude='./staticfiles' \
    --exclude='./node_modules' \
    --exclude='*.tgz' \
    --exclude='*.sql' \
    -czf "$OUTPUT" .

echo "Snapshot creato: $OUTPUT"
echo "Dimensione: $(du -h "$OUTPUT" | cut -f1)"
echo ""
echo "Percorso Windows per trovarlo:"
echo "  \\\\wsl\$\\Ubuntu\\home\\$USER\\$(basename "$OUTPUT")"
