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


def _active_event_esente(request):
    """True se la richiesta NON va ristretta all'evento attivo (il RBAC
    resta sempre): ricerche autocomplete dei form (es. scelta sponsor su
    un nuovo contratto -> anagrafica completa) e pagine di DETTAGLIO
    (un link diretto a una scheda/documento/scadenza di un altro evento
    deve aprirsi, non dare 404). Le viste di dettaglio si riconoscono
    dall'URL che punta a UN oggetto preciso (pk/uuid nei kwargs): vale per
    l'admin (_change/_delete/_history) e per le pagine del cruscotto
    (documento_apri, scadenza, evento...). Le LISTE non hanno kwargs e
    restano filtrate."""
    rm = getattr(request, 'resolver_match', None)
    if rm is None:
        return False
    if (rm.url_name or '') == 'autocomplete':
        return True
    return bool(rm.kwargs)


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
    if active and not _active_event_esente(request):
        qs = qs.filter(**{event_path: active})
    return qs


def scope_anagrafica_by_event(request, qs, contract_path):
    """Anagrafiche (Sponsor/Contact): con un EVENTO ATTIVO le LISTE mostrano
    solo chi ha contratti (non cestinati) su quell'evento. Nessun RBAC qui:
    senza evento attivo l'anagrafica resta completa per tutti. Autocomplete
    e schede di dettaglio non vengono mai ristrette (vedi _active_event_esente).

    contract_path: percorso ORM verso il contratto, es. 'contracts' (Sponsor)
    o 'sponsor__contracts' (Contact).
    """
    active = get_active_event_id(request)
    if not active or _active_event_esente(request):
        return qs
    # Cestino (SoftDeleteAdminMixin): chi e' stato cestinato ha per forza i
    # contratti gia' cestinati (FK PROTECT), quindi il filtro "contratto vivo
    # sull'evento" lo renderebbe introvabile e non ripristinabile. Nel
    # cestino si vede tutto.
    try:
        if request.GET.get('trash') in ('cestino', 'tutti'):
            return qs
    except Exception:
        pass
    return qs.filter(**{
        f"{contract_path}__event": active,
        f"{contract_path}__deleted_at__isnull": True,
    }).distinct()


def scope_lista_evento_attivo(request, qs, event_path, include_senza_evento=False):
    """Solo filtro EVENTO ATTIVO per le liste dei modelli collegati a un
    evento che NON hanno il RBAC per-evento (catalogo servizi, campagne,
    messaggi portale, carrelli...): niente dati di un altro evento quando
    un evento e' attivo. Autocomplete e viste di dettaglio restano completi
    (vedi _active_event_esente).

    include_senza_evento=True mantiene visibili le righe senza evento
    (es. messaggi generici del portale).
    """
    active = get_active_event_id(request)
    if not active or _active_event_esente(request):
        return qs
    if include_senza_evento:
        from django.db.models import Q
        return qs.filter(Q(**{event_path: active}) |
                         Q(**{f"{event_path}__isnull": True}))
    return qs.filter(**{event_path: active})


def escludi_figli_di_contratti_cestinati(request, qs, contract_path='contract'):
    """Le LISTE dei modelli figli del contratto (scadenze, righe, pagamenti,
    carrelli, export fatture) non mostrano i record dei contratti NEL
    CESTINO: sono storia del contratto cancellato, non lavoro da fare
    (es. scadenze esonerate che restavano in elenco col conto alla
    rovescia). Restano nel DB e visibili dentro la scheda del contratto
    cestinato; le viste di dettaglio restano raggiungibili."""
    if _active_event_esente(request):
        return qs
    return qs.filter(**{f"{contract_path}__deleted_at__isnull": True})


def scope_generic_by_event(request, qs):
    """Scoping per modelli con GenericForeignKey (es. Document, Communication).

    Operatori/Sola lettura vedono gli oggetti collegati a Contratti o Scadenze
    dei propri eventi (managed_events), piu' quelli collegati ad anagrafiche
    (Sponsor/Contact), che restano visibili a tutti. Superuser/Amministratori: tutto.
    """
    user = getattr(request, "user", None)
    active = get_active_event_id(request)
    if active and _active_event_esente(request):
        active = None
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
