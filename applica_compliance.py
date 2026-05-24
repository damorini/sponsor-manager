#!/usr/bin/env python3
"""
Sposta la gestione AIFA / MEDTECH-SVC dal livello SPONSOR al livello CONTRATTO
(la richiesta dipende dall'evento, non e' fissa dell'azienda) e aggiunge i
numeri di riferimento sull'EVENTO (solo archivio).

Modifiche:
  1. sponsors/models.py -> RIMUOVE requires_aifa e requires_svc_medtech.
  2. sponsors/admin.py   -> rimuove ogni riferimento a quei campi
     (list_display, list_filter, fieldset, funzione compliance_badges).
  3. contracts/models.py -> AGGIUNGE requires_aifa e requires_svc_medtech
     (flag per-contratto, etichette chiare).
  4. contracts/admin.py  -> mostra i due flag nell'admin del contratto.
  5. events/models.py    -> AGGIUNGE aifa_reference e medtech_svc_reference
     (campi testo, archivio).
  6. events/admin.py     -> mostra i due reference in "Dati per contratti".

Backup di ogni file (.bak_compliance). Idempotente. Si ferma se un punto
atteso non viene trovato (senza modifiche parziali pericolose: i file gia'
scritti restano, ma vedrai dove si e' fermato).

DOPO: migrazioni
    python manage.py makemigrations sponsors contracts events
    python manage.py migrate

Lancialo dalla cartella del progetto:
    python applica_compliance.py
"""
import sys
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SP_MODELS = ROOT / "sponsors" / "models.py"
SP_ADMIN = ROOT / "sponsors" / "admin.py"
CT_MODELS = ROOT / "contracts" / "models.py"
CT_ADMIN = ROOT / "contracts" / "admin.py"
EV_MODELS = ROOT / "events" / "models.py"
EV_ADMIN = ROOT / "events" / "admin.py"
SUFFIX = ".bak_compliance"


def fail(msg):
    print(f"\n[X] ERRORE: {msg}")
    print("    Mi fermo. Controlla ed eventualmente ripristina dai .bak_compliance.")
    sys.exit(1)


def backup_write(path, content):
    shutil.copy2(path, str(path) + SUFFIX)
    path.write_text(content, encoding="utf-8")
    print(f"[OK] {path.relative_to(ROOT)} aggiornato")


for p in (SP_MODELS, SP_ADMIN, CT_MODELS, CT_ADMIN, EV_MODELS, EV_ADMIN):
    if not p.exists():
        fail(f"Non trovo {p}.")

# idempotenza globale
ct_models_src = CT_MODELS.read_text(encoding="utf-8")
if "requires_aifa" in ct_models_src:
    print("[OK] I flag risultano gia' sul contratto (salto tutto).")
    sys.exit(0)

# ===========================================================================
# 1. SPONSOR models — rimuovo i due flag
# ===========================================================================
src = SP_MODELS.read_text(encoding="utf-8")
block = (
    '\n    # Compliance\n'
    '    requires_aifa = models.BooleanField(\n'
    '        default=False,\n'
    '        verbose_name="Richiede AIFA",\n'
    '    )\n'
    '    requires_svc_medtech = models.BooleanField(\n'
    '        default=False,\n'
    '        verbose_name="Richiede SVC MedTech",\n'
    '    )\n'
)
if block not in src:
    fail("Non trovo il blocco flag atteso in sponsors/models.py.")
backup_write(SP_MODELS, src.replace(block, "\n", 1))

# ===========================================================================
# 2. SPONSOR admin — rimuovo tutti i riferimenti
# ===========================================================================
src = SP_ADMIN.read_text(encoding="utf-8")

# 2a. list_display: rimuovo ', compliance_badges'
src = src.replace("'industry', 'compliance_badges',", "'industry',")
src = src.replace(", 'compliance_badges'", "")
src = src.replace("'compliance_badges', ", "")

# 2b. list_filter: rimuovo i due campi
src = src.replace(
    "'industry', 'requires_aifa', 'requires_svc_medtech', 'address_country',",
    "'industry', 'address_country',"
)

# 2c. fieldset Compliance intero
fs_compliance = (
    "        ('Compliance', {\n"
    "            'fields': ('requires_aifa', 'requires_svc_medtech'),\n"
    "        }),\n"
)
if fs_compliance in src:
    src = src.replace(fs_compliance, "")
else:
    fail("Non trovo il fieldset 'Compliance' in sponsors/admin.py.")

