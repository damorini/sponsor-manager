"""
Visibilita' per-evento nell'admin. Due livelli, entrambi centralizzati qui:

1. RBAC (permessi): Operatori e "Sola lettura" vedono solo i dati degli eventi
   abilitati (User.managed_events). Superuser e Amministratori vedono tutto.
2. EVENTO ATTIVO (comodita'): l'operatore sceglie su quale evento lavorare
   (chiave di sessione) e TUTTE le liste si filtrano da sole su quello,
   senza dover impostare filtri. Vale per chiunque, superuser compresi;
   si cambia/spegne dal selettore nell'header dell'admin.

I clienti (anagrafiche/aziende) NON passano da qui: restano visibili a tutti.
"""

SESSION_EVENT_KEY = 'vt_active_event_id'
SESSION_EVENT_CHOSEN = 'vt_event_scelto'


def can_see_all(user):
    return bool(
        getattr(user, "is_superuser", False)
        or getattr(user, "can_see_all_events", False)
    )


def get_active_event_id(request):
    """Id (str) dell'evento attivo scelto in sessione, o None (= tutti)."""
    try:
        return request.session.get(SESSION_EVENT_KEY) or None
    except Exception:
        return None


def set_active_event(request, event_id):
    """Imposta l'evento attivo ('' o None = tutti gli eventi)."""
    request.session[SESSION_EVENT_KEY] = str(event_id) if event_id else ''
    request.session[SESSION_EVENT_CHOSEN] = True


def events_for_user(request):
    """Eventi selezionabili dall'operatore (SOLO filtro RBAC, mai il filtro
    evento attivo: serve al selettore e alla pagina di scelta)."""
    from events.models import Event, EventStatus
    qs = (Event.objects
          .exclude(status=EventStatus.ARCHIVED)
          .order_by('-start_date'))
    user = getattr(request, "user", None)
    if user is not None and not can_see_all(user):
        managed = getattr(user, "managed_events", None)
        if managed is None:
            return qs.none()
        qs = qs.filter(pk__in=managed.all())
    return qs


def scope_by_event(request, qs, event_path):
    """Limita qs agli eventi gestiti dall'utente (RBAC) e, se scelto,
    all'EVENTO ATTIVO di sessione.

    event_path: percorso ORM verso l'evento, es. 'event', 'contract__event', 'id'.
    """
    user = getattr(request, "user", None)
    if user is not None and not can_see_all(user):
        managed = getattr(user, "managed_events", None)
        if managed is None:
            return qs.none()
        qs = qs.filter(**{f"{event_path}__in": managed.all()})
    active = get_active_event_id(request)
    if active:
        qs = qs.filter(**{event_path: active})
    return qs


def scope_generic_by_event(request, qs):
    """Scoping per modelli con GenericForeignKey (es. Document, Communication).

    Operatori/Sola lettura vedono gli oggetti collegati a Contratti o Scadenze
    dei propri eventi (managed_events), piu' quelli collegati ad anagrafiche
    (Sponsor/Contact), che restano visibili a tutti. Superuser/Amministratori: tutto.
    """
    user = getattr(request, "user", None)
    active = get_active_event_id(request)
    if (user is None or can_see_all(user)) and not active:
        return qs
    from django.contrib.contenttypes.models import ContentType
    from django.db.models import Q
    from contracts.models import Contract, Deadline
    from sponsors.models import Sponsor, Contact

    # Base eventi: RBAC (managed_events) per operatori/sola lettura,
    # tutti gli eventi per chi vede tutto; poi ristretta all'evento attivo.
    from events.models import Event
    if user is not None and not can_see_all(user):
        eventi = user.managed_events.all() if getattr(user, "managed_events", None) is not None else Event.objects.none()
    else:
        eventi = Event.objects.all()
    if active:
        eventi = eventi.filter(pk=active)

    q = Q()
    ct_contract = ContentType.objects.get_for_model(Contract)
    contract_ids = list(Contract.objects.filter(event__in=eventi).values_list("pk", flat=True))
    q |= Q(content_type=ct_contract, object_id__in=contract_ids)

    ct_deadline = ContentType.objects.get_for_model(Deadline)
    deadline_ids = list(Deadline.objects.filter(contract__event__in=eventi).values_list("pk", flat=True))
    q |= Q(content_type=ct_deadline, object_id__in=deadline_ids)

    # anagrafiche: visibili a tutti gli operatori
    ct_sponsor = ContentType.objects.get_for_model(Sponsor)
    ct_contact = ContentType.objects.get_for_model(Contact)
    q |= Q(content_type__in=[ct_sponsor, ct_contact])

    return qs.filter(q)
