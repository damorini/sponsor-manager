# MANUALE OPERATIVO COMPLETO — Sponsor Manager

> Guida operativa completa del gestionale **Sponsor Manager** (Valet): gestione di congressi/eventi, sponsor/espositori, stand, catalogo servizi, preventivi/domande di ammissione, pagamenti, scadenze e portale clienti.
>
> Questo è il **manuale operativo di sistema** (backoffice + portale + manutenzione). Per la guida rapida utente esiste anche `docs/manuale_utente.html` (apribile nel browser). In caso di dubbio, questo documento è la fonte completa.
>
> *Ultimo aggiornamento: agosto 2026.*

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
 • sponsor + evento   ──>  • stato: INVIATO      ──>  • GATE: anagrafica completa
 • stand / blocco          • stand: RISERVATO           (incl. Codice SIS farmaceutiche)
 • righe servizio          • PDF preventivo             + firmatario registrato
 • (opz.) opzione          • email al cliente           (se manca → il cliente completa
 • FIRMATARIO!               (avviso se manca            «I miei dati» e TORNA da solo
                              il firmatario)             alla conferma)
                                                        • stato: FIRMATO · stand: ASSEGNATO
                                                        • si generano le SCADENZE
                                                          (acconto/saldo, materiali,
                                                           «Invio contratto firmato» +10gg)
                                                        │
                                                        └─> GENERATO IN AUTOMATICO (non-ECM):
                                                            UN SOLO PDF: Contratto di
                                                            sponsorizzazione con il riepilogo
                                                            servizi come ALLEGATO 1
                                                            → email «Grazie per aver confermato»
                                                              con il contratto allegato
                                                            → email al contatto OPERATIVO
                                                              in CC: amministrazione@valet.it
                                                                     morini@valet.it
                                                            (eventi ECM: resta la Domanda
                                                             di ammissione)
```

> **Ritorno del firmato**: il cliente restituisce il contratto firmato via email ad
> **amministrazione@valet.it** oppure caricandolo nei **Materiali** del portale (pulsante
> diretto nell'email). Scadenza a **+10 giorni** con reminder 10/3/0 e solleciti ogni 3 giorni;
> al caricamento parte l'**avviso email ad amministrazione**.

### Schema B — Chi paga come (IMPORTANTE)

```
 CONTRATTO PRINCIPALE                    SERVIZI ACQUISTATI ONLINE
 (contratto di sponsorizzazione)         (carrello / addon ecommerce)
        │                                        │
        └──> SOLO BONIFICO                       └──> PAYPAL / MYBANK / CARTA / BONIFICO
             acconto + saldo                          pagamento immediato
             l'operatore registra l'incasso           il contratto si firma all'incasso
