# -*- coding: utf-8 -*-
"""ONE-OFF (manage.py shell): porta in MAIUSCOLO i nomi gia' esistenti
(Sponsor: ragione sociale + nome commerciale; Contatti: nome completo).
Prima anteprima; scrive solo con APPLICA=True. Non elimina nulla, ripetibile."""

APPLICA = False   # <-- metti True e rilancia per applicare davvero

from sponsors.models import Sponsor, Contact

ns = 0
print("=== SPONSOR ===")
for s in Sponsor.objects.all():
    nl = (s.legal_name or '').upper()
    nd = (s.display_name or '').upper()
    if nl != (s.legal_name or '') or nd != (s.display_name or ''):
        print(f"  {s.legal_name!r} -> {nl!r}")
        if APPLICA:
            s.legal_name = nl
            s.display_name = nd
            s.save()
        ns += 1

nc = 0
print("=== CONTATTI ===")
for c in Contact.objects.all():
    nf = (c.full_name or '').upper()
    if nf != (c.full_name or ''):
        print(f"  {c.full_name!r} -> {nf!r}")
        if APPLICA:
            c.full_name = nf
            c.save()
        nc += 1

print(f"Sponsor da aggiornare: {ns} | Contatti da aggiornare: {nc}")
if APPLICA:
    print(">>> Applicato.")
else:
    print(">>> ANTEPRIMA: nessuna modifica. Metti APPLICA=True e rilancia.")
