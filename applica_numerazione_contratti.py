#!/usr/bin/env python3
"""
Applica la nuova numerazione contratti formato SIGLA-AA-NNN (es. HIFU-26-001).

Cosa fa:
  1. Aggiunge il campo `code` (sigla evento) al modello Event.
  2. Sostituisce _generate_contract_number() nel modello Contract con la
     versione che produce SIGLA-AA-NNN, progressivo per-evento per-anno.

Fa un BACKUP di ogni file prima di toccarlo (estensione .bak_numerazione).
Se qualcosa non torna, si ferma SENZA aver modificato nulla.

Lancialo dalla cartella del progetto:
    python applica_numerazione_contratti.py
"""
import re
import sys
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EVENTS = ROOT / "events" / "models.py"
CONTRACTS = ROOT / "contracts" / "models.py"

BACKUP_SUFFIX = ".bak_numerazione"


def fail(msg):
    print(f"\n[X] ERRORE: {msg}")
    print("    Nessuna modifica applicata. Tutto invariato.")
    sys.exit(1)


def ok(msg):
    print(f"[OK] {msg}")


# ---------------------------------------------------------------------------
# Controlli preliminari
# ---------------------------------------------------------------------------
if not EVENTS.exists():
    fail(f"Non trovo {EVENTS}. Lancia lo script dalla cartella del progetto.")
if not CONTRACTS.exists():
    fail(f"Non trovo {CONTRACTS}. Lancia lo script dalla cartella del progetto.")

events_src = EVENTS.read_text(encoding="utf-8")
contracts_src = CONTRACTS.read_text(encoding="utf-8")

# Idempotenza: se gia' applicato, non rifare
if "Sigla evento" in events_src and "code = models.CharField" in events_src:
    ok("Il campo 'code' sembra gia' presente in events/models.py (salto).")
    events_already = True
else:
    events_already = False

if "SIGLA-AA-NNN" in contracts_src or 'getattr(self.event, \'code\'' in contracts_src:
    ok("Il nuovo generatore sembra gia' presente in contracts/models.py (salto).")
    contracts_already = True
else:
    contracts_already = False

if events_already and contracts_already:
    print("\nTutto gia' applicato. Niente da fare.")
    sys.exit(0)


# ---------------------------------------------------------------------------
# MODIFICA 1 — campo `code` in events/models.py, dopo il blocco slug
# ---------------------------------------------------------------------------
if not events_already:
    # Ancora: la fine del blocco slug = la riga che chiude lo SlugField.
    slug_block = (
        '    slug = models.SlugField(\n'
        '        max_length=100,\n'
        '        unique=True,\n'
        '        verbose_name="Slug",\n'
        '        help_text="Identificatore breve per URL, es. \'ferrara-cardio-2026\'",\n'
        '    )\n'
    )
    if slug_block not in events_src:
        fail("Non trovo il blocco 'slug' atteso in events/models.py. "
             "Il file e' diverso da quello previsto: meglio fermarsi.")

    code_field = (
        '    code = models.CharField(\n'
        '        max_length=12,\n'
        '        blank=True,\n'
        '        verbose_name="Sigla evento",\n'
        '        help_text="Sigla breve per i numeri di contratto, es. \'HIFU\'. "\n'
        '                  "Se vuota, viene generata automaticamente.",\n'
        '    )\n'
    )
    new_events = events_src.replace(slug_block, slug_block + "\n" + code_field, 1)
    if new_events == events_src:
        fail("Sostituzione in events/models.py non riuscita (nessun cambiamento).")

    shutil.copy2(EVENTS, str(EVENTS) + BACKUP_SUFFIX)
    EVENTS.write_text(new_events, encoding="utf-8")
    ok(f"events/models.py aggiornato (backup: events/models.py{BACKUP_SUFFIX})")