```
> Il pagamento **online** è riservato agli **acquisti ecommerce** ed è **LIVE dal 7/7/2026**
> (soldi veri sul conto PayPal Business VALET): PayPal, **MyBank** (bonifico istantaneo
> dall'home banking del cliente) e carta. Il **contratto principale si salda solo con bonifico**.
> Un ordine rimasto in attesa mostra in «I miei acquisti» il pulsante **«Paga ora con carta o
> PayPal»**; l'ordine PayPal scaduto o lasciato a metà viene **rigenerato da solo** alla
> riapertura della pagina di pagamento.

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
- **Duplica per NUOVA EDIZIONE** (azione nel menu): clona l'evento con tutta la struttura — servizi (con varianti, inclusi e template scadenze), stand e blocchi. Il clone nasce in stato *Pianificazione* con stand tutti *disponibili*; contratti/sponsor dell'originale NON vengono toccati né copiati. Dopo la duplicazione: aggiorna nome, date e prezzi.
- Colonna **"Fatturato (IVA escl.)"** nella lista eventi: somma degli imponibili dei contratti non annullati.
- **Ragione sociale organizzatore** (scheda evento, dati per i contratti): compilala **solo se l'organizzatore dell'evento non è VALET** — il nome inserito sostituisce la ragione sociale nei PDF (contratto e domanda di ammissione). Se resta **vuota**, nei documenti esce la dicitura standard VALET. ⚠️ Cambia solo il nome: sede, P.IVA e rappresentante nei documenti restano quelli VALET (sono fissi nei template Word).

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
- **Note per lo sponsor (IT/EN)** (su Stand e Blocco): indicazioni per il cliente — es. come preparare le grafiche — che compaiono nel **preventivo** (riquadro "Note sullo spazio espositivo") e nella **domanda di ammissione/contratto** (sotto la tabella dei servizi). Sono separate dalle **Note interne**, che il cliente non vede. L'inglese si compila da solo. La colonna `note_sponsor` è anche nel **modello Excel** degli stand (Utility → Scarica il Modello).
- **Ordinamento naturale dei codici**: gli stand sono elencati per prefisso e poi per numero (S-1…S-9, S-10 — non più S-10 in fondo dopo altri prefissi).
- Lo **stato** (disponibile/riservato/assegnato) è automatico in base ai contratti.
- *Nota*: non c'è una mappa interattiva; lo stand si assegna al contratto via ricerca/autocomplete (mostra solo i disponibili).

### 4.5 Sponsor e Anagrafiche (contatti)
- **Sponsor**: ragione sociale, P.IVA, C.F., SDI, PEC, indirizzo, logo, ecc.
- **Azienda farmaceutica + Codice SIS**: spunta nei *Dati fiscali*; per le aziende flaggate il Codice SIS è **obbligatorio** (rientra nel gate anagrafica del portale: conferma preventivo e acquisti). Filtro dedicato nella lista Sponsor.
- **Anagrafica di riferimento (Contatti)**: referenti dell'azienda con ruoli funzionali (firmatario, marketing, amministrazione, operativo, CC, educational) e **lingua preferita**.
- ⚠️ **Il firmatario è indispensabile**: senza un contatto con «È il legale rappresentante firmatario?» il contratto non si può generare e il cliente viene **bloccato alla conferma**. All'invio del preventivo il sistema ti avvisa (banner giallo + warning) se manca.
- ⚠️ **Dati anagrafici del firmatario OBBLIGATORI** (da luglio 2026): il contratto stampa nato il/a, provincia di nascita, residenza completa (via, civico, città, CAP, provincia), tipo+numero documento e **codice fiscale** del firmatario. **Senza tutti questi campi il contratto NON si genera** (né da admin né alla conferma dal portale, con l'elenco esatto di cosa manca). Il cliente può compilarli da solo nel portale («I miei dati» → checkbox «È il legale rappresentante che firma il contratto?»), oppure li inserisce l'operatore sul Contatto.
- Colonna **"Accesso portale"** nella lista Sponsor (+ filtro): mostra chi ha fatto login dopo l'invito (✓ verde con data ultimo accesso, "Invitato, mai entrato" in arancio, "—" se nessun contatto invitato).
- Import contatti/sponsor da Excel (colonne Cognome/Nome separate).

### 4.6 Contratti (Domande di ammissione)
Cuore operativo. Per un contratto:
1. Scegli **sponsor** + **evento**; assegna **stand** o **blocco** (opzionale).
2. Aggiungi **righe servizio** (con quantità/variante). I servizi inclusi si aggiungono da soli a €0. I prezzi sono **congelati** (snapshot) alla creazione della riga.
3. (Opzionale) imposta un'**opzione**: nella sezione **Spazio espositivo**, campo **"Spazio opzionato fino al"** (`option_until`). Finché quella data non è passata lo spazio resta *riservato* per lo sponsor anche a preventivo in bozza; oltre la data torna disponibile. Puoi modificare/togliere questa data quando vuoi.
4. **Invia preventivo** (azione "Genera e invia PREVENTIVO"): stato → *Inviato*, stand → *riservato*, genera il PDF e invia l'email allo sponsor.
5. **Firma** (lo sponsor conferma dal portale, o l'operatore con l'azione "Marca come FIRMATO", o automaticamente all'incasso): stato → *Firmato*, stand → *assegnato*, **genera le scadenze** (tecniche + acconto/saldo + **«Invio contratto firmato»** a +10 giorni), **rimuove la scadenza-opzione** e invia notifica. La conferma dal portale è protetta dai **gate**: anagrafica completa (con ritorno automatico da «I miei dati») e firmatario registrato. Vedi anche il punto seguente.
6. **Annulla o cancella** se serve: **libera subito lo stand/blocco** (torna disponibile) e i **servizi a numero limitato**; le scadenze pendenti diventano "esonerate". I collegati **già nel cestino** e i pagamenti registrati **non bloccano** l'eliminazione del principale; bloccano solo i figli ancora attivi.
- **Generazione automatica alla conferma** (contratti principali di eventi **non-ECM**): il sistema genera **UN SOLO documento da firmare** — il **contratto di sponsorizzazione** con il riepilogo servizi come *Allegato 1* — e lo invia sia al cliente («Grazie per aver confermato il preventivo», con PDF allegato) sia al **contatto operativo**, in CC ad *amministrazione@valet.it* e *morini@valet.it*. La domanda di ammissione **non esce più come documento separato** (resta per gli eventi **ECM**). L'email spiega come restituire il firmato: email ad amministrazione@valet.it o **upload nei Materiali** (pulsante diretto). Vedi Schema A.
- **Numerazione** automatica `SIGLA-AA-NNN` (anti-collisione), anche per gli addon.
- **Azione "Genera scadenze dai template"**: per contratti **già firmati** a cui hai aggiunto/modificato scadenze dopo la firma (vedi §11 e Troubleshooting).
- **Termini di cancellazione / penale**: la percentuale di penale del contratto/domanda si imposta per evento in *Eventi → Dati per contratti → "Penale cancellazione (%)"* (default 50%). Nel PDF il testo si adatta alla forma di pagamento (con o senza acconto).

**Novità luglio/agosto 2026 sui contratti:**
- **Riga LIBERA** (richieste specifiche non a catalogo): nelle righe del contratto lascia vuoto «Servizio» e compila **«Descrizione libera»** + quantità + prezzo. Nessun controllo di quantità/disponibilità; usabile più volte nello stesso contratto; compare nei PDF come le altre righe.
- **Ordine delle righe nel documento**: il campo **«Ordine»** della riga (se ≠0) forza la sua posizione nel preventivo/allegato (es. voci relatore in fondo). Con tutte a 0 resta l'ordinamento automatico per importo.
- **Clausola di pagamento del contratto** (campo *Modalità pagamento* + *Termini*): con **RI.BA.** la frase diventa «SALDO: € … da regolarsi tramite Ri.Ba. \<termini\>» (es. "60 gg F.M."); con **Bonifico (B.B.) con scadenza fissa** diventa «PAGAMENTO: € … tramite B.B. con scadenza \<data in lettere\>». Negli altri casi resta «…valuta fissa al gg/mm/aaaa».
- **Azioni nel menu**: «**Rigenera PDF contratto**» (dopo aver cambiato firmatario/prezzi/righe — niente più interventi manuali), «**Trasforma preventivo in contratto**», «**Genera riga dallo stand**», «**Genera fattura proforma**» (vedi sotto). «**Annulla domande**» ora apre una **pagina di conferma** con elenco, avvertenze e campo *motivo*.
- **Colonna "Incassato / Residuo"** nella lista: verde «✓ saldato», ambra parziale, rosso zero — ordinabile.
- **Cambio stato a mano**: impostare «Firmato» dal menu a tendina ora esegue comunque la **cascata completa** (scadenze, stand assegnato, data firma) come l'azione dedicata. Meglio comunque usare le azioni.
- **Cambio/rimozione stand** su contratto esistente: la riga del vecchio spazio viene rimossa automaticamente (niente doppio stand nel preventivo).
- **Flag IVA**: attivarlo/disattivarlo ricalcola subito l'IVA di tutte le righe. **Prezzo o aliquota 0 espliciti** su una riga nuova vengono rispettati (omaggi), non sostituiti dal listino.
- **Cestino e ripristino**: cancellare libera stand ed esonera le scadenze aperte; il **ripristino ri-assegna automaticamente lo stand**, ma le scadenze esonerate vanno **ricontrollate a mano** (admin Scadenze).
- **Fattura PROFORMA**: azione «Genera FATTURA PROFORMA» (1 documento a pagamento unico, 2 numerati /1 acconto e /2 saldo se previsto l'acconto). Documento NON fiscale; finisce tra i Documenti del contratto (visibile al cliente in «I miei documenti»), alimenta l'«Export fatture» e **invia in automatico un'email al cliente** che lo avvisa del documento disponibile.

### 4.7 Pagamenti
- **Contratto principale = solo bonifico.** Acconto e saldo si pagano con bonifico; l'operatore registra l'incasso con l'azione **"Registra pagamento bonifico ricevuto"**. Il pagamento online **non** è disponibile per il contratto principale.
- **Pagamento online (PayPal / MyBank / carta) = solo acquisti ecommerce** (servizi dal carrello, contratti *addon*): si registrano da soli e il contratto addon si firma all'incasso. **LIVE dal 7/7/2026** (app PayPal Business VALET, webhook attivo). MyBank = bonifico istantaneo dall'home banking del cliente, comodo per le aziende. Vedi Schema B.
- Ordini in attesa: il cliente ha il pulsante **«Paga ora con carta o PayPal»** in «I miei acquisti»; un ordine PayPal scaduto/lasciato a metà viene rigenerato da solo.
- I dati bancari mostrati al cliente vengono dalle variabili `.env` `BANK_TRANSFER_*`; le chiavi PayPal da `PAYPAL_*` (vedi §14).
- La lista Pagamenti in admin ha la colonna **Cliente** (ragione sociale, ordinabile) accanto al numero contratto.
- **Contabile del bonifico dal portale**: il cliente può caricare la ricevuta del bonifico sulla scadenza di pagamento (una volta sola). Il caricamento **NON marca "Pagato"**: arriva un'email ad *amministrazione@valet.it* e tocca a te verificare l'accredito e **registrare l'incasso** dal cruscotto («Registra incasso») — solo allora la scadenza va in Pagato.
- «Conferma bonifico ricevuto» funziona anche su contratti già *Attivi/Completati* (registra l'incasso senza toccare lo stato del contratto).

### 4.8 Scadenze cliente (Cruscotto)
`/admin/cruscotto/scadenze-cliente/`: elenco di tutte le scadenze tecniche generate dai template, con stato (da fare / in ritardo / completata) e chi/quando ha consegnato. Filtrabile per evento.

### 4.9 Template Email
- **Template email** (`Template email`): oggetto + corpo dell'**email** (bilingue IT/EN, editor WYSIWYG). È il messaggio che il cliente legge in posta. Segnaposti: `{{ contact.full_name }}`, `{{ event.name }}`, `{{ contract.contract_number }}`.
  - La lista contiene **una riga per ogni punto d'invio × tipo evento**: **12 punti** (invito portale, preventivo, conferma, contratto sponsor, conferma pagamento, reminder e sollecito scadenze, reminder opzione, recupero carrello, alert operatore, reset password, notifica messaggio) × **ECM / Non-ECM** = 24 modelli.
  - Ogni riga ha **Punto di invio**, **Tipo evento**, **Attivo** e l'editor oggetto/corpo. **Finché una riga non è "Attivo", parte l'email standard di sistema.** Quando la attivi, sostituisce l'email standard **solo per quel tipo di evento**. Vedi Schema C.
> ⚠️ Creare un **servizio** o un **evento** non aggiunge righe ai Template email: i 12 punti sono fissi (sono i momenti in cui il sistema manda email).
> *Nota: il "Template lettera" è stato rimosso dal menu — non era usato dal preventivo grafico attuale.*

### 4.10 Impostazioni segreteria, SMTP, Utenti
- **Impostazioni segreteria** (`OrganizerSettings`): dati azienda organizzatrice (nome, indirizzo, email, P.IVA, REA, **logo** mostrato nel footer dei documenti/email), giorni acconto/saldo, testi privacy.
- **Configurazione email (SMTP)**: server di invio (host/porta/utente/password/TLS). Se non configurato, le email vanno in console (sviluppo).
- **Utenti**: account operatori (staff) e gestione accessi.

### 4.11 Cruscotto
Home operatore `/admin/cruscotto/`: KPI (soci/sponsor, incassi, eventi, ecc.), messaggi non letti dai clienti, scadenze, e questi **avvisi automatici**:
- **Preventivi da inviare** (bozze mai inviate — compare anche in cima alle pagine admin)
- **Preventivi inviati SENZA RISPOSTA da oltre 7 giorni** (per valutare un sollecito)
- **Opzioni stand in scadenza entro 7 giorni** (alla scadenza lo spazio torna disponibile in silenzio)
- **Materiali ricevuti da visionare**

**Cruscotto evento** (`/admin/cruscotto/evento/<id>/`) — dal luglio 2026:
- ⚠️ **Tutti gli importi sono in IVA ESCLUSA (imponibile)**, con il complessivo IVA inclusa mostrato sotto in piccolo: sommare aziende con e senza IVA su basi diverse rendeva i totali incomprensibili. Gli incassi (che sono denaro lordo reale) vengono convertiti proporzionalmente alla loro quota imponibile.
- Card **Incassato** cliccabile → pagina «chi ha pagato» (cliente, netto/lordo, n. pagamenti, data ultimo incasso); card **Da incassare** → dettaglio residui con «Registra incasso». Entrambe le pagine hanno il pulsante **⬇ Scarica Excel**.
- Sezione **Contratti e stand**: il numero grande sono i **contratti** (gli stand come dettaglio — un contratto di sola sponsorizzazione senza stand non fa più sembrare "mancante" un confermato). Card cliccabili verso le liste filtrate, incluse quelle degli **Importi**.

---

## 5. PORTALE SPONSOR (lato cliente)

- **Login** con email → Dashboard «In evidenza» con prossimi eventi, la card **Scadenze aperte** (se ce ne sono, il click apre la pagina scadenze dell'evento più urgente; con zero scadenze è verde e non cliccabile) e la card **«Pagamenti in sospeso»** (importo ancora da versare, click → pagina Pagamenti). Chi apre un link del portale **senza un profilo utilizzabile** (mai fatto il primo accesso) vede la pagina di cortesia **«Ci siamo quasi»** con le due strade: accedi con le credenziali ricevute, o scrivi a **helpdesk@valet.it**.
- **Pagamenti**: una card per ogni scadenza acconto/saldo con badge Firmato/Pagato; le voci aperte hanno il pulsante **«Paga ora»** (per il contratto principale = pagina bonifico con IBAN e causale).
- **I miei dati**: l'azienda aggiorna anagrafica e **contatti**. Ogni contatto (principale e altri) ha la **scelta lingua** con bandierina (IT/EN); per i contatti esistenti si cambia al volo cliccando la bandiera (pulsante **«Modifica»** per gli altri campi). Domanda **«Azienda farmaceutica?»**: se spuntata compare il campo **Codice SIS** (obbligatorio). Checkbox **«È il legale rappresentante che firma il contratto?»** su ogni contatto: aprendola compaiono i **campi anagrafici obbligatori del firmatario** (nascita, residenza, documento, CF) che il cliente può compilare da solo; badge verde «✓ Firmatario» o giallo «⚠ dati incompleti» in tabella.
- **Conferma preventivo**: protetta dai gate (anagrafica completa → ritorno automatico alla conferma; firmatario registrato). Alla conferma il cliente riceve il **contratto** (unico PDF con Allegato 1) via email e in area riservata, e trova la scadenza **«Invio contratto firmato»** nei Materiali.
- **Servizi / Catalogo**: visibile solo se l'azienda ha **almeno un contratto firmato/attivo**. I servizi acquistabili sono mostrati come **card per evento** (con varianti/quantità e cutoff). *Gli stand non si scelgono dal portale*: li assegna l'operatore; il cliente li vede nel dettaglio del contratto. Se non ha ancora firmato, c'è il link per rivedere/confermare il preventivo.
- **Carrello / Wishlist**: un carrello per evento (= contratto addon in bozza). Checkout con **PayPal / MyBank / Carta / Bonifico**; ordini in attesa riprendibili con «Paga ora».
- **Materiali / Scadenze**: l'azienda carica i file richiesti dalle scadenze tecniche (es. logo, file relatori) **e il contratto firmato** (avviso automatico ad amministrazione al caricamento). Sulle scadenze di **pagamento** può caricare la **contabile del bonifico** (una volta sola): non risulta "Pagato" finché la segreteria non verifica l'accredito e registra l'incasso — il cliente vede la nota «in attesa di verifica».
- **Documenti**: i PDF (preventivo, contratto/domanda, proforma) sono scaricabili da «I miei documenti».
- 🔒 **Sicurezza download** (da agosto 2026): i documenti dei clienti NON sono più raggiungibili da chi conosce l'URL — il download richiede il login e verifica che il file appartenga all'azienda (o che sia un operatore). I file caricati sono salvati con nome randomizzato e serviti come allegato; upload limitato a estensioni sicure (PDF, immagini, ZIP, Office, AI/EPS).

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

- **PayPal / MyBank / Carta** (solo ecommerce/addon): tramite PayPal JS SDK (Smart Buttons + Card Fields); alla cattura il pagamento diventa *Succeeded* e il contratto addon si firma. Webhook PayPal idempotente e verificato. **LIVE dal 7/7/2026** (app "Sponsor Manager" sul conto PayPal Business VALET): i pagamenti sono soldi veri.
- **MyBank** = bonifico istantaneo dall'home banking del cliente (lo propone PayPal automaticamente ai compratori italiani in euro): utile per aziende senza carta con plafond alto.
- **Ordini in attesa**: pulsante «Paga ora con carta o PayPal» in «I miei acquisti»; l'ordine PayPal riusato solo se ancora "vergine" (CREATED), altrimenti rigenerato da solo (evita l'errore "si è verificato un errore nel sistema" da ordini scaduti/lasciati a metà).
- **Bonifico** (principale e, se scelto, ecommerce): lo sponsor vede IBAN e causale (dai `.env` `BANK_TRANSFER_*`); l'operatore registra l'incasso manualmente.
- All'incasso, le **scadenze di pagamento** (acconto/saldo) coperte vengono marcate come ricevute.
- Configurazione PayPal in `.env` (`PAYPAL_MODE/CLIENT_ID/SECRET/WEBHOOK_ID`); per test usare la sandbox (mai il sito live).

---

## 11. SCADENZE E REMINDER

- **Tecniche**: generate **alla firma** dai *Template scadenze* dei servizi con "Genera scadenze" attivo. Data = inizio evento − giorni del template. Lo sponsor le soddisfa caricando file/compilando campi dal portale. Se il tipo è **"Materiale fisico"**, invece dell'upload il cliente vede le tue **istruzioni di spedizione**.
- **«Invio contratto firmato»** (contratti principali): creata **alla firma**, scade a **+10 giorni**. Il cliente carica il PDF firmato nei Materiali (o lo manda ad amministrazione@valet.it); al caricamento la scadenza va in *Ricevuto* e parte l'**avviso email ad amministrazione** (CC morini@valet.it).
- **Pagamento**: acconto (firma + N giorni) e saldo (inizio evento − M giorni), da *Impostazioni segreteria*.
- **Reminder/solleciti** automatici via Celery beat (giorni configurati nei template; solleciti per le scadute). Per le scadenze di **pagamento** il tono delle email è volutamente cortese («forse avete già provveduto e non abbiamo ancora registrato…»); per i materiali resta diretto.
- **Azione "Sposta scadenze"** (admin Scadenze): seleziona più scadenze e spostale **di N giorni** (anche negativi) o **a una data fissa** in un colpo solo — per proroghe concesse o cambio data evento.
- Registrare un incasso **riconcilia** le scadenze di pagamento coperte (vanno in *Ricevuto* = "Pagato" per il cliente) e **ferma i loro reminder**; le altre scadenze continuano il loro ciclo normalmente.
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
| `riallinea_lingua_righe [--dry-run]` | ri-traduce nella lingua del contratto le righe dei preventivi NON confermati (nomi/descrizioni servizio, etichetta stand) |
| `compilemessages` | compila le traduzioni EN (.po → .mo) |

---

## 14. VARIABILI DI CONFIGURAZIONE (.env)

Obbligatorie: `SECRET_KEY`, `DB_PASSWORD`, `ALLOWED_HOSTS`, `SITE_ADDRESS`.
Funzionalità (se mancano, la feature non va):
- `DEEPL_API_KEY` → traduzioni automatiche IT→EN.
- `BANK_TRANSFER_HOLDER/_BANK/_IBAN/_BIC` → dati del bonifico al checkout (senza, compaiono i placeholder "DA CONFIGURARE").
- `EMAIL_*` → invio email reali (senza, vanno in console).
- `PAYPAL_MODE/_CLIENT_ID/_CLIENT_SECRET/_WEBHOOK_ID` → pagamenti PayPal (**in produzione: `live` con le chiavi dell'app "Sponsor Manager"** — cambiare i valori nel `.env` e ricreare i container).
- `SUPPORT_EMAIL` (default `helpdesk@valet.it`) → email di assistenza mostrata ai clienti (portale, email, PDF).
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
| Menu admin invisibile su **mobile** | Django nasconde la sidebar sotto 767px | usare l'**hamburger ☰** in alto a sinistra (dal 8/7/2026 il pannello si apre per intero) |
| Il cliente **non riesce a confermare** il preventivo | anagrafica incompleta (incl. Codice SIS farmaceutiche) o **firmatario mancante** | il cliente completa «I miei dati» (torna da solo alla conferma); il firmatario lo registra l'operatore sul contatto |
| **Email di conferma senza allegato** / contratto assente in area riservata | (risolto) generazione fallita per firmatario mancante | oggi la conferma è bloccata prima dal gate; registrare il firmatario e far riconfermare |
| Preventivo **EN con voci in italiano** | righe fotografate nella lingua sbagliata (storico) | cambiare lingua del contratto le ri-traduce; in blocco: `riallinea_lingua_righe --dry-run` poi senza flag |
| **Impossibile eliminare** un contratto principale | contratti figli ancora **attivi** (quelli nel cestino e i pagamenti non bloccano più) | cestinare prima i figli attivi, poi il principale |
| Download admin arrivano con nome UUID senza estensione | Service Worker "fantasma" su `localhost:8000` da altro progetto | usare un'altra porta o deregistrare il SW da `chrome://serviceworker-internals` |

