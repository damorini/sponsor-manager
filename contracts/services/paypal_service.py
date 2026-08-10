"""
Service layer per integrazione PayPal.

Gestisce:
- Creazione ordini PayPal (sia per checkout standard che per carta diretta)
- Cattura del pagamento dopo approvazione
- Verifica firma webhook (sicurezza)
- Mapping tra ordini PayPal e modelli interni Payment

SDK usato: paypal-server-sdk (versione 2.2.0+, gennaio 2026).
Documentazione: https://developer.paypal.com/docs/api/orders/v2/

Modalità supportate:
- sandbox: per test, account fittizi, zero soldi reali
- live: produzione

Configurazione via settings:
    PAYPAL_MODE = 'sandbox' | 'live'
    PAYPAL_CLIENT_ID = '...'
    PAYPAL_CLIENT_SECRET = '...'
    PAYPAL_WEBHOOK_ID = '...'  # configurato nel dashboard PayPal Developer
"""
import json
import logging
from decimal import Decimal
from typing import Optional

from django.conf import settings
from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)


# ============================================================================
# Client PayPal (lazy init)
# ============================================================================

_paypal_client = None


def get_paypal_client():
    """
    Restituisce il client PayPal inizializzato (singleton lazy).
    
    Importa l'SDK solo quando serve, così se PayPal non è configurato
    il resto dell'app continua a funzionare.
    """
    global _paypal_client

    if _paypal_client is not None:
        return _paypal_client

    try:
        from paypalserversdk.configuration import Environment
        from paypalserversdk.http.auth.o_auth_2 import ClientCredentialsAuthCredentials
        from paypalserversdk.paypal_serversdk_client import PaypalServersdkClient
    except ImportError as e:
        raise RuntimeError(
            "paypal-server-sdk non installato. "
            "Esegui: pip install paypal-server-sdk==2.2.0"
        ) from e

    # Verifica che le credenziali siano configurate
    client_id = getattr(settings, 'PAYPAL_CLIENT_ID', '')
    client_secret = getattr(settings, 'PAYPAL_CLIENT_SECRET', '')
    if not client_id or not client_secret:
        raise RuntimeError(
            "PAYPAL_CLIENT_ID e PAYPAL_CLIENT_SECRET devono essere configurate "
            "nel file .env. Crea credenziali su https://developer.paypal.com"
        )

    mode = getattr(settings, 'PAYPAL_MODE', 'sandbox').lower()
    environment = Environment.SANDBOX if mode == 'sandbox' else Environment.PRODUCTION

    _paypal_client = PaypalServersdkClient(
        client_credentials_auth_credentials=ClientCredentialsAuthCredentials(
            o_auth_client_id=client_id,
            o_auth_client_secret=client_secret,
        ),
        environment=environment,
    )

    logger.info("PayPal client inizializzato (mode: %s)", mode)
    return _paypal_client


# ============================================================================
# Creazione ordine PayPal
# ============================================================================

def _response_to_dict(response):
    """Normalizza la risposta dell'SDK PayPal (ApiResponse) in un dict semplice.

    L'SDK espone la risposta sia come oggetto tipizzato (.body -> Order/Order
    catturato) sia come JSON grezzo (.text). Usiamo il JSON grezzo cosi' il resto
    del codice puo' fare .get(...) e la risposta resta serializzabile nel
    JSONField paypal_response. Fallback difensivi se .text mancasse.
    """
    raw = getattr(response, 'text', None)
    if isinstance(raw, str) and raw.strip():
        try:
            return json.loads(raw)
        except Exception:
            pass
    body = getattr(response, 'body', response)
    if isinstance(body, dict):
        return body
    if isinstance(body, str):
        try:
            return json.loads(body)
        except Exception:
            return {}
    # Oggetto tipizzato senza .text: serializza via __dict__ come ultima spiaggia.
    try:
        return json.loads(json.dumps(body, default=lambda o: getattr(o, '__dict__', str(o))))
    except Exception:
        return {}


