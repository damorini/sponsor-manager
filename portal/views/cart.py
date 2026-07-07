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

    THREAD-SAFE: usa select_for_update() dentro una transazione atomica
    per evitare la creazione di carrelli duplicati quando arrivano due
    richieste simultanee (es. doppio click o due tab del browser).

    Return: (contract, cart, was_created)
    """
    from contracts.models import Contract, ContractKind, ContractStatus
    from contracts.payments import CartSession, CartSessionStatus

    with transaction.atomic():
        # Lock: nessun altro processo puo' SELECT/UPDATE questa riga
        # fino al termine della transazione.
        existing_cart = CartSession.objects.select_for_update().filter(
            contract__sponsor=sponsor,
            contract__event=event,
            contract__contract_kind=ContractKind.ADDON,
            contract__status=ContractStatus.DRAFT,
            status=CartSessionStatus.ACTIVE,
        ).select_related('contract').first()

        if existing_cart:
            existing_cart.last_activity_at = timezone.now()
            existing_cart.save(update_fields=['last_activity_at', 'updated_at'])
            return existing_cart.contract, existing_cart, False

        # Trova il contratto principale (per parent_contract)
        parent = Contract.objects.filter(
            sponsor=sponsor,
            event=event,
            status__in=[ContractStatus.SIGNED, ContractStatus.ACTIVE],
            contract_kind=ContractKind.MAIN,
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
            origin='ecommerce',
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
    # Aggiunge un servizio (o una sua variante) al carrello.
    from django.db.models import Sum
    from catalog.models import Service, ServiceVariant
    from contracts.models import Contract, ContractLine, ContractStatus
    from events.models import Event

    service_id = request.POST.get('service_id')
    event_id = request.POST.get('event_id')
    variant_id = request.POST.get('variant_id') or None
    try:
        quantity = int(request.POST.get('quantity', 1))
    except (TypeError, ValueError):
        quantity = 1
    quantity = max(1, min(quantity, 100))

    if not service_id:
        messages.error(request, "Servizio non specificato.")
        return redirect('portal:catalog')

    service = get_object_or_404(
        Service, id=service_id, is_active=True, is_self_purchasable=True,
    )
    event = service.event

    # Evento archiviato: niente acquisti.
    if not event.is_active:
        messages.error(request, "Questo evento è archiviato: non è più possibile acquistare.")
        return redirect('portal:catalog')

    # Se il servizio ha varianti attive, una va scelta
    variant = None
    if service.variants.filter(is_active=True).exists():
        if not variant_id:
            messages.error(request, f"Scegli un'opzione per '{service.translated('name')}'.")
            return redirect('portal:service_detail', service_id=service.id)
        variant = get_object_or_404(
            ServiceVariant, id=variant_id, service=service, is_active=True,
        )

    etichetta = service.translated('name') + (f" - {variant.label}" if variant else "")

    # Verifica cutoff
    today = date.today()
    days_to_event = (event.start_date - today).days
    if service.self_purchase_cutoff_days is not None and days_to_event < service.self_purchase_cutoff_days:
        messages.error(request, f"Il termine per acquistare '{etichetta}' è scaduto.")
        return redirect('portal:service_detail', service_id=service.id)

    # Trova/crea contratto carrello
    try:
        contract, cart, was_created = _get_or_create_cart_contract(
            request.sponsor, event, request.contact
        )
    except ValueError as e:
        messages.error(request, str(e))
        return redirect('portal:catalog')

    existing_line = contract.lines.filter(service=service, service_variant=variant).first()

    # Disponibilita': applica SIA il limite del servizio SIA quello della variante
    limiti = []
    if service.total_available is not None:
        avail_srv = service.quantity_available(exclude_contract_id=contract.id)
        in_cart_srv = contract.lines.filter(service=service).aggregate(s=Sum('quantity'))['s'] or 0
        limiti.append(avail_srv - in_cart_srv)
    if variant is not None and variant.total_available is not None:
        avail_var = variant.quantity_available(exclude_contract_id=contract.id)
        in_cart_var = existing_line.quantity if existing_line else 0
        limiti.append(avail_var - in_cart_var)
    if limiti:
        max_addable = max(0, min(limiti))
        if max_addable <= 0:
            messages.error(
                request,
                f"'{etichetta}' non e' piu' disponibile nella quantita' richiesta."
            )
            return redirect('portal:service_detail', service_id=service.id)
        if quantity > max_addable:
            quantity = max_addable
            messages.warning(
                request,
                f"Disponibili solo {max_addable}; ho adeguato la quantita'."
            )

    prezzo = variant.base_price if variant is not None else service.base_price

    if existing_line:
        existing_line.quantity = (existing_line.quantity or 0) + quantity
        existing_line.save()
        messages.success(request, f"Quantità di '{etichetta}' aggiornata.")
    else:
        line = ContractLine.objects.create(
            contract=contract,
            service=service,
            service_variant=variant,
            variant_label_snapshot=(variant.label if variant else ''),
            service_name_snapshot=service.translated(
                'name', getattr(contract, 'language', None) or 'it'),
            service_description_snapshot=service.translated(
                'description', getattr(contract, 'language', None) or 'it'),
            quantity=quantity,
            unit_price=prezzo,
            vat_rate=service.vat_rate,
        )
        line.save()
        messages.success(request, f"'{etichetta}' aggiunto al carrello.")

    contract.recalculate_totals()
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

    # Le righe 'incluse' (accessori) non si rimuovono singolarmente:
    # vanno via solo insieme al loro servizio padre.
    if line.is_included:
        messages.error(request, "Non puoi rimuovere un servizio incluso. "
                                "Rimuovi il servizio principale per eliminarlo.")
        return redirect('portal:cart_view')

    contract = line.contract
    service_name = line.service_name_snapshot

    # Cascade: se questa riga e' 'padre' di righe incluse, eliminale insieme.
    # Il marker dei figli e' '[incluso:<parent_code>>...'.
    if line.service_id:
        parent_code = line.service.code or str(line.service_id)
        marker_prefix = "[incluso:%s>" % parent_code
        contract.lines.filter(notes__startswith=marker_prefix).delete()

    line.delete()  # ContractLine.delete() richiama gia' recalculate_totals

    contract.refresh_from_db()
    contract.recalculate_totals()  # save=True di default

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

    # La quantita' delle righe 'incluse' (accessori) e' fissata dall'admin
    # e non puo' essere cambiata dal cliente.
    if line.is_included:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False,
                                 'error': 'Quantita\' bloccata: servizio incluso.'},
                                status=400)
        messages.error(request, "Non puoi modificare la quantita' di un servizio incluso.")
        return redirect('portal:cart_view')

    try:
        new_quantity = int(request.POST.get('quantity', 1))
    except (TypeError, ValueError):
        new_quantity = 1
    new_quantity = max(1, min(new_quantity, 100))

    line.quantity = new_quantity
    line.save()  # save() ricalcola i totali della riga e del contratto

    contract = line.contract
    contract.recalculate_totals()  # save=True di default

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

    # Controllo finale disponibilità: nessuna riga puo' superare il disponibile
    from django.db.models import Sum
    esauriti = []
    adeguate = []
    cambi = False
    for line in contract.lines.all():
        srv = line.service
        var = line.service_variant
        limiti = []
        if srv is not None and srv.total_available is not None:
            av = srv.quantity_available(exclude_contract_id=contract.id)
            altri = (contract.lines.filter(service=srv).exclude(id=line.id)
                     .aggregate(s=Sum('quantity'))['s'] or 0)
            limiti.append(av - altri)
        if var is not None and var.total_available is not None:
            avv = var.quantity_available(exclude_contract_id=contract.id)
            altriv = (contract.lines.filter(service=srv, service_variant=var).exclude(id=line.id)
                      .aggregate(s=Sum('quantity'))['s'] or 0)
            limiti.append(avv - altriv)
        if not limiti:
            continue
        massimo = min(limiti)
        nome = line.service_name_snapshot + (
            f" \u2013 {line.variant_label_snapshot}" if line.variant_label_snapshot else "")
        if massimo < 1:
            esauriti.append(nome)
        elif line.quantity > massimo:
            line.quantity = massimo
            line.save()
            cambi = True
            adeguate.append(f"{nome}: max {massimo}")
    if cambi:
        contract.recalculate_totals()
    if esauriti:
        messages.error(
            request,
            "Non più disponibili: " + ", ".join(esauriti) +
            ". Rimuovili dal carrello per procedere."
        )
        return redirect('portal:cart_view')
    if adeguate:
        messages.warning(
            request,
            "Disponibilità aggiornata, quantità adeguata al massimo \u2014 " + "; ".join(adeguate)
        )

    return render(request, 'portal/cart/checkout.html', {
        'contract': contract,
        'event': contract.event,
    })
