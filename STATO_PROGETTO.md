# Stato progetto Sponsor Manager

## Cos'è
Sistema Django per gestione sponsor congressi (VALET S.r.l.).
Backoffice admin + portale self-service sponsor con ecommerce, contratti PDF, email automatiche.
Stack: Django 5.1, PostgreSQL, Redis, Celery, PayPal. Gira in WSL2/Ubuntu.
Path progetto: ~/progetti/sponsor_manager

## Lavoro fatto sessione 1 (2026-05-20 mattina) — commit fino a 521c373
1. Race condition carrello (select_for_update in cart.py)
2. Bug ContractKind.STANDARD -> MAIN
3. admin.py corrotto ricostruito
4. urls.py rotta cart_checkout ricomposta
5. Recuperata migrazione portal/0001_initial (wishlist)
6. Email recovery non partiva in produzione (scheduled.py)
7. Rimossi campi billing inesistenti da creazione Contract

## Lavoro fatto sessione 2 (2026-05-20 sera) — commit fino a df78bd1
8. DB RIALLINEATO: rimosse colonne fantasma (dumpdata->drop schema->migrate->loaddata).
   Schema ora pulito e allineato al codice. Dati preservati (38 record).
9. Migrazione wishlist 0002_alter_wishlist_user generata e applicata.
10. FIX BUG JSON snapshot ContractLine: usa service.translated('name')
    invece del JSONField grezzo (commit a940cca).
11. FIX template email non trovati: aggiunto BASE_DIR ai TEMPLATES['DIRS']
    in config/settings/base.py (commit df78bd1).

## TEST END-TO-END RIUSCITO
Flusso completo verificato: crea carrello ADDON -> aggiungi articolo ->
CartSession -> task check_abandoned_carts -> email recovery inviata (console).
Tutto funziona insieme.

## Problemi ANCORA APERTI (da fare)
1. BUG LATENTE contract_number: campo unique=True ma NON auto-generato per
   contratti ADDON (carrelli). Restano con number=''. Primo carrello ok,
   secondo crasha per collisione unicità. Serve logica di numerazione addon
   (es. nel save() del Contract o in cart.py). PRIORITARIO prima della produzione.
2. Valutare se i template email vanno spostati in templates/ (soluzione più
   ortodossa) invece di aggiungere BASE_DIR ai DIRS. Funziona ma è un filo insolito.

## Dati di test nel DB
Sponsor "gloriamed", evento "International HIFU Days".
Contratto MAIN attivo id: a1cbf214-7eee-48b6-b1c9-f2b910c05c7e
Contatto con email: ammazzucchi@gloria.it
Servizi: 9 (es. FARETTO_LED). Backup DB: ~/backup_pre_riallineamento_*.sql

## Note pratiche
- Terminale WSL: incollare blocchi lunghi li accavalla. Usare file + echo riga per riga,
  o cat con heredoc, MAI incollare l'output/prompt insieme ai comandi nella shell.
- grep -n dà numeri riga affidabili; attenzione a sed -i con pattern ambigui.
- python manage.py shell < file.py per eseguire script. Settings dev: CELERY_TASK_ALWAYS_EAGER=True, email su console.
