# Deploy — Sponsor Manager

Questa app si mette online con **Docker Compose**: un solo comando avvia tutto
(database, redis, app web, worker email/PDF, task schedulati, nginx).

> Oggi **non c'è ancora un deploy attivo**: giri l'app in locale (WSL). Questa
> guida ti porta da zero a online su un server.
>
> ✅ Lo stack è stato **collaudato davvero** (2026-06-05) con `docker compose up`
> su una macchina con Docker: tutti i container partono, `/health` risponde 200,
> Celery si connette, e i PDF (LibreOffice + WeasyPrint) vengono generati nel
> container. Resta da configurare **HTTPS** sul tuo dominio (vedi §4).

## 1. Cosa ti serve

- Un **server Linux** (VPS) con IP pubblico — es. Hetzner, OVH, DigitalOcean,
  Aruba. Bastano 2 vCPU / 4 GB RAM.
- Un **dominio** che punta all'IP del server (es. `valet.it`).
- **Docker** e **Docker Compose** installati sul server:
  ```bash
  curl -fsSL https://get.docker.com | sh
  ```

## 2. Primo avvio

```bash
# 1. Prendi il codice sul server
sudo git clone <URL_DEL_REPO> /opt/sponsor_manager
cd /opt/sponsor_manager

# 2. Crea il file di configurazione e compilalo (SECRET_KEY, ALLOWED_HOSTS, DB_PASSWORD)
cp .env.prod.example .env
nano .env

# 3. Avvia tutto (build + up). Il container 'web' fa da solo
#    migrate + compilemessages + collectstatic all'avvio.
docker compose up -d --build

# 4. Crea il primo utente amministratore
docker compose exec web python manage.py createsuperuser

# 5. Controlla che sia tutto su
docker compose ps
curl -i http://localhost/health/      # deve rispondere 200 {"status":"ok"}
```

Poi apri `http://<tuo-dominio>/admin/` (backoffice) e
`http://<tuo-dominio>/portal/login/` (portale sponsor).

## 3. Aggiornamenti successivi

Dopo aver fatto `git push` dal tuo PC:
```bash
cd /opt/sponsor_manager
./scripts/deploy.sh        # git pull + build + up + reload nginx
```

## 4. Note e HTTPS

Lo stack è stato collaudato e parte correttamente. Punti da sapere:

- **PDF**: la generazione (LibreOffice per contratti/domande, WeasyPrint per il
  preventivo grafico) gira nei container `web`/`celery_worker` — verificata.
- **HTTPS**: di default lo stack serve in **HTTP** sulla porta 80, con il
  redirect HTTPS dell'app **disattivato** se imposti `SECURE_SSL_REDIRECT=False`.
  Per andare in produzione vera con HTTPS hai due strade:
  1. **Consigliata**: metti un reverse proxy con certificati automatici davanti
     (es. **Caddy** o **Traefik** con Let's Encrypt), che gira il traffico a
     `web:8000`. Lascia `SECURE_SSL_REDIRECT=True` (default).
  2. Configura i certificati direttamente in `nginx.conf` (blocco `server` su 443).
- **Email**: finché non imposti `EMAIL_HOST` nel `.env`, le email vanno nei log
  (console), non vengono inviate davvero. L'app parte comunque.

Per ri-collaudare in locale (serve Docker installato):
```bash
printf 'SECRET_KEY=test\nALLOWED_HOSTS=localhost\nDB_PASSWORD=test\nSECURE_SSL_REDIRECT=False\n' > .env
docker compose up -d --build
curl -i http://localhost/health/     # 200 {"status":"ok"}
docker compose down -v               # pulizia
```

## 5. Backup / restore database

```bash
./scripts/backup_db.sh     # crea un dump
./scripts/restore_db.sh    # ripristina (attenzione: sovrascrive)
```

## Architettura dei servizi (docker-compose.yml)

| Servizio        | Cosa fa                                        |
|-----------------|------------------------------------------------|
| `db`            | PostgreSQL 15                                  |
| `redis`         | Redis 7 (broker Celery)                        |
| `web`           | Django + Gunicorn (HTTP su 8000, interno)      |
| `celery_worker` | invio email, generazione PDF                   |
| `celery_beat`   | task schedulati (reminder, solleciti, recovery)|
| `nginx`         | reverse proxy pubblico (porta 80/443)          |

I segreti stanno solo nel file `.env` sul server. Mai nel repo.
