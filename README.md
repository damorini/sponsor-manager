# Sponsor Manager

Sistema di gestione sponsor per congressi VALET S.r.l.

Backoffice operatore (Django admin) + portale self-service per sponsor con
ecommerce integrato + email automatiche + generazione contratti PDF.

## Cosa fa

- **Anagrafica sponsor e contatti** (con dati firmatario per contratti)
- **Gestione eventi** (ECM e non-ECM, multilingua IT/EN)
- **Catalogo servizi** (pricing, scaglioni, IVA, scadenze automatiche)
- **Contratti** con generazione PDF auto-compilata (ECM + non-ECM, allegato auto)
- **Portale sponsor** self-service: dashboard, contratti, ecommerce, materiali
- **Pagamenti online** (PayPal Standard + Carta diretta)
- **Email automatiche** (10 template HTML responsive, IT+EN)
- **Task schedulati** (reminder scadenze, solleciti, recovery carrelli)

## Requisiti

- Windows 10/11 con WSL2 (Ubuntu 22.04 raccomandato)
- Python 3.12+
- PostgreSQL 16
- Redis 7+ (per Celery)
- LibreOffice (per conversione contratti DOCX→PDF)

## Setup completo (10 step)

### 1. Installa WSL2 con Ubuntu

Se non l'hai già fatto, da PowerShell come amministratore:
```powershell
wsl --install -d Ubuntu-22.04
```
Riavvia il PC quando richiesto. Dentro Ubuntu, crea l'utente come da prompt.

### 2. Installa le dipendenze di sistema

Da Ubuntu (WSL):
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3.12 python3.12-venv python3-pip \
    postgresql postgresql-contrib redis-server libreoffice \
    build-essential libpq-dev git
```

### 3. Avvia PostgreSQL e Redis

```bash
sudo service postgresql start
sudo service redis-server start
```

(In futuro, ad ogni riavvio di WSL, ripeti questi due comandi.)

### 4. Crea il database

```bash
sudo -u postgres psql -c "CREATE DATABASE sponsor_manager;"
sudo -u postgres psql -c "ALTER USER postgres WITH PASSWORD 'tuapassword';"
```

Sostituisci `tuapassword` con qualcosa di tuo (segnatela!).

### 5. Estrai il progetto

Dalla tua home WSL:
```bash
mkdir -p ~/progetti && cd ~/progetti
# Copia lo zip dal tuo Windows (esempio:)
cp /mnt/c/Users/$USER/Documenti/sponsor_manager/sponsor_manager_complete.zip .
unzip sponsor_manager_complete.zip
cd sponsor_manager
```

### 6. Crea virtualenv e installa Python deps

```bash
python3.12 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 7. Configura .env

```bash
cp .env.example .env
nano .env
```

Modifica almeno:
- `SECRET_KEY` (un valore lungo casuale)
- `DB_PASSWORD` (la password che hai messo allo step 4)

Salva con Ctrl+O, Invio, Ctrl+X.

### 8. Migrazioni database

```bash
python manage.py migrate
```

Dovresti vedere ~30 migrations applicate senza errori.

### 9. Crea il primo super-utente

```bash
python manage.py createsuperuser
```

Inserisci email, username, password (almeno 10 caratteri).

### 10. Avvia il server

```bash
python manage.py runserver 0.0.0.0:8000
```

Apri il browser su Windows:
- **Backoffice**: http://localhost:8000/admin/
- **Portale**: http://localhost:8000/portal/login/

Login con le credenziali create al passo 9.

## Setup completo (riepilogo comandi)

Una volta installato, per le prossime volte ti basta:
```bash
# Avvia servizi (a ogni riavvio WSL)
sudo service postgresql start
sudo service redis-server start

# Vai nella cartella progetto
cd ~/progetti/sponsor_manager
source venv/bin/activate

# Avvia Django
python manage.py runserver 0.0.0.0:8000
```

In un'altra shell, per i task asincroni (email, PDF):
```bash
cd ~/progetti/sponsor_manager
source venv/bin/activate
celery -A config worker -l info
```

In una terza shell, per i task schedulati (reminder, solleciti):
```bash
cd ~/progetti/sponsor_manager
source venv/bin/activate
celery -A config beat -l info
```

## Primi passi nell'admin

1. Vai su http://localhost:8000/admin/ e fai login
2. Crea un primo **Evento** (es. "Test 2026", date, tipo ECM/non-ECM)
3. Crea un primo **Sponsor** con dati anagrafici completi (P.IVA, sede, REA)
4. Crea un **Contatto** per quello sponsor, spuntando "is_signer" e
   compilando i dati anagrafici personali (codice fiscale, residenza, ecc.)
5. Crea uno o più **Service** per l'evento (con accounting_category)
6. Crea un **Contract** legando sponsor + evento + righe servizi
7. Cambia stato contratto a "SENT" → si genera automaticamente il PDF in
   `media/documents/contracts/<id>/`

## Risorse documentazione

- `docs/` – documentazione tecnica per dev futuri
- `README_ORIGINAL.md` – README dettagliato originale del setup
- Email template: `shared/email_templates/it/`
- Template contratti: `contracts/templates_pdf/`
- App portale: `portal/`

## Risoluzione problemi comuni

**"connection refused" su Postgres**:
```bash
sudo service postgresql restart
```

**Email non arrivano**: in dev sono stampate in console. Per email reali,
configura SMTP nel `.env` (es. Postmark, Brevo).

**Generazione PDF fallisce**: serve LibreOffice. Verifica con:
```bash
libreoffice --version
```

**Celery dice "Connection refused" a Redis**:
```bash
sudo service redis-server start
```

## Stack tecnologico

- Python 3.12 + Django 5.1
- PostgreSQL 16
- Redis 7 + Celery 5.4
- docxtpl + LibreOffice (PDF generation)
- PayPal Server SDK 1.0
- Tailwind CSS via CDN (no build step)
- Sentry (monitoring, opzionale)

## Note su VALET

I dati VALET sono hard-coded nei template contratto:
- Sede: Via Dei Fornaciai 29/B, 40129 Bologna
- P.IVA: 02107230373
- REA: BO252016
- Legale rappresentante: Daniele Morini
- IBAN: IT37 A030 6902 5201 0000 0011 856 (Intesa Sanpaolo)
- PEC: valet@pec.it

Se cambiano questi dati, vanno aggiornati in 2 file:
- `contracts/templates_pdf/template_ecm_it.docx`
- `contracts/templates_pdf/template_non_ecm_it.docx`
