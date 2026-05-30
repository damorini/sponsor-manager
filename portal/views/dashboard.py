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
    """Pagina home del portale: KPI, scadenze, contratti recenti."""
    from contracts.models import Contract, ContractStatus, Deadline, DeadlineStatus
    from catalog.models import Service

    sponsor = request.sponsor
    today = date.today()

    # Tutti i contratti dello sponsor (non eliminati)
    all_contracts = Contract.objects.filter(
        sponsor=sponsor,
        deleted_at__isnull=True,
    ).select_related('event', 'stand', 'stand_block')

    # KPI counts
    active_contracts_count = all_contracts.filter(
        status__in=[ContractStatus.SIGNED, ContractStatus.ACTIVE]
    ).count()

    pending_contracts_count = all_contracts.filter(
        status=ContractStatus.PENDING_PAYMENT
    ).count()

    # Eventi attivi (con almeno un contratto signed/active)
    active_events_count = all_contracts.filter(
        status__in=[ContractStatus.SIGNED, ContractStatus.ACTIVE]
    ).values('event_id').distinct().count()

    # Deadlines
    contract_ids = list(all_contracts.values_list('id', flat=True))

    upcoming_deadlines_qs = Deadline.objects.filter(
        contract_id__in=contract_ids,
        status__in=[DeadlineStatus.PENDING, DeadlineStatus.REMINDER_SENT],
        due_date__gte=today,
        due_date__lte=today + timedelta(days=14),
    ).select_related('contract', 'contract__event').order_by('due_date')

    overdue_deadlines_qs = Deadline.objects.filter(
        contract_id__in=contract_ids,
        status__in=[
            DeadlineStatus.PENDING,
            DeadlineStatus.REMINDER_SENT,
            DeadlineStatus.OVERDUE,
        ],
        due_date__lt=today,
    ).select_related('contract', 'contract__event').order_by('due_date')

    # Calcola days_until/days_overdue per il template
    # days_until_due e' gia' una property del modello Deadline (sola lettura):
    # il template la usa direttamente, non serve assegnarla qui.
    upcoming_deadlines = list(upcoming_deadlines_qs[:5])

    overdue_deadlines = list(overdue_deadlines_qs[:5])
    for d in overdue_deadlines:
        d.days_overdue = (today - d.due_date).days

    # Recent contracts (ultimi 5)
    recent_contracts = all_contracts.order_by('-created_at')[:5]

    # Verifica se ci sono servizi acquistabili (per mostrare CTA "Esplora servizi")
    has_purchasable_services = Service.objects.filter(
        event__in=all_contracts.values('event'),
        is_active=True,
        is_self_purchasable=True,
    ).exists()

    return render(request, 'portal/dashboard/dashboard.html', {
        'sponsor': sponsor,
        'active_contracts_count': active_contracts_count,
        'pending_contracts_count': pending_contracts_count,
        'active_events_count': active_events_count,
        'upcoming_deadlines_count': upcoming_deadlines_qs.count(),
        'overdue_deadlines_count': overdue_deadlines_qs.count(),
        'upcoming_deadlines': upcoming_deadlines,
        'overdue_deadlines': overdue_deadlines,
        'recent_contracts': recent_contracts,
        'has_purchasable_services': has_purchasable_services,
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
    ).select_related('event', 'stand', 'stand_block')

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
    """In evidenza: fotografia delle scadenze immediate (amministrative e tecniche)."""
    from django.shortcuts import get_object_or_404
    from contracts.models import Contract, Deadline, DeadlineStatus
    from events.models import Event

    sponsor = request.sponsor
    today = date.today()
    event = get_object_or_404(Event, id=event_id)

    contracts = Contract.objects.filter(
        sponsor=sponsor, event_id=event_id, deleted_at__isnull=True)
    if not contracts.exists():
        return HttpResponseForbidden("Accesso negato.")

    contract_ids = list(contracts.values_list('id', flat=True))
    done = [DeadlineStatus.RECEIVED, DeadlineStatus.WAIVED]
    open_dls = list(
        Deadline.objects.filter(contract_id__in=contract_ids)
        .exclude(status__in=done)
        .order_by('due_date')
    )

    def _is_admin(d):
        t = (d.deadline_type or '').lower()
        return t.startswith('pagament') or t == 'scadenza_opzione'

    admin_deadlines, tech_deadlines = [], []
    for d in open_dls:
        row = {
            'title': d.title,
            'due_date': d.due_date,
            'overdue': bool(d.due_date and d.due_date < today),
        }
        (admin_deadlines if _is_admin(d) else tech_deadlines).append(row)

    return render(request, 'portal/events/dashboard.html', {
        'event': event,
        'admin_deadlines': admin_deadlines[:8],
        'tech_deadlines': tech_deadlines[:8],
    })
