# PASSAGGIO DI CONSEGNE — Sponsor Manager

> Documento di onboarding per chi prende in mano il progetto.
> Aggiornato al **10 luglio 2026**. Punto d'ingresso: da qui si arriva a tutto il resto.
> **Non contiene segreti**: dice solo dove vivono e come ottenere gli accessi.

---

## 1. Cos'è e in che stato è

**Sponsor Manager** è il gestionale sponsor dei congressi VALET S.r.l.: backoffice
(`/admin/` + cruscotto operatore) e portale self-service per gli sponsor (`/portal/`).
Django 5.1 + PostgreSQL + Redis + Celery, deploy Docker Compose con Caddy (HTTPS).

**Stato: IN PRODUZIONE CON CLIENTI E PAGAMENTI VERI.**

- ⚠️ **PayPal è in modalità LIVE dal 7/7/2026**: ogni pagamento sul portale muove
  soldi veri sul conto PayPal Business VALET. Per fare prove di pagamento NON usare
  il sito di produzione: passare a credenziali sandbox in un ambiente locale.
- Sponsor reali attivi (es. TEOXANE, EVOLUS sul 7° Congresso AITEB), preventivi,
  contratti ed email automatiche in funzione ogni giorno.
- Suite di test: **280 test verdi** (`pytest`).

---

## 2. Le tre regole d'oro (prima di toccare qualsiasi cosa)

1. **La produzione si aggiorna SOLO via git**: commit → push su GitHub →
   `./scripts/deploy.sh` sul server. Mai modificare file a mano sul server.
2. **`.env` e `media/` NON stanno su git** e sono insostituibili: il `.env` contiene
   tutti i segreti (chiavi PayPal live comprese), `media/` contiene loghi e PDF
   generati. Prima di qualsiasi operazione rischiosa: `./scripts/backup_completo.sh`.
3. **I dati non si cancellano mai davvero**: Sponsor e Contratti usano il
   *soft delete* (cestino). Il comando `delete(hard=True)` esiste ma non va usato
   su dati di produzione senza una ragione fortissima.

---

## 3. Accessi necessari (checklist, in sicurezza)

| Accesso | A cosa serve | Come ottenerlo (mai condividere credenziali altrui) |
|---|---|---|
| **Repo GitHub** `damorini/sponsor-manager` | codice, storia, deploy | Daniele ti invita come collaborator dal repo |
| **Server di produzione** `167.233.78.124` (progetto in `/opt/sponsor_manager`) | deploy, log, shell Django | generi la TUA coppia di chiavi SSH (`ssh-keygen -t ed25519`) e Daniele aggiunge la tua chiave pubblica a `~/.ssh/authorized_keys` sul server |
| **Admin Django** (`https://167.233.78.124.sslip.io/admin/`) | backoffice | Daniele ti crea un utente admin PERSONALE (Utenti → Aggiungi, ruolo admin). Niente account condivisi |
| **PayPal Business VALET** | pannello pagamenti live, rimborsi, chiavi API | Daniele ti aggiunge come utente secondario dal pannello PayPal (Impostazioni → Accesso utenti), con i soli permessi che servono |
| **Casella SMTP di invio** | configurata nel pannello: Admin → Configurazione email | i parametri sono già nel DB/pannello; per cambiarli serve chi gestisce la casella |
| **DeepL API** (traduzioni automatiche) | chiave in `.env` (`DEEPL_API_KEY`) | già configurata sul server; il pannello DeepL è intestato a VALET |

**Dove vivono i segreti**: solo in `/opt/sponsor_manager/.env` sul server (mai in
git, mai in chat/email). I backup `.tgz` prodotti da `backup_completo.sh` CONTENGONO
il `.env` e il database: trattarli come segreti.

---

## 4. Architettura in breve

Tutto ruota attorno a: **Event → Sponsor ↔ Contract → ContractLine → Service**.
Tutte le regole di dettaglio sono in **`CLAUDE.md`** (repo root) — leggerlo per primo.

- `events/` — eventi/congressi (ECM vs non-ECM, campi bilingui) + **campagne promozionali**
- `sponsors/` — anagrafica aziende (soft-delete, flag *azienda farmaceutica* + Codice SIS) e contatti (ruoli, firmatario, lingua)
- `catalog/` — catalogo servizi (madre + per-evento), varianti, inclusi, template scadenze
- `contracts/` — contratti/preventivi (stati, PDF docxtpl+LibreOffice, scadenze, pagamenti PayPal, task Celery)
- `venues/` — stand e blocchi
- `portal/` — portale sponsor (dashboard, conferma preventivo, carrello/checkout, materiali, messaggi)
- `shared/` — documenti e comunicazioni polimorfici, template email, log email
- `core/` — modelli base (UUID pk, soft delete), cruscotto, tema admin, widget multilingua