def create_paypal_order(payment, return_url=None, cancel_url=None):
    """
    Crea un ordine PayPal per un Payment esistente.
    
    Args:
        payment: istanza Payment (deve essere status=PENDING, method=PAYPAL)
        return_url: URL dove PayPal redirige dopo approvazione
        cancel_url: URL dove PayPal redirige se utente annulla
    
    Returns:
        dict con keys: order_id, approval_url
        
    Raises:
        ValidationError se i parametri sono sbagliati
        RuntimeError se PayPal API ritorna errore
    """
    from contracts.payments import PaymentMethodChoice, PaymentStatus

    if payment.payment_method != PaymentMethodChoice.PAYPAL:
        raise ValidationError("Payment method deve essere 'paypal'")
    if payment.status != PaymentStatus.PENDING:
        raise ValidationError(
            f"Payment già processato (status: {payment.status})"
        )

    contract = payment.contract
    sponsor = contract.sponsor

    # Default URLs (sovrascrivibili)
    site_url = getattr(settings, 'SITE_URL', 'http://localhost:8000')
    if not return_url:
        return_url = f"{site_url}/portal/checkout/return/{payment.id}/"
    if not cancel_url:
        cancel_url = f"{site_url}/portal/checkout/cancel/{payment.id}/"

    # Costruisci request body PayPal.
    # breakdown+items SOLO se l'importo del pagamento coincide col totale del
    # contratto: per importi parziali (residuo dopo pagamenti precedenti) o
    # righe scontate, un breakdown incoerente fa rifiutare l'ordine a PayPal
    # (422 AMOUNT_MISMATCH) e il checkout resta bloccato per sempre.
    amount_block = {
        "currency_code": payment.currency,
        "value": str(payment.amount_gross),
    }
    include_items = (payment.amount_gross == contract.total)
    if include_items:
        amount_block["breakdown"] = {
            "item_total": {
                "currency_code": payment.currency,
                "value": str(contract.subtotal),
            },
            "tax_total": {
                "currency_code": payment.currency,
                "value": str(contract.vat_amount),
            },
        }
    request_body = {
        "intent": "CAPTURE",
        "purchase_units": [{
            "reference_id": str(payment.id),
            "description": f"Sponsor {contract.contract_kind} - {contract.contract_number}",
            "custom_id": str(payment.id),  # nostro id per tracking
            "invoice_id": contract.contract_number,
            "amount": amount_block,
            **({"items": _build_items_from_contract(contract, payment.currency)}
               if include_items else {}),
            "payee": {
                "merchant_id": getattr(settings, 'PAYPAL_MERCHANT_ID', None),
            } if getattr(settings, 'PAYPAL_MERCHANT_ID', None) else None,
        }],
        "payment_source": {
            "paypal": {
                "experience_context": {
                    "brand_name": getattr(
                        settings, 'ORGANIZER_DISPLAY_NAME', 'Sponsor Manager'
                    ),
                    "locale": "it-IT" if contract.language == 'it' else "en-US",
                    "landing_page": "LOGIN",
                    "shipping_preference": "NO_SHIPPING",
                    "user_action": "PAY_NOW",
                    "return_url": return_url,
                    "cancel_url": cancel_url,
                },
            },
        },
    }

    # Pulisci campi None (PayPal è schizzinoso)
    if not request_body["purchase_units"][0].get("payee"):
        del request_body["purchase_units"][0]["payee"]

    client = get_paypal_client()
    orders_controller = client.orders

    try:
        response = orders_controller.create_order({
            "body": request_body,
            "prefer": "return=representation",  # restituisce ordine completo
        })
        order_data = _response_to_dict(response)
    except Exception as e:
        logger.exception("Errore creazione ordine PayPal per payment %s", payment.id)
        raise RuntimeError(f"PayPal API error: {e}") from e

    order_id = order_data.get('id')
    if not order_id:
        raise RuntimeError(f"PayPal non ha restituito order_id: {order_data}")

    # Estrai approval URL
    approval_url = None
    for link in order_data.get('links', []):
        if link.get('rel') == 'approve' or link.get('rel') == 'payer-action':
            approval_url = link.get('href')
            break

    # Salva order_id sul Payment
    payment.paypal_order_id = order_id
    payment.paypal_response = order_data
    payment.save(update_fields=['paypal_order_id', 'paypal_response', 'updated_at'])

    logger.info(
        "Ordine PayPal creato: payment=%s order_id=%s",
        payment.id, order_id
    )

    return {
        'order_id': order_id,
        'approval_url': approval_url,
        'raw_response': order_data,
    }


