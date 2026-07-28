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

    language = contract.language or 'it'
    event_name = (
        contract.event.get_name(language)
        if hasattr(contract.event, 'get_name')
        else str(contract.event.name)
    )

    # MAIN non-ECM: si allega il CONTRATTO di sponsorizzazione, che include gia'
    # la domanda di ammissione come Allegato 1 — il cliente firma UN documento
    # solo. Negli altri casi (eventi ECM, addendum) resta la domanda.
    from contracts.models import ContractKind
    from events.models import EventType
    is_main_non_ecm = (
        contract.contract_kind == ContractKind.MAIN
        and getattr(contract.event, 'event_type', None) == EventType.NON_ECM
    )

    # --- MAIN non-ECM: UN SOLO documento (contratto + Allegato 1 gia' uniti)
    # e UNA SOLA email corretta (firmatario+marketing+operational, CC
    # amministrazione/morini). Prima venivano inviate DUE email per lo stesso
    # evento — questa email generica (col soggetto/testo ormai obsoleto
    # "Domanda di ammissione confermata", ereditato da prima che esistesse il
    # documento unico) E quella specifica del contratto sponsor. Se la
    # generazione del documento fallisce, si RITENTA (niente email senza
    # l'allegato giusto).
    if is_main_non_ecm:
        from contracts.services.pdf_generator import generate_sponsor_contract_pdf
        try:
            document = generate_sponsor_contract_pdf(contract)
        except Exception as e:
            logger.exception(
                "Contratto sponsor non generato per %s: notifica NON inviata "
                "(evito di mandare un'email senza il documento corretto).",
                contract.contract_number,
            )
            raise self.retry(exc=e)
        try:
            _invia_contratto_sponsor(
                contract, language, event_name,
                document=document, extra_recipients=recipients,
            )
        except Exception as e:
            logger.exception("Errore invio contratto sponsor %s", contract_id)
            raise self.retry(exc=e)
        return

    # --- ECM / addendum: domanda di ammissione (flusso invariato) ---
    pdf_attachment = None
    try:
        document = generate_admission_request_pdf(contract)
        from django.conf import settings
        from pathlib import Path
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

    primary_contact = contract.sponsor.contacts.filter(is_primary=True).first()
    if not primary_contact:
        primary_contact = contract.sponsor.contacts.first()

    context = {
        'contract': contract,
        'sponsor': contract.sponsor,
        'event': contract.event,
        'event_name': event_name,
        'contact': primary_contact,
        'has_deadlines': contract.deadlines.exists(),
        'is_main_non_ecm': False,
    }

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


