#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
RESET dati di test: elimina SERVIZI, PREVENTIVI/CONTRATTI, STAND (e dati collegati:
righe, scadenze, pagamenti, carrelli, export fattura, documenti dei contratti).
MANTIENE: sponsor, eventi, contatti/anagrafica, template (scadenze/lettere),
impostazioni organizzatore, loghi.

USO (dalla cartella del progetto):
    python reset_test_data.py            # DRY-RUN: mostra solo cosa eliminerebbe
    python reset_test_data.py --yes      # esegue davvero

ATTENZIONE: irreversibile. Fai un backup del DB PRIMA (es. pg_dump).
"""
import os, sys, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from django.db import transaction
from django.contrib.contenttypes.models import ContentType
from contracts.models import Contract, ContractLine, Deadline
from contracts.payments import Payment, CartSession
from catalog.models import Service, ServiceVariant
from venues.models import Stand, StandBlock
from shared.models import Document, InvoiceExport


def conta():
    ct = ContentType.objects.get_for_model(Contract)
    return [
        ("Contratti/preventivi (incl. soft-deleted)", Contract.all_objects.count()),
        ("  Righe contratto", ContractLine.objects.count()),
        ("  Scadenze", Deadline.objects.count()),
        ("  Pagamenti", Payment.objects.count()),
        ("  Carrelli", CartSession.objects.count()),
        ("  Export fattura", InvoiceExport.objects.count()),
        ("  Documenti dei contratti", Document.all_objects.filter(content_type=ct).count()),
        ("Servizi", Service.objects.count()),
        ("  Varianti servizio", ServiceVariant.objects.count()),
        ("Stand", Stand.objects.count()),
        ("Blocchi stand", StandBlock.objects.count()),
    ]


def stampa(titolo):
    print(titolo)
    for nome, n in conta():
        print(f"   {nome}: {n}")


print("=" * 60)
print("RESET DATI DI TEST")
print("Mantengo: sponsor, eventi, contatti, template, impostazioni, loghi.")
print("=" * 60)
stampa("Conteggio ATTUALE (verrà eliminato):")

if "--yes" not in sys.argv:
    print("\nDRY-RUN: nessuna modifica effettuata.")
    print("Per eseguire DAVVERO (dopo aver fatto il backup del DB):")
    print("   python reset_test_data.py --yes")
    sys.exit(0)

print("\nEsecuzione in corso...")
with transaction.atomic():
    ct = ContentType.objects.get_for_model(Contract)
    # 1) record che PROTEGGONO i contratti
    InvoiceExport.objects.all().delete()
    Payment.objects.all().delete()
    CartSession.objects.all().delete()
    # 2) documenti dei contratti (hard delete)
    for d in Document.all_objects.filter(content_type=ct):
        d.delete(hard=True)
    # 3) contratti: prima gli addon (parent PROTECT), poi i padri -> cascata righe/scadenze
    for c in Contract.all_objects.filter(parent_contract__isnull=False):
        c.delete(hard=True)
    for c in Contract.all_objects.filter(parent_contract__isnull=True):
        c.delete(hard=True)
    # 4) eventuali orfani
    ContractLine.objects.all().delete()
    Deadline.objects.all().delete()
    # 5) servizi
    ServiceVariant.objects.all().delete()
    Service.objects.all().delete()
    # 6) stand
    Stand.objects.all().delete()
    StandBlock.objects.all().delete()

print("\nFatto.")
stampa("Conteggio DOPO il reset:")
print("\nRicorda di riavviare il server se necessario.")
