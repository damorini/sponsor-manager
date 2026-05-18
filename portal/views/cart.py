"""
View del carrello acquisti.

Implementa la logica con CartSession + Contract di tipo ADDON.

Funzionamento:
- L'utente può avere UN SOLO carrello attivo PER EVENTO (vincolo logico, non
  enforced a DB)
- Aggiungere un servizio crea (o riusa) un CartSession ACTIVE per quell'evento
- Il CartSession è collegato a un Contract DRAFT con kind=ADDON e parent_contract
  = al primo contratto SIGNED/ACTIVE dello sponsor per quell'evento
- Le righe sono ContractLine sul contract draft

Quando l'utente checkout:
- Il contract draft passa a PENDING_PAYMENT
- Si avvia il flow PayPal classico (riusa start_paypal_checkout / card_checkout_page)
- A pagamento completato, il contract diventa SIGNED → ACTIVE
"""
import logging
from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.db import transaction
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from portal.views.dashboard import sponsor_required

logger = logging.getLogger(__name__)


# ============================================================================
# Helper: trova/crea contratto carrello per un evento
# ============================================================================

def _get_or_create_cart_contract(sponsor, event, contact):
    """
    Trova o crea un Contract DRAFT (con kind=ADDON) che funge da carrello
    per uno sponsor/evento.
    
    Return: (contract, was_created)
    """
    from contracts.models import Contract, ContractKind, ContractStatus
    from contracts.payments import CartSession, CartSessionStatus

    # Cerca un cart attivo
    existing_cart = CartSession.objects.filter(
        contract__sponsor=sponsor,
        contract__event=event,
        contract__contract_kind=ContractKind.ADDON,
        contract__status=ContractStatus.DRAFT,
        status=CartSessionStatus.ACTIVE,
    ).select_related('contract').first()

    if existing_cart:
        # Aggiorna last_activity
        existing_cart.last_activity_at = timezone.now()
        existing_cart.save(update_fields=['last_activity_at', 'updated_at'])
        return existing_cart.contract, existing_cart, False

    # Trova il contratto principale (per parent_contract)
    parent = Contract.objects.filter(
        sponsor=sponsor,
        event=event,
        status__in=[ContractStatus.SIGNED, ContractStatus.ACTIVE],
        contract_kind=ContractKind.STANDARD,
        deleted_at__isnull=True,
    ).first()

    if not parent:
        raise ValueError(
            "Nessun contratto standard attivo per questo evento. "
            "Impossibile creare carrello addon."
        )

    # Crea nuovo Contract draft + CartSession
    contract = Contract.objects.create(
        sponsor=sponsor,
        event=event,
        contract_kind=ContractKind.ADDON,
        parent_contract=parent,
        status=ContractStatus.DRAFT,
        language=contact.preferred_language or 'it',
        origin='portal_self_service',
        # Eredita dati fiscali dal parent (snapshot)
        billing_legal_name=parent.billing_legal_name,
        billing_vat_number=parent.billing_vat_number,
        billing_tax_code=parent.billing_tax_code,
        billing_address=parent.billing_address,
        billing_email=parent.billing_email,
        billing_pec=parent.billing_pec,
        billing_sdi_code=parent.billing_sdi_code,
        vat_rate=parent.vat_rate,
        currency=parent.currency,
    )

    cart = CartSession.objects.create(
        contract=contract,
        contact=contact,
        status=CartSessionStatus.ACTIVE,
        last_activity_at=timezone.now(),
    )

    logger.info(
        "Cart creato: sponsor=%s event=%s contract=%s",
        sponsor.id, event.id, contract.id
    )
    return contract, cart, True


# ============================================================================
# View: visualizza carrello
# ============================================================================

