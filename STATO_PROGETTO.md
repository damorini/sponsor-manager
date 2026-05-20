# Stato progetto Sponsor Manager

## Cos'è
Sistema Django per gestione sponsor congressi (VALET S.r.l.).
Backoffice admin + portale self-service sponsor con ecommerce, contratti PDF, email automatiche.
Stack: Django 5.1, PostgreSQL, Redis, Celery, PayPal. Gira in WSL2/Ubuntu.
Path progetto: ~/progetti/sponsor_manager

## Lavoro fatto (sessione del 2026-05-20) — branch main, commit fino a 521c373
Risolti e committati:
1. Race condition carrello (select_for_update in portal/views/cart.py)
2. Bug ContractKind.STANDARD -> MAIN in cart.py
3. admin.py corrotto (aveva comandi terminale incollati dentro) ricostruito
4. urls.py: rotta cart_checkout spezzata, ricomposta
5. Recuperata migrazione portal/migrations/0001_initial.py (wishlist)
6. Email recovery carrello non partiva in produzione (contracts/tasks/scheduled.py)
7. Rimossi campi billing inesistenti dalla creazione Contract in cart.py
Extra: dato default DB a colonne fantasma payment_plan_mode e single_payment_days_from_signing.
Backup DB: ~/backup_sponsor_manager_20260520_135811.sql

## Problemi ANCORA APERTI (da fare)
1. BUG JSON snapshot in ContractLine.save(): salva {'en':...} (apici singoli)
   invece di JSON valido. Blocca l'aggiunta articoli al carrello. PRIORITARIO.
2. DB disallineato dal codice: ci sono colonne nel DB non presenti nel modello
   né nelle migrazioni (es. payment_plan_mode). Il DB è ricreabile.
   Andrebbe riallineato (ricreare DB dalle migrazioni + ri-seed dati test).
3. Migrazione wishlist pendente: portal/migrations/0002_alter_wishlist_user.py da generare.

## Dati di test nel DB
Sponsor "gloriamed", evento "International HIFU Days".
Contratto MAIN attivo id: a1cbf214-7eee-48b6-b1c9-f2b910c05c7e
Contatto con email: ammazzucchi@gloria.it
Servizi evento: 9 (es. FARETTO_LED)

## Note pratiche imparate
- Terminale WSL: incollare blocchi lunghi li accavalla. Meglio righe singole o file.
- python manage.py shell -c "..." per comandi rapidi senza shell interattiva.
- Settings dev: config.settings.development, CELERY_TASK_ALWAYS_EAGER=True, email su console.
