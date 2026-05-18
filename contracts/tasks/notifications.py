"""
Task Celery on-demand: vengono lanciati esplicitamente da altre parti del codice
quando succede qualcosa.

Esempi d'uso:
    # In Contract.mark_as_signed():
    from contracts.tasks.notifications import send_contract_signed_notification
    send_contract_signed_notification.delay(self.id)
    
    # In Payment.mark_succeeded():
    from contracts.tasks.notifications import send_payment_confirmation_notification
    send_payment_confirmation_notification.delay(self.id)

Tutti i task qui usano @shared_task così funzionano sia con Celery che senza
(in development con CELERY_TASK_ALWAYS_EAGER=True girano sincroni).

Idempotency: i task sono pensati per essere richiamabili più volte senza
side effects multipli — la verifica avviene a livello di logica (es. controllo
stato del contratto, presenza di Communication già inviata, ecc.).
"""
import logging

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


# ============================================================================
# Notifica contratto firmato (con PDF allegato)
# ============================================================================

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_contract_signed_notification(self, contract_id):
    """
    Invia email di conferma contratto firmato con PDF allegato.
    
    Triggerato da: Contract.mark_as_signed()
    Destinatari: firmatario + marketing + operational dello sponsor
    """
    from contracts.models import Contract
    from contracts.services.email_sender import send_email, get_recipients_for_contract
    from contracts.services.pdf_generator import generate_contract_pdf

    try:
        contract = Contract.objects.select_related('sponsor', 'event').get(pk=contract_id)
    except Contract.DoesNotExist:
        logger.error("Contract %s non trovato per notifica firmato", contract_id)
        return

    # Destinatari: firmatario + marketing + operational
    recipients = get_recipients_for_contract(
        contract, roles=['signer', 'marketing', 'operational']
    )
    if not recipients:
        logger.warning("Nessun destinatario per contratto %s", contract.contract_number)
        return

    # Genera PDF e prepara allegato
    pdf_attachment = None
    try:
        document = generate_contract_pdf(contract)
        # Leggi il file salvato
        from django.conf import settings
        from pathlib import Path
        # storage_url include MEDIA_URL prefix; ricostruisco il path locale
        relative = document.storage_url.replace(settings.MEDIA_URL, '')
        pdf_path = Path(settings.MEDIA_ROOT) / relative
        if pdf_path.exists():
            pdf_attachment = (
                document.file_name,
                pdf_path.read_bytes(),
                'application/pdf',
            )
    except Exception as e:
        logger.warning(
            "Impossibile generare PDF per %s: %s. Mando email senza allegato.",
            contract.contract_number, e
        )

    # Determina lingua
    language = contract.language or 'it'

    # Costruisci context
    primary_contact = contract.sponsor.contacts.filter(is_primary=True).first()
    if not primary_contact:
        primary_contact = contract.sponsor.contacts.first()

    event_name = (
        contract.event.get_name(language)
        if hasattr(contract.event, 'get_name')
        else str(contract.event.name)
    )

    context = {
        'contract': contract,
        'sponsor': contract.sponsor,
        'event': contract.event,
        'event_name': event_name,
        'contact': primary_contact,
        'has_deadlines': contract.deadlines.exists(),
    }

    # Subject in lingua
    if language == 'en':
        subject = f"Contract {contract.contract_number} confirmed · {event_name}"
    else:
        subject = f"Contratto {contract.contract_number} confermato · {event_name}"

    try:
        send_email(
            template_name='contract_signed',
            context=context,
            to=recipients,
            subject=subject,
            language=language,
            attachments=[pdf_attachment] if pdf_attachment else None,
            related_to=contract,
            communication_type='initial_send',
            is_automated=True,
        )
    except Exception as e:
        logger.exception("Errore invio notifica contratto firmato %s", contract_id)
        raise self.retry(exc=e)


