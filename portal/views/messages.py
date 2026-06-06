"""
Archivio messaggi del portale sponsor: lista (letti/da leggere) e conferma
di lettura tramite pulsante.
"""
from django.contrib import messages as flash
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from portal.views.dashboard import sponsor_required


@sponsor_required
def messages_list(request):
    """Archivio di tutti i messaggi ricevuti dallo sponsor."""
    from sponsors.models import PortalMessage

    qs = (PortalMessage.objects
          .filter(sponsor=request.sponsor, is_active=True)
          .select_related('event')
          .order_by('-created_at'))
    msgs = list(qs)
    non_letti = sum(1 for m in msgs if not m.is_read)
    return render(request, 'portal/messages/list.html', {
        'messaggi': msgs,
        'non_letti': non_letti,
    })


@sponsor_required
@require_POST
def message_mark_read(request, message_id):
    """Il cliente conferma di aver letto un messaggio."""
    from sponsors.models import PortalMessage

    msg = get_object_or_404(
        PortalMessage, id=message_id, sponsor=request.sponsor, is_active=True)
    msg.mark_read(contact=request.contact)
    flash.success(request, "Messaggio segnato come letto. Grazie!")
    next_url = request.POST.get('next') or 'portal:messages'
    if next_url.startswith('/'):
        return redirect(next_url)
    return redirect(next_url)