Convenzioni chiave: **UUID ovunque**, campi multilingua come JSON `{it,en}` letti con
`.translated()`, admin con RBAC per evento, prezzi **congelati (snapshot)** sulle
righe contratto nella **lingua del contratto**.

---

## 5. Ambienti

### Produzione
- Server: `167.233.78.124` (Hetzner) · sito `https://167.233.78.124.sslip.io`
- Progetto: `/opt/sponsor_manager` · container: `web`, `celery_worker`, `celery_beat`, `db`, `redis`, `caddy`
- **Deploy**: `cd /opt/sponsor_manager && ./scripts/deploy.sh` (git pull + build di web+worker+beat + up; le migrazioni girano da sole nell'entrypoint)
- Dopo ogni deploy: ~30s di 502 mentre il container web fa boot — è normale. Verifica: `curl https://167.233.78.124.sslip.io/health/` → 200
- Log: `docker compose logs web --since 1h` (idem `celery_worker`)
- Shell Django: `docker compose exec web python manage.py shell`

### Sviluppo locale
- Setup completo passo-passo nel **`README.md`** (WSL2, PostgreSQL, Redis, venv Python 3.12)
- `pytest` per i test; in dev le email vanno in console e Celery gira inline (EAGER)
- ⚠️ in dev **niente chiavi PayPal live**: usare la sandbox (app sandbox sul pannello developer PayPal)

---

## 6. Operazioni ricorrenti

| Operazione | Comando |
|---|---|
| Deploy | `./scripts/deploy.sh` (sul server) |
| Backup completo (.env+db+media) | `./scripts/backup_completo.sh` |
| Restore | `./scripts/restore_completo.sh <file.tgz>` (vedi `TRASFERIMENTO.md`) |
| Test | `pytest` (280 verdi al 10/7/2026) |
| Comandi gestionali | vedi §13 del `docs/MANUALE-OPERATIVO-COMPLETO.md` (import Excel, `riallinea_lingua_righe`, `diagnosi_scadenze`, …) |

**Automazioni Celery Beat** (config/celery.py): 7:00 alert operatore · 8:00 reminder
scadenze · 9:00 solleciti · 10:00 recupero carrelli · 11:00 campagne promozionali ·
lunedì 9:30 reminder wishlist. Tutte escludono contratti nel cestino.

---

## 7. Flussi business (come funziona davvero)

1. **Preventivo → contratto**: l'operatore crea il contratto e invia il preventivo
   (avviso se manca il firmatario). Il cliente conferma dal portale, protetto da due
   *gate*: anagrafica completa (con ritorno automatico a «I miei dati») e firmatario
   registrato. Alla conferma (eventi non-ECM) si genera **UN solo PDF da firmare**:
   contratto di sponsorizzazione + riepilogo servizi come Allegato 1. Email di
   ringraziamento col PDF; per gli ECM resta la domanda di ammissione.
2. **Ritorno del firmato**: scadenza automatica «Invio contratto firmato» a +10 giorni;
   il cliente lo carica nei Materiali (avviso automatico ad amministrazione@valet.it)
   o lo manda via email. Reminder 10/3/0 e solleciti ogni 3 giorni.
3. **Pagamenti**: contratto principale SOLO bonifico (incasso registrato a mano);
   acquisti online (addon) con PayPal/MyBank/carta — LIVE. Ordini in attesa
   riprendibili con «Paga ora».
4. **Campagne promozionali** (novità 10/7): email ricorrente per evento agli sponsor
   CONFERMATI, con disiscrizione one-click dalla singola campagna. Admin → Eventi →
   Campagne promozionali. Una campagna per il 7° AITEB è pronta (spenta) in attesa
   di attivazione.

Dettaglio completo: `docs/MANUALE-OPERATIVO-COMPLETO.md` (operativo) e
`docs/manuale_utente.html` (guida illustrata, servita anche dentro l'admin).

---

## 8. Trappole note (imparate sul campo)

- **docker-compose `x-app-env`**: una variabile nuova nel `.env` NON arriva al
  container finché non è elencata anche nel blocco `x-app-env` di
  `docker-compose.yml`. Poi `docker compose up -d`.
- **Task Celery**: vivono in package (`contracts/tasks/`); i sotto-moduli DEVONO
  essere importati in `__init__.py` o il worker scarta i task in silenzio.
  Dopo modifiche ai task, il deploy ricostruisce anche worker e beat (già nel
  deploy.sh) — non solo web.
- **CSRF in produzione**: `CSRF_COOKIE_HTTPONLY=True` → il JS non può leggere il
  cookie; nelle pagine con AJAX il token va iniettato dal template
  (`{{ csrf_token }}`). Il dev non evidenzia questo problema.
- **Template DOCX** (`contracts/templates_pdf/`): contengono dati VALET hardcoded e
  tag Jinja delicati (i tag run-level `{%r if %}` per contenuti condizionali).
  Dopo ogni modifica, generare un documento reale di prova con e senza condizione.
- **Snapshot di lingua**: le righe contratto si fotografano nella lingua del
  contratto; cambiare lingua a un preventivo non confermato le ri-traduce da solo.
- **`.dockerignore`**: esclude `docs/` e `*.md`; i file letti a runtime richiedono
  un'eccezione `!path` (i due manuali ce l'hanno già).
- **Cestino**: cestinare un contratto esonera le scadenze e chiude il carrello
  collegato. I figli nel cestino non bloccano l'eliminazione del padre; i figli
  attivi sì.
- **Email**: gli override dei testi si fanno da Admin → Template email (bilingue,
  per tipo evento); nei template salvati nel DB mai usare `<`/`>` nella logica
  `{% if %}` (il WYSIWYG li escapa e rompe il render).

---

## 9. Lavori recenti (luglio 2026, ordine cronologico)

- Flag **Azienda farmaceutica + Codice SIS** (obbligatorio se flaggata) su anagrafica e gate portale
- **Gate conferma preventivo**: anagrafica (con ritorno automatico) + firmatario; avviso operatore all'invio
- **Documento unico da firmare** per i non-ECM + email «Grazie per aver confermato»
- Scadenza **«Invio contratto firmato»** con upload nei Materiali e avviso ad amministrazione
- **Preventivi EN corretti** (snapshot nella lingua del contratto + comando `riallinea_lingua_righe`)
- **PayPal LIVE** (PayPal + MyBank + carta), fix ordini riusati e CSRF, pulsante «Paga ora»
- Pagina **«Ci siamo quasi»** per chi non ha mai fatto il primo accesso
- **helpdesk@valet.it** come email di assistenza (SUPPORT_EMAIL)
- **Backoffice mobile** (menu hamburger completo)
- **Cestino coerente**: scadenze esonerate, carrelli chiusi, niente reminder orfani
- **Campagne promozionali** con disiscrizione one-click per campagna

La cronologia completa è nei commit (`git log`), scritti in italiano descrittivo.

---

## 10. Cose aperte / da valutare

- **Campagna 7° AITEB**: creata e pronta, spenta — la attiva Daniele quando decide.
- **Firma elettronica** (Yousign/DocuSign) come evoluzione dell'upload manuale del
  contratto firmato: flusso già predisposto per l'innesto (scadenza + notifiche).
- **Backlog migliorie** da audit di giugno: vedi `TODO.md` e `STATO_PROGETTO.md`
  nel repo (note di lavoro di Daniele) — verificare con lui le priorità.
- Eventi **ECM**: alla conferma esce ancora la domanda di ammissione (non esiste un
  template di contratto ECM); se serve, va preparato il DOCX.
- Dati di test: lo sponsor «Azienda Del Cazzo» e relativi contratti sono nel
  cestino; l'anagrafica è ancora presente se serve per prove.

---

## 11. Mappa della documentazione

| Documento | Contenuto |
|---|---|
| `CLAUDE.md` | convenzioni di codice, architettura, comandi, gotchas per sviluppatori |
| `README.md` | setup ambiente di sviluppo da zero |
| `DEPLOY.md` | primo deploy e aggiornamenti |
| `TRASFERIMENTO.md` | migrare il server senza perdere nulla (cosa NON sta su git) |
| `docs/MANUALE-OPERATIVO-COMPLETO.md` | guida operativa sezione per sezione + troubleshooting |
| `docs/manuale_utente.html` | manuale illustrato (accessibile da Admin → Manuale d'uso) |
| `docs/PASSAGGIO-CONSEGNE.md` | questo documento |
| `STATO_PROGETTO.md`, `TODO.md` | note di lavoro e backlog di Daniele |

**Contatti applicativi cablati**: assistenza clienti `helpdesk@valet.it` ·
amministrazione `amministrazione@valet.it` (riceve contratti firmati e CC contratti)
· mittente email configurato in Admin → Configurazione email.
