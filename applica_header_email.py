#!/usr/bin/env python3
"""
TAPPA 1 — Header congresso nelle email.

Fa tre modifiche:
  1. events/models.py  -> aggiunge il campo `email_header_image` (FileField).
  2. events/admin.py    -> rende il campo visibile nel fieldset.
  3. shared/email_templates/base/email_base.html
                         -> mostra l'header dell'evento a tutta larghezza,
                            sopra l'header brand esistente, se presente.

Backup di ogni file toccato (.bak_header). Se non trova un punto atteso,
si ferma SENZA modificare nulla.

DOPO lo script servira' la migrazione (te la guido io):
    python manage.py makemigrations events
    python manage.py migrate events

Lancialo dalla cartella del progetto:
    python applica_header_email.py
"""
import sys
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODELS = ROOT / "events" / "models.py"
ADMIN = ROOT / "events" / "admin.py"
BASE = ROOT / "shared" / "email_templates" / "base" / "email_base.html"

SUFFIX = ".bak_header"


def fail(msg):
    print(f"\n[X] ERRORE: {msg}")
    print("    Nessuna modifica applicata (i file gia' salvati restano, "
          "ma lo script si ferma qui).")
    sys.exit(1)


for p in (MODELS, ADMIN, BASE):
    if not p.exists():
        fail(f"Non trovo {p}. Lancia dalla cartella del progetto.")

models_src = MODELS.read_text(encoding="utf-8")
admin_src = ADMIN.read_text(encoding="utf-8")
base_src = BASE.read_text(encoding="utf-8")

# ---------------------------------------------------------------------------
# 1. MODELLO — campo email_header_image dopo il blocco `code`
# ---------------------------------------------------------------------------
if "email_header_image" in models_src:
    print("[OK] Campo email_header_image gia' presente nel modello (salto).")
else:
    code_block = (
        '    code = models.CharField(\n'
        '        max_length=12,\n'
        '        blank=True,\n'
        '        verbose_name="Sigla evento",\n'
        '        help_text="Sigla breve per i numeri di contratto, es. \'HIFU\'. "\n'
        '                  "Se vuota, viene generata automaticamente.",\n'
        '    )\n'
    )
    if code_block not in models_src:
        fail("Non trovo il blocco 'code' atteso in events/models.py.")

    header_field = (
        '    email_header_image = models.FileField(\n'
        "        upload_to='events/email_headers/',\n"
        '        null=True,\n'
        '        blank=True,\n'
        '        verbose_name="Header email congresso",\n'
        '        help_text="Immagine mostrata in cima alle email di questo evento, '
        'a tutta larghezza (max 600px). Consigliato PNG/JPG.",\n'
        '    )\n'
    )
    new_models = models_src.replace(code_block, code_block + "\n" + header_field, 1)
    if new_models == models_src:
        fail("Sostituzione nel modello non riuscita.")
    shutil.copy2(MODELS, str(MODELS) + SUFFIX)
    MODELS.write_text(new_models, encoding="utf-8")
    print(f"[OK] events/models.py aggiornato (backup: events/models.py{SUFFIX})")

# ---------------------------------------------------------------------------
# 2. ADMIN — aggiunge email_header_image al fieldset
# ---------------------------------------------------------------------------
if "email_header_image" in admin_src:
    print("[OK] Campo email_header_image gia' presente nell'admin (salto).")
else:
    old_fs = "'fields': ('slug', 'code', 'name', 'description', 'event_type', 'status'),"
    new_fs = ("'fields': ('slug', 'code', 'email_header_image', 'name', "
              "'description', 'event_type', 'status'),")
    if old_fs not in admin_src:
        fail("Non trovo la riga 'fields' attesa in events/admin.py "
             "(forse il campo 'code' non era stato aggiunto?).")
    new_admin = admin_src.replace(old_fs, new_fs, 1)
    shutil.copy2(ADMIN, str(ADMIN) + SUFFIX)
    ADMIN.write_text(new_admin, encoding="utf-8")
    print(f"[OK] events/admin.py aggiornato (backup: events/admin.py{SUFFIX})")

# ---------------------------------------------------------------------------
# 3. TEMPLATE BASE — header evento a tutta larghezza, sopra il brand header
# ---------------------------------------------------------------------------
if "email_header_image" in base_src:
    print("[OK] Header evento gia' presente nel template base (salto).")
else:
    anchor = '        <!-- HEADER con logo/brand -->\n'
    if anchor not in base_src:
        fail("Non trovo il commento '<!-- HEADER con logo/brand -->' nel template base.")

    event_header = (
        '        <!-- HEADER CONGRESSO (immagine a tutta larghezza, per-evento) -->\n'
        '        {% if event and event.email_header_image %}\n'
        '        <tr>\n'
        '          <td style="padding:0; font-size:0; line-height:0;">\n'
        '            <img src="{{ site_url }}{{ event.email_header_image.url }}"\n'
        '                 alt="{{ event_name|default:\'\' }}"\n'
        '                 width="600"\n'
        '                 style="display:block; width:100%; max-width:600px; height:auto;">\n'
        '          </td>\n'
        '        </tr>\n'
        '        {% endif %}\n'
        '\n'
    )
    new_base = base_src.replace(anchor, event_header + anchor, 1)
    if new_base == base_src:
        fail("Inserimento nel template base non riuscito.")
    shutil.copy2(BASE, str(BASE) + SUFFIX)
    BASE.write_text(new_base, encoding="utf-8")
    print(f"[OK] email_base.html aggiornato (backup: email_base.html{SUFFIX})")

# ---------------------------------------------------------------------------
# 4. EMAIL_SENDER — espone site_url nel contesto comune
# ---------------------------------------------------------------------------
SENDER = ROOT / "contracts" / "services" / "email_sender.py"
if not SENDER.exists():
    fail(f"Non trovo {SENDER}.")
sender_src = SENDER.read_text(encoding="utf-8")
if "'site_url'" in sender_src:
    print("[OK] site_url gia' presente in email_sender.py (salto).")
else:
    old_line = "        'brand_logo_url': getattr(settings, 'BRAND_LOGO_URL', ''),"
    new_lines = ("        'site_url': getattr(settings, 'SITE_URL', '').rstrip('/'),\n"
                 "        'brand_logo_url': getattr(settings, 'BRAND_LOGO_URL', ''),")
    if old_line not in sender_src:
        fail("Non trovo la riga 'brand_logo_url' attesa in email_sender.py.")
    new_sender = sender_src.replace(old_line, new_lines, 1)
    shutil.copy2(SENDER, str(SENDER) + SUFFIX)
    SENDER.write_text(new_sender, encoding="utf-8")
    print(f"[OK] email_sender.py aggiornato (backup: email_sender.py{SUFFIX})")

print("\n=== CODICE APPLICATO (4 file). ===")
print("Manca solo la migrazione DB. Te la guido io adesso nella chat.")
