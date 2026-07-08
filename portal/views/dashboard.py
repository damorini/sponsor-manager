"""
View della dashboard portale e lista contratti.

Tutte le view richiedono autenticazione + ruolo SPONSOR + Contact collegato.
Il decorator @sponsor_required centralizza questi check.
"""
import logging
from datetime import date, timedelta
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render

logger = logging.getLogger(__name__)


# ============================================================================
# Decorator: richiede sponsor autenticato con Contact collegato
# ============================================================================

def user_contacts_qs(user):
    """Contatti attivi (di aziende attive) collegati a questo utente portale."""
    from sponsors.models import Contact
    return (Contact.objects
            .filter(portal_user=user, sponsor__deleted_at__isnull=True)
            .select_related('sponsor')
            .order_by('sponsor__legal_name'))


def get_active_contact(request):
    """Contatto dell'AZIENDA ATTIVA per questo utente.

    La stessa persona (stesso login) puo' gestire piu' aziende: la scelta vive
    in sessione ('active_contact_id', impostata dalla maschera scegli_azienda).
    Con un solo contatto la scelta e' automatica. Ritorna None se l'utente non
    ha contatti oppure ne ha piu' d'uno e non ha ancora scelto."""
    qs = user_contacts_qs(request.user)
    cid = request.session.get('active_contact_id')
    if cid:
        c = qs.filter(pk=cid).first()
        if c is not None:
            return c
    contacts = list(qs[:2])
    if len(contacts) == 1:
        request.session['active_contact_id'] = str(contacts[0].pk)
        return contacts[0]
    return None


def accesso_quasi_fatto(request):
    """Pagina cortese 'Ci siamo quasi' al posto del Forbidden bianco: spiega
    che serve il primo accesso con le credenziali ricevute via email
    (o contattare helpdesk@valet.it). Mantiene lo status 403."""
    return render(request, 'portal/accesso_quasi.html', status=403)


def sponsor_required(view_func):
    """
    Verifica che l'utente sia loggato + sia uno sponsor + abbia Contact collegato.
    Salva contact e sponsor nella request per comodità della view.
    Se l'utente gestisce PIU' aziende e non ha ancora scelto, rimanda alla
    maschera 'Scegli l'azienda'.
    """
    @wraps(view_func)
    @login_required(login_url='portal:login')
    def wrapper(request, *args, **kwargs):
        if not getattr(request.user, 'is_sponsor', False):
            return accesso_quasi_fatto(request)

        contact = get_active_contact(request)
        if contact is None:
            if user_contacts_qs(request.user).exists():
                # piu' aziende, nessuna scelta in sessione: chiedi quale
                return redirect('portal:scegli_azienda')
            logger.warning("User %s sponsor senza Contact", request.user.id)
            return accesso_quasi_fatto(request)

        request.contact = contact
        request.sponsor = contact.sponsor

        _name = getattr(getattr(request, 'resolver_match', None), 'url_name', None)
        _impersonando = bool(request.session.get('impersonator_id'))

        # PRIVACY: al primo accesso (o se cambia la versione) serve la presa
        # visione dell'informativa. Non vale durante l'impersonazione dell'operatore.
        _allow_privacy = {'privacy_consent', 'privacy_policy', 'logout', 'impersonate_stop', 'guida'}
        if _name not in _allow_privacy and not _impersonando:
            from core.models import OrganizerSettings
            versione = OrganizerSettings.load().privacy_policy_version or '1.0'
            if not contact.privacy_accettata(versione):
                return redirect('portal:privacy_consent')

        # Per ACQUISTARE servono: un contatto OPERATIVO (riceve le comunicazioni)
        # e l'anagrafica di fatturazione completa. Senza, blocchiamo SOLO il
        # flusso di acquisto/checkout rimandando a "I miei dati"; il resto del
        # portale resta navigabile (con promemoria persistente, vedi base.html).
        # Non vale durante l'impersonazione dell'operatore.
        _purchase = {
            'catalog', 'catalog_event', 'service_detail',
            'cart_view', 'cart_add', 'cart_remove', 'cart_update_quantity',
            'cart_checkout', 'checkout_start_paypal', 'checkout_return',
            'checkout_cancel', 'checkout_card', 'checkout_card_capture',
            'checkout_success', 'checkout_dev_mark_paid', 'checkout_bank_transfer',
        }
        if _name in _purchase and not _impersonando:
            from django.contrib import messages
            _has_op = contact.sponsor.contacts.filter(
                roles__contains=['operational']).exists()
            if not _has_op:
                messages.warning(
                    request,
                    "Per acquistare servizi indica prima almeno un contatto "
                    "OPERATIVO nella tua anagrafica.")
                return redirect('portal:profile')
            _mancanti = contact.sponsor.campi_anagrafica_mancanti()
            if _mancanti:
                messages.warning(
                    request,
                    "Per acquistare servizi completa prima l'anagrafica della tua "
                    "azienda (dati di fatturazione). Campi mancanti: "
                    + ", ".join(_mancanti) + ".")
                return redirect('portal:profile')

        return view_func(request, *args, **kwargs)

    return wrapper


