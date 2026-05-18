# Sponsor Manager

Gestionale per congressi e sponsor: anagrafica, contratti, stand, scadenze
automatiche, portale sponsor con ecommerce, multilingua italiano/inglese.

## Stack tecnologico

- Python 3.12
- Django 5.1
- PostgreSQL 16
- Redis (cache + Celery broker)
- Celery (task in background)
- Gunicorn (WSGI server in produzione)
- Nginx (reverse proxy + HTTPS)
- Docker (solo per produzione su VPS)

## Struttura del progetto

```
sponsor_manager/
├── config/                  # Configurazione Django
│   ├── settings/
│   │   ├── base.py          # Settings comuni
│   │   ├── development.py   # Settings sviluppo locale
│   │   └── production.py    # Settings produzione
│   ├── urls.py
│   ├── wsgi.py
│   ├── asgi.py
│   └── celery.py
├── core/                    # Modelli base, mixin
├── users/                   # Utenti backoffice e sponsor
├── events/                  # Eventi/congressi
├── sponsors/                # Sponsor e contatti
├── venues/                  # Stand e blocchi stand
├── catalog/                 # Listino servizi e template scadenze
├── contracts/               # Contratti, righe, scadenze, pagamenti
├── shared/                  # Documenti, comunicazioni, audit
├── locale/                  # Traduzioni i18n (it, en)
├── deploy/                  # Configurazioni deployment
│   ├── nginx/               # Nginx config
│   ├── backups/             # Directory backup
│   └── letsencrypt/         # Certificati HTTPS
├── scripts/                 # Script ops (deploy, backup, restore)
├── docs/                    # Documentazione
├── .github/workflows/       # CI/CD GitHub Actions
├── manage.py
├── requirements.txt
├── requirements-dev.txt
├── Dockerfile               # Per produzione
├── docker-compose.prod.yml  # Stack completo produzione
├── pyproject.toml           # Config tools (ruff, black, pytest)
├── .pre-commit-config.yaml
├── .env.example             # Template variabili ambiente
└── .gitignore
```

---

## Sviluppo locale (Mac/Linux)

### Prerequisiti

Ti serve installato sulla macchina:

1. **Python 3.12+**
   - Mac: `brew install python@3.12`
   - Linux: già presente o `apt install python3.12`
   - Verifica: `python3 --version`

2. **PostgreSQL 16**
   - Mac: `brew install postgresql@16` poi `brew services start postgresql@16`
   - Linux: `apt install postgresql-16`
   - Verifica: `psql --version`

3. **Git**
   - Quasi sempre già presente

### Setup iniziale (una volta sola)

```bash
# 1. Clona il progetto (o entra nella cartella se già scaricato)
cd sponsor_manager

# 2. Crea virtual environment Python
python3 -m venv venv
source venv/bin/activate

# 3. Installa dipendenze (versione dev)
pip install -r requirements-dev.txt

# 4. Configura .env
cp .env.example .env
# Modifica .env con un editor (puoi lasciare i default per sviluppo)

# 5. Genera SECRET_KEY casuale e mettila in .env
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
# Copia il risultato e sostituisci SECRET_KEY in .env

# 6. Crea il database PostgreSQL
createdb sponsor_manager

# 7. Esegue le migration
python manage.py migrate

# 8. Crea il primo super utente (admin)
python manage.py createsuperuser

# 9. (Opzionale) Installa pre-commit hooks
pre-commit install
```

### Avvio quotidiano

```bash
# Attiva venv (se non già attivo)
source venv/bin/activate

# Avvia il server di sviluppo
python manage.py runserver

# In un altro terminale (se vuoi testare Celery):
celery -A config worker --loglevel=info
```

L'app è ora su http://localhost:8000/admin

### Comandi utili