def _build_items_from_contract(contract, currency):
    """Costruisce la lista 'items' per PayPal dalle ContractLine.

    Ogni riga viene rappresentata come UN item con il suo imponibile
    POST-sconto (line_subtotal): PayPal verifica che la somma degli items
    coincida con breakdown.item_total (= contract.subtotal), quindi usare
    quantita' x prezzo pre-sconto farebbe rifiutare gli ordini con sconti."""
    items = []
    for line in contract.lines.all():
        nome = line.service_name_snapshot
        if line.quantity and line.quantity > 1:
            nome = f"{nome} x{line.quantity}"
        items.append({
            "name": nome[:127],  # limite PayPal
            "quantity": "1",
            "unit_amount": {
                "currency_code": currency,
                "value": str(line.line_subtotal),
            },
            "category": "DIGITAL_GOODS",  # servizi digitali, no shipping
        })
    return items


# ============================================================================
# Stato ordine
# ============================================================================

def get_paypal_order_status(order_id):
    """Stato attuale di un ordine PayPal: 'CREATED' (vergine), 'APPROVED',
    'PAYER_ACTION_REQUIRED' (flusso lasciato a meta', es. MyBank abbandonato),
    'COMPLETED', 'VOIDED'. Solleva eccezione se l'ordine non esiste o la
    chiamata fallisce."""
    client = get_paypal_client()
    response = client.orders.get_order({'id': order_id})
    data = _response_to_dict(response)
    return data.get('status')


# ============================================================================
# Cattura ordine (dopo approvazione utente)
# ============================================================================

def capture_paypal_order(order_id):
    """
    Cattura il pagamento di un ordine PayPal approvato dall'utente.
    
    Da chiamare nel return URL handler dopo che l'utente ha approvato.
    Aggiorna il Payment associato con i dati della cattura.
    
    Args:
        order_id: ID ordine PayPal
    
    Returns:
        dict con risultato della cattura (status, capture_id, ecc.)
    
    Raises:
        Payment.DoesNotExist se l'ordine non corrisponde a nessun Payment
        RuntimeError se la cattura fallisce
    """
    from django.db import transaction
    from contracts.payments import Payment, PaymentStatus

    # Serializza le catture concorrenti sullo stesso ordine (return-URL del
    # cliente + webhook PayPal possono arrivare quasi insieme): il primo
    # prende il lock, cattura e marca SUCCEEDED; il secondo resta in attesa
    # e al risveglio vede SUCCEEDED -> esce dal ramo idempotente, invece di
    # ricevere ORDER_ALREADY_CAPTURED da PayPal e marcare FAILED un
    # pagamento in realta' riuscito.
    with transaction.atomic():
        try:
            payment = Payment.objects.select_for_update().get(paypal_order_id=order_id)
        except Payment.DoesNotExist:
            logger.error("Nessun Payment trovato per order_id %s", order_id)
            raise

        # Idempotency: se già succeeded, restituisci dati attuali senza richiamare PayPal
        if payment.status == PaymentStatus.SUCCEEDED:
            logger.info("Payment %s già succeeded, skip capture", payment.id)
            return {
                'status': 'COMPLETED',
                'capture_id': payment.paypal_capture_id,
                'already_processed': True,
            }

        client = get_paypal_client()
        orders_controller = client.orders

        try:
            response = orders_controller.capture_order({
                "id": order_id,
                "prefer": "return=representation",
            })
            capture_data = _response_to_dict(response)
        except Exception as e:
            # ORDER_ALREADY_CAPTURED: qualcun altro ha gia' incassato questo
            # ordine (es. run precedente morto dopo la capture ma prima del
            # save). L'addebito e' REALE: trattalo come successo idempotente,
            # non come fallimento.
            if 'ALREADY_CAPTURED' in str(e).upper():
                logger.warning(
                    "Order %s gia' catturato lato PayPal: marco succeeded "
                    "payment %s senza nuova capture", order_id, payment.id)
                payment.mark_succeeded()
                return {
                    'status': 'COMPLETED',
                    'capture_id': payment.paypal_capture_id,
                    'already_processed': True,
                }
            logger.exception("Errore capture order %s", order_id)
            payment.mark_failed(reason=f"PayPal capture error: {e}")
            raise RuntimeError(f"PayPal capture failed: {e}") from e

        # Estrai dati cattura (ancora dentro il lock: la serializzazione deve
        # coprire anche il salvataggio dell'esito, non solo la chiamata API)
        status = capture_data.get('status')
        purchase_units = capture_data.get('purchase_units', [])
        captures = []
        if purchase_units:
            captures = purchase_units[0].get('payments', {}).get('captures', [])

        if status == 'COMPLETED' and captures:
            capture = captures[0]
            capture_id = capture.get('id')

            # Estrai dati payer
            payer = capture_data.get('payer', {})
            payment.paypal_payer_email = payer.get('email_address', '')
            payment.paypal_payer_id = payer.get('payer_id', '')

            # Estrai fee dalla seller_receivable_breakdown
            fee_amount = Decimal('0')
            breakdown = capture.get('seller_receivable_breakdown', {})
            if 'paypal_fee' in breakdown:
                fee_amount = Decimal(breakdown['paypal_fee']['value'])

            payment.amount_fee = fee_amount
            payment.paypal_response = capture_data
            payment.save(update_fields=[
                'paypal_payer_email', 'paypal_payer_id',
                'amount_fee', 'paypal_response', 'updated_at'
            ])

            # Marca come succeeded (questo triggera anche il Contract.mark_payment_succeeded)
            payment.mark_succeeded(paypal_capture_id=capture_id)

            logger.info(
                "Payment %s catturato con successo: capture_id=%s amount=%s",
                payment.id, capture_id, payment.amount_gross
            )

            return {
                'status': 'COMPLETED',
                'capture_id': capture_id,
                'payment_id': str(payment.id),
                'already_processed': False,
            }
        else:
            # Cattura fallita o in stato pending
            reason = capture_data.get('status_details', {}).get('reason', 'unknown')
            payment.mark_failed(reason=f"Capture status: {status}, reason: {reason}")
            raise RuntimeError(f"Cattura PayPal non completata: status={status}")