# ============================================================================
# Dashboard
# ============================================================================

@sponsor_required
def dashboard_view(request):
    """Home del portale: In evidenza generale - scadenze immediate di tutti gli eventi."""
    from contracts.models import Contract, ContractStatus, Deadline, DeadlineStatus
    from events.models import EventStatus

    sponsor = request.sponsor
    today = date.today()

    contracts = (Contract.objects
                 .filter(sponsor=sponsor, deleted_at__isnull=True)
                 .exclude(status__in=[ContractStatus.DRAFT, ContractStatus.CANCELLED])
                 .exclude(event__status=EventStatus.ARCHIVED)
                 .select_related('event'))
    contract_event = {c.id: c.event for c in contracts if c.event_id}
    contract_by_id = {c.id: c for c in contracts}
    contract_ids = list(contract_event.keys())

    done = [DeadlineStatus.RECEIVED, DeadlineStatus.WAIVED]
    open_dls = list(
        Deadline.objects.filter(contract_id__in=contract_ids)
        .exclude(status__in=done)
        .order_by('due_date')
    )

    def _is_admin(d):
        t = (d.deadline_type or '').lower()
        title = (d.title or '').lower()
        if t.startswith('pagament') or t == 'scadenza_opzione':
            return True
        kw = ('pagament', 'acconto', 'caparra', 'saldo', 'fattura', 'bonifico', 'opzione')
        return any(k in t for k in kw) or any(k in title for k in kw)

    from decimal import Decimal
    saldo_da_pagare = Decimal('0.00')
    admin_items, tech_items = [], []
    for d in open_dls:
        ev = contract_event.get(d.contract_id)
        if ev is None:
            continue
        row = {
            'title': d.portal_title,
            'due_date': d.due_date,
            'overdue': bool(d.due_date and d.due_date < today),
            'event': ev,
            'event_id': ev.id,
        }
        (admin_items if _is_admin(d) else tech_items).append(row)
        _c = contract_by_id.get(d.contract_id)
        if _c is not None:
            _dt = (d.deadline_type or '').lower()
            if _dt == 'pagamento_acconto':
                saldo_da_pagare += _c.deposit_amount
            elif _dt == 'pagamento_saldo':
                saldo_da_pagare += _c.balance_amount

    _eventi = {ev.id: ev for ev in contract_event.values() if ev}
    _futuri = sorted(
        [ev for ev in _eventi.values()
         if getattr(ev, 'start_date', None) and ev.start_date >= today],
        key=lambda e: e.start_date)
    _passati = sorted(
        [ev for ev in _eventi.values()
         if not (getattr(ev, 'start_date', None) and ev.start_date >= today)],
        key=lambda e: e.start_date or date.min, reverse=True)
    prossimi_eventi = _futuri + _passati
    prossimo_evento = _futuri[0] if _futuri else None

    from sponsors.models import PortalMessage, MessageSender
    messaggi_non_letti = list(
        PortalMessage.objects.filter(
            sponsor=sponsor, is_active=True, read_at__isnull=True,
            sender=MessageSender.OPERATOR, archived_at__isnull=True)
        .order_by('-created_at'))

    return render(request, 'portal/dashboard/dashboard.html', {
        'admin_items': admin_items[:15],
        'tech_items': tech_items[:15],
        'has_events': bool(contract_ids),
        'n_scadenze': len(open_dls),
        'saldo_da_pagare': saldo_da_pagare,
        'prossimo_evento': prossimo_evento,
        'prossimi_eventi': prossimi_eventi,
        'messaggi_non_letti': messaggi_non_letti,
    })