```bash
# Crea nuove migration dopo modifiche ai modelli
python manage.py makemigrations

# Applica le migration
python manage.py migrate

# Apri shell Django con autoload modelli
python manage.py shell_plus

# Esegui i test
pytest

# Esegui i test con coverage
pytest --cov

# Lint del codice
ruff check .
black .

# Estrai stringhe da tradurre
python manage.py makemessages -l it -l en

# Compila traduzioni
python manage.py compilemessages

# Crea un dump del db (utile prima di esperimenti)
pg_dump sponsor_manager > backup_$(date +%Y%m%d).sql
```

---

## Sviluppo su Windows (con WSL2)

Su Windows, il modo più affidabile è usare **WSL2** (Windows Subsystem for Linux).
Sviluppare con Python nativo Windows funziona ma incontri spesso problemi con
le librerie binarie (psycopg2, paypal-server-sdk). WSL2 elimina questi problemi
e ti dà un ambiente Linux che è esattamente come la produzione.

### Setup iniziale WSL2 (una volta sola)

1. **Installa WSL2 e Ubuntu**

   Apri PowerShell **come Amministratore** e lancia:
   ```powershell
   wsl --install
   ```
   Questo installa WSL2 e Ubuntu come distribuzione default. Dopo il riavvio
   richiesto, Ubuntu si apre automaticamente per la prima configurazione
   (creazione utente Linux con password).

2. **Aggiorna Ubuntu**

   Dentro Ubuntu:
   ```bash
   sudo apt update && sudo apt upgrade -y
   ```

3. **Installa Python 3.12 e PostgreSQL 16**

   ```bash
   # Python 3.12 (Ubuntu 24.04 LTS lo ha già)
   sudo apt install -y python3.12 python3.12-venv python3-pip

   # PostgreSQL 16
   sudo apt install -y postgresql-16 postgresql-contrib libpq-dev

   # Avvia PostgreSQL (su WSL non c'è systemd di default)
   sudo service postgresql start

   # Crea utente postgres con password (per uso da Django)
   sudo -u postgres psql -c "ALTER USER postgres PASSWORD 'tua-password';"
   ```

4. **Installa Git e altri tool**

   ```bash
   sudo apt install -y git build-essential
   ```

