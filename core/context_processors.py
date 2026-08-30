"""
Context processor per i badge dell'admin (es. messaggi clienti non letti).
"""


def admin_badges(request):
    """Badge per l'admin, calcolati solo per utenti staff:
    - portal_unread_count: risposte clienti non lette;
    - bozze_count / bozze_url: preventivi creati ma NON ancora inviati
      (contratti principali in Bozza), mostrati come avviso su OGNI pagina.
    """
    count = 0
    bozze_count = 0
    bozze_url = ''
    evento_attivo = None
    eventi_switcher = []
    try:
        user = getattr(request, 'user', None)
        if user and user.is_authenticated and user.is_staff:
            # Evento attivo di sessione + lista per il selettore nell'header.
            from core.event_scope import events_for_user, get_active_event_id
            eventi_switcher = list(events_for_user(request))
            active_id = get_active_event_id(request)
            if active_id:
                evento_attivo = next(
                    (e for e in eventi_switcher if str(e.pk) == str(active_id)), None)
                if evento_attivo is None:
                    # evento archiviato/sparito: spegni il filtro per non
                    # lasciare l'operatore su liste vuote inspiegabili
                    from core.event_scope import set_active_event
                    set_active_event(request, '')
            from sponsors.models import PortalMessage, MessageSender
            count = PortalMessage.objects.filter(
                sender=MessageSender.SPONSOR, read_at__isnull=True, is_active=True,
                archived_at__isnull=True,
            ).count()

            from contracts.models import Contract, ContractStatus, ContractKind
            # Il numero del banner deve corrispondere ESATTAMENTE alle righe
            # che l'operatore trova cliccando: stesso RBAC della changelist
            # (eventi gestiti) e stesso evento attivo di sessione. Prima il
            # conteggio era globale e la lista filtrata: "2 da inviare" poteva
            # aprire una lista vuota.
            bozze_qs = Contract.objects.filter(
                status=ContractStatus.DRAFT,
                contract_kind=ContractKind.MAIN,
                deleted_at__isnull=True,
            )
            from core.event_scope import can_see_all
            if not can_see_all(user):
                bozze_qs = bozze_qs.filter(
                    event__in=user.managed_events.all())
            if active_id:
                bozze_qs = bozze_qs.filter(event_id=active_id)
            bozze_count = bozze_qs.count()
            if bozze_count:
                from django.urls import reverse
                # ?todo=da_inviare = SOLO i preventivi principali in bozza
                # (il vecchio ?status__exact=draft mostrava anche i carrelli)
                bozze_url = (reverse('admin:contracts_contract_changelist')
                             + '?todo=da_inviare')
    except Exception:
        pass
    return {
        'portal_unread_count': count,
        'bozze_count': bozze_count,
        'bozze_url': bozze_url,
        'evento_attivo': evento_attivo,
        'eventi_switcher': eventi_switcher,
    }
