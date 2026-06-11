#!/bin/bash
# =============================================================================
# Deploy in produzione (Docker Compose)
# =============================================================================
# Da eseguire sul server dopo aver clonato/aggiornato il repo.
# Prerequisiti sul server: Docker + Docker Compose, e un file .env accanto al
# docker-compose.yml con almeno SECRET_KEY, DB_PASSWORD, ALLOWED_HOSTS.
#
# Il container 'web' esegue da solo migrate + compilemessages + collectstatic
# all'avvio (vedi docker-compose.yml), quindi qui basta build + up.
# =============================================================================

set -euo pipefail

# Cartella del progetto (modifica se il repo non è in /opt/sponsor_manager)
PROJECT_DIR="${PROJECT_DIR:-/opt/sponsor_manager}"
cd "${PROJECT_DIR}"

echo "[$(date)] === Deploy iniziato ==="

# 1. Pull ultimo codice
echo "[$(date)] Git pull..."
git pull origin main

# 2. Build nuove immagini (web, worker, beat condividono lo stesso Dockerfile)
echo "[$(date)] Build immagini Docker..."
docker compose build web celery_worker celery_beat

# 3. Avvia/aggiorna tutti i servizi. 'web' fa migrate+compilemessages+collectstatic
#    all'avvio; db e redis restano up (zero downtime sul database).
#    L'edge e' Caddy: serve gli statici dal volume condiviso, nessun reload da fare.
echo "[$(date)] Avvio servizi..."
docker compose up -d

# 4. Pulizia immagini Docker vecchie
echo "[$(date)] Pulizia immagini vecchie..."
docker image prune -f

echo "[$(date)] === Deploy completato. Stato servizi: ==="
docker compose ps