def _invia_contratto_sponsor(contract, language, event_name, document=None, extra_recipients=None):
    """Invia il contratto di sponsorizzazione (con Domanda di ammissione come
    Allegato 1) allo sponsor, in CC ad amministrazione@valet.it e morini@valet.it.

    Destinatari: extra_recipients (se passata, es. firmatario+marketing+operational)
    piu' comunque il contatto OPERATIVO (aggiunto se non gia' presente). Se
    extra_recipients non e' passata, va solo al contatto operativo (comportamento
    storico, per compatibilita' con eventuali altri chiamanti).
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

    to_list = list(dict.fromkeys(extra_recipients or []))  # dedup, ordine stabile
    op = _get_operational_contact(contract)
    op_email = getattr(op, 'email', None)
    if op_email and op_email not in to_list:
        to_list.append(op_email)
    if not to_list:
        logger.warning("Nessun destinatario per contratto sponsor %s", contract.contract_number)
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
        to=to_list,
        cc=['amministrazione@valet.it', 'morini@valet.it'],
        subject=subject,
        language=language,
        attachments=[attachment],
        related_to=contract,
        communication_type='initial_send',
        is_automated=True,
    )
    logger.info("Contratto sponsor %s inviato a %s (CC amministrazione, morini)",
                contract.contract_number, to_list)


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
# Avviso: contabile del bonifico caricata dallo sponsor
# ============================================================================

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_payment_receipt_uploaded_alert(self, deadline_id):
    """Avvisa l'amministrazione che lo sponsor ha caricato nel portale la
    contabile del bonifico su una scadenza di pagamento (deadline_type
    'pagamento_acconto'/'pagamento_saldo'). La scadenza NON viene marcata
    pagata: tocca alla segreteria verificare l'accredito e registrare
    l'incasso dal cruscotto."""
    from contracts.models import Deadline
    from contracts.services.email_sender import send_email

    try:
        deadline = Deadline.objects.select_related(
            'contract__sponsor', 'contract__event').get(pk=deadline_id)
    except Deadline.DoesNotExist:
        logger.error("Deadline %s non trovata per alert contabile pagamento", deadline_id)
        return

    contract = deadline.contract
    event_name = (
        contract.event.get_name('it')
        if hasattr(contract.event, 'get_name') else str(contract.event)
    )
    subject = (f"Contabile bonifico caricata · {contract.sponsor.legal_name} "
               f"· {contract.contract_number}")
    try:
        send_email(
            template_name='payment_receipt_uploaded',
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
            communication_type='document_request',
            is_automated=True,
        )
    except Exception as e:
        logger.exception("Errore invio alert contabile pagamento %s", deadline_id)
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
# Notifica fattura proforma generata
# ============================================================================

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_proforma_generated_notification(self, contract_id, document_ids):
    """
    Avvisa il cliente che la/e fattura/e proforma sono state generate e sono
    disponibili nell'area riservata, sezione "I miei documenti".

    Triggerato da: contracts.admin.ContractAdmin.action_genera_proforma
    (generazione manuale, di solito una tantum per contratto/installment).
    """
    from contracts.models import Contract
    from contracts.services.email_sender import send_email, get_recipients_for_contract

    try:
        contract = Contract.all_objects.select_related('sponsor', 'event').get(pk=contract_id)
    except Contract.DoesNotExist:
        logger.error("Contract %s non trovato (notifica proforma)", contract_id)
        return

    recipients = get_recipients_for_contract(
        contract, roles=['signer', 'finance', 'operational']
    )
    if not recipients:
        logger.warning("Nessun destinatario per notifica proforma contratto %s", contract_id)
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

    from django.conf import settings
    from django.urls import reverse
    site_url = getattr(settings, 'SITE_URL', '').rstrip('/')
    document_url = site_url + reverse('portal:contract_detail', args=[contract.id])

    context = {
        'contract': contract,
        'sponsor': contract.sponsor,
        'event': contract.event,
        'event_name': event_name,
        'contact': primary_contact,
        'document_url': document_url,
        'plurale': len(document_ids or []) > 1,
    }

    if language == 'en':
        subject = f"Proforma invoice available · {contract.contract_number}"
    else:
        subject = f"Fattura proforma disponibile · {contract.contract_number}"

    try:
        send_email(
            template_name='proforma_generated',
            context=context,
            to=recipients,
            subject=subject,
            language=language,
            related_to=contract,
            communication_type='proforma_generated',
            is_automated=True,
        )
    except Exception as e:
        logger.exception("Errore invio notifica proforma contratto %s", contract_id)
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
        context['etichetta_pagamento'] = {
            'pagamento_acconto': 'Acconto',
            'pagamento_saldo': 'Saldo',
        }.get(deadline.deadline_type, 'Pagamento')
        # Dati bonifico: il contratto principale si paga solo cosi'.
        # Nel riquadro compaiono solo se configurati davvero (niente placeholder).
        from django.conf import settings as _settings
        _iban = getattr(_settings, 'BANK_TRANSFER_IBAN', '') or ''
        _holder = getattr(_settings, 'BANK_TRANSFER_HOLDER', '') or ''
        if _iban and 'CONFIGURARE' not in _iban.upper() and 'CONFIGURARE' not in _holder.upper():
            context['bank_holder'] = _holder
            context['bank_name'] = getattr(_settings, 'BANK_TRANSFER_BANK', '')
            context['bank_iban'] = _iban
            context['bank_bic'] = getattr(_settings, 'BANK_TRANSFER_BIC', '')

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
        if line.service and line.service.self_purchase_cutoff_days is not None:
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