# ============================================================================
# Conferma pagamento ricevuto
# ============================================================================

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_payment_confirmation_notification(self, payment_id):
    """
    Invia email di conferma pagamento ricevuto.
    
    Triggerato da: Payment.mark_succeeded()
    """
    from contracts.payments import Payment
    from contracts.services.email_sender import send_email, get_recipients_for_contract

    try:
        payment = Payment.objects.select_related(
            'contract__sponsor', 'contract__event'
        ).get(pk=payment_id)
    except Payment.DoesNotExist:
        logger.error("Payment %s non trovato", payment_id)
        return

    contract = payment.contract

    # Destinatari: firmatario + finance + operational
    recipients = get_recipients_for_contract(
        contract, roles=['signer', 'finance', 'operational']
    )
    if not recipients:
        logger.warning("Nessun destinatario per payment %s", payment_id)
        return

    language = contract.language or 'it'
    primary_contact = contract.sponsor.contacts.filter(is_primary=True).first()
    if not primary_contact:
        primary_contact = contract.sponsor.contacts.first()

    event_name = (
        contract.event.get_name(language)
        if hasattr(contract.event, 'get_name')
        else str(contract.event.name)
    )

    context = {
        'payment': payment,
        'contract': contract,
        'sponsor': contract.sponsor,
        'event': contract.event,
        'event_name': event_name,
        'contact': primary_contact,
    }

    if language == 'en':
        subject = f"Payment received · {contract.contract_number}"
    else:
        subject = f"Pagamento ricevuto · {contract.contract_number}"

    try:
        send_email(
            template_name='payment_confirmation',
            context=context,
            to=recipients,
            subject=subject,
            language=language,
            related_to=payment,
            communication_type='thank_you',
            is_automated=True,
        )
    except Exception as e:
        logger.exception("Errore invio conferma pagamento %s", payment_id)
        raise self.retry(exc=e)


# ============================================================================
# Reminder scadenza singola
# ============================================================================

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_deadline_reminder(self, deadline_id, reminder_type='reminder'):
    """
    Invia reminder per una scadenza specifica.
    
    Args:
        deadline_id: id della Deadline
        reminder_type: 'reminder' (T-N) o 'overdue' (scaduta)
    """
    from contracts.models import Deadline, DeadlineStatus
    from contracts.services.email_sender import send_email, get_recipients_for_contract

    try:
        deadline = Deadline.objects.select_related(
            'contract__sponsor', 'contract__event', 'deadline_template'
        ).get(pk=deadline_id)
    except Deadline.DoesNotExist:
        logger.error("Deadline %s non trovata", deadline_id)
        return

    # Skip se già completata
    if deadline.status in [DeadlineStatus.RECEIVED, DeadlineStatus.WAIVED]:
        logger.info("Skip reminder per deadline %s (già %s)",
                     deadline_id, deadline.status)
        return

    contract = deadline.contract

    # Destinatari: ruoli specifici dal template (es. marketing per ADV,
    # operational per workshop)
    notify_roles = (
        deadline.deadline_template.notify_roles
        if deadline.deadline_template
        else ['marketing', 'operational']
    )
    recipients = get_recipients_for_contract(contract, roles=notify_roles)
    if not recipients:
        logger.warning("Nessun destinatario per deadline %s", deadline_id)
        return

    language = contract.language or 'it'
    primary_contact = contract.sponsor.contacts.filter(is_primary=True).first()
    if not primary_contact:
        primary_contact = contract.sponsor.contacts.first()

    event_name = (
        contract.event.get_name(language)
        if hasattr(contract.event, 'get_name')
        else str(contract.event.name)
    )

    days_remaining = deadline.days_until_due
    days_overdue = abs(days_remaining) if days_remaining < 0 else 0

    context = {
        'deadline': deadline,
        'contract': contract,
        'sponsor': contract.sponsor,
        'event': contract.event,
        'event_name': event_name,
        'contact': primary_contact,
        'days_remaining': days_remaining,
        'days_overdue': days_overdue,
    }

    # Scegli template e subject in base al tipo
    if reminder_type == 'overdue':
        template_name = 'deadline_overdue'
        if language == 'en':
            subject = f"Overdue · {deadline.title}"
        else:
            subject = f"Sollecito · {deadline.title}"
        comm_type = 'overdue_alert'
    else:
        template_name = 'deadline_reminder'
        if language == 'en':
            subject = f"Reminder · {deadline.title} by {deadline.due_date.strftime('%d/%m/%Y')}"
        else:
            subject = f"Promemoria · {deadline.title} entro il {deadline.due_date.strftime('%d/%m/%Y')}"
        comm_type = 'reminder'

    try:
        send_email(
            template_name=template_name,
            context=context,
            to=recipients,
            subject=subject,
            language=language,
            related_to=deadline,
            communication_type=comm_type,
            is_automated=True,
        )

        # Aggiorna tracking sulla deadline
        deadline.last_reminder_sent_at = timezone.now()
        deadline.reminder_count = (deadline.reminder_count or 0) + 1
        if deadline.status == DeadlineStatus.PENDING:
            deadline.status = DeadlineStatus.REMINDER_SENT
        deadline.save(update_fields=[
            'last_reminder_sent_at', 'reminder_count', 'status', 'updated_at'
        ])

    except Exception as e:
        logger.exception("Errore reminder deadline %s", deadline_id)
        raise self.retry(exc=e)