@sponsor_required
def cart_view(request):
    """Mostra tutti i carrelli attivi dello sponsor (uno per evento)."""
    from contracts.models import Contract, ContractKind, ContractStatus
    from contracts.payments import CartSession, CartSessionStatus

    carts = CartSession.objects.filter(
        contract__sponsor=request.sponsor,
        contract__contract_kind=ContractKind.ADDON,
        contract__status=ContractStatus.DRAFT,
        status=CartSessionStatus.ACTIVE,
    ).select_related(
        'contract', 'contract__event'
    ).prefetch_related('contract__lines__service')

    # Calcola is_within_cutoff per ciascuna riga
    today = date.today()
    cart_data = []
    for cart in carts:
        contract = cart.contract
        event = contract.event
        days_to_event = (event.start_date - today).days

        lines_data = []
        for line in contract.lines.all():
            cutoff = line.service.self_purchase_cutoff_days
            if cutoff is None:
                is_valid = True
                cutoff_remaining = None
            else:
                cutoff_remaining = days_to_event - cutoff
                is_valid = cutoff_remaining >= 0

            lines_data.append({
                'line': line,
                'is_valid': is_valid,
                'cutoff_remaining': cutoff_remaining,
            })

        cart_data.append({
            'cart': cart,
            'contract': contract,
            'event': event,
            'lines': lines_data,
            'has_invalid_lines': any(not ld['is_valid'] for ld in lines_data),
        })

    return render(request, 'portal/cart/view.html', {
        'cart_data': cart_data,
        'is_empty': not cart_data,
    })


# ============================================================================
# View: aggiungi al carrello
# ============================================================================

@sponsor_required
@require_POST
@transaction.atomic
def cart_add_view(request):
    """Aggiunge un servizio al carrello."""
    from catalog.models import Service
    from contracts.models import Contract, ContractLine, ContractStatus
    from events.models import Event

    service_id = request.POST.get('service_id')
    event_id = request.POST.get('event_id')
    try:
        quantity = int(request.POST.get('quantity', 1))
    except (TypeError, ValueError):
        quantity = 1
    quantity = max(1, min(quantity, 100))

    if not service_id:
        messages.error(request, "Servizio non specificato.")
        return redirect('portal:catalog')

    service = get_object_or_404(
        Service,
        id=service_id,
        is_active=True,
        is_self_purchasable=True,
    )

    event = service.event

    # Verifica cutoff
    today = date.today()
    days_to_event = (event.start_date - today).days
    if service.self_purchase_cutoff_days is not None:
        if days_to_event < service.self_purchase_cutoff_days:
            messages.error(
                request,
                f"Il termine per acquistare '{service.name}' è scaduto."
            )
            return redirect('portal:service_detail', service_id=service.id)

    # Trova/crea contratto carrello
    try:
        contract, cart, was_created = _get_or_create_cart_contract(
            request.sponsor, event, request.contact
        )
    except ValueError as e:
        messages.error(request, str(e))
        return redirect('portal:catalog')

    # Verifica se la riga esiste già (stesso service nel cart)
    existing_line = contract.lines.filter(service=service).first()

    if existing_line:
        # Aumenta quantità
        existing_line.quantity = (existing_line.quantity or 0) + quantity
        existing_line.recalc_totals()
        existing_line.save()
        messages.success(
            request,
            f"Quantità di '{service.name}' aggiornata."
        )
    else:
        # Crea nuova riga
        line = ContractLine.objects.create(
            contract=contract,
            service=service,
            service_name_snapshot=service.name,
            service_description_snapshot=service.description,
            quantity=quantity,
            unit_price=service.unit_price,
            vat_rate=service.vat_rate,
        )
        line.recalc_totals()
        line.save()
        messages.success(
            request,
            f"'{service.name}' aggiunto al carrello."
        )

    # Ricalcola totali contratto
    contract.recalc_totals()
    contract.save()

    return redirect('portal:cart_view')


# ============================================================================
# View: rimuovi dal carrello
# ============================================================================

