#!/usr/bin/env python3
"""
Aggiunge la pulizia automatica della sigla evento (campo 'code') nel save()
del modello Event: toglie spazi e mette in MAIUSCOLO.
Es: 'hi fu' -> 'HIFU', 'parma 2026' -> 'PARMA2026'.

Fa un backup di events/models.py (.bak_codeclean).
Se non trova il punto atteso, si ferma senza toccare nulla.

Lancialo dalla cartella del progetto:
    python applica_pulizia_sigla.py
"""
import sys
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODELS = ROOT / "events" / "models.py"
BACKUP = str(MODELS) + ".bak_codeclean"


def fail(msg):
    print(f"\n[X] ERRORE: {msg}")
    print("    Nessuna modifica applicata.")
    sys.exit(1)


if not MODELS.exists():
    fail(f"Non trovo {MODELS}. Lancia dalla cartella del progetto.")

src = MODELS.read_text(encoding="utf-8")

# idempotenza
if "Pulizia sigla evento" in src or "self.code = " in src:
    print("[OK] La pulizia della sigla sembra gia' presente (salto).")
    sys.exit(0)

# Ancora: la riga finale del save() dell'evento.
# Inseriamo la pulizia subito PRIMA di super().save(...)
old = (
    "            year = start_date.year if start_date else ''\n"
    "            self.slug = f\"{base_slug}-{year}\" if year else base_slug\n"
    "        super().save(*args, **kwargs)\n"
)

new = (
    "            year = start_date.year if start_date else ''\n"
    "            self.slug = f\"{base_slug}-{year}\" if year else base_slug\n"
    "\n"
    "        # Pulizia sigla evento: niente spazi, sempre MAIUSCOLO\n"
    "        if self.code:\n"
    "            self.code = ''.join(self.code.split()).upper()\n"
    "\n"
    "        super().save(*args, **kwargs)\n"
)

if old not in src:
    fail("Non trovo il blocco finale del save() atteso in events/models.py. "
         "Il file e' diverso dal previsto: meglio fermarsi.")

result = src.replace(old, new, 1)
if result == src:
    fail("Sostituzione non riuscita (nessun cambiamento).")

shutil.copy2(MODELS, BACKUP)
MODELS.write_text(result, encoding="utf-8")
print(f"[OK] events/models.py aggiornato (backup: {BACKUP})")
print("\n=== FATTO. La sigla verra' pulita automaticamente al salvataggio. ===")
