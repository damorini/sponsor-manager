"""
Task Celery schedulati: girano automaticamente secondo la schedule definita
in config/celery.py (Celery Beat).

Schedule consigliata:
- check_upcoming_deadlines: ogni giorno alle 8:00
- check_overdue_deadlines: ogni giorno alle 9:00
- check_abandoned_carts: ogni giorno alle 10:00
- send_operator_alerts: ogni giorno alle 7:00 (prima di tutti)

Tutti i task qui delegano l'invio email effettivo ai task on-demand
in notifications.py, così la logica di invio resta unica.
"""
import logging
from datetime import date, timedelta

from celery import shared_task
from django.db.models import F, Q
from django.utils import timezone

logger = logging.getLogger(__name__)


# ============================================================================
# Reminder scadenze in arrivo
# ============================================================================

@shared_task
def check_upcoming_deadlines():
    """
    Cerca scadenze in arrivo per cui mandare reminder.
    
    Per ogni Deadline pending/reminder_sent:
    - Calcola days_until_due
    - Se days_until_due è in deadline_template.reminder_days_before, manda reminder
    
    Default: reminder a [10, 3, 0] giorni prima (configurabile per servizio).
    """
    from contracts.models import Deadline, DeadlineStatus
    from contracts.tasks.notifications import send_deadline_reminder

    today = date.today()

    # Pesca solo scadenze "vive" e non scadute
    deadlines = Deadline.objects.select_related(
        'deadline_template'
    ).filter(
        status__in=[DeadlineStatus.PENDING, DeadlineStatus.REMINDER_SENT],
        due_date__gte=today,  # non in ritardo
    )

    sent_count = 0
    for deadline in deadlines:
        days_remaining = (deadline.due_date - today).days

        # Reminder days dal template (con default)
        reminder_days = (
            deadline.deadline_template.reminder_days_before
            if deadline.deadline_template
            else [10, 3, 0]
        )

        if days_remaining in reminder_days:
            # Evita doppio invio nello stesso giorno
            if deadline.last_reminder_sent_at:
                last = deadline.last_reminder_sent_at.date()
                if last == today:
                    continue

            send_deadline_reminder.delay(deadline.id, reminder_type='reminder')
            sent_count += 1

    logger.info("check_upcoming_deadlines: %d reminder schedulati", sent_count)
    return sent_count


# ============================================================================
# Solleciti scadenze in ritardo
# ============================================================================

@shared_task
def check_overdue_deadlines():
    """
    Cerca scadenze già scadute e manda solleciti.
    
    Frequenza solleciti per scadenza in ritardo: ogni 3 giorni.
    """
    from contracts.models import Deadline, DeadlineStatus
    from contracts.tasks.notifications import send_deadline_reminder

    today = date.today()
    three_days_ago = timezone.now() - timedelta(days=3)

    overdue = Deadline.objects.filter(
        status__in=[DeadlineStatus.PENDING, DeadlineStatus.REMINDER_SENT],
        due_date__lt=today,  # in ritardo
    ).filter(
        # Mai inviato sollecito OR ultimo sollecito >3 giorni fa
        Q(last_reminder_sent_at__isnull=True) |
        Q(last_reminder_sent_at__lt=three_days_ago)
    )

    sent_count = 0
    for deadline in overdue:
        # Aggiorna stato a OVERDUE se non già impostato
        if deadline.status != DeadlineStatus.OVERDUE:
            deadline.status = DeadlineStatus.OVERDUE
            deadline.save(update_fields=['status', 'updated_at'])

        send_deadline_reminder.delay(deadline.id, reminder_type='overdue')
        sent_count += 1

    logger.info("check_overdue_deadlines: %d solleciti schedulati", sent_count)
    return sent_count


# ============================================================================
# Carrelli abbandonati
# ============================================================================

