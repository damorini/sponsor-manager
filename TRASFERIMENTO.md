# Trasferire Sponsor Manager su un nuovo server (senza perdere nulla)

I problemi tipici dopo un trasferimento (bonifico vuoto, niente traduzioni,
logo mancante nel footer, modulo su 2 pagine) nascono **sempre** dalle stesse
3 cose, che **NON stanno su GitHub** e vanno portate a mano:

| Cosa | Dove vive | Se manca… |
|------|-----------|-----------|
| **`.env`** | file nella cartella progetto (gitignored) | bonifico coi placeholder, niente traduzioni DeepL, email/PayPal ko |
| **database** | volume Docker `postgres_data` | nessun dato (sponsor, eventi, contratti) |
| **`media/`** | volume Docker `media_data` (`/app/media`) | logo segreteria/header eventi/loghi sponsor mancanti, PDF generati persi |

Il **codice** invece arriva da `git pull`. I **font** del PDF arrivano dal
rebuild dell'immagine (`docker compose build web`).

---

## Procedura rapida (con gli script)

**Sul server VECCHIO** (sorgente), dalla cartella del progetto:
```bash
./scripts/backup_completo.sh
# -> crea trasferimento_sponsor_AAAAMMGG_HHMMSS.tgz (contiene .env + db + media)
```

Copia il file sul nuovo server:
```bash
scp trasferimento_sponsor_*.tgz utente@NUOVO_SERVER:/opt/sponsor_manager/
```

**Sul server NUOVO**:
```bash
cd /opt/sponsor_manager
git clone … .            # se non l'hai già fatto
docker compose up -d db web
./scripts/restore_completo.sh trasferimento_sponsor_*.tgz
git pull
docker compose build web && docker compose up -d
```

---

## Variabili del `.env` (e cosa rompono se mancano)

Obbligatorie:
- `SECRET_KEY` — l'app non parte
- `DB_PASSWORD` — il database non parte
- `ALLOWED_HOSTS` — 400 Bad Request
- `SITE_ADDRESS` — HTTPS automatico (Caddy) / link nelle email

Funzionalità (se mancano, quella feature non funziona):
- `DEEPL_API_KEY` — **traduzioni automatiche IT→EN** al salvataggio
- `BANK_TRANSFER_HOLDER` / `_BANK` / `_IBAN` / `_BIC` — **dati del bonifico** al checkout
- `EMAIL_BACKEND` + `EMAIL_HOST` / `_PORT` / `_HOST_USER` / `_HOST_PASSWORD` / `_USE_TLS` / `DEFAULT_FROM_EMAIL` — invio email reali (senza, vanno in console)
- `PAYPAL_MODE` / `_CLIENT_ID` / `_CLIENT_SECRET` / `_WEBHOOK_ID` — pagamenti PayPal

> Riferimento completo con esempi: `.env.prod.example`.

---

## Controlli post-trasferimento (5 minuti)

1. **Migrazioni** applicate? (l'entrypoint le fa da solo sul container `web`).
2. **Font PDF**: apri una *domanda di ammissione* → deve stare su **1 pagina**
   (serve il rebuild con `fonts-liberation`/`fonts-crosextra-carlito`).
3. **Bonifico**: vai al checkout di un addon → l'IBAN deve essere quello vero,
   non "DA CONFIGURARE".
4. **Traduzioni**: salva un servizio solo in IT → l'EN si compila da solo.
5. **Logo segreteria** nel footer del preventivo: se manca, ricaricalo da
   *Admin → Impostazioni segreteria → Logo* (è un file media).
6. **Email**: manda un'email di prova dall'admin e verifica che arrivi.

---

## Note
- Gli script lavorano **attraverso i container** (`docker compose exec`), quindi
  non dipendono dai nomi esatti dei volumi.
- `restore_completo.sh` salva il `.env` precedente come
  `.env.prima_del_restore_*` prima di sovrascriverlo.
- Il soft-delete dei contratti annullati e il resto dei dati sono già dentro il
  dump del database.
