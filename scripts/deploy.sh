#!/bin/bash
# =============================================================================
# Deploy in produzione
# =============================================================================
# Da eseguire sul server VPS dopo aver fatto git pull.
# Esegue: build immagine, migrate, collectstatic, restart container app.
# Non riavvia db/redis (zero downtime per il database).
# =============================================================================

set -euo pipefail

PROJECT_DIR="/opt/sponsor_manager"
cd "${PROJECT_DIR}"

echo "[$(date)] === Deploy iniziato ==="

# 1. Pull ultimo codice
echo "[$(date)] Git pull..."
git pull origin main

# 2. Build nuova immagine app
echo "[$(date)] Build immagine Docker..."
docker compose -f docker-compose.prod.yml build app celery_worker celery_beat

# 3. Esegue migrate (in un container temporaneo)
echo "[$(date)] Esecuzione migrazioni..."
docker compose -f docker-compose.prod.yml run --rm app python manage.py migrate --noinput

# 4. Collectstatic
echo "[$(date)] Raccolta file statici..."
docker compose -f docker-compose.prod.yml run --rm app python manage.py collectstatic --noinput

# 5. Compila traduzioni
echo "[$(date)] Compilazione traduzioni..."
docker compose -f docker-compose.prod.yml run --rm app python manage.py compilemessages

# 6. Riavvia solo i servizi applicativi (db, redis, nginx restano up)
echo "[$(date)] Riavvio servizi app..."
docker compose -f docker-compose.prod.yml up -d --no-deps app celery_worker celery_beat

# 7. Reload nginx (per nuovi file statici)
echo "[$(date)] Reload nginx..."
docker compose -f docker-compose.prod.yml exec nginx nginx -s reload

# 8. Pulizia immagini Docker vecchie
echo "[$(date)] Pulizia immagini vecchie..."
docker image prune -f

echo "[$(date)] === Deploy completato con successo ==="
