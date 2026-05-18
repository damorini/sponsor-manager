# Setup rapido su Windows con WSL2

Questo file è un riassunto operativo. Per dettagli completi vedi il README.md
principale.

## Prima volta (setup iniziale)

### 1. Installa WSL2 (PowerShell come Amministratore)

```powershell
wsl --install
```

Riavvia il PC quando richiesto. Al primo avvio di Ubuntu, crea utente Linux
e password (può essere diversa dalla password Windows).

### 2. Setup Ubuntu (dentro WSL)

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3.12 python3.12-venv python3-pip postgresql-16 \
    postgresql-contrib libpq-dev git build-essential unzip

# Avvia PostgreSQL
sudo service postgresql start

# Imposta password per utente postgres
sudo -u postgres psql -c "ALTER USER postgres PASSWORD 'sponsor_dev_pwd';"
```

### 3. Sposta il progetto in WSL

```bash
# IMPORTANTE: usa la home Linux, NON /mnt/c/...
cd ~
mkdir -p progetti && cd progetti

# Copia lo zip da Downloads di Windows
cp /mnt/c/Users/$USER_WINDOWS/Downloads/sponsor_manager.zip .
unzip sponsor_manager.zip
cd sponsor_manager
```

(sostituisci `$USER_WINDOWS` con il nome del tuo utente Windows)

### 4. Setup Python virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-dev.txt
```

### 5. Configura .env

```bash
cp .env.example .env

# Genera SECRET_KEY
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
# Copia il risultato

# Modifica .env (con nano o VS Code)
nano .env
```

Modifica almeno:
- `SECRET_KEY=<chiave-generata-sopra>`
- `DB_PASSWORD=sponsor_dev_pwd` (la password che hai dato a postgres)

### 6. Database

```bash
sudo -u postgres createdb sponsor_manager
python manage.py migrate
python manage.py createsuperuser
```

### 7. Avvio

```bash
python manage.py runserver 0.0.0.0:8000
```

Apri il browser su Windows: http://localhost:8000/admin

---

## Avvio quotidiano

Apri Ubuntu da Start Menu. Poi:

```bash
cd ~/progetti/sponsor_manager
source venv/bin/activate
sudo service postgresql start
python manage.py runserver 0.0.0.0:8000
```

Per fermare: `Ctrl+C` nel terminale.

---

## Lavorare con VS Code

1. Installa **VS Code** su Windows: https://code.visualstudio.com/
2. Installa l'estensione **Remote - WSL** in VS Code
3. Apri WSL terminale → cd nel progetto → `code .`
   - VS Code si apre con tutto il filesystem WSL
   - L'estensione Python rileva automaticamente il venv

---

## Comandi rapidi

| Cosa | Comando |
|------|---------|
| Avvia server | `python manage.py runserver 0.0.0.0:8000` |
| Apri shell Django | `python manage.py shell_plus` |
| Crea migration | `python manage.py makemigrations` |
| Applica migration | `python manage.py migrate` |
| Crea utente admin | `python manage.py createsuperuser` |
| Test | `pytest` |
| Avvia PostgreSQL | `sudo service postgresql start` |
| Verifica PostgreSQL | `sudo service postgresql status` |
| Apri psql | `sudo -u postgres psql sponsor_manager` |

---

## Problemi comuni

### "psql: error: connection to server on socket failed"
PostgreSQL non è avviato:
```bash
sudo service postgresql start
```

### "ModuleNotFoundError: No module named 'django'"
Hai dimenticato di attivare il venv:
```bash
source venv/bin/activate
```

### "FATAL: Peer authentication failed for user postgres"
Modifica `/etc/postgresql/16/main/pg_hba.conf`, cambia `peer` in `md5` per
le righe locali, poi riavvia: `sudo service postgresql restart`

### "WSL non ha accesso a internet"
Da PowerShell come admin:
```powershell
wsl --shutdown
netsh winsock reset
# Riavvia il PC
```

### Server lento
Verifica che il progetto sia in `~/progetti/...` e NON in `/mnt/c/...`.
Se è in `/mnt/c/`, spostalo nella home Linux.

### VS Code non vede il venv
In VS Code, premi `Ctrl+Shift+P` → "Python: Select Interpreter" →
scegli quello dentro `venv/bin/python`.

---

## Persistenza servizi (opzionale ma consigliato)

Per evitare di lanciare `sudo service postgresql start` ogni volta:

1. Crea/modifica `%USERPROFILE%\.wslconfig` su Windows:
   ```
   [wsl2]
   systemd=true
   ```

2. Da PowerShell:
   ```powershell
   wsl --shutdown
   ```

3. Riapri Ubuntu. Ora puoi:
   ```bash
   sudo systemctl enable postgresql
   sudo systemctl start postgresql
   ```
   Da qui in poi PostgreSQL parte da solo all'avvio di WSL.
