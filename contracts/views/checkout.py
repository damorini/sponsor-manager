"""
Views per il flusso checkout PayPal.

Endpoint:
- POST /portal/checkout/start/<contract_id>/      → avvia pagamento
- GET  /portal/checkout/return/<payment_id>/      → return URL dopo approvazione
- GET  /portal/checkout/cancel/<payment_id>/      → cancel URL se utente annulla
- POST /webhooks/paypal/                           → webhook handler (esterno)
- POST /portal/checkout/card/<contract_id>/       → pagamento con carta diretto

Tutti gli endpoint sono atomici e idempotenti.
"""
import json
import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_http_methods

logger = logging.getLogger(__name__)


# ============================================================================
# Avvio checkout PayPal Standard (redirect su paypal.com)
# ============================================================================

@login_required
@require_POST
@transaction.atomic
def start_paypal_checkout(request, contract_id):
    """
    Avvia checkout PayPal: crea Payment + ordine PayPal, redirect su PayPal.
    
    Chiamato dal portale sponsor quando l'utente clicca "Paga con PayPal".
    """
    from contracts.models import Contract, ContractStatus
    from contracts.payments import Payment, PaymentMethodChoice, PaymentStatus
    from contracts.services.paypal_service import create_paypal_order

    # Verifica accesso: solo lo sponsor proprietario può pagare
    contract = get_object_or_404(
        Contract.objects.select_related('sponsor', 'event'),
        id=contract_id,
    )

    # Controllo proprietà (lo sponsor user deve essere collegato a un Contact dello sponsor)
    if not _user_owns_contract(request.user, contract):
        return HttpResponse('Forbidden', status=403)

    # Il contratto deve essere in stato pagabile
    if contract.status not in [ContractStatus.DRAFT, ContractStatus.PENDING_PAYMENT]:
        messages.error(request, "Questo contratto non è più pagabile.")
        return redirect('portal:contract_detail', contract_id=contract.id)

    # Se draft, passa a pending_payment
    if contract.status == ContractStatus.DRAFT:
        contract.mark_as_pending_payment()

    # Crea Payment in pending (o riusa esistente non scaduto)
    payment, created = Payment.objects.get_or_create(
        contract=contract,
        status=PaymentStatus.PENDING,
        payment_method=PaymentMethodChoice.PAYPAL,
        defaults={
            'amount_gross': contract.total,
            'currency': 'EUR',
        },
    )

    # Crea ordine PayPal e ottieni approval URL
    try:
        result = create_paypal_order(payment)
    except Exception as e:
        logger.exception("Errore creazione ordine PayPal")
        messages.error(
            request,
            "Errore durante l'avvio del pagamento. Riprova più tardi."
        )
        return redirect('portal:contract_detail', contract_id=contract.id)

    approval_url = result.get('approval_url')
    if not approval_url:
        messages.error(request, "PayPal non ha fornito un URL di approvazione.")
        return redirect('portal:contract_detail', contract_id=contract.id)

    # Redirect su PayPal
    return redirect(approval_url)


# ============================================================================
# Return URL (utente torna dopo aver approvato su PayPal)
# ============================================================================

@login_required
@require_http_methods(['GET'])
def paypal_return(request, payment_id):
    """
    URL dove PayPal redirige dopo che l'utente ha approvato.
    
    Cattura il pagamento e mostra pagina di esito.
    
    Nota: PayPal manda anche un webhook indipendente per la conferma.
    Sia il return URL che il webhook chiamano capture_paypal_order, ma
    grazie all'idempotency solo il primo effettivamente cattura.
    """
    from contracts.payments import Payment
    from contracts.services.paypal_service import capture_paypal_order

    payment = get_object_or_404(Payment.objects.select_related('contract'), id=payment_id)
    contract = payment.contract

    # Verifica accesso
    if not _user_owns_contract(request.user, contract):
        return HttpResponse('Forbidden', status=403)

    # Cattura il pagamento (idempotente)
    try:
        result = capture_paypal_order(payment.paypal_order_id)
    except Exception as e:
        logger.exception("Errore capture nel return URL")
        return render(request, 'portal/checkout/error.html', {
            'contract': contract,
            'payment': payment,
            'error_message': str(e),
        })

    # Pagamento completato
    return render(request, 'portal/checkout/success.html', {
        'contract': contract,
        'payment': payment,
        'capture_id': result.get('capture_id'),
        'already_processed': result.get('already_processed', False),
    })