@sponsor_required
@require_POST
@transaction.atomic
def cart_remove_view(request, line_id):
    """Rimuove una riga dal carrello."""
    from contracts.models import ContractLine, ContractStatus

    line = get_object_or_404(
        ContractLine.objects.select_related('contract'),
        id=line_id,
    )

    # Verifica accesso (la riga deve essere su un contract dello sponsor in DRAFT)
    if line.contract.sponsor_id != request.sponsor.id:
        return HttpResponseForbidden("Accesso negato.")
    if line.contract.status != ContractStatus.DRAFT:
        messages.error(request, "Non puoi modificare un carrello già confermato.")
        return redirect('portal:cart_view')

    contract = line.contract
    service_name = line.service_name_snapshot

    line.delete()

    contract.recalc_totals()
    contract.save()

    # Se il contract è rimasto vuoto, marca cart come abbandonato/expired
    if not contract.lines.exists():
        from contracts.payments import CartSession, CartSessionStatus
        CartSession.objects.filter(contract=contract).update(
            status=CartSessionStatus.EXPIRED,
            updated_at=timezone.now(),
        )

    messages.success(request, f"'{service_name}' rimosso dal carrello.")
    return redirect('portal:cart_view')


# ============================================================================
# View: aggiorna quantità (AJAX)
# ============================================================================

@sponsor_required
@require_POST
@transaction.atomic
def cart_update_quantity_view(request, line_id):
    """Aggiorna quantità di una riga (anche via AJAX)."""
    from contracts.models import ContractLine, ContractStatus

    line = get_object_or_404(
        ContractLine.objects.select_related('contract'),
        id=line_id,
    )

    if line.contract.sponsor_id != request.sponsor.id:
        return HttpResponseForbidden("Accesso negato.")
    if line.contract.status != ContractStatus.DRAFT:
        return JsonResponse({'success': False, 'error': 'Carrello già confermato'}, status=400)

    try:
        new_quantity = int(request.POST.get('quantity', 1))
    except (TypeError, ValueError):
        new_quantity = 1
    new_quantity = max(1, min(new_quantity, 100))

    line.quantity = new_quantity
    line.recalc_totals()
    line.save()

    contract = line.contract
    contract.recalc_totals()
    contract.save()

    # AJAX: ritorna JSON con totali aggiornati
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'line_total': str(line.line_total),
            'contract_subtotal': str(contract.subtotal),
            'contract_vat': str(contract.vat_amount),
            'contract_total': str(contract.total),
        })

    messages.success(request, "Quantità aggiornata.")
    return redirect('portal:cart_view')


# ============================================================================
# View: checkout review (riepilogo finale prima di pagare)
# ============================================================================

@sponsor_required
def cart_checkout_view(request, contract_id):
    """
    Pagina di riepilogo pre-pagamento.
    
    Mostra ricapitolazione carrello + scelta metodo pagamento.
    Da qui i bottoni portano al flow PayPal già implementato.
    """
    from contracts.models import Contract, ContractStatus

    contract = get_object_or_404(
        Contract.objects.select_related('event', 'sponsor').prefetch_related('lines__service'),
        id=contract_id,
        sponsor=request.sponsor,
        status=ContractStatus.DRAFT,
    )

    # Verifica che le righe siano ancora valide (cutoff)
    today = date.today()
    days_to_event = (contract.event.start_date - today).days

    invalid_lines = []
    for line in contract.lines.all():
        cutoff = line.service.self_purchase_cutoff_days
        if cutoff is not None and days_to_event < cutoff:
            invalid_lines.append(line)

    if invalid_lines:
        messages.error(
            request,
            "Alcuni servizi nel carrello sono scaduti. Rimuovili prima di procedere."
        )
        return redirect('portal:cart_view')

    if not contract.lines.exists():
        messages.warning(request, "Il carrello è vuoto.")
        return redirect('portal:cart_view')

    return render(request, 'portal/cart/checkout.html', {
        'contract': contract,
        'event': contract.event,
    })
