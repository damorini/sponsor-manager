"""
View catalogo servizi acquistabili dal portale.

Mostra:
- Lista di tutti gli eventi a cui lo sponsor partecipa, con i servizi
  acquistabili per ciascuno
- Filtro per evento singolo
- Dettaglio servizio con descrizione completa e bottone "Aggiungi al carrello"

Logica acquistabilità:
- Service.is_active = True
- Service.is_self_purchasable = True
- Se Service.self_purchase_cutoff_days è valorizzato, today must be
  <= event.start_date - cutoff_days
"""
import logging
from datetime import date, timedelta

from django.http import HttpResponseForbidden
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from portal.views.dashboard import sponsor_required

logger = logging.getLogger(__name__)


def _get_purchasable_services(event, today=None):
    """
    Restituisce queryset di Service acquistabili per un evento, con flag
    is_within_cutoff calcolato.
    """
    from catalog.models import Service

    # Eventi archiviati: nessun servizio acquistabile.
    if not getattr(event, 'is_active', True):
        return Service.objects.none()

    today = today or date.today()
    services = Service.objects.filter(
        event=event,
        is_active=True,
        is_self_purchasable=True,
    ).order_by('display_order', 'name')

    # Calcola cutoff per ciascun servizio
    days_to_event = (event.start_date - today).days
    for s in services:
        if s.self_purchase_cutoff_days is None:
            s.is_within_cutoff = True
            s.cutoff_days_remaining = None
        else:
            s.cutoff_days_remaining = days_to_event - s.self_purchase_cutoff_days
            s.is_within_cutoff = s.cutoff_days_remaining >= 0

    return services


@sponsor_required
def catalog_view(request):
    """
    Vista catalogo principale: mostra eventi attivi dello sponsor con servizi
    acquistabili raggruppati per evento.
    """
    from contracts.models import Contract, ContractStatus

    sponsor = request.sponsor

    # Eventi a cui lo sponsor è attivo (ha almeno un contratto signed/active)
    sponsor_events = list(set(
        Contract.objects.filter(
            sponsor=sponsor,
            status__in=[ContractStatus.SIGNED, ContractStatus.ACTIVE],
            deleted_at__isnull=True,
        ).select_related('event').values_list('event_id', flat=True)
    ))

    # Per ciascun evento, calcola i servizi disponibili
    from events.models import Event, EventStatus
    events = Event.objects.filter(
        id__in=sponsor_events,
        end_date__gte=date.today(),  # eventi futuri
    ).exclude(status=EventStatus.ARCHIVED).order_by('start_date')

    events_with_services = []
    for event in events:
        services = list(_get_purchasable_services(event))
        if services:
            events_with_services.append({
                'event': event,
                'services': services,
                'has_purchasable': any(s.is_within_cutoff for s in services),
            })

    return render(request, 'portal/catalog/list.html', {
        'events_with_services': events_with_services,
    })


@sponsor_required
def catalog_event_view(request, event_id):
    """Catalogo dei servizi per un singolo evento."""
    from contracts.models import Contract, ContractStatus
    from events.models import Event

    sponsor = request.sponsor
    event = get_object_or_404(Event, id=event_id)

    # Evento archiviato o gia' concluso: non acquistabile.
    if not event.is_active:
        return HttpResponseForbidden("Questo evento è archiviato: non è più possibile acquistare.")
    if event.end_date and event.end_date < date.today():
        messages.info(request, "Questo evento si è già concluso: non è più possibile acquistare.")
        return redirect('portal:catalog')

    # Verifica che lo sponsor abbia un contratto attivo per questo evento
    has_contract = Contract.objects.filter(
        sponsor=sponsor,
        event=event,
        status__in=[ContractStatus.SIGNED, ContractStatus.ACTIVE],
        deleted_at__isnull=True,
    ).exists()

    if not has_contract:
        return HttpResponseForbidden(
            "Non risulta un contratto attivo per questo evento."
        )

    services = _get_purchasable_services(event)

    return render(request, 'portal/catalog/event.html', {
        'event': event,
        'services': services,
    })


@sponsor_required
def service_detail_view(request, service_id):
    """Dettaglio di un singolo servizio."""
    from catalog.models import Service
    from contracts.models import Contract, ContractStatus

    service = get_object_or_404(
        Service.objects.select_related('event'),
        id=service_id,
        is_active=True,
        is_self_purchasable=True,
    )

    # Evento archiviato o gia' concluso: non acquistabile.
    if not service.event.is_active:
        return HttpResponseForbidden("Questo evento è archiviato: non è più possibile acquistare.")
    if service.event.end_date and service.event.end_date < date.today():
        messages.info(request, "Questo evento si è già concluso: non è più possibile acquistare.")
        return redirect('portal:catalog')

    # Verifica accesso (sponsor deve avere contratto attivo per l'evento)
    has_contract = Contract.objects.filter(
        sponsor=request.sponsor,
        event=service.event,
        status__in=[ContractStatus.SIGNED, ContractStatus.ACTIVE],
        deleted_at__isnull=True,
    ).exists()

    if not has_contract:
        return HttpResponseForbidden(
            "Non risulta un contratto attivo per questo evento."
        )

    # Calcola cutoff
    today = date.today()
    days_to_event = (service.event.start_date - today).days
    if service.self_purchase_cutoff_days is None:
        service.is_within_cutoff = True
        service.cutoff_days_remaining = None
    else:
        service.cutoff_days_remaining = days_to_event - service.self_purchase_cutoff_days
        service.is_within_cutoff = service.cutoff_days_remaining >= 0

    variants = list(
        service.variants.filter(is_active=True).order_by('display_order', 'label')
    )
    service_sold_out = service.is_sold_out
    service.remaining = service.quantity_available()
    for _v in variants:
        _v.sold_out = service_sold_out or _v.is_sold_out()
        _v.remaining = _v.quantity_available()
    all_variants_sold_out = bool(variants) and all(_v.sold_out for _v in variants)

    return render(request, 'portal/catalog/service_detail.html', {
        'service': service,
        'event': service.event,
        'variants': variants,
        'all_variants_sold_out': all_variants_sold_out,
    })
