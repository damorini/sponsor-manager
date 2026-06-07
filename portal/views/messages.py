"""
Conversazione messaggi del portale (operatore <-> sponsor):
- lista dei thread (messaggio + risposte),
- conferma di lettura,
- risposta del cliente.
"""
from django.contrib import messages as flash
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from portal.views.dashboard import sponsor_required


def _build_threads(sponsor):
    from sponsors.models import PortalMessage
    roots = (PortalMessage.objects
             .filter(sponsor=sponsor, is_active=True, parent__isnull=True)
             .prefetch_related('replies', 'replies__read_by')
             .order_by('-created_at'))
    threads = []
    for root in roots:
        msgs = [root] + list(
            root.replies.filter(is_active=True).order_by('created_at'))
        # un thread ha "novità" per il cliente se c'è un messaggio operatore non letto
        has_unread = any(
            m.is_from_operator and not m.is_read for m in msgs)
        threads.append({'root': root, 'messages': msgs, 'has_unread': has_unread})
    return threads


@sponsor_required
def messages_list(request):
    """Archivio conversazioni dello sponsor."""
    from sponsors.models import PortalMessage, MessageSender
    threads = _build_threads(request.sponsor)
    non_letti = PortalMessage.objects.filter(
        sponsor=request.sponsor, is_active=True,
        sender=MessageSender.OPERATOR, read_at__isnull=True).count()
    return render(request, 'portal/messages/list.html', {
        'threads': threads,
        'non_letti': non_letti,
    })


@sponsor_required
@require_POST
def message_mark_read(request, message_id):
    """Il cliente conferma di aver letto un messaggio dell'operatore."""
    from sponsors.models import PortalMessage, MessageSender
    msg = get_object_or_404(
        PortalMessage, id=message_id, sponsor=request.sponsor, is_active=True,
        sender=MessageSender.OPERATOR)
    msg.mark_read(contact=request.contact)
    flash.success(request, "Messaggio segnato come letto. Grazie!")
    return redirect('portal:messages')


@sponsor_required
@require_POST
def message_reply(request, message_id):
    """Il cliente risponde a un messaggio (nuovo messaggio nel thread)."""
    from sponsors.models import PortalMessage, MessageSender
    msg = get_object_or_404(
        PortalMessage, id=message_id, sponsor=request.sponsor, is_active=True)
    root = msg.parent or msg
    body = (request.POST.get('body') or '').strip()
    if not body:
        flash.error(request, "Scrivi un testo prima di inviare.")
        return redirect('portal:messages')

    PortalMessage.objects.create(
        sponsor=request.sponsor, sender=MessageSender.SPONSOR,
        parent=root, body=body, is_active=True)
    # rispondendo, il cliente ha letto i messaggi dell'operatore nel thread
    PortalMessage.objects.filter(
        Q(pk=root.pk) | Q(parent=root),
        sender=MessageSender.OPERATOR, read_at__isnull=True,
    ).update(read_at=timezone.now(), read_by=request.contact)
    flash.success(request, "Risposta inviata.")
    return redirect('portal:messages')
