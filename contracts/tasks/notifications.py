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
    from contracts.services.pdf_generator import generate_admission_request_pdf

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

    # Genera PDF e prepara allegato.
    # MAIN non-ECM: si allega il CONTRATTO di sponsorizzazione, che include gia'
    # la domanda di ammissione come Allegato 1 — il cliente firma UN documento
    # solo. Negli altri casi (eventi ECM, addendum) resta la domanda.
    from contracts.models import ContractKind
    from events.models import EventType
    is_main_non_ecm = (
        contract.contract_kind == ContractKind.MAIN
        and getattr(contract.event, 'event_type', None) == EventType.NON_ECM
    )
    pdf_attachment = None
    contract_document = None
    try:
        if is_main_non_ecm:
            from contracts.services.pdf_generator import generate_sponsor_contract_pdf
            document = generate_sponsor_contract_pdf(contract)
            contract_document = document
        else:
            document = generate_admission_request_pdf(contract)
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
        # il template ringrazia e cita l'allegato giusto:
        # contratto (non-ECM) oppure domanda di ammissione (ECM/addendum)
        'is_main_non_ecm': is_main_non_ecm,
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

    # --- Contratto di sponsorizzazione (solo MAIN non-ECM): genera e invia ---
    # Wrappato: un errore qui NON deve far ritentare l'intera notifica.
    try:
        if is_main_non_ecm:
            _invia_contratto_sponsor(contract, language, event_name,
                                     document=contract_document)
    except Exception:
        logger.exception(
            "Generazione/invio contratto di sponsorizzazione fallito per %s",
            contract.contract_number,
        )


def _invia_contratto_sponsor(contract, language, event_name, document=None):
    """Invia il contratto di sponsorizzazione (con Domanda di ammissione come
    Allegato 1) al contatto OPERATIVO dello sponsor, in CC ad
    amministrazione@valet.it ed elisa.fantini@valet.it.
    Se 'document' non viene passato, il PDF viene generato qui."""
    from django.conf import settings
    from pathlib import Path
    from contracts.services.pdf_generator import (
        generate_sponsor_contract_pdf, _get_operational_contact,
    )
    from contracts.services.email_sender import send_email

    if document is None:
        document = generate_sponsor_contract_pdf(contract)
    rel = document.storage_url.replace(settings.MEDIA_URL, '')
    pdf_path = Path(settings.MEDIA_ROOT) / rel
    if not pdf_path.exists():
        logger.warning("PDF contratto sponsor mancante per %s", contract.contract_number)
        return
    attachment = (document.file_name, pdf_path.read_bytes(), 'application/pdf')

    op = _get_operational_contact(contract)
    to_email = getattr(op, 'email', None)
    if not to_email:
        logger.warning("Nessuna email (contatto operativo) per contratto sponsor %s",
                       contract.contract_number)
        return

    subject = f"Contratto di sponsorizzazione {contract.contract_number} · {event_name}"
    send_email(
        template_name='sponsor_contract_email',
        context={
            'contract': contract,
            'sponsor': contract.sponsor,
            'event': contract.event,
            'event_name': event_name,
        },
        to=[to_email],
        cc=['amministrazione@valet.it', 'morini@valet.it'],
        subject=subject,
        language=language,
        attachments=[attachment],
        related_to=contract,
        communication_type='initial_send',
        is_automated=True,
    )
    logger.info("Contratto sponsor %s inviato a %s (CC amministrazione, elisa.fantini)",
                contract.contract_number, to_email)


