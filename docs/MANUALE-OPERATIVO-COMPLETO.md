# MANUALE OPERATIVO COMPLETO — Sponsor Manager

> Guida operativa completa del gestionale **Sponsor Manager** (Valet): gestione di congressi/eventi, sponsor/espositori, stand, catalogo servizi, preventivi/domande di ammissione, pagamenti, scadenze e portale clienti.
>
> Questo è il **manuale operativo di sistema** (backoffice + portale + manutenzione). Per la guida rapida utente esiste anche `docs/manuale_utente.html` (apribile nel browser). In caso di dubbio, questo documento è la fonte completa.
>
> *Ultimo aggiornamento: luglio 2026.*

---

## INDICE
1. Panoramica e architettura
2. Ambienti e accesso
3. Concetti chiave (glossario operativo)
3-bis. **Schemi pratici (i flussi in un colpo d'occhio)**
4. Backoffice — guida sezione per sezione
5. Portale sponsor (lato cliente)
6. Flussi operativi completi (passo-passo)
7. Multilingua e traduzioni automatiche
8. Documenti PDF (preventivo, domanda di ammissione)
9. Import da Excel
10. Pagamenti
11. Scadenze e reminder
12. Manutenzione, backup e trasferimento
13. Comandi utili (management commands)
14. Variabili di configurazione (.env)
15. Troubleshooting (problemi noti e soluzioni)
16. FAQ

---

## 1. PANORAMICA E ARCHITETTURA

**Cos'è**: applicazione web per gestire la partecipazione degli **sponsor/espositori** ai congressi: dalla creazione dell'evento e del listino (stand + servizi), alla generazione del **preventivo / domanda di ammissione**, alla firma, ai **pagamenti** (PayPal, carta, bonifico) e alle **scadenze** (tecniche e di pagamento). Gli sponsor hanno un **portale** dedicato.

**Stack tecnico**:
- Backend **Django 5.1** + **PostgreSQL**; task asincroni con **Celery + Redis**.
- Frontend portale: **Tailwind** + JavaScript vanilla (no framework SPA).
- Backoffice: **Django Admin** tematizzato (tema caldo chiaro/scuro) + un **Cruscotto** operatore.
- PDF: **docxtpl + LibreOffice** (contratto/domanda di ammissione), **WeasyPrint** (preventivo grafico).
- Pagamenti: **PayPal** (paypal-server-sdk) per carta e PayPal; **bonifico** registrato manualmente.
- Traduzioni IT/EN automatiche via **DeepL** al salvataggio.
- Deploy: **Docker Compose** (web Gunicorn, db Postgres, redis, celery worker+beat, **Caddy** per HTTPS automatico).

**App principali**: `events` (eventi), `sponsors` (sponsor/contatti), `venues` (stand/blocchi), `catalog` (servizi/catalogo), `contracts` (contratti/pagamenti/scadenze), `portal` (area cliente), `core` (impostazioni, cruscotto, traduzioni), `shared` (documenti, template email/lettera).

---

## 2. AMBIENTI E ACCESSO

| Area | URL | Chi |
|---|---|---|
| **Backoffice (Admin)** | `/admin/` | segreteria/operatori Valet |
| **Cruscotto** | `/admin/cruscotto/` | operatori (KPI, scadenze, alert) |
| **Manuale d'uso** | `/admin/cruscotto/manuale/` | operatori |
| **Portale sponsor** | `/` (login con **email**) | aziende sponsor invitate |

- Login portale = via **email** (USERNAME_FIELD=email). Gli sponsor accedono solo su invito (l'operatore invia l'email d'accesso dall'admin).
- Il backoffice ha un **menu laterale** (su mobile si apre con l'hamburger ☰; parte **chiuso** di default e ricorda la scelta).
- L'operatore può **impersonare** uno sponsor per vedere il portale come lui ("Stai navigando come cliente…").

---

## 3. CONCETTI CHIAVE (glossario operativo)

- **Evento / Edizione**: il congresso (es. "Congresso Nazionale AITEB 2026"). Ha date, luogo, lingua di default, eventuale immagine header per email/PDF.
- **Sponsor**: l'azienda espositrice. Ha **Contatti** (referenti); il contatto principale ha una **lingua preferita** (IT/EN). Anche gli altri contatti possono avere la propria lingua.
- **Stand**: postazione espositiva fisica (codice, dimensioni, dotazioni, prezzo, stato). **Blocco stand**: più stand venduti come un'unica unità.
- **Servizio**: voce vendibile in un evento (workshop, hostess, logo, ecc.). Può avere **varianti** (con prezzo/stock proprio) e **servizi inclusi** a €0.
- **Catalogo (servizio madre)**: voce riutilizzabile su più eventi, da cui istanziare i servizi per-evento.
- **Contratto / Domanda di ammissione**: l'accordo con lo sponsor. Nel backoffice si chiama "Contratto"; lato sponsor "Domanda di ammissione". Ha **stati** e una **numerazione** automatica `SIGLA-AA-NNN`.
- **Scadenza**: un adempimento con data. Due tipi: **tecniche** (es. invio file relatori, generate dai *Template scadenze* dei servizi) e di **pagamento** (acconto/saldo).
- **Pagamento**: incasso registrato (PayPal/carta/bonifico).

**Stati dello stand**: `disponibile` → `riservato` (preventivo inviato o opzione attiva) → `assegnato` (contratto firmato). Lo stato è **automatico**, derivato dai contratti.

**Stati del contratto**: `Bozza` → `Inviato` → `Firmato` → `Attivo` → `Completato`; oppure (acquisti ecommerce) `Bozza` → `In attesa pagamento` → `Firmato`. Sempre annullabile (`Annullato`).

---

## 3-BIS. SCHEMI PRATICI (i flussi in un colpo d'occhio)

### Schema A — Ciclo di vita: dal preventivo alla firma

```
 CREO IL CONTRATTO         INVIO IL PREVENTIVO        IL CLIENTE CONFERMA
 (bozza)                   (azione admin)             (dal portale)
 • sponsor + evento   ──>  • stato: INVIATO      ──>  • stato: FIRMATO
 • stand / blocco          • stand: RISERVATO         • stand: ASSEGNATO
 • righe servizio          • PDF preventivo            • si generano le SCADENZE
 • (opz.) opzione          • email al cliente          • l'OPZIONE sparisce
                                                        │
                                                        └─> GENERATI IN AUTOMATICO:
                                                            1) Domanda di ammissione (PDF)
                                                            2) Contratto di sponsorizzazione (non-ECM)
                                                               con la domanda come ALLEGATO 1
                                                               → email al contatto OPERATIVO
                                                                 in CC: amministrazione@valet.it
                                                                        elisa.fantini@valet.it
```

### Schema B — Chi paga come (IMPORTANTE)

```
 CONTRATTO PRINCIPALE                    SERVIZI ACQUISTATI ONLINE
 (domanda di ammissione)                 (carrello / addon ecommerce)
        │                                        │
        └──> SOLO BONIFICO                       └──> CARTA / PAYPAL / BONIFICO
             acconto + saldo                          pagamento immediato
             l'operatore registra l'incasso           il contratto si firma all'incasso
```
> Il pagamento **online (carta/PayPal)** è riservato agli **acquisti ecommerce**. Il **contratto principale si salda solo con bonifico**.

### Schema C — Quale email parte (template per tipo evento)

```
 Il sistema deve mandare un'email (es. "Reminder scadenza")
        │
        ├─ c'è un modello ATTIVO per il TIPO EVENTO (ECM / Non-ECM)? ──> usa QUELLO
        ├─ altrimenti un modello ATTIVO "Tutti gli eventi"?          ──> usa QUELLO
        └─ altrimenti                                                ──> email STANDARD di sistema
```
> I modelli si gestiscono in **Template email**: 12 punti d'invio × ECM/Non-ECM. Finché un modello non è **Attivo**, parte l'email standard.

### Schema D — Stati (automatici)

```
 STAND:      disponibile ──> riservato ──> assegnato
                             (preventivo    (contratto
                              inviato o       firmato)
                              opzione attiva)
 CONTRATTO:  Bozza → Inviato → Firmato → Attivo → Completato      ( → Annullato in qualsiasi momento)
```
> Annullare **o cancellare** un contratto **libera** subito lo stand/blocco e i servizi a numero limitato.

---

## 4. BACKOFFICE — GUIDA SEZIONE PER SEZIONE

### 4.1 Eventi
Crea l'evento (nome IT/EN, slug, date, luogo, lingua default, flag ECM, immagine header). L'evento è il contenitore di stand, servizi e contratti.

### 4.2 Catalogo (servizi madre) + Categorie
- **Catalogo servizi**: voci generiche riutilizzabili. Campi: codice, nome/descrizione IT/EN, categoria, prezzo, IVA, modalità prezzo, ecc.
- **Categorie servizio (catalogo)**: lista gestita di categorie.
- Import del catalogo da Excel (vedi §9).

### 4.3 Servizi (per evento)
Voci vendibili in un evento specifico. Si possono creare **da zero** o **dal catalogo** (il campo "Crea da catalogo" auto-compila i dati).
- **Prezzo**: modalità `fixed` (prezzo unico), `quantity` (× quantità), `tiered` (scaglioni `[{min,max,unit_price}]`).
- **Disponibilità**: `quantità massima` per riga, `quantità totale` (stock; vuoto = illimitato).
- **Ecommerce sponsor**: `is_self_purchasable` (appare nel portale) + `cutoff` giorni (vuoto = sempre, 0 = fino al giorno, N = chiude N giorni prima).
- **Varianti**: opzioni con prezzo/stock proprio.
- **Servizi inclusi**: servizi aggiunti automaticamente a €0 quando si vende il servizio padre (con quantità).
- **Scadenze automatiche**: spunta **"Genera scadenze"** (`triggers_deadlines`) + uno o più **Template scadenze** sotto. ⚠️ **Servono entrambi**: la spunta da sola non basta.
- Immagini: rinominate automaticamente in nome neutro (anti adblock) e ottimizzate.
- **Colonne utili nella lista servizi**: **Img** (✓ verde = immagine caricata, ○ grigio = mancante) e **Scadenze** (badge verde con quante scadenze programmate ha il servizio). Servono a capire a colpo d'occhio cosa manca.
- **Tipo di consegna della scadenza** (`submission_kind` nel Template scadenza): *File*, *Contenuto*, *Entrambi* oppure **"Materiale fisico (spedizione postale)"**. Scegliendo *Materiale fisico* si attiva il campo **Istruzioni di spedizione** che compili tu e il cliente vede nel portale (indirizzo, imballo, riferimento, ecc.).

### 4.4 Stand e Blocchi
- **Stand**: codice (unico per evento), dimensioni (larghezza/profondità → area calcolata), tipologia, dotazioni (elettrico/acqua/internet/altezza), prezzo base, **descrizione preventivo IT/EN** (mostrata solo nel preventivo), stato.
- **Blocchi**: raggruppano più stand venduti insieme; prezzo blocco (se vuoto = somma stand). Uno stand in blocco **non** è vendibile singolarmente.
- Lo **stato** (disponibile/riservato/assegnato) è automatico in base ai contratti.
- *Nota*: non c'è una mappa interattiva; lo stand si assegna al contratto via ricerca/autocomplete (mostra solo i disponibili).

### 4.5 Sponsor e Anagrafiche (contatti)
- **Sponsor**: ragione sociale, P.IVA, C.F., SDI, PEC, indirizzo, logo, ecc.
- **Anagrafica di riferimento (Contatti)**: referenti dell'azienda con ruoli funzionali (firmatario, marketing, amministrazione, operativo, CC, educational) e **lingua preferita**.
- Import contatti/sponsor da Excel (colonne Cognome/Nome separate).

### 4.6 Contratti (Domande di ammissione)
Cuore operativo. Per un contratto:
1. Scegli **sponsor** + **evento**; assegna **stand** o **blocco** (opzionale).
2. Aggiungi **righe servizio** (con quantità/variante). I servizi inclusi si aggiungono da soli a €0. I prezzi sono **congelati** (snapshot) alla creazione della riga.
3. (Opzionale) imposta un'**opzione**: nella sezione **Spazio espositivo**, campo **"Spazio opzionato fino al"** (`option_until`). Finché quella data non è passata lo spazio resta *riservato* per lo sponsor anche a preventivo in bozza; oltre la data torna disponibile. Puoi modificare/togliere questa data quando vuoi.
4. **Invia preventivo** (azione "Genera e invia PREVENTIVO"): stato → *Inviato*, stand → *riservato*, genera il PDF e invia l'email allo sponsor.
5. **Firma** (lo sponsor conferma dal portale, o l'operatore con l'azione "Marca come FIRMATO", o automaticamente all'incasso): stato → *Firmato*, stand → *assegnato*, **genera le scadenze** (tecniche + acconto/saldo), **rimuove la scadenza-opzione** e invia notifica. Vedi anche il punto seguente.
6. **Annulla o cancella** se serve: **libera subito lo stand/blocco** (torna disponibile) e i **servizi a numero limitato**; le scadenze pendenti diventano "esonerate".
- **Generazione automatica alla conferma** (contratti principali di eventi **non-ECM**): oltre alla domanda di ammissione, il sistema genera il **contratto di sponsorizzazione** (con la domanda come *Allegato 1*) e lo invia via email al **contatto operativo** dello sponsor, in CC ad *amministrazione@valet.it* ed *elisa.fantini@valet.it*. Vedi Schema A.
- **Numerazione** automatica `SIGLA-AA-NNN` (anti-collisione), anche per gli addon.
- **Azione "Genera scadenze dai template"**: per contratti **già firmati** a cui hai aggiunto/modificato scadenze dopo la firma (vedi §11 e Troubleshooting).
- **Termini di cancellazione / penale**: la percentuale di penale del contratto/domanda si imposta per evento in *Eventi → Dati per contratti → "Penale cancellazione (%)"* (default 50%). Nel PDF il testo si adatta alla forma di pagamento (con o senza acconto).

### 4.7 Pagamenti
- **Contratto principale (domanda di ammissione) = solo bonifico.** Acconto e saldo si pagano con bonifico; l'operatore registra l'incasso con l'azione **"Registra pagamento bonifico ricevuto"**. Il pagamento online **non** è disponibile per il contratto principale.
- **Pagamento online (carta/PayPal) = solo acquisti ecommerce** (servizi dal carrello, contratti *addon*): si registrano da soli e il contratto addon si firma all'incasso. Vedi Schema B.
- I dati bancari mostrati al cliente vengono dalle variabili `.env` `BANK_TRANSFER_*` (vedi §14).

### 4.8 Scadenze cliente (Cruscotto)
`/admin/cruscotto/scadenze-cliente/`: elenco di tutte le scadenze tecniche generate dai template, con stato (da fare / in ritardo / completata) e chi/quando ha consegnato. Filtrabile per evento.

### 4.9 Template Email e Template Lettera
Due cose **diverse**:
- **Template email** (`Template email`): oggetto + corpo dell'**email** (bilingue IT/EN, editor WYSIWYG). È il messaggio che il cliente legge in posta. Segnaposti: `{{ contact.full_name }}`, `{{ event.name }}`, `{{ contract.contract_number }}`.
  - La lista contiene **una riga per ogni punto d'invio × tipo evento**: **12 punti** (invito portale, preventivo, conferma, contratto sponsor, conferma pagamento, reminder e sollecito scadenze, reminder opzione, recupero carrello, alert operatore, reset password, notifica messaggio) × **ECM / Non-ECM** = 24 modelli.
  - Ogni riga ha **Punto di invio**, **Tipo evento**, **Attivo** e l'editor oggetto/corpo. **Finché una riga non è "Attivo", parte l'email standard di sistema.** Quando la attivi, sostituisce l'email standard **solo per quel tipo di evento**. Vedi Schema C.
- **Template lettera** (`Template lettera`): il **corpo della lettera dentro il PDF** del preventivo. Segnaposti: `{{ azienda }}`, `{{ numero }}`, `{{ totale }}`, `{{ stand }}`, `{{ servizi }}`, `{{ luogo_evento }}`. È collegato al contratto ("Template lettera preventivo").
> In sintesi: **email = la busta** che arriva; **lettera = il foglio di offerta dentro la busta (PDF)**.
> ⚠️ Creare un **servizio** o un **evento** non aggiunge righe ai Template email: i 12 punti sono fissi (sono i momenti in cui il sistema manda email).

### 4.10 Impostazioni segreteria, SMTP, Utenti
- **Impostazioni segreteria** (`OrganizerSettings`): dati azienda organizzatrice (nome, indirizzo, email, P.IVA, REA, **logo** mostrato nel footer dei documenti/email), giorni acconto/saldo, testi privacy.
- **Configurazione email (SMTP)**: server di invio (host/porta/utente/password/TLS). Se non configurato, le email vanno in console (sviluppo).
- **Utenti**: account operatori (staff) e gestione accessi.

### 4.11 Cruscotto
Home operatore `/admin/cruscotto/`: KPI (soci/sponsor, incassi, eventi, ecc.), **avviso "preventivi da inviare"** (compare anche in cima a tutte le pagine admin), messaggi non letti dai clienti, scadenze.

---

## 5. PORTALE SPONSOR (lato cliente)

- **Login** con email → Dashboard con prossimi eventi, scadenze aperte, saldo da pagare, messaggi.
- **I miei dati**: l'azienda aggiorna anagrafica e **contatti**. Ogni contatto (principale e altri) ha la **scelta lingua** con bandierina (IT/EN); per i contatti esistenti si cambia al volo cliccando la bandiera.
- **Servizi / Catalogo**: visibile solo se l'azienda ha **almeno un contratto firmato/attivo**. I servizi acquistabili sono mostrati come **card per evento** (con varianti/quantità e cutoff). *Gli stand non si scelgono dal portale*: li assegna l'operatore; il cliente li vede nel dettaglio del contratto. Se non ha ancora firmato, c'è il link **"Vai alla domanda di ammissione"** per rivedere/confermare il preventivo.
- **Carrello / Wishlist**: un carrello per evento (= contratto addon in bozza). Checkout con **Carta / PayPal / Bonifico**.
- **Materiali / Scadenze**: l'azienda carica i file richiesti dalle scadenze tecniche (es. logo, file relatori).
- **Documenti**: i PDF (preventivo, domanda di ammissione) sono scaricabili.

---

## 6. FLUSSI OPERATIVI COMPLETI (passo-passo)

### 6.1 Allestire un nuovo evento
1. Crea **Evento** (date, luogo, lingua, header).
2. Importa/crea **Servizi** dell'evento (da catalogo o da zero); imposta prezzi, varianti, inclusi, scadenze.
3. Importa/crea **Stand** (e **Blocchi** se servono).
4. Verifica i **listini** e i **template** (email + lettera) per l'evento.

### 6.2 Vendere a uno sponsor (flusso completo)
1. Crea/seleziona lo **Sponsor** e i suoi **Contatti** (con lingua).
2. Crea il **Contratto**: assegna stand/blocco, aggiungi servizi.
3. **Genera e invia il preventivo** → email allo sponsor + PDF.
4. Lo sponsor **conferma** dal portale (o paga) → contratto **Firmato**, scadenze generate.
5. Gli incassi (acconto/saldo) si registrano (portale o bonifico).
6. Lo sponsor **carica i materiali** entro le scadenze tecniche.

### 6.3 Acquisto ecommerce (addon) dello sponsor
1. Lo sponsor (con contratto firmato) sceglie servizi self-purchasable → **carrello**.
2. **Checkout** (Carta/PayPal/Bonifico) → contratto addon *In attesa pagamento* → all'incasso *Firmato*.

---

## 7. MULTILINGUA E TRADUZIONI AUTOMATICHE

- I campi nome/descrizione (servizi, catalogo, stand) e i template sono **bilingue IT/EN** (JSON `{it,en}`).
- Al salvataggio, se l'inglese manca, viene **tradotto automaticamente da DeepL** (serve `DEEPL_API_KEY` nel `.env`). Non sovrascrive l'EN inserito a mano; non blocca il salvataggio in caso di errore.
- L'interfaccia (portale e backoffice) ha la **lingua IT/EN** con bandierine.
- ⚠️ Se le traduzioni "non partono", manca `DEEPL_API_KEY` nell'ambiente (vedi §14/§15).

---

## 8. DOCUMENTI PDF

- **Preventivo grafico**: HTML→PDF via WeasyPrint. In fondo a ogni pagina il **footer segreteria** (logo a sinistra, dati a destra). Il logo arriva da *Impostazioni segreteria → Logo* (file media).
- **Domanda di ammissione / Contratto**: docx (template in `contracts/templates_pdf/`) → PDF via LibreOffice.
- ⚠️ Per una resa corretta servono i **font** giusti sul server (Liberation/Carlito): senza, il modulo può sforare su 2 pagine (vedi §15).

---

## 9. IMPORT DA EXCEL

Comandi (vedi §13) per caricare in blocco. Regole comuni:
- **Upsert** per chiave (`evento_slug`+`code`): se esiste, aggiorna; altrimenti crea.
- **Protezione**: se un servizio/stand ha già contratti, vengono aggiornati solo campi non critici (non prezzo/stato/blocco).
- **Anti-duplicati** nel file: righe con codice duplicato vengono saltate e segnalate.
- **Dry-run** disponibile per simulare senza scrivere.
- Booleani accettati: `s/si/sì/yes/y/1/true/x/✓` = vero; `n/no/0/false/-` = falso. Decimali: la virgola è accettata.

File template scaricabili dal Cruscotto (Utility) per catalogo, servizi, stand.

---

## 10. PAGAMENTI

> **Regola generale**: contratto **principale** (domanda di ammissione) → **solo bonifico**; **servizi ecommerce** (carrello/addon) → carta/PayPal/bonifico. Il pulsante di pagamento online compare solo per i contratti *addon*.

- **PayPal / Carta** (solo ecommerce/addon): tramite PayPal SDK; al ritorno/cattura il pagamento diventa *Succeeded* e il contratto addon si firma. Webhook PayPal idempotente.
- **Bonifico** (principale e, se scelto, ecommerce): lo sponsor vede IBAN e causale (dai `.env` `BANK_TRANSFER_*`); l'operatore registra l'incasso manualmente.
- All'incasso, le **scadenze di pagamento** (acconto/saldo) coperte vengono marcate come ricevute.
- Configurazione PayPal in `.env` (`PAYPAL_MODE/CLIENT_ID/SECRET/WEBHOOK_ID`).

---

## 11. SCADENZE E REMINDER

- **Tecniche**: generate **alla firma** dai *Template scadenze* dei servizi con "Genera scadenze" attivo. Data = inizio evento − giorni del template. Lo sponsor le soddisfa caricando file/compilando campi dal portale. Se il tipo è **"Materiale fisico"**, invece dell'upload il cliente vede le tue **istruzioni di spedizione**.
- **Pagamento**: acconto (firma + N giorni) e saldo (inizio evento − M giorni), da *Impostazioni segreteria*.
- **Reminder/solleciti** automatici via Celery beat (giorni configurati nei template; solleciti per le scadute).
- ⚠️ Le scadenze si generano **all'istante della firma**. Se aggiungi una scadenza **dopo** che il contratto è già firmato: usa l'azione **"Genera scadenze dai template"** sul contratto, oppure salva di nuovo il servizio (la rigenerazione automatica via signal è attiva).

---

## 12. MANUTENZIONE, BACKUP E TRASFERIMENTO

- **Deploy**: Docker Compose. `git pull && docker compose build web && docker compose up -d`. Le migrazioni e `compilemessages` (traduzioni) girano nell'entrypoint del container web.
- **HTTPS**: automatico con Caddy impostando `SITE_ADDRESS=dominio`.
- **Backup completo / trasferimento**: usa gli script `scripts/backup_completo.sh` (crea un `.tgz` con `.env` + database + media) e `scripts/restore_completo.sh`. Vedi `TRASFERIMENTO.md`.
- ⚠️ **Cosa NON sta in git e va trasferito a mano**: il file **`.env`** (segreti: SECRET_KEY, DB_PASSWORD, DEEPL_API_KEY, BANK_TRANSFER_*, SMTP, PayPal) e la cartella **`media/`** (logo segreteria, header eventi, loghi sponsor, PDF generati).

---

## 13. COMANDI UTILI (management commands)

Eseguibili con `python manage.py <comando>` (in Docker: `docker compose exec web python manage.py <comando>`).

| Comando | A cosa serve |
|---|---|
| `importa_catalogo --file X.xlsx [--dry-run] [--immagini DIR]` | importa il catalogo madre |
| `importa_servizi --file X.xlsx [--dry-run]` | importa servizi per-evento |
| `importa_stand --file X.xlsx [--dry-run]` | importa stand |
| `copia_servizi --da EVENTO --a EVENTO [--dry-run]` | copia i servizi tra eventi |
| `diagnosi_scadenze "NOME SERVIZIO"` | diagnostica perché un servizio non genera scadenze |
| `elimina_contratti_annullati [--conferma] [--hard]` | rimuove i contratti annullati (anteprima → conferma; `--hard` = definitivo) |
| `compilemessages` | compila le traduzioni EN (.po → .mo) |

---

## 14. VARIABILI DI CONFIGURAZIONE (.env)

Obbligatorie: `SECRET_KEY`, `DB_PASSWORD`, `ALLOWED_HOSTS`, `SITE_ADDRESS`.
Funzionalità (se mancano, la feature non va):
- `DEEPL_API_KEY` → traduzioni automatiche IT→EN.
- `BANK_TRANSFER_HOLDER/_BANK/_IBAN/_BIC` → dati del bonifico al checkout (senza, compaiono i placeholder "DA CONFIGURARE").
- `EMAIL_*` → invio email reali (senza, vanno in console).
- `PAYPAL_MODE/_CLIENT_ID/_CLIENT_SECRET/_WEBHOOK_ID` → pagamenti PayPal.
- `AUTO_TRANSLATE_ON_SAVE` (default True) → on/off auto-traduzione.

Riferimento completo con esempi: `.env.prod.example`.

---

## 15. TROUBLESHOOTING (problemi noti e soluzioni)

| Sintomo | Causa | Soluzione |
|---|---|---|
| Modulo "domanda di ammissione" su **2 pagine** | font Arial/Liberation mancanti sul server → LibreOffice sostituisce con font più largo | installare `fonts-liberation` + `fonts-crosextra-carlito` (già nel Dockerfile); rebuild immagine |
| Bonifico mostra **"DA CONFIGURARE"** / IBAN finto | variabili `BANK_TRANSFER_*` non nel `.env` del server | aggiungerle al `.env` e `docker compose up -d` |
| **Traduzioni automatiche** non funzionano | manca `DEEPL_API_KEY` | impostarla nel `.env` |
| **Scadenza non creata** su contratto firmato | il template scadenza è stato aggiunto/abilitato **dopo** la firma | azione "Genera scadenze dai template" sul contratto, o ri-salva il servizio. Verifica con `diagnosi_scadenze "NOME"` |
| **Logo segreteria assente** nel footer PDF | la cartella `media/` non è stata trasferita (volume nuovo vuoto) | ricaricare il logo da *Impostazioni segreteria* |
| Template email **non salva** oggetto/corpo | (risolto) campi resi multilingua JSON | assicurarsi di avere l'ultima versione (migrazione `shared 0009`) |
| Menu admin invisibile su **mobile** | Django nasconde la sidebar sotto 767px | usare l'**hamburger ☰** in alto a sinistra |
| Download admin arrivano con nome UUID senza estensione | Service Worker "fantasma" su `localhost:8000` da altro progetto | usare un'altra porta o deregistrare il SW da `chrome://serviceworker-internals` |

---

## 16. FAQ

**Posso vendere uno stand che fa parte di un blocco?** No: si vende il blocco intero.

**I prezzi cambiano nei contratti già firmati se aggiorno il listino?** No: i prezzi sono congelati (snapshot) nelle righe del contratto.

**Lo sponsor sceglie lo stand dal portale?** No: lo assegna l'operatore; lo sponsor lo vede nel dettaglio contratto.

**Differenza Template email vs Template lettera?** Email = il messaggio di posta; Lettera = il testo dell'offerta dentro il PDF allegato.

**Come tolgo dalla lista i contratti annullati?** Comando `elimina_contratti_annullati` (anteprima, poi `--conferma`; reversibile, salvo `--hard`).

**Dove ricarico il logo che appare sui PDF/email?** *Backoffice → Impostazioni segreteria → Logo*.

**Perché il cliente non può pagare la domanda di ammissione con carta/PayPal?** È voluto: il **contratto principale si paga solo con bonifico**. Carta/PayPal restano per i **servizi acquistati online** (carrello/addon).

**Il contratto di sponsorizzazione a chi arriva?** Alla conferma del preventivo (eventi **non-ECM**) parte in automatico al **contatto operativo** dello sponsor, in CC ad *amministrazione@valet.it* ed *elisa.fantini@valet.it*, con la domanda di ammissione come *Allegato 1*.

**Ho creato un nuovo servizio: devo creare anche un template email?** No. I template email sono **12 punti fissi** (× ECM/Non-ECM). I servizi non aggiungono email.

**Come personalizzo un'email solo per gli eventi ECM (o solo non-ECM)?** In *Template email* apri la riga del punto voluto per quel tipo evento, scrivi oggetto/corpo e mettila **Attivo**.

---

*Fine manuale operativo. Per la guida rapida illustrata vedi `docs/manuale_utente.html`. Per l'integrazione del modulo stand in altri sistemi vedi `SPEC-INTEGRAZIONE-STAND.md`.*