# ============================================================================
# Pagamenti: una card per ogni scadenza di pagamento (importo + badge)
# ============================================================================

def build_payment_items(sponsor, today):
    """Costruisce le card della pagina Pagamenti dello sponsor.

    Una voce per ogni scadenza di pagamento ('pagament*') dei contratti non
    bozza/annullati su eventi non archiviati. Ritorna (items, totale_da_pagare):
    nel totale entrano solo le scadenze ancora aperte (non pagate/non esonerate).
    """
    from decimal import Decimal
    from contracts.models import Contract, ContractStatus, Deadline, DeadlineStatus
    from events.models import EventStatus

    contracts = (Contract.objects
                 .filter(sponsor=sponsor, deleted_at__isnull=True)
                 .exclude(status__in=[ContractStatus.DRAFT, ContractStatus.CANCELLED])
                 .exclude(event__status=EventStatus.ARCHIVED)
                 .select_related('event'))
    by_id = {c.id: c for c in contracts}

    firmato_states = {
        ContractStatus.SIGNED, ContractStatus.ACTIVE, ContractStatus.COMPLETED}

    dls = (Deadline.objects
           .filter(contract_id__in=list(by_id.keys()),
                   deadline_type__startswith='pagament')
           .order_by('due_date'))

    items = []
    totale_da_pagare = Decimal('0.00')
    for d in dls:
        c = by_id.get(d.contract_id)
        if c is None:
            continue
        dtype = (d.deadline_type or '').lower()
        if dtype == 'pagamento_acconto':
            amount = c.deposit_amount
        elif dtype == 'pagamento_saldo':
            amount = c.balance_amount
        else:
            amount = c.total
        pagato = d.status == DeadlineStatus.RECEIVED
        esonerato = d.status == DeadlineStatus.WAIVED
        aperta = not pagato and not esonerato
        if aperta:
            totale_da_pagare += (amount or Decimal('0.00'))
        items.append({
            'title': d.portal_title,
            'event': c.event,
            'event_id': c.event_id,
            'contract_number': c.contract_number,
            'amount': amount,
            'due_date': d.due_date,
            'overdue': bool(aperta and d.due_date and d.due_date < today),
            'firmato': c.status in firmato_states,
            'pagato': pagato,
            'esonerato': esonerato,
        })

    # Aperte prima (per data scadenza), poi le pagate/esonerate.
    items.sort(key=lambda x: (not (not x['pagato'] and not x['esonerato']),
                              x['due_date'] or date.max))
    return items, totale_da_pagare


@sponsor_required
def payments_view(request):
    """Pagamenti: una card per ogni scadenza di pagamento (importo, data,
    badge separati Firmato/Pagato)."""
    items, totale = build_payment_items(request.sponsor, date.today())
    return render(request, 'portal/payments/list.html', {
        'payment_items': items,
        'totale_da_pagare': totale,
    })


# ============================================================================
# Guida rapida (consultazione veloce per lo sponsor)
# ============================================================================

@sponsor_required
def guida_view(request):
    """Guida rapida del portale: istruzioni a schemi per le operazioni tipiche.
    Raggiungibile sempre (whitelist nei gate del decorator), utile anche al
    primo accesso quando l'anagrafica non e' ancora completa."""
    return render(request, 'portal/guida.html', {})


# ============================================================================
# Lista contratti
# ============================================================================