# ============================================================================
# Contratto firmato caricato dallo sponsor
# ============================================================================

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_signed_contract_uploaded_alert(self, deadline_id):
    """Avvisa l'amministrazione che lo sponsor ha caricato il contratto
    firmato nel portale (scadenza deadline_type='contratto_firmato')."""
    from contracts.models import Deadline
    from contracts.services.email_sender import send_email

    try:
        deadline = Deadline.objects.select_related(
            'contract__sponsor', 'contract__event').get(pk=deadline_id)
    except Deadline.DoesNotExist:
        logger.error("Deadline %s non trovata per alert contratto firmato", deadline_id)
        return

    contract = deadline.contract
    event_name = (
        contract.event.get_name('it')
        if hasattr(contract.event, 'get_name') else str(contract.event)
    )
    subject = (f"Contratto firmato ricevuto · {contract.sponsor.legal_name} "
               f"· {contract.contract_number}")
    try:
        send_email(
            template_name='signed_contract_uploaded',
            context={
                'contract': contract,
                'sponsor': contract.sponsor,
                'event': contract.event,
                'event_name': event_name,
                'deadline': deadline,
            },
            to=['amministrazione@valet.it'],
            cc=['morini@valet.it'],
            subject=subject,
            language='it',
            related_to=contract,
            communication_type='initial_send',
            is_automated=True,
        )
    except Exception as e:
        logger.exception("Errore invio alert contratto firmato %s", deadline_id)
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

    # Scadenze di pagamento: il promemoria va al CLIENTE + STAFF interno (role='admin').
    _dtype = (deadline.deadline_type or '')
    _is_pagamento = _dtype.startswith('pagamento')
    _is_opzione = (_dtype == 'scadenza_opzione')
    if _is_pagamento or _is_opzione:
        # cliente: assicura almeno il contatto primario
        if not recipients:
            recipients = get_recipients_for_contract(contract, roles=None)
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            staff = list(User.objects.filter(role='admin', is_active=True).exclude(email=''))
            for u in staff:
                if u.email and u.email not in recipients:
                    recipients.append(u.email)
        except Exception:
            logger.exception("Impossibile aggiungere staff ai destinatari del reminder pagamento")

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

    # Importo della scadenza di pagamento (acconto o saldo, IVA inclusa)
    if _is_pagamento:
        _imp = None
        try:
            if deadline.deadline_type == 'pagamento_acconto':
                _imp = contract.deposit_amount
            elif deadline.deadline_type == 'pagamento_saldo':
                _imp = contract.balance_amount
        except Exception:
            _imp = None
        context['is_pagamento'] = True
        context['importo_scadenza'] = _imp

    # Scegli template e subject in base al tipo
    if reminder_type == 'overdue':
        template_name = 'deadline_overdue'
        if language == 'en':
            subject = f"Overdue · {deadline.title}"
        else:
            subject = f"Sollecito · {deadline.title}"
        comm_type = 'overdue_alert'
    elif _is_opzione:
        template_name = 'option_reminder'
        _dd = deadline.due_date.strftime('%d/%m/%Y')
        if language == 'en':
            subject = f"Your space option expires on {_dd}"
        else:
            subject = f"La vostra opzione sullo spazio scade il {_dd}"
        comm_type = 'reminder'
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


# ============================================================================
# Reminder wishlist (al cliente: hai ancora articoli osservati)
# ============================================================================

@shared_task(bind=True, max_retries=2, default_retry_delay=120)
def send_wishlist_reminder(self, wishlist_id):
    """Promemoria al cliente degli articoli nella wishlist.
    Se ci sono articoli a disponibilita' limitata, aggiunge un invito a non
    perdere l'occasione. Aggiorna last_reminder_sent_at."""
    from django.conf import settings
    from django.urls import reverse
    from portal.models import Wishlist
    from contracts.services.email_sender import send_plain_email

    try:
        wl = Wishlist.objects.select_related('user').prefetch_related(
            'items__service').get(id=wishlist_id)
    except Wishlist.DoesNotExist:
        return

    email = (wl.user.email or '').strip()
    items = list(wl.items.select_related('service').all())
    if not email or not items:
        return

    limitati = []
    for it in items:
        s = it.service
        try:
            if s.total_available is not None or getattr(s, 'is_sold_out', False):
                limitati.append(s)
        except Exception:
            pass

    base = (getattr(settings, 'SITE_URL', '') or '').rstrip('/')
    link = base + reverse('portal:wishlist_page')
    n = len(items)

    righe = [
        'Ciao,',
        '',
        ('hai ancora %d articolo/i tra i tuoi preferiti (wishlist) nel portale: '
         'non lasciarli li ad aspettare!') % n,
    ]
    if limitati:
        righe += [
            '',
            ("Attenzione: fra gli articoli che osservi ce ne sono alcuni con "
             "DISPONIBILITA' LIMITATA. Non rischiare di perdere l'articolo di tuo "
             "interesse: completa l'acquisto finche' sei in tempo."),
        ]
    righe += ['', 'Vai a vederli qui: ' + link, '', 'A presto!']
    body = "\n".join(righe)

    try:
        send_plain_email('I tuoi articoli preferiti ti aspettano', body, [email])
        wl.last_reminder_sent_at = timezone.now()
        wl.save(update_fields=['last_reminder_sent_at', 'updated_at'])
    except Exception as e:
        logger.exception('Errore reminder wishlist %s', wishlist_id)
        raise self.retry(exc=e)
