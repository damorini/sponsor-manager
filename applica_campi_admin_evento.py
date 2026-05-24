#!/usr/bin/env python3
"""
Rende visibili nell'admin dell'evento alcuni campi che esistono nel modello
ma non erano nel fieldset:
  - scientific_director (Responsabile scientifico) -> per i contratti
  - venue_address (Indirizzo sede)
  - ecm_id (ID Provider ECM)

Li aggiunge alla sezione "Dati per contratti" e "Date e luogo".
Backup di events/admin.py (.bak_campiadmin). Idempotente.

Lancialo dalla cartella del progetto:
    python applica_campi_admin_evento.py
"""
import sys
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ADMIN = ROOT / "events" / "admin.py"
BACKUP = str(ADMIN) + ".bak_campiadmin"


def fail(msg):
    print(f"\n[X] ERRORE: {msg}")
    print("    Nessuna modifica applicata.")
    sys.exit(1)


if not ADMIN.exists():
    fail(f"Non trovo {ADMIN}.")

src = ADMIN.read_text(encoding="utf-8")

if "scientific_director" in src:
    print("[OK] I campi sembrano gia' presenti nell'admin (salto).")
    sys.exit(0)

# 1. Aggiungo venue_address a "Date e luogo"
old1 = "            'fields': ('start_date', 'end_date', 'location'),"
new1 = "            'fields': ('start_date', 'end_date', 'location', 'venue_address'),"
if old1 not in src:
    fail("Non trovo il fieldset 'Date e luogo'.")
src = src.replace(old1, new1, 1)

# 2. Aggiungo scientific_director e ecm_id a "Dati per contratti"
old2 = "            'fields': ('organizer_legal_name', 'contract_signing_location'),"
new2 = ("            'fields': ('scientific_director', 'ecm_id', "
        "'organizer_legal_name', 'contract_signing_location'),")
if old2 not in src:
    fail("Non trovo il fieldset 'Dati per contratti'.")
src = src.replace(old2, new2, 1)

shutil.copy2(ADMIN, BACKUP)
ADMIN.write_text(src, encoding="utf-8")
print(f"[OK] events/admin.py aggiornato (backup: {BACKUP})")
print("\n=== FATTO. Ricarica la pagina dell'evento nell'admin. ===")
print("Troverai 'Responsabile scientifico' nella sezione 'Dati per contratti'")
print("(potrebbe essere una sezione richiudibile: cliccaci sopra per aprirla).")