@sponsor_required
def contracts_list_view(request):
    """Lista contratti con filtri (per evento, per stato)."""
    from contracts.models import Contract, ContractStatus, ContractKind, DeadlineStatus
    from events.models import Event, EventStatus

    sponsor = request.sponsor

    # Base queryset (esclude gli eventi ARCHIVIATI: stanno in 'Archivio eventi')
    qs = Contract.objects.filter(
        sponsor=sponsor,
        deleted_at__isnull=True,
    ).exclude(status__in=[ContractStatus.DRAFT, ContractStatus.CANCELLED]).exclude(contract_kind='addon').exclude(event__status=EventStatus.ARCHIVED).select_related('event', 'stand', 'stand_block')

    # Filtro per evento
    event_id = request.GET.get('event')
    if event_id:
        qs = qs.filter(event_id=event_id)

    # Filtro per stato (raggruppa stati)
    status_filter = request.GET.get('status')
    if status_filter == 'active':
        qs = qs.filter(status__in=[ContractStatus.SIGNED, ContractStatus.ACTIVE])
    elif status_filter == 'pending':
        qs = qs.filter(status__in=[
            ContractStatus.DRAFT, ContractStatus.SENT, ContractStatus.PENDING_PAYMENT
        ])
    elif status_filter == 'completed':
        qs = qs.filter(status=ContractStatus.COMPLETED)

    # Annotation: count scadenze pending per ogni contratto
    qs = qs.annotate(
        pending_deadlines_count=Count(
            'deadlines',
            filter=Q(deadlines__status__in=[
                DeadlineStatus.PENDING,
                DeadlineStatus.REMINDER_SENT,
                DeadlineStatus.OVERDUE,
            ]),
        )
    ).order_by('-created_at')

    # Eventi disponibili per il filtro (solo quelli dello sponsor, non archiviati)
    available_events = Event.objects.filter(
        contracts__sponsor=sponsor,
        contracts__deleted_at__isnull=True,
    ).exclude(status=EventStatus.ARCHIVED).distinct().order_by('-start_date')

    # Paginazione
    paginator = Paginator(qs, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # Copia degli acquisti ecommerce (contratti addon pagati): mostrati anche qui,
    # nella stessa pagina "I miei documenti". Filtrati per evento se il filtro e' attivo.
    paid = [ContractStatus.SIGNED, ContractStatus.ACTIVE, ContractStatus.COMPLETED]
    eco_qs = (Contract.objects
              .filter(sponsor=sponsor, contract_kind=ContractKind.ADDON,
                      status__in=paid, deleted_at__isnull=True)
              .exclude(event__status=EventStatus.ARCHIVED)
              .select_related('event')
              .prefetch_related('lines')
              .order_by('-signed_date', '-created_at'))
    if event_id:
        eco_qs = eco_qs.filter(event_id=event_id)
    ecommerce_orders = list(eco_qs)

    return render(request, 'portal/dashboard/contracts_list.html', {
        'contracts': page_obj.object_list,
        'page_obj': page_obj,
        'is_paginated': page_obj.has_other_pages(),
        'total_count': qs.count(),
        'available_events': available_events,
        'ecommerce_orders': ecommerce_orders,
    })


# ============================================================================
# I miei eventi (landing per il cliente)
# ============================================================================

def _build_event_items(sponsor, today, only_archived):
    """Riepilogo eventi del cliente con stato scadenze.
    only_archived=False -> eventi attivi; True -> eventi archiviati."""
    from contracts.models import Contract, ContractStatus, Deadline, DeadlineStatus

    contracts = (Contract.objects
                 .filter(sponsor=sponsor, deleted_at__isnull=True)
                 .exclude(status__in=[ContractStatus.DRAFT, ContractStatus.CANCELLED])
                 .select_related('event'))

    events_map = {}
    contracts_by_event = {}
    for c in contracts:
        if not c.event_id:
            continue
        archived = not c.event.is_active
        if archived != only_archived:
            continue
        events_map.setdefault(c.event_id, c.event)
        contracts_by_event.setdefault(c.event_id, []).append(c.id)

    items = []
    for ev_id, ev in events_map.items():
        dls = Deadline.objects.filter(contract_id__in=contracts_by_event[ev_id])
        open_status = [DeadlineStatus.PENDING, DeadlineStatus.REMINDER_SENT]
        items.append({
            'event': ev,
            'total': dls.count(),
            'completed': dls.filter(
                status__in=[DeadlineStatus.RECEIVED, DeadlineStatus.WAIVED]
            ).count(),
            'overdue': dls.filter(status__in=open_status, due_date__lt=today).count(),
            'pending': dls.filter(status__in=open_status, due_date__gte=today).count(),
        })

    items.sort(key=lambda x: (x['event'].start_date or date.max))
    return items


@sponsor_required
def events_view(request):
    """Eventi ATTIVI a cui il cliente partecipa, con riepilogo scadenze."""
    items = _build_event_items(request.sponsor, date.today(), only_archived=False)
    return render(request, 'portal/events/list.html', {'events_items': items})


@sponsor_required
def archived_events_view(request):
    """Archivio eventi: eventi archiviati (sola consultazione, non acquistabili)."""
    items = _build_event_items(request.sponsor, date.today(), only_archived=True)
    return render(request, 'portal/events/archived.html', {'events_items': items})


@sponsor_required
def archived_event_detail_view(request, event_id):
    """Storico (sola consultazione) di un evento archiviato: contratti, righe,
    scadenze e documenti dello sponsor per quell'evento."""
    from django.shortcuts import get_object_or_404, redirect
    from contracts.models import Contract, ContractStatus
    from events.models import Event
    from shared.models import Document
    from django.contrib.contenttypes.models import ContentType

    sponsor = request.sponsor
    event = get_object_or_404(Event, id=event_id)

    # Solo eventi archiviati; se attivo, manda alla pagina evento normale.
    if event.is_active:
        return redirect('portal:event_dashboard', event_id=event.id)

    contracts = list(
        Contract.objects
        .filter(sponsor=sponsor, event=event, deleted_at__isnull=True)
        .exclude(status=ContractStatus.CANCELLED)
        .prefetch_related('lines__service', 'deadlines')
        .order_by('-created_at')
    )
    if not contracts:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Non risultano documenti per questo evento.")

    # Documenti allegati a ciascun contratto (PDF domanda, ecc.)
    ct_type = ContentType.objects.get_for_model(Contract)
    for c in contracts:
        c.docs = list(
            Document.objects.filter(
                content_type=ct_type, object_id=c.id, deleted_at__isnull=True,
                is_visible_to_sponsor=True,
            ).order_by('-created_at')
        )

    return render(request, 'portal/events/archived_detail.html', {
        'event': event,
        'contracts': contracts,
    })


@sponsor_required
def event_dashboard_view(request, event_id):
    """Pagina evento: info dell'evento + servizi disponibili."""
    from django.shortcuts import get_object_or_404
    from contracts.models import Contract, ContractStatus
    from events.models import Event
    from portal.views.catalog import _get_purchasable_services

    sponsor = request.sponsor
    today = date.today()
    event = get_object_or_404(Event, id=event_id)

    contracts = Contract.objects.filter(
        sponsor=sponsor, event_id=event_id, deleted_at__isnull=True)
    if not contracts.exists():
        return HttpResponseForbidden("Accesso negato.")

    has_active_contract = contracts.filter(
        status__in=[ContractStatus.SIGNED, ContractStatus.ACTIVE]
    ).exists()

    # Se il cliente non ha ancora firmato, offriamo un link al preventivo
    # (domanda di ammissione) da rivedere/confermare. Preferiamo quello inviato.
    pending_contract = None
    if not has_active_contract:
        pending_contract = (
            contracts.filter(status=ContractStatus.SENT).order_by('-created_at').first()
            or contracts.filter(
                status__in=[ContractStatus.DRAFT, ContractStatus.PENDING_PAYMENT]
            ).order_by('-created_at').first()
        )

    try:
        services = list(_get_purchasable_services(event, today))
    except Exception:
        services = []

    return render(request, 'portal/events/dashboard.html', {
        'event': event,
        'services': services,
        'has_active_contract': has_active_contract,
        'pending_contract': pending_contract,
    })


@sponsor_required
def purchases_view(request):
    """I miei acquisti: contratti addon ecommerce pagati (data + importo)."""
    from contracts.models import Contract, ContractStatus, ContractKind
    from events.models import EventStatus

    sponsor = request.sponsor
    paid = [ContractStatus.SIGNED, ContractStatus.ACTIVE, ContractStatus.COMPLETED]
    orders = list(
        Contract.objects
        .filter(sponsor=sponsor, contract_kind=ContractKind.ADDON,
                status__in=paid, deleted_at__isnull=True)
        .exclude(event__status=EventStatus.ARCHIVED)
        .select_related('event')
        .prefetch_related('lines')
        .order_by('-signed_date', '-created_at')
    )
    pending_orders = list(
        Contract.objects
        .filter(sponsor=sponsor, contract_kind=ContractKind.ADDON,
                status=ContractStatus.PENDING_PAYMENT, deleted_at__isnull=True)
        .exclude(event__status=EventStatus.ARCHIVED)
        .select_related('event')
        .prefetch_related('lines')
        .order_by('-created_at')
    )
    return render(request, 'portal/purchases/list.html',
                  {'orders': orders, 'pending_orders': pending_orders})