# ============================================================================
# Recovery carrello abbandonato
# ============================================================================

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_cart_recovery_email(self, cart_session_id):
    """
    Invia email di recovery per un carrello abbandonato.
    
    Triggerato da: task Celery scheduled `check_abandoned_carts`
    """
    from contracts.payments import CartSession, CartSessionStatus
    from contracts.services.email_sender import send_email
    from datetime import date

    try:
        cart = CartSession.objects.select_related(
            'contract__sponsor', 'contract__event', 'contact'
        ).prefetch_related('contract__lines').get(pk=cart_session_id)
    except CartSession.DoesNotExist:
        logger.error("CartSession %s non trovato", cart_session_id)
        return

    # Skip se già completato
    if cart.status != CartSessionStatus.ACTIVE:
        return

    # Skip se già inviata recovery email
    if cart.abandoned_email_sent_at:
        return

    contract = cart.contract
    contact = cart.contact
    if not contact.email:
        return

    language = contact.preferred_language or 'it'
    event_name = (
        contract.event.get_name(language)
        if hasattr(contract.event, 'get_name')
        else str(contract.event.name)
    )

    # Calcola giorni mancanti al cutoff più vicino tra i servizi nel carrello
    days_until_cutoff = 30
    for line in contract.lines.select_related('service').all():
        if line.service.self_purchase_cutoff_days is not None:
            days_to_event = (contract.event.start_date - date.today()).days
            cutoff_remaining = days_to_event - line.service.self_purchase_cutoff_days
            days_until_cutoff = min(days_until_cutoff, cutoff_remaining)

    context = {
        'cart': cart,
        'cart_lines': contract.lines.all(),
        'cart_total': contract.total,
        'days_until_cutoff': days_until_cutoff,
        'sponsor': contract.sponsor,
        'event': contract.event,
        'event_name': event_name,
        'contact': contact,
    }

    if language == 'en':
        subject = f"You left items in your cart · {event_name}"
    else:
        subject = f"Hai un carrello in sospeso · {event_name}"

    try:
        send_email(
            template_name='cart_recovery',
            context=context,
            to=[contact.email],
            subject=subject,
            language=language,
            related_to=cart,
            communication_type='reminder',
            is_automated=True,
        )

        # Marca recovery inviata
        cart.abandoned_email_sent_at = timezone.now()
        cart.save(update_fields=['abandoned_email_sent_at', 'updated_at'])

    except Exception as e:
        logger.exception("Errore cart recovery %s", cart_session_id)
        raise self.retry(exc=e)
