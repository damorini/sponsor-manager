"""
Visibilita' per-evento nell'admin.

Operatori e "Sola lettura" vedono solo i dati degli eventi abilitati
(User.managed_events). Superuser e Amministratori vedono tutto.
I clienti (anagrafiche/aziende) NON passano da qui: restano visibili a tutti.
"""


def can_see_all(user):
    return bool(
        getattr(user, "is_superuser", False)
        or getattr(user, "can_see_all_events", False)
    )


def scope_by_event(request, qs, event_path):
    """Limita qs agli eventi gestiti dall'utente.

    event_path: percorso ORM verso l'evento, es. 'event', 'contract__event', 'id'.
    """
    user = getattr(request, "user", None)
    if user is None or can_see_all(user):
        return qs
    managed = getattr(user, "managed_events", None)
    if managed is None:
        return qs.none()
    return qs.filter(**{f"{event_path}__in": managed.all()})


def scope_generic_by_event(request, qs):
    """Scoping per modelli con GenericForeignKey (es. Document, Communication).

    Operatori/Sola lettura vedono gli oggetti collegati a Contratti o Scadenze
    dei propri eventi (managed_events), piu' quelli collegati ad anagrafiche
    (Sponsor/Contact), che restano visibili a tutti. Superuser/Amministratori: tutto.
    """
    user = getattr(request, "user", None)
    if user is None or can_see_all(user):
        return qs
    from django.contrib.contenttypes.models import ContentType
    from django.db.models import Q
    from contracts.models import Contract, Deadline
    from sponsors.models import Sponsor, Contact

    managed = user.managed_events.all() if getattr(user, "managed_events", None) is not None else []

    q = Q()
    ct_contract = ContentType.objects.get_for_model(Contract)
    contract_ids = list(Contract.objects.filter(event__in=managed).values_list("pk", flat=True))
    q |= Q(content_type=ct_contract, object_id__in=contract_ids)

    ct_deadline = ContentType.objects.get_for_model(Deadline)
    deadline_ids = list(Deadline.objects.filter(contract__event__in=managed).values_list("pk", flat=True))
    q |= Q(content_type=ct_deadline, object_id__in=deadline_ids)

    # anagrafiche: visibili a tutti gli operatori
    ct_sponsor = ContentType.objects.get_for_model(Sponsor)
    ct_contact = ContentType.objects.get_for_model(Contact)
    q |= Q(content_type__in=[ct_sponsor, ct_contact])

    return qs.filter(q)