# ============================================================================
# Cancel URL (utente annulla il pagamento su PayPal)
# ============================================================================

@login_required
@require_http_methods(['GET'])
def paypal_cancel(request, payment_id):
    """URL dove PayPal redirige se l'utente clicca 'Annulla'."""
    from contracts.payments import Payment, PaymentStatus

    payment = get_object_or_404(Payment.objects.select_related('contract'), id=payment_id)

    if not _user_owns_contract(request.user, payment.contract):
        return HttpResponse('Forbidden', status=403)

    # Marca payment come cancellato
    if payment.status == PaymentStatus.PENDING:
        payment.mark_failed(reason='Cancellato dall\'utente')

    messages.warning(
        request,
        "Hai annullato il pagamento. Puoi riprovare quando vuoi."
    )
    return redirect('portal:contract_detail', contract_id=payment.contract.id)


# ============================================================================
# Pagamento con carta diretto (Advanced Card Payments)
# ============================================================================

@login_required
@require_http_methods(['GET'])
def card_checkout_page(request, contract_id):
    """
    Pagina checkout con form carta diretto (PayPal Hosted Fields).
    
    Il form è renderizzato lato client tramite JS SDK PayPal.
    Il template HTML contiene il bootstrap necessario.
    """
    from contracts.models import Contract, ContractStatus
    from contracts.payments import Payment, PaymentMethodChoice, PaymentStatus
    from contracts.services.paypal_service import create_paypal_order

    contract = get_object_or_404(
        Contract.objects.select_related('sponsor', 'event'),
        id=contract_id,
    )

    if not _user_owns_contract(request.user, contract):
        return HttpResponse('Forbidden', status=403)

    if contract.status not in [ContractStatus.DRAFT, ContractStatus.PENDING_PAYMENT]:
        messages.error(request, "Contratto non più pagabile.")
        return redirect('portal:contract_detail', contract_id=contract.id)

    # Passa a pending_payment se necessario
    if contract.status == ContractStatus.DRAFT:
        contract.mark_as_pending_payment()

    # Crea Payment + ordine PayPal (per ottenere order_id da passare al JS SDK)
    payment, _ = Payment.objects.get_or_create(
        contract=contract,
        status=PaymentStatus.PENDING,
        payment_method=PaymentMethodChoice.PAYPAL,
        defaults={
            'amount_gross': contract.total,
            'currency': 'EUR',
        },
    )

    if not payment.paypal_order_id:
        try:
            create_paypal_order(payment)
        except Exception as e:
            logger.exception("Errore creazione ordine carta")
            messages.error(request, "Errore durante l'avvio del pagamento.")
            return redirect('portal:contract_detail', contract_id=contract.id)

    return render(request, 'portal/checkout/card_payment.html', {
        'contract': contract,
        'payment': payment,
        'paypal_client_id': settings.PAYPAL_CLIENT_ID,
        'paypal_order_id': payment.paypal_order_id,
        'amount': contract.total,
        'currency': 'EUR',
    })


@login_required
@require_POST
def card_capture_ajax(request, payment_id):
    """
    Endpoint AJAX chiamato dal JS SDK dopo che l'utente ha confermato la carta.
    
    Cattura il pagamento e restituisce JSON con esito.
    Il client JS poi redirige sulla pagina di success/error.
    """
    from contracts.payments import Payment
    from contracts.services.paypal_service import capture_paypal_order

    payment = get_object_or_404(Payment, id=payment_id)

    if not _user_owns_contract(request.user, payment.contract):
        return JsonResponse({'success': False, 'error': 'Forbidden'}, status=403)

    try:
        result = capture_paypal_order(payment.paypal_order_id)
        return JsonResponse({
            'success': True,
            'capture_id': result.get('capture_id'),
            'redirect_url': reverse(
                'portal:checkout_success', args=[payment.id]
            ),
        })
    except Exception as e:
        logger.exception("Errore capture carta")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# ============================================================================
