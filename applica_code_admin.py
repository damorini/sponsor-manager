#!/usr/bin/env python3
"""
Aggiunge il campo 'code' (Sigla evento) all'admin di Events, cosi' diventa
visibile e modificabile nella scheda dell'evento.

Fa un backup di events/admin.py prima di modificarlo (.bak_codeadmin).
Se non trova il punto atteso, si ferma senza toccare nulla.

Lancialo dalla cartella del progetto:
    python applica_code_admin.py
"""
import sys
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ADMIN = ROOT / "events" / "admin.py"
BACKUP = str(ADMIN) + ".bak_codeadmin"


def fail(msg):
    print(f"\n[X] ERRORE: {msg}")
    print("    Nessuna modifica applicata.")
    sys.exit(1)


if not ADMIN.exists():
    fail(f"Non trovo {ADMIN}. Lancia dalla cartella del progetto.")

src = ADMIN.read_text(encoding="utf-8")

# idempotenza
if "'slug', 'code'" in src or '"slug", "code"' in src:
    print("[OK] Il campo 'code' sembra gia' presente nel fieldset (salto).")
    sys.exit(0)

old = "'fields': ('slug', 'name', 'description', 'event_type', 'status'),"
new = "'fields': ('slug', 'code', 'name', 'description', 'event_type', 'status'),"

if old not in src:
    fail("Non trovo la riga 'fields' attesa nel primo fieldset. "
         "Il file e' diverso dal previsto: meglio fermarsi.")

result = src.replace(old, new, 1)
if result == src:
    fail("Sostituzione non riuscita (nessun cambiamento).")

shutil.copy2(ADMIN, BACKUP)
ADMIN.write_text(result, encoding="utf-8")
print(f"[OK] events/admin.py aggiornato (backup: {BACKUP})")
print("\n=== FATTO. Ricarica la pagina dell'evento nell'admin. ===")