# 2d. funzione compliance_badges
func_badges = (
    "    @admin.display(description='Compliance')\n"
    "    def compliance_badges(self, obj):\n"
    "        badges = []\n"
    "        if obj.requires_aifa:\n"
    "            badges.append('<span style=\"background:#ba2121; color:white; padding:1px 6px; '\n"
    "                          'border-radius:3px; font-size:0.75em;\">AIFA</span>')\n"
    "        if obj.requires_svc_medtech:\n"
    "            badges.append('<span style=\"background:#e6a23c; color:white; padding:1px 6px; '\n"
    "                          'border-radius:3px; font-size:0.75em;\">MedTech</span>')\n"
    "        return format_html(' '.join(badges)) if badges else '\u2014'\n"
    "\n"
)
if func_badges in src:
    src = src.replace(func_badges, "")
else:
    fail("Non trovo la funzione compliance_badges in sponsors/admin.py.")

backup_write(SP_ADMIN, src)

# ===========================================================================
# 3. CONTRACT models — aggiungo i due flag (dopo vat_exemption_reason o
#    comunque dopo 'special_clauses' che e' un buon ancoraggio testuale)
# ===========================================================================
src = CT_MODELS.read_text(encoding="utf-8")
anchor = '    special_clauses = models.TextField(blank=True, verbose_name="Clausole speciali")\n'
if anchor not in src:
    fail("Non trovo 'special_clauses' in contracts/models.py.")
flags = (
    anchor +
    '\n'
    '    # Compliance regolatoria (dipende da evento+sponsor, quindi per-contratto)\n'
    '    requires_aifa = models.BooleanField(\n'
    '        default=False,\n'
    '        verbose_name="Richiede AIFA (per questo evento)",\n'
    '    )\n'
    '    requires_svc_medtech = models.BooleanField(\n'
    '        default=False,\n'
    '        verbose_name="Richiede MEDTECH/SVC (per questo evento)",\n'
    '    )\n'
)
backup_write(CT_MODELS, src.replace(anchor, flags, 1))

# ===========================================================================
# 4. CONTRACT admin — mostro i flag
# ===========================================================================
src = CT_ADMIN.read_text(encoding="utf-8")
# Provo ad agganciarmi a un fieldset esistente con 'special_clauses' o 'internal_notes'
added = False
for key in ("'special_clauses'", "'internal_notes'"):
    if key in src:
        src = src.replace(key, key + ", 'requires_aifa', 'requires_svc_medtech'", 1)
        added = True
        break
if not added:
    # fallback: provo a metterli in list_display se esiste
    if "list_display" in src:
        print("[..] Non ho trovato un fieldset adatto in contracts/admin.py: "
              "i flag esistono ma potresti doverli aggiungere a mano all'admin.")
    else:
        print("[..] contracts/admin.py: non ho trovato dove mostrare i flag; "
              "esistono comunque nel modello.")
backup_write(CT_ADMIN, src)

# ===========================================================================
# 5. EVENT models — aggiungo i reference (dopo scientific_director)
# ===========================================================================
src = EV_MODELS.read_text(encoding="utf-8")
anchor = (
    '    scientific_director = models.CharField(\n'
    '        max_length=200,\n'
    '        blank=True,\n'
    '        verbose_name="Responsabile scientifico",\n'
    "        help_text=\"Nome completo, es. 'Prof. Mario Rossi'\",\n"
    '    )\n'
)
if anchor not in src:
    fail("Non trovo il campo scientific_director in events/models.py.")
refs = anchor + (
    '\n'
    '    aifa_reference = models.CharField(\n'
    '        max_length=100,\n'
    '        blank=True,\n'
    '        verbose_name="Numero riferimento AIFA",\n'
    '        help_text="Solo per archivio/consultazione interna.",\n'
    '    )\n'
    '    medtech_svc_reference = models.CharField(\n'
    '        max_length=100,\n'
    '        blank=True,\n'
    '        verbose_name="Numero riferimento MEDTECH/SVC",\n'
    '        help_text="Solo per archivio/consultazione interna.",\n'
    '    )\n'
)
backup_write(EV_MODELS, src.replace(anchor, refs, 1))

# ===========================================================================
# 6. EVENT admin — mostro i reference in "Dati per contratti"
# ===========================================================================
src = EV_ADMIN.read_text(encoding="utf-8")
old = ("            'fields': ('scientific_director', 'ecm_id', "
       "'organizer_legal_name', 'contract_signing_location'),")
if old not in src:
    fail("Non trovo il fieldset 'Dati per contratti' aggiornato in events/admin.py "
         "(hai applicato lo script dei campi admin evento?).")
new = ("            'fields': ('scientific_director', 'ecm_id', "
       "'aifa_reference', 'medtech_svc_reference', "
       "'organizer_legal_name', 'contract_signing_location'),")
backup_write(EV_ADMIN, src.replace(old, new, 1))

print("\n=== CODICE APPLICATO (6 file). ===")
print("Ora le MIGRAZIONI:")
print("    python manage.py makemigrations sponsors contracts events")
print("    python manage.py migrate")