# Webhook handler (PayPal → server)
# ============================================================================

@csrf_exempt
@require_POST
def paypal_webhook(request):
    """
    Endpoint per webhook PayPal.
    
    PayPal invia eventi qui per ogni cambio di stato di un pagamento.
    Eventi gestiti:
    - PAYMENT.CAPTURE.COMPLETED: pagamento completato (ridondante con return URL)
    - PAYMENT.CAPTURE.DENIED: pagamento rifiutato
    - PAYMENT.CAPTURE.REFUNDED: pagamento rimborsato
    
    Sicurezza:
    - Verifica firma PayPal (OBBLIGATORIA, non disabilitarla)
    - Idempotency via last_webhook_event_id sul Payment
    
    Configura il webhook su PayPal Developer Dashboard con URL pubblico:
        https://gestionale.tuodominio.it/webhooks/paypal/
    """
    from contracts.payments import Payment, PaymentStatus
    from contracts.services.paypal_service import verify_webhook_signature

    # 1. Verifica firma (sicurezza fondamentale)
    if not verify_webhook_signature(dict(request.headers), request.body.decode('utf-8')):
        logger.warning("Webhook PayPal con firma non valida, ignoro")
        return HttpResponse('Invalid signature', status=403)

    # 2. Parse del payload
    try:
        event = json.loads(request.body)
    except json.JSONDecodeError:
        return HttpResponse('Invalid JSON', status=400)

    event_id = event.get('id')
    event_type = event.get('event_type')
    resource = event.get('resource', {})

    logger.info("Webhook PayPal ricevuto: %s (id=%s)", event_type, event_id)

    # 3. Gestisci tipo evento
    if event_type == 'PAYMENT.CAPTURE.COMPLETED':
        return _handle_capture_completed(event_id, resource)
    elif event_type == 'PAYMENT.CAPTURE.DENIED':
        return _handle_capture_denied(event_id, resource)
    elif event_type == 'PAYMENT.CAPTURE.REFUNDED':
        return _handle_capture_refunded(event_id, resource)
    else:
        # Evento non gestito ma rispondiamo 200 per non far ritrasmettere
        logger.info("Webhook event_type non gestito: %s", event_type)
        return HttpResponse('OK (event not handled)', status=200)


def _handle_capture_completed(event_id, resource):
    """Gestisce PAYMENT.CAPTURE.COMPLETED."""
    from contracts.payments import Payment, PaymentStatus

    # Estrai order_id (può essere in supplementary_data.related_ids)
    related_ids = resource.get('supplementary_data', {}).get('related_ids', {})
    order_id = related_ids.get('order_id')

    # Fallback: cerca custom_id (è il payment.id che abbiamo passato)
    if not order_id:
        custom_id = resource.get('custom_id')
        if custom_id:
            try:
                payment = Payment.objects.get(id=custom_id)
            except Payment.DoesNotExist:
                logger.error("Payment %s non trovato (da custom_id)", custom_id)
                return HttpResponse('Payment not found', status=404)
        else:
            logger.error("Webhook senza order_id né custom_id")
            return HttpResponse('Missing references', status=400)
    else:
        try:
            payment = Payment.objects.get(paypal_order_id=order_id)
        except Payment.DoesNotExist:
            logger.error("Payment per order_id %s non trovato", order_id)
            return HttpResponse('Payment not found', status=404)

    # Idempotency check
    if payment.last_webhook_event_id == event_id:
        logger.info("Webhook %s già processato, skip", event_id)
        return HttpResponse('Already processed', status=200)

    if payment.status == PaymentStatus.SUCCEEDED:
        # Già marcato come succeeded (probabilmente dal return URL)
        # Salviamo solo l'event_id per idempotency futura
        payment.last_webhook_event_id = event_id
        payment.save(update_fields=['last_webhook_event_id', 'updated_at'])
        return HttpResponse('Already succeeded', status=200)

    # Marca succeeded
    payment.last_webhook_event_id = event_id
    payment.paypal_capture_id = resource.get('id')
    payment.save(update_fields=[
        'last_webhook_event_id', 'paypal_capture_id', 'updated_at'
    ])
    payment.mark_succeeded(paypal_capture_id=payment.paypal_capture_id)

    return HttpResponse('OK', status=200)