# ============================================================================
# Verifica firma webhook
# ============================================================================

def verify_webhook_signature(headers: dict, body: str) -> bool:
    """
    Verifica che il webhook ricevuto sia autenticamente da PayPal.
    
    Senza questa verifica, chiunque potrebbe inviare webhook fasulli al tuo
    endpoint e marcare pagamenti come ricevuti.
    
    Args:
        headers: dict di header HTTP della request webhook
        body: body raw (string) della request
    
    Returns:
        True se la firma è valida, False altrimenti
    """
    webhook_id = getattr(settings, 'PAYPAL_WEBHOOK_ID', '')
    if not webhook_id:
        logger.error(
            "PAYPAL_WEBHOOK_ID non configurato, impossibile verificare webhook"
        )
        return False

    client = get_paypal_client()

    try:
        from paypalserversdk.controllers.webhooks_management_controller import (
            WebhooksManagementController
        )
    except ImportError:
        # SDK potrebbe non avere il controller in tutte le versioni;
        # fallback con chiamata HTTP diretta
        return _verify_webhook_signature_http(headers, body, webhook_id)

    # Estrai header richiesti
    required_headers = [
        'paypal-transmission-id',
        'paypal-transmission-time',
        'paypal-cert-url',
        'paypal-auth-algo',
        'paypal-transmission-sig',
    ]
    # Headers HTTP sono case-insensitive: normalizziamo
    normalized = {k.lower(): v for k, v in headers.items()}
    for h in required_headers:
        if h not in normalized:
            logger.warning("Webhook header mancante: %s", h)
            return False

    try:
        webhook_event = json.loads(body) if isinstance(body, str) else body
    except (ValueError, TypeError):
        logger.error("Webhook body non è JSON valido")
        return False

    verification_request = {
        "auth_algo": normalized['paypal-auth-algo'],
        "cert_url": normalized['paypal-cert-url'],
        "transmission_id": normalized['paypal-transmission-id'],
        "transmission_sig": normalized['paypal-transmission-sig'],
        "transmission_time": normalized['paypal-transmission-time'],
        "webhook_id": webhook_id,
        "webhook_event": webhook_event,
    }

    try:
        # API PayPal: POST /v1/notifications/verify-webhook-signature
        # Implementazione dipende dalla versione SDK; questo è il pattern generico
        controller = WebhooksManagementController(client)
        response = controller.verify_webhook_signature({"body": verification_request})
        result = response.body if hasattr(response, 'body') else response
        if isinstance(result, str):
            result = json.loads(result)

        verification_status = result.get('verification_status')
        is_valid = verification_status == 'SUCCESS'

        if not is_valid:
            logger.warning(
                "Verifica webhook fallita: status=%s", verification_status
            )
        return is_valid

    except Exception as e:
        logger.exception("Errore verifica webhook PayPal")
        return False


