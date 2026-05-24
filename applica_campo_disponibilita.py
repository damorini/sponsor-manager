#!/usr/bin/env python3
"""
Rende il campo 'total_available' (Quantità totale disponibile) VISIBILE e
modificabile nella scheda del Servizio nell'admin: lo aggiunge al fieldset
accanto a 'max_quantity'.

(Lo script precedente aveva aggiunto la colonna 'Disponibili' nella lista ma
non il campo editabile nella scheda: per questo il valore non si salvava.)

Backup di catalog/admin.py (.bak_dispfield). Idempotente.

Lancialo dalla cartella del progetto:
    python applica_campo_disponibilita.py
"""
import sys
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ADMIN = ROOT / "catalog" / "admin.py"
BACKUP = str(ADMIN) + ".bak_dispfield"


def fail(msg):
    print(f"\n[X] ERRORE: {msg}")
    print("    Nessuna modifica applicata.")
    sys.exit(1)


if not ADMIN.exists():
    fail(f"Non trovo {ADMIN}.")

src = ADMIN.read_text(encoding="utf-8")

# idempotenza: gia' nei fieldsets?
if "'max_quantity', 'total_available'" in src:
    print("[OK] total_available gia' nel fieldset (salto).")
    sys.exit(0)

old = "'fields': ('is_active', 'max_quantity', 'display_order'),"
new = "'fields': ('is_active', 'max_quantity', 'total_available', 'display_order'),"

if old not in src:
    fail("Non trovo il fieldset con 'max_quantity' atteso in catalog/admin.py.")

src = src.replace(old, new, 1)

shutil.copy2(ADMIN, BACKUP)
ADMIN.write_text(src, encoding="utf-8")
print(f"[OK] catalog/admin.py aggiornato (backup: {BACKUP})")
print("\n=== FATTO. Ricarica la scheda del servizio nell'admin. ===")
print("Troverai 'Quantità totale disponibile' accanto a 'Quantità massima'.")
