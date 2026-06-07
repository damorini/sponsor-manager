# -*- coding: utf-8 -*-
"""
Inserisce le 7 categorie servizio nel catalogo. Idempotente (per codice).
Richiede che il catalogo sia gia' migrato (applica_catalogo_servizi.py + migrate).
USO:  python inserisci_categorie.py
"""
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from catalog.models import ServiceCategory

CATEGORIE = [
    ("formazione",      "Formazione",       10),
    ("arredamento",     "Arredamento",      20),
    ("articoli-tecnici", "Articoli tecnici", 30),
    ("ospitalita",      "Ospitalità",       40),
    ("promozione",      "Promozione",       50),
    ("advertising",     "Advertising",      60),
    ("operativita",     "Operatività",      70),
]

print("Inserimento categorie servizio"); print("-" * 45)
creati = gia = 0
for code, nome, ordine in CATEGORIE:
    obj, creato = ServiceCategory.objects.get_or_create(
        code=code,
        defaults={"name": nome, "display_order": ordine, "is_active": True},
    )
    if creato:
        creati += 1; print(f"  + creata: {nome}")
    else:
        gia += 1; print(f"  = gia' presente: {obj.name}")
print("-" * 45)
print(f"FATTO: {creati} create, {gia} gia' presenti.")
