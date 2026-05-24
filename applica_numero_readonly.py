#!/usr/bin/env python3
"""
Rende 'contract_number' un campo in SOLA LETTURA nell'admin del contratto,
cosi' l'admin non lo chiede piu' come obbligatorio e lascia che venga generato
automaticamente dal save() del modello (formato SIGLA-AA-NNN).

Aggiunge anche un piccolo metodo che, sui contratti NUOVI (non ancora salvati),
mostra "(generato al salvataggio)" invece di un campo vuoto.

Backup di contracts/admin.py (.bak_ctnum). Idempotente.

Lancialo dalla cartella del progetto:
    python applica_numero_readonly.py
"""
import sys
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ADMIN = ROOT / "contracts" / "admin.py"
BACKUP = str(ADMIN) + ".bak_ctnum"


def fail(msg):
    print(f"\n[X] ERRORE: {msg}")
    print("    Nessuna modifica applicata.")
    sys.exit(1)


if not ADMIN.exists():
    fail(f"Non trovo {ADMIN}.")

src = ADMIN.read_text(encoding="utf-8")

if "contract_number_display" in src:
    print("[OK] Modifica gia' presente (salto).")
    sys.exit(0)

# 1. Nel fieldset, sostituisco 'contract_number' con il metodo display
old_fs = "'fields': ('contract_number', 'event', 'sponsor', 'sponsor_signer_contact'),"
new_fs = "'fields': ('contract_number_display', 'event', 'sponsor', 'sponsor_signer_contact'),"
if old_fs not in src:
    fail("Non trovo il fieldset con contract_number atteso in contracts/admin.py.")
src = src.replace(old_fs, new_fs, 1)

# 2. Aggiungo contract_number_display ai readonly_fields
old_ro = (
    "    readonly_fields = (\n"
    "        'created_at', 'updated_at',\n"
    "        'subtotal', 'vat_amount', 'total',\n"
    "        'sent_date', 'cancelled_date',\n"
    "    )"
)
new_ro = (
    "    readonly_fields = (\n"
    "        'contract_number_display',\n"
    "        'created_at', 'updated_at',\n"
    "        'subtotal', 'vat_amount', 'total',\n"
    "        'sent_date', 'cancelled_date',\n"
    "    )"
)
if old_ro not in src:
    fail("Non trovo il blocco readonly_fields atteso in contracts/admin.py.")
src = src.replace(old_ro, new_ro, 1)

# 3. Aggiungo il metodo display dentro la classe ContractAdmin.
#    Lo inserisco subito dopo la riga 'class ContractAdmin(admin.ModelAdmin):'
anchor = "class ContractAdmin(admin.ModelAdmin):\n"
if anchor not in src:
    fail("Non trovo 'class ContractAdmin' in contracts/admin.py.")

method = (
    anchor +
    '    @admin.display(description="Numero contratto")\n'
    '    def contract_number_display(self, obj):\n'
    '        # Mostra il numero; sui nuovi (non salvati) avvisa che e automatico\n'
    '        if obj and obj.pk and obj.contract_number:\n'
    '            return obj.contract_number\n'
    '        return "(generato automaticamente al salvataggio)"\n'
    '\n'
)
src = src.replace(anchor, method, 1)

shutil.copy2(ADMIN, BACKUP)
ADMIN.write_text(src, encoding="utf-8")
print(f"[OK] contracts/admin.py aggiornato (backup: {BACKUP})")
print("\n=== FATTO. Ricarica la pagina 'Aggiungi contratto'. ===")
print("Il numero non sara' piu' richiesto: appare '(generato automaticamente)'")
print("e verra' creato al salvataggio nel formato SIGLA-AA-NNN.")