def _handle_capture_denied(event_id, resource):
    """Gestisce PAYMENT.CAPTURE.DENIED."""
    from contracts.payments import Payment

    custom_id = resource.get('custom_id')
    if custom_id:
        try:
            payment = Payment.objects.get(id=custom_id)
            if payment.last_webhook_event_id != event_id:
                payment.last_webhook_event_id = event_id
                payment.save(update_fields=['last_webhook_event_id', 'updated_at'])
                payment.mark_failed(
                    reason=f"Pagamento rifiutato da PayPal: "
                           f"{resource.get('status_details', {}).get('reason', '')}"
                )
        except Payment.DoesNotExist:
            pass

    return HttpResponse('OK', status=200)


def _handle_capture_refunded(event_id, resource):
    """Gestisce PAYMENT.CAPTURE.REFUNDED (può venire anche da admin PayPal)."""
    from contracts.payments import Payment, PaymentStatus
    from decimal import Decimal

    capture_id = resource.get('links', [{}])[0].get('href', '').split('/')[-1]
    # Cerca payment dal capture_id
    try:
        payment = Payment.objects.get(paypal_capture_id=capture_id)
    except Payment.DoesNotExist:
        return HttpResponse('Payment not found', status=404)

    if payment.last_webhook_event_id == event_id:
        return HttpResponse('Already processed', status=200)

    refund_amount = Decimal(resource.get('amount', {}).get('value', '0'))
    new_status = (
        PaymentStatus.REFUNDED if refund_amount >= payment.amount_gross
        else PaymentStatus.PARTIAL_REFUND
    )

    payment.status = new_status
    payment.last_webhook_event_id = event_id
    payment.notes = (payment.notes or '') + f"\nRefund da webhook: {refund_amount}€"
    payment.save(update_fields=['status', 'last_webhook_event_id', 'notes', 'updated_at'])

    return HttpResponse('OK', status=200)


# ============================================================================
# Helper: verifica accesso utente al contratto
# ============================================================================

def _user_owns_contract(user, contract) -> bool:
    """
    Verifica che l'utente sia autorizzato a interagire con questo contratto.
    
    Logica:
    - Admin/operator: accesso a tutti i contratti
    - Sponsor: solo se Contact.portal_user == user E contact.sponsor == contract.sponsor
    """
    if not user.is_authenticated:
        return False

    # Admin/operator hanno accesso totale
    if hasattr(user, 'is_internal_user') and user.is_internal_user:
        return True

    # Sponsor: verifica via Contact
    try:
        contact = user.contact_profile  # OneToOne reverse
    except Exception:
        return False

    return contact.sponsor_id == contract.sponsor_id


@login_required
@require_POST
@transaction.atomic
def dev_mark_paid(request, contract_id):
    """SOLO SVILUPPO: simula pagamento riuscito. Disponibile solo con DEBUG=True."""
    from django.http import Http404
    from contracts.models import Contract, ContractStatus

    if not settings.DEBUG:
        raise Http404()

    contract = get_object_or_404(
        Contract.objects.select_related('sponsor', 'event'),
        id=contract_id,
    )
    if not _user_owns_contract(request.user, contract):
        return HttpResponse('Forbidden', status=403)

    if contract.status == ContractStatus.DRAFT:
        contract.mark_as_pending_payment()
    if contract.status == ContractStatus.PENDING_PAYMENT:
        contract.mark_payment_succeeded()
        messages.success(request, "[DEV] Pagamento simulato: contratto pagato/firmato.")
    else:
        messages.info(request, f"[DEV] Nessuna azione: stato '{contract.get_status_display()}'.")

    return redirect('portal:contract_detail', contract_id=contract.id)
