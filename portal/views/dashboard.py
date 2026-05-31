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

def sponsor_required(view_func):
    """
    Verifica che l'utente sia loggato + sia uno sponsor + abbia Contact collegato.
    Salva contact e sponsor nella request per comodità della view.
    """
    @wraps(view_func)
    @login_required(login_url='portal:login')
    def wrapper(request, *args, **kwargs):
        if not getattr(request.user, 'is_sponsor', False):
            return HttpResponseForbidden(
                "Questa pagina è riservata agli sponsor."
            )

        try:
            contact = request.user.contact_profile
        except Exception:
            logger.warning("User %s sponsor senza Contact", request.user.id)
            return HttpResponseForbidden(
                "Account configurato in modo incompleto."
            )

        request.contact = contact
        request.sponsor = contact.sponsor
        return view_func(request, *args, **kwargs)

    return wrapper


# ============================================================================
# Dashboard
# ============================================================================

@sponsor_required
def dashboard_view(request):
    """Home del portale: In evidenza generale - scadenze immediate di tutti gli eventi."""
    from contracts.models import Contract, Deadline, DeadlineStatus

    sponsor = request.sponsor
    today = date.today()

    contracts = (Contract.objects
                 .filter(sponsor=sponsor, deleted_at__isnull=True)
                 .exclude(status=ContractStatus.CANCELLED)
                 .select_related('event'))
    contract_event = {c.id: c.event for c in contracts if c.event_id}
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

    admin_items, tech_items = [], []
    for d in open_dls:
        ev = contract_event.get(d.contract_id)
        if ev is None:
            continue
        row = {
            'title': d.title,
            'due_date': d.due_date,
            'overdue': bool(d.due_date and d.due_date < today),
            'event': ev,
            'event_id': ev.id,
        }
        (admin_items if _is_admin(d) else tech_items).append(row)

    return render(request, 'portal/dashboard/dashboard.html', {
        'admin_items': admin_items[:15],
        'tech_items': tech_items[:15],
        'has_events': bool(contract_ids),
        'n_scadenze': len(open_dls),
        'portal_message': (getattr(sponsor, 'portal_message', '') or '').strip(),
    })



# ============================================================================
# Lista contratti
# ============================================================================

@sponsor_required
def contracts_list_view(request):
    """Lista contratti con filtri (per evento, per stato)."""
    from contracts.models import Contract, ContractStatus, DeadlineStatus
    from events.models import Event

    sponsor = request.sponsor

    # Base queryset
    qs = Contract.objects.filter(
        sponsor=sponsor,
        deleted_at__isnull=True,
    ).exclude(status=ContractStatus.CANCELLED).select_related('event', 'stand', 'stand_block')

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

    # Eventi disponibili per il filtro (solo quelli dello sponsor)
    available_events = Event.objects.filter(
        contracts__sponsor=sponsor,
        contracts__deleted_at__isnull=True,
    ).distinct().order_by('-start_date')

    # Paginazione
    paginator = Paginator(qs, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    return render(request, 'portal/dashboard/contracts_list.html', {
        'contracts': page_obj.object_list,
        'page_obj': page_obj,
        'is_paginated': page_obj.has_other_pages(),
        'total_count': qs.count(),
        'available_events': available_events,
    })


# ============================================================================
# I miei eventi (landing per il cliente)
# ============================================================================

@sponsor_required
def events_view(request):
    """Eventi a cui il cliente partecipa, con riepilogo scadenze."""
    from contracts.models import Contract, Deadline, DeadlineStatus

    sponsor = request.sponsor
    today = date.today()

    contracts = (Contract.objects
                 .filter(sponsor=sponsor, deleted_at__isnull=True)
                 .exclude(status=ContractStatus.CANCELLED)
                 .select_related('event'))

    events_map = {}
    contracts_by_event = {}
    for c in contracts:
        if not c.event_id:
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

    return render(request, 'portal/events/list.html', {'events_items': items})


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

    try:
        services = list(_get_purchasable_services(event, today))
    except Exception:
        services = []

    return render(request, 'portal/events/dashboard.html', {
        'event': event,
        'services': services,
        'has_active_contract': has_active_contract,
    })


@sponsor_required
def purchases_view(request):
    """I miei acquisti: contratti addon ecommerce pagati (data + importo)."""
    from contracts.models import Contract, ContractStatus, ContractKind

    sponsor = request.sponsor
    paid = [ContractStatus.SIGNED, ContractStatus.ACTIVE, ContractStatus.COMPLETED]
    orders = list(
        Contract.objects
        .filter(sponsor=sponsor, contract_kind=ContractKind.ADDON,
                status__in=paid, deleted_at__isnull=True)
        .select_related('event')
        .prefetch_related('lines')
        .order_by('-signed_date', '-created_at')
    )
    return render(request, 'portal/purchases/list.html', {'orders': orders})