def _verify_webhook_signature_http(headers, body, webhook_id):
    """
    Fallback: chiamata HTTP diretta all'API verify-webhook-signature.
    
    Usata se il controller SDK non è disponibile in questa versione.
    """
    import requests

    mode = getattr(settings, 'PAYPAL_MODE', 'sandbox').lower()
    base_url = (
        'https://api-m.sandbox.paypal.com' if mode == 'sandbox'
        else 'https://api-m.paypal.com'
    )

    # Ottieni access token
    auth_response = requests.post(
        f'{base_url}/v1/oauth2/token',
        auth=(settings.PAYPAL_CLIENT_ID, settings.PAYPAL_CLIENT_SECRET),
        data={'grant_type': 'client_credentials'},
        timeout=10,
    )
    if auth_response.status_code != 200:
        logger.error("PayPal auth failed: %s", auth_response.text)
        return False
    access_token = auth_response.json()['access_token']

    # Verifica firma
    normalized = {k.lower(): v for k, v in headers.items()}
    try:
        webhook_event = json.loads(body) if isinstance(body, str) else body
    except (ValueError, TypeError):
        return False

    verify_response = requests.post(
        f'{base_url}/v1/notifications/verify-webhook-signature',
        headers={
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
        },
        json={
            "auth_algo": normalized.get('paypal-auth-algo', ''),
            "cert_url": normalized.get('paypal-cert-url', ''),
            "transmission_id": normalized.get('paypal-transmission-id', ''),
            "transmission_sig": normalized.get('paypal-transmission-sig', ''),
            "transmission_time": normalized.get('paypal-transmission-time', ''),
            "webhook_id": webhook_id,
            "webhook_event": webhook_event,
        },
        timeout=10,
    )

    if verify_response.status_code != 200:
        logger.error("Verify webhook HTTP error: %s", verify_response.text)
        return False

    result = verify_response.json()
    return result.get('verification_status') == 'SUCCESS'


# ============================================================================
# Refund (rimborso)
# ============================================================================

def refund_paypal_capture(payment, amount=None, reason=''):
    """
    Rimborsa (parzialmente o totalmente) un pagamento PayPal completato.
    
    Args:
        payment: Payment con status=SUCCEEDED e paypal_capture_id valorizzato
        amount: Decimal, importo da rimborsare. None = rimborso totale.
        reason: stringa con motivo del rimborso
    
    Returns:
        dict con dati del refund
    """
    from contracts.payments import PaymentStatus

    if payment.status != PaymentStatus.SUCCEEDED:
        raise ValidationError("Si possono rimborsare solo pagamenti completati")
    if not payment.paypal_capture_id:
        raise ValidationError("Payment senza paypal_capture_id, impossibile rimborsare")

    refund_amount = amount or payment.amount_gross

    request_body = {
        "amount": {
            "value": str(refund_amount),
            "currency_code": payment.currency,
        },
        "note_to_payer": reason[:255] if reason else "Rimborso",
    }

    client = get_paypal_client()
    payments_controller = client.payments

    try:
        response = payments_controller.refund_captured_payment({
            "capture_id": payment.paypal_capture_id,
            "body": request_body,
        })
        refund_data = response.body if hasattr(response, 'body') else response
        if isinstance(refund_data, str):
            refund_data = json.loads(refund_data)
    except Exception as e:
        logger.exception("Errore refund payment %s", payment.id)
        raise RuntimeError(f"PayPal refund failed: {e}") from e

    # Aggiorna payment status
    new_status = (
        PaymentStatus.REFUNDED if refund_amount >= payment.amount_gross
        else PaymentStatus.PARTIAL_REFUND
    )
    payment.status = new_status
    payment.notes = (
        (payment.notes or '') +
        f"\nRefund {refund_amount}€: {reason} (id: {refund_data.get('id')})"
    )
    payment.save(update_fields=['status', 'notes', 'updated_at'])

    return refund_data
