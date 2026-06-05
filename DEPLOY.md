# Deploy — Sponsor Manager

Questa app si mette online con **Docker Compose**: un solo comando avvia tutto
(database, redis, app web, worker email/PDF, task schedulati, nginx).

> Oggi **non c'è ancora un deploy attivo**: giri l'app in locale (WSL). Questa
> guida ti porta da zero a online su un server. I file Docker sono stati resi
> coerenti, ma **vanno collaudati con un `docker compose build` su una macchina
> con Docker** prima di considerarli "in produzione" (vedi §4).

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

## 4. Collaudo PRIMA della produzione (importante)

I file Docker non sono ancora stati eseguiti su una macchina con Docker. Prima
di affidarci, su un server di test (o sul tuo PC con Docker installato):

```bash
cp .env.prod.example .env   # metti valori di test
docker compose build        # deve finire senza errori
docker compose up -d
docker compose ps           # tutti 'healthy'/'running'
docker compose logs web     # nessun traceback; deve arrivare a "Booting worker"
curl -i http://localhost/health/
```

Cose da verificare in particolare (sono i punti più a rischio):
- **PDF**: conferma un preventivo e genera un PDF → serve LibreOffice nel
  container (aggiunto nel Dockerfile). Se fallisce, controlla `docker compose logs celery_worker`.
- **Permessi volumi**: `collectstatic` scrive in `static_data`. Se dà
  "permission denied", il container gira come utente non-root (uid 1000):
  potrebbe servire `chown` sui volumi o passare a bind mount.
- **HTTPS**: questa config serve in HTTP sulla porta 80. Per HTTPS aggiungi un
  reverse proxy con certificati (es. Caddy o Traefik con Let's Encrypt) davanti,
  oppure configura i certificati in `nginx.conf`.

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