# ============================================================================
# Campagne promozionali (upsell servizi extra agli sponsor di un evento)
# ============================================================================

UNSUB_SALT = 'promo-campaign-optout'

_UNSUB_TEXT = {
    'it': {
        'intro': ("Non vuoi più ricevere questo tipo di comunicazioni? Le altre "
                 "email relative al tuo contratto continueranno ad arrivarti "
                 "normalmente."),
        'label': 'Disiscriviti da questo tipo di messaggio',
    },
    'en': {
        'intro': ("Don't want to receive this type of communication anymore? "
                 "Emails about your contract will keep arriving as usual."),
        'label': 'Unsubscribe from this message type',
    },
}


@shared_task(bind=True, max_retries=2, default_retry_delay=120)
def send_promotional_campaign_batch(self, campaign_id):
    """
    Invia una campagna promozionale a tutti i contatti eleggibili (sponsor
    confermati dell'evento, esclusi i disiscritti da QUESTA campagna) e
    aggiorna last_sent_at. Un fallimento su un singolo destinatario non
    blocca gli altri (loop protetto).
    """
    from django.conf import settings
    from django.core import signing
    from django.urls import reverse
    from events.models import PromotionalCampaign
    from contracts.services.email_sender import send_email, _pick_lang

    try:
        campaign = PromotionalCampaign.objects.select_related('event').get(pk=campaign_id)
    except PromotionalCampaign.DoesNotExist:
        logger.error("Campagna promozionale %s non trovata", campaign_id)
        return 0

    event = campaign.event
    event_name_cache = {}

    def _event_name(lang):
        if lang not in event_name_cache:
            event_name_cache[lang] = (
                event.get_name(lang) if hasattr(event, 'get_name') else str(event))
        return event_name_cache[lang]

    base_url = (getattr(settings, 'SITE_URL', '') or '').rstrip('/')
    from django.template import engines
    dj = engines['django']

    sent = 0
    for contact in campaign.eligible_contacts_queryset().select_related('sponsor'):
        lang = contact.preferred_language if contact.preferred_language in ('it', 'en') else 'it'
        placeholders = {
            'sponsor': contact.sponsor,
            'contact': contact,
            'event': event,
            'event_name': _event_name(lang),
        }
        subject_raw = _pick_lang(campaign.subject, lang) or campaign.name
        body = _pick_lang(campaign.body, lang) or ''
        if not body.strip():
            continue
        # Il corpo viene ri-risolto da send_email/_render_custom_body con lo
        # stesso context; l'oggetto va risolto qui perche' send_email non lo
        # fa passare dal motore dei placeholder.
        subject = dj.from_string(subject_raw).render(placeholders)

        token = signing.dumps({'c': str(campaign.id), 'k': str(contact.id)}, salt=UNSUB_SALT)
        unsubscribe_url = base_url + reverse('portal:campaign_unsubscribe', args=[token])
        txt = _UNSUB_TEXT.get(lang, _UNSUB_TEXT['it'])

        try:
            send_email(
                template_name='promotional_campaign',
                context={
                    **placeholders,
                    'unsubscribe_url': unsubscribe_url,
                    'unsubscribe_intro': txt['intro'],
                    'unsubscribe_label': txt['label'],
                },
                to=[contact.email],
                subject=subject,
                language=lang,
                custom_body_html=body,
                related_to=campaign,
                communication_type='promotional_campaign',
                is_automated=True,
            )
            sent += 1
        except Exception:
            logger.exception("Invio campagna %s a %s fallito", campaign_id, contact.email)

    campaign.last_sent_at = timezone.now()
    campaign.save(update_fields=['last_sent_at', 'updated_at'])
    logger.info("Campagna '%s' (evento %s) inviata a %d contatti",
               campaign.name, event, sent)
    return sent
