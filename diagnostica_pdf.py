#!/usr/bin/env python3
"""
DIAGNOSTICA — non modifica NULLA. Controlla solo cosa e' disponibile
nell'ambiente per la generazione PDF con header/footer.

Lancialo dalla cartella del progetto:
    python diagnostica_pdf.py
"""
import shutil
import subprocess
import sys

print("=" * 60)
print("DIAGNOSTICA AMBIENTE PDF — nessuna modifica ai file")
print("=" * 60)

# 1. python-docx
try:
    import docx
    print(f"[OK] python-docx disponibile (v{docx.__version__})")
except Exception as e:
    print(f"[--] python-docx NON disponibile: {e}")

# 2. docxtpl
try:
    import docxtpl
    print(f"[OK] docxtpl disponibile")
except Exception as e:
    print(f"[--] docxtpl NON disponibile: {e}")

# 3. docxcompose (utile per unire/manipolare)
try:
    import docxcompose
    print(f"[OK] docxcompose disponibile")
except Exception:
    print(f"[..] docxcompose non presente (non indispensabile)")

# 4. LibreOffice (conversione docx->pdf)
lo = shutil.which("libreoffice") or shutil.which("soffice")
if lo:
    print(f"[OK] LibreOffice trovato: {lo}")
    try:
        r = subprocess.run([lo, "--version"], capture_output=True, timeout=30)
        print(f"     versione: {r.stdout.decode('utf-8','ignore').strip()[:60]}")
    except Exception as e:
        print(f"     (impossibile leggere versione: {e})")
else:
    print("[!!] LibreOffice NON trovato nel PATH — la conversione PDF "
          "potrebbe non funzionare. Verifica come gira oggi la generazione.")

# 5. Pillow (per leggere dimensioni immagini header)
try:
    import PIL
    print(f"[OK] Pillow disponibile (v{PIL.__version__})")
except Exception:
    print("[..] Pillow non presente — gestibile, calcoleremo le dimensioni "
          "in altro modo.")

# 6. Verifica template e immagini header eventi
import os
print("-" * 60)
tpl_dir = "contracts/templates_pdf"
if os.path.isdir(tpl_dir):
    for fn in os.listdir(tpl_dir):
        if fn.endswith(".docx"):
            print(f"[OK] Template presente: {fn}")
else:
    print(f"[!!] Cartella template non trovata: {tpl_dir}")

print("-" * 60)
print("Diagnostica completata. Incolla TUTTO questo output in chat.")
