# -*- coding: utf-8 -*-
"""
Fix: rimuove le assegnazioni a d.days_remaining / d.is_overdue (che nel
modello sono property in sola lettura). Il template usa direttamente le
property del modello, quindi i valori restano corretti.
Sistema sia la pagina scadenze-per-evento sia quella per-contratto.
"""
import shutil, datetime
STAMP = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
path = "portal/views/materials.py"
shutil.copy2(path, f"{path}.bak_{STAMP}")
s = open(path, encoding='utf-8').read()

block = (
    "        if d.due_date >= today:\n"
    "            d.days_remaining = (d.due_date - today).days\n"
    "            d.is_overdue = False\n"
    "        else:\n"
    "            d.days_remaining = (today - d.due_date).days\n"
    "            d.is_overdue = True\n\n"
)
n = s.count(block)
if n != 2:
    raise SystemExit(f"atteso 2 blocchi, trovati {n} - fermo per sicurezza")
s = s.replace(block, "")
open(path, 'w', encoding='utf-8').write(s)
print(f"rimossi {n} blocchi. OK")
