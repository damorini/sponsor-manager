"""
Controlli "cosa manca": lavori lasciati a meta' o cose fatte che il cliente
non puo' vedere nel portale. Una sola definizione per ciascun controllo,
usata da:
- gli avvisi della home del cruscotto (core/views.py cruscotto_home);
- i filtri delle liste (contratti: "Cose da fare"; contatti: "Invito portale");
- l'email mattutina di alert all'operatore (send_operator_alerts);
- l'avviso al salvataggio di azienda/contatto (sponsors/admin.py).
"""
from datetime import date

from django.db.models import Exists, OuterRef, Q


def contatti_da_invitare(qs=None):
    """Contatti con la spunta 'Accesso al portale' ma senza account: la
    spunta da sola non crea nome utente e password, serve l'azione
    'Invita al portale'. Finche' non la si usa il contatto non puo' entrare."""
    from sponsors.models import Contact
    if qs is None:
        qs = Contact.objects.all()
    return qs.filter(has_portal_access=True, portal_user__isnull=True,
                     sponsor__deleted_at__isnull=True)


def _contratti_evento_in_corso(qs):
    """Contratti principali vivi di eventi non archiviati e non ancora finiti."""
    from contracts.models import ContractKind
    from events.models import EventStatus
    oggi = date.today()
    return (qs.filter(contract_kind=ContractKind.MAIN, deleted_at__isnull=True)
              .exclude(event__status=EventStatus.ARCHIVED)
              .filter(Q(event__end_date__isnull=True) | Q(event__end_date__gte=oggi)))


def contratti_cliente_senza_accesso(qs=None):
    """Contratti inviati o firmati di aziende in cui NESSUN contatto puo'
    entrare nel portale: preventivo, scadenze e pagamenti ci sono, ma il
    cliente non li vede."""
    from contracts.models import Contract, ContractStatus
    from sponsors.models import Contact
    if qs is None:
        qs = Contract.objects.all()
    con_accesso = Contact.objects.filter(
        sponsor=OuterRef('sponsor'), has_portal_access=True,
        portal_user__isnull=False, portal_user__is_active=True)
    return (_contratti_evento_in_corso(qs)
            .filter(status__in=[ContractStatus.SENT, ContractStatus.SIGNED,
                                ContractStatus.ACTIVE])
            .exclude(Exists(con_accesso)))


def contratti_senza_scadenze_pagamento(qs=None):
    """Contratti firmati con un importo ma senza scadenze di acconto/saldo:
    il cliente non vede cosa deve pagare e non partono i promemoria.
    Succede se il contratto nasce gia' 'Firmato' invece di passarci."""
    from contracts.models import Contract, ContractStatus, Deadline
    if qs is None:
        qs = Contract.objects.all()
    scad_pag = Deadline.objects.filter(
        contract=OuterRef('pk'), deadline_type__startswith='pagamento')
    return (_contratti_evento_in_corso(qs)
            .filter(status__in=[ContractStatus.SIGNED, ContractStatus.ACTIVE],
                    total__gt=0)
            .exclude(Exists(scad_pag)))


def nomi_aziende(qs, campo='sponsor__legal_name', limite=10):
    """Primi nomi di azienda distinti, per la riga dell'avviso."""
    nomi = []
    for n in qs.values_list(campo, flat=True):
        if n and n not in nomi:
            nomi.append(n)
        if len(nomi) >= limite:
            break
    return nomi