5. **Editor di codice**

   Installa **VS Code** su Windows (https://code.visualstudio.com/) e l'estensione
   **Remote - WSL**. Aprendo VS Code da dentro WSL con `code .`, lavora sui file
   Linux con prestazioni native ma interfaccia Windows.

### Setup del progetto in WSL

```bash
# 1. Crea cartella progetti nella tua home Linux (NON in /mnt/c/...!)
# I file dentro WSL vanno SEMPRE nella home Linux per prestazioni native.
# Mettere il codice in /mnt/c/Users/... è 10-50 volte più lento.
cd ~
mkdir progetti
cd progetti

# 2. Estrai il progetto (assumendo che hai scaricato sponsor_manager.zip su Windows)
# Copialo in WSL prima di estrarlo:
cp /mnt/c/Users/<tuo-utente-windows>/Downloads/sponsor_manager.zip .
unzip sponsor_manager.zip
cd sponsor_manager

# 3. Crea virtual environment
python3 -m venv venv
source venv/bin/activate

# 4. Installa dipendenze
pip install -r requirements-dev.txt

# 5. Configura .env
cp .env.example .env
nano .env  # modifica password DB e SECRET_KEY

# 6. Genera SECRET_KEY casuale
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
# Copia il risultato e sostituisci SECRET_KEY in .env

# 7. Crea database
sudo -u postgres createdb sponsor_manager

# 8. Migrazioni
python manage.py migrate

# 9. Crea superuser
python manage.py createsuperuser

# 10. Avvia il server
python manage.py runserver 0.0.0.0:8000
```

L'app è ora accessibile da Windows su `http://localhost:8000/admin`. WSL2
fa il port forwarding automatico.

### Avvio quotidiano su Windows

Crea uno script `start_dev.sh` nella radice del progetto:
```bash
#!/bin/bash
cd ~/progetti/sponsor_manager
source venv/bin/activate
sudo service postgresql start  # se non è già attivo
python manage.py runserver 0.0.0.0:8000
```

Da PowerShell o terminale Windows:
```powershell
wsl bash ~/progetti/sponsor_manager/start_dev.sh
```

### Tip importanti per WSL

**File: SEMPRE in home Linux.** Non lavorare mai sui file in `/mnt/c/...`,
sono 10-50 volte più lenti perché vanno in cross-filesystem. Tienili in
`~/progetti/sponsor_manager`.

**Servizi che si fermano.** Su WSL2 non c'è systemd (a meno di abilitarlo).
PostgreSQL e Redis vanno avviati manualmente con `sudo service nome start`.
Per evitarlo, abilita systemd:
```bash
# In Windows, modifica %USERPROFILE%\.wslconfig:
[wsl2]
systemd=true
```
Poi `wsl --shutdown` da PowerShell e riapri Ubuntu.

**File da Windows in WSL.** Per copiare file da Windows a WSL:
`cp /mnt/c/Users/<utente>/Downloads/file.zip ~/`

**File da WSL in Windows.** L'inverso:
`cp ~/file.txt /mnt/c/Users/<utente>/Desktop/`

**Da VS Code, apri WSL.** Apri VS Code, premi `Ctrl+Shift+P`, scegli
"WSL: Connect to WSL". Da qui in poi VS Code mostra l'ambiente Linux.

---

## Deploy in produzione (VPS Hetzner)

### Setup VPS iniziale (una volta sola)

Prendi un VPS Hetzner CX22 (€4/mese) o CX32 (€7/mese) per iniziare.
Datacenter europeo (Falkenstein o Helsinki) per GDPR.

```bash
# Sul VPS appena creato (login come root via SSH)

# 1. Crea utente non-root
adduser deploy
usermod -aG sudo deploy
# Configura SSH per il nuovo utente, poi disabilita login root

# 2. Aggiorna sistema
apt update && apt upgrade -y

# 3. Installa Docker e Docker Compose
curl -fsSL https://get.docker.com | sh
usermod -aG docker deploy

# 4. Installa firewall e UFW
apt install -y ufw fail2ban
ufw allow ssh
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

# 5. Su deploy user
su - deploy

# 6. Clona il progetto
sudo mkdir -p /opt/sponsor_manager
sudo chown deploy:deploy /opt/sponsor_manager
cd /opt
git clone <tuo-repo-git> sponsor_manager
cd sponsor_manager

# 7. Configura .env per produzione
cp .env.example .env
nano .env
# Imposta:
# - DJANGO_SETTINGS_MODULE=config.settings.production
# - SECRET_KEY=<chiave-sicura-generata>
# - DEBUG=False
# - ALLOWED_HOSTS=gestionale.tuodominio.it
# - CSRF_TRUSTED_ORIGINS=https://gestionale.tuodominio.it
# - tutte le credenziali email, paypal, sentry...

# 8. Modifica deploy/nginx/conf.d/sponsor_manager.conf
# Sostituisci 'gestionale.tuodominio.it' con il tuo dominio reale

# 9. Punta il dominio al VPS
# Dal pannello DNS del tuo registrar, crea record A:
#   gestionale.tuodominio.it → <IP-del-VPS>

# 10. Ottieni primo certificato Let's Encrypt
docker compose -f docker-compose.prod.yml run --rm certbot \
    certonly --webroot -w /var/www/certbot \
    -d gestionale.tuodominio.it \
    --email tua@email.it \
    --agree-tos --no-eff-email

# 11. Avvia tutto
docker compose -f docker-compose.prod.yml up -d

# 12. Crea superuser
docker compose -f docker-compose.prod.yml exec app \
    python manage.py createsuperuser

# 13. Verifica funzionamento
curl https://gestionale.tuodominio.it/admin/login/
```

### Setup backup automatici

```bash
# Cron come deploy user
crontab -e

# Aggiungi:
0 3 * * * /opt/sponsor_manager/scripts/backup_db.sh >> /var/log/sponsor-backup.log 2>&1
```

Per uploadare backup su Backblaze B2 (€5/TB/mese, ottimo rapporto qualità/prezzo):
```bash
# Installa b2 CLI
pip install b2

# Configura
b2 account authorize <key-id> <application-key>

# Aggiungi B2_BUCKET_NAME a .env
# Lo script backup_db.sh userà automaticamente B2 se trova queste variabili
```

### Deploy successivi

Dopo il setup iniziale, ogni nuovo deploy è:

```bash
# Sul tuo Mac, push su GitHub
git push origin main

# GitHub Actions deploya automaticamente (se hai configurato i secrets)
# Oppure manualmente sul VPS:
ssh deploy@vps-ip
cd /opt/sponsor_manager
./scripts/deploy.sh
```

### GitHub Actions: secrets necessari

Su GitHub repo → Settings → Secrets and variables → Actions:

- `SSH_HOST`: IP del VPS
- `SSH_USER`: deploy
- `SSH_PRIVATE_KEY`: chiave privata SSH (genera coppia con `ssh-keygen`)
- `SSH_PORT`: 22 (o quello che usi)

---

## Configurazione PayPal

1. Account su https://developer.paypal.com
2. Crea un'app in sandbox (per test)
3. Copia Client ID e Client Secret in `.env`:
   ```
   PAYPAL_MODE=sandbox
   PAYPAL_CLIENT_ID=...
   PAYPAL_CLIENT_SECRET=...
   ```
4. Configura webhook su PayPal Dashboard:
   - URL: `https://gestionale.tuodominio.it/webhooks/paypal/`
   - Eventi: `PAYMENT.CAPTURE.COMPLETED`, `PAYMENT.CAPTURE.DENIED`
5. Copia il Webhook ID in `.env`:
   ```
   PAYPAL_WEBHOOK_ID=...
   ```

Per andare in produzione: ripeti tutto con account live (non sandbox).

---

## Configurazione Sentry (error tracking)

1. Crea account su https://sentry.io (free tier sufficient)
2. Crea progetto Django
3. Copia il DSN nel `.env` di produzione:
   ```
   SENTRY_DSN=https://xxx@xxx.ingest.sentry.io/xxx
   ```

In sviluppo Sentry resta disattivo (DSN vuoto).

---

## Struttura comandi rapidi

| Comando | Cosa fa |
|---------|---------|
| `python manage.py runserver` | Avvia dev server |
| `python manage.py shell_plus` | Shell con autoload modelli |
| `python manage.py migrate` | Applica migration |
| `python manage.py createsuperuser` | Crea utente admin |
| `pytest` | Esegue test |
| `ruff check .` | Lint |
| `black .` | Formatta codice |
| `./scripts/deploy.sh` | Deploy in produzione (sul VPS) |
| `./scripts/backup_db.sh` | Backup manuale db (sul VPS) |

---

## Risoluzione problemi comuni

**`psycopg2.OperationalError: could not connect to server`**
PostgreSQL non è avviato. Su Mac: `brew services start postgresql@16`.

**`ModuleNotFoundError: No module named 'django'`**
Virtualenv non attivo. Esegui `source venv/bin/activate`.

**`SECRET_KEY setting must not be empty`**
Manca il file `.env` o `SECRET_KEY` non valorizzata.

**Migrazioni in conflitto**
Se hai cancellato il db: `python manage.py migrate --fake-initial`.
Se invece sviluppi e hai migration "spurie": cancella tutti i file in
`*/migrations/` (tranne `__init__.py`) e rifai `makemigrations`.

**Pre-commit lento al primo run**
Normale: scarica e configura tutti i tool. Da qui in poi è veloce.

---

## Documentazione aggiuntiva

Vedi `docs/`:
- `docs/architecture.md` (da creare): scelte architetturali
- `docs/deployment.md` (da creare): troubleshooting deploy
- `docs/runbook.md` (da creare): procedure operative
