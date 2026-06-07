"""
Context processor per i badge dell'admin (es. messaggi clienti non letti).
"""


def admin_badges(request):
    """Aggiunge il numero di risposte dei clienti non lette (per il badge nel
    menu admin 'Messaggi portale'). Calcolato solo per utenti staff."""
    count = 0
    try:
        user = getattr(request, 'user', None)
        if user and user.is_authenticated and user.is_staff:
            from sponsors.models import PortalMessage, MessageSender
            count = PortalMessage.objects.filter(
                sender=MessageSender.SPONSOR, read_at__isnull=True, is_active=True,
                archived_at__isnull=True,
            ).count()
    except Exception:
        count = 0
    return {'portal_unread_count': count}