@shared_task
def check_abandoned_carts():
    """
    Cerca carrelli inattivi da >24 ore e manda email di recovery.
    
    Logica:
    - Cart è "abbandonato" se status=ACTIVE e last_activity > 24h fa
    - Manda recovery solo se non già inviata
    - Marca cart come ABANDONED dopo recovery
    """
    from contracts.payments import CartSession, CartSessionStatus
    from contracts.tasks.notifications import send_cart_recovery_email

    threshold = timezone.now() - timedelta(hours=24)

    abandoned = CartSession.objects.filter(
        status=CartSessionStatus.ACTIVE,
        last_activity_at__lt=threshold,
        abandoned_email_sent_at__isnull=True,
    )

    sent_count = 0
    for cart in abandoned:
        # Skip carrelli vuoti (Contract senza righe)
        if not cart.contract.lines.exists():
            cart.status = CartSessionStatus.EXPIRED
            cart.save(update_fields=['status', 'updated_at'])
            continue

        send_cart_recovery_email.delay(cart.id)

        # Marca abbandonato dopo invio
        cart.status = CartSessionStatus.ABANDONED
        cart.save(update_fields=['status', 'updated_at'])
        sent_count += 1

    logger.info("check_abandoned_carts: %d recovery email schedulate", sent_count)
    return sent_count


# ============================================================================
# Alert operatore (solo se ci sono cose urgenti)
# ============================================================================

@shared_task
def send_operator_alerts():
    """
    Manda email di alert all'operatore SE e SOLO SE ci sono situazioni urgenti.
    
    Situazioni urgenti monitorate:
    - Scadenze in ritardo > 3 giorni
    - Pagamenti in pending > 7 giorni (per bonifici non ancora confermati)
    - Email fallite negli ultimi 24h
    
    Se nessuna situazione urgente: nessuna email inviata (silent ok).
    """
    from contracts.models import Deadline, DeadlineStatus
    from contracts.payments import Payment, PaymentStatus
    from contracts.services.email_sender import send_email
    from shared.models import Communication, CommunicationStatus
    from django.contrib.auth import get_user_model

    today = date.today()

    # 1. Scadenze in ritardo > 3 giorni
    overdue_deadlines = list(Deadline.objects.select_related(
        'contract__sponsor'
    ).filter(
        status=DeadlineStatus.OVERDUE,
        due_date__lt=today - timedelta(days=3),
    )[:20])  # max 20 per non riempire l'email

    # Calcola days_overdue per ciascuna
    for d in overdue_deadlines:
        d.days_overdue = (today - d.due_date).days

    # 2. Pagamenti pendenti > 7 giorni
    seven_days_ago = timezone.now() - timedelta(days=7)
    pending_payments = list(Payment.objects.select_related(
        'contract__sponsor'
    ).filter(
        status=PaymentStatus.PENDING,
        initiated_at__lt=seven_days_ago,
    )[:20])

    for p in pending_payments:
        p.days_pending = (timezone.now() - p.initiated_at).days

    # 3. Email fallite ultime 24h
    yesterday = timezone.now() - timedelta(hours=24)
    failed_emails = list(Communication.objects.filter(
        status__in=[CommunicationStatus.FAILED, CommunicationStatus.BOUNCED],
        bounced_at__gt=yesterday,
    )[:20])

    # Se nulla di urgente, esci silenzioso
    if not overdue_deadlines and not pending_payments and not failed_emails:
        logger.info("send_operator_alerts: nulla di urgente, skip email")
        return

    # Trova destinatari (admin del sistema)
    User = get_user_model()
    admins = list(User.objects.filter(
        role='admin',
        is_active=True,
    ).exclude(email=''))

    if not admins:
        logger.warning("Nessun admin attivo, alert non inviato")
        return

    recipients = [u.email for u in admins]

    context = {
        'user': admins[0],  # primo admin per saluto
        'overdue_deadlines': overdue_deadlines,
        'pending_payments': pending_payments,
        'failed_emails': failed_emails,
    }

    counts = []
    if overdue_deadlines:
        counts.append(f"{len(overdue_deadlines)} scadenze in ritardo")
    if pending_payments:
        counts.append(f"{len(pending_payments)} pagamenti da confermare")
    if failed_emails:
        counts.append(f"{len(failed_emails)} email non recapitate")
    subject = f"⚠ Alert Sponsor Manager: {', '.join(counts)}"

    try:
        send_email(
            template_name='operator_alert',
            context=context,
            to=recipients,
            subject=subject,
            language='it',
            related_to=None,
            communication_type='manual',
            is_automated=True,
        )
        logger.info("Operator alert inviato: %s", subject)
    except Exception:
        logger.exception("Errore invio operator alert")