---

## 16. FAQ

**Posso vendere uno stand che fa parte di un blocco?** No: si vende il blocco intero.

**I prezzi cambiano nei contratti già firmati se aggiorno il listino?** No: i prezzi sono congelati (snapshot) nelle righe del contratto.

**Lo sponsor sceglie lo stand dal portale?** No: lo assegna l'operatore; lo sponsor lo vede nel dettaglio contratto.

**Come tolgo dalla lista i contratti annullati?** Comando `elimina_contratti_annullati` (anteprima, poi `--conferma`; reversibile, salvo `--hard`).

**Dove ricarico il logo che appare sui PDF/email?** *Backoffice → Impostazioni segreteria → Logo*.

**Perché il cliente non può pagare il contratto principale con carta/PayPal?** È voluto: il **contratto principale si paga solo con bonifico**. PayPal/MyBank/carta restano per i **servizi acquistati online** (carrello/addon).

**Il contratto di sponsorizzazione a chi arriva?** Alla conferma del preventivo (eventi **non-ECM**) è l'**unico documento da firmare** (riepilogo servizi come *Allegato 1*): arriva al cliente con l'email «Grazie per aver confermato il preventivo» e al **contatto operativo** con l'email dedicata, in CC ad *amministrazione@valet.it* e *morini@valet.it*. L'email spiega come restituirlo firmato (email ad amministrazione o upload nei Materiali, dove c'è la scadenza a +10 giorni con solleciti automatici).

**Come segnalo che uno sponsor è un'azienda farmaceutica?** Spunta «Azienda farmaceutica» nei *Dati fiscali* dello Sponsor (o la spunta il cliente in «I miei dati»): a quel punto il **Codice SIS** diventa obbligatorio per confermare/acquistare.

**Ho creato un nuovo servizio: devo creare anche un template email?** No. I template email sono **12 punti fissi** (× ECM/Non-ECM). I servizi non aggiungono email.

**Come personalizzo un'email solo per gli eventi ECM (o solo non-ECM)?** In *Template email* apri la riga del punto voluto per quel tipo evento, scrivi oggetto/corpo e mettila **Attivo**.

---

*Fine manuale operativo. Per la guida rapida illustrata vedi `docs/manuale_utente.html`. Per l'integrazione del modulo stand in altri sistemi vedi `SPEC-INTEGRAZIONE-STAND.md`.*