# ---------------------------------------------------------------------------
# MODIFICA 2 — nuovo _generate_contract_number in contracts/models.py
# ---------------------------------------------------------------------------
if not contracts_already:
    old_method = (
        '    def _generate_contract_number(self):\n'
        '        from datetime import date\n'
        '        anno = date.today().year\n'
        '        prefix = f"{anno}-N"\n'
        '        with transaction.atomic():\n'
        '            ultimo = (\n'
        '                Contract.all_objects\n'
        '                .filter(contract_number__startswith=prefix)\n'
        '                .order_by(\'-contract_number\')\n'
        '                .values_list(\'contract_number\', flat=True)\n'
        '                .first()\n'
        '            )\n'
        '            if ultimo:\n'
        '                try:\n'
        '                    n = int(ultimo.split(\'-N\')[1]) + 1\n'
        '                except (IndexError, ValueError):\n'
        '                    n = 1\n'
        '            else:\n'
        '                n = 1\n'
        '            while True:\n'
        '                candidato = f"{prefix}{n:04d}"\n'
        '                if not Contract.all_objects.filter(contract_number=candidato).exists():\n'
        '                    return candidato\n'
        '                n += 1\n'
    )
    if old_method not in contracts_src:
        fail("Non trovo il metodo _generate_contract_number atteso in "
             "contracts/models.py. Il file e' diverso dal previsto: meglio fermarsi.")

    new_method = (
        '    def _generate_contract_number(self):\n'
        '        """Genera il numero contratto formato SIGLA-AA-NNN (es. HIFU-26-001).\n'
        '\n'
        '        - SIGLA: event.code (maiuscolo). Se vuota, fallback dallo slug.\n'
        '        - AA: ultime 2 cifre dell\'anno dell\'evento.\n'
        '        - NNN: progressivo a 3 cifre, riparte da 1 per ogni evento/anno.\n'
        '          Oltre 999 passa a 4 cifre automaticamente.\n'
        '        """\n'
        '        from datetime import date\n'
        '\n'
        '        sigla = (getattr(self.event, \'code\', \'\') or \'\').strip().upper()\n'
        '        if not sigla:\n'
        '            base = (self.event.slug or \'EV\').replace(\'-\', \'\')\n'
        '            sigla = base[:4].upper() or \'EV\'\n'
        '\n'
        '        anno_full = self.event.start_date.year if self.event.start_date else date.today().year\n'
        '        anno = f"{anno_full % 100:02d}"\n'
        '\n'
        '        prefix = f"{sigla}-{anno}-"\n'
        '\n'
        '        with transaction.atomic():\n'
        '            ultimo = (\n'
        '                Contract.all_objects\n'
        '                .filter(event=self.event, contract_number__startswith=prefix)\n'
        '                .order_by(\'-contract_number\')\n'
        '                .values_list(\'contract_number\', flat=True)\n'
        '                .first()\n'
        '            )\n'
        '            if ultimo:\n'
        '                try:\n'
        '                    n = int(ultimo.rsplit(\'-\', 1)[1]) + 1\n'
        '                except (IndexError, ValueError):\n'
        '                    n = 1\n'
        '            else:\n'
        '                n = 1\n'
        '            while True:\n'
        '                candidato = f"{prefix}{n:03d}"\n'
        '                if not Contract.all_objects.filter(contract_number=candidato).exists():\n'
        '                    return candidato\n'
        '                n += 1\n'
    )
    new_contracts = contracts_src.replace(old_method, new_method, 1)
    if new_contracts == contracts_src:
        fail("Sostituzione in contracts/models.py non riuscita (nessun cambiamento).")

    shutil.copy2(CONTRACTS, str(CONTRACTS) + BACKUP_SUFFIX)
    CONTRACTS.write_text(new_contracts, encoding="utf-8")
    ok(f"contracts/models.py aggiornato (backup: contracts/models.py{BACKUP_SUFFIX})")


print("\n=== FATTO. Modifiche al codice applicate. ===")
print("Prossimo passo (te lo guido io): creare e applicare la migrazione DB.")
