"""View del cruscotto: home con eventi in programmazione."""
from django.contrib.admin import site as admin_site
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render

from events.models import Event, EventStatus


@staff_member_required
def cruscotto_home(request):
    """Home cruscotto: card degli eventi attivi (SELLING + LIVE)."""
    eventi = (Event.objects
              .filter(status__in=[EventStatus.SELLING, EventStatus.LIVE])
              .order_by('start_date', 'id'))

    cards = []
    for ev in eventi:
        try:
            nome = ev.get_name() if hasattr(ev, 'get_name') else str(ev)
        except Exception:
            nome = str(ev)
        cards.append({
            'id': ev.id,
            'nome': nome,
            'slug': ev.slug,
            'status_label': ev.get_status_display(),
            'status_code': ev.status,
            'start_date': ev.start_date,
            'end_date': getattr(ev, 'end_date', None),
            'location': getattr(ev, 'location', '') or '',
        })

    context = {
        **admin_site.each_context(request),
        'title': 'Cruscotto',
        'cards': cards,
        'n_eventi': len(cards),
    }
    return render(request, 'cruscotto/home.html', context)


@staff_member_required
def evento_dettaglio(request, pk):
    """Dashboard di dettaglio dell'evento: KPI principali."""
    from datetime import date
    from decimal import Decimal

    from django.http import Http404
    from contracts.models import Contract, ContractStatus
    from venues.models import Stand, StandBlock

    try:
        ev = Event.objects.get(pk=pk)
    except Event.DoesNotExist:
        raise Http404("Evento non trovato")

    oggi = date.today()
    CONFIRMED = [ContractStatus.SIGNED, ContractStatus.ACTIVE, ContractStatus.COMPLETED]

    contratti_ev = Contract.objects.filter(event=ev).exclude(status=ContractStatus.CANCELLED)

    def _num_stand(c):
        """Numero di stand effettivi di un contratto (singolo o dentro un blocco)."""
        if c.stand_id:
            return 1
        if c.stand_block_id:
            try:
                return c.stand_block.stands.count()
            except Exception:
                return 0
        return 0

    def _aggrega(qs):
        n_contratti = 0
        n_stand = 0
        n_servizi = 0
        totale = Decimal('0.00')
        for c in qs.select_related('stand_block'):
            n_contratti += 1
            n_stand += _num_stand(c)
            n_servizi += c.lines.exclude(notes__startswith='stand:').exclude(
                notes__startswith='block:').count()
            totale += (c.total or Decimal('0.00'))
        return {'n_contratti': n_contratti, 'n_stand': n_stand,
                'n_servizi': n_servizi, 'totale': totale}

    confermati = _aggrega(contratti_ev.filter(status__in=CONFIRMED))
    opzionati = _aggrega(contratti_ev.filter(
        status=ContractStatus.DRAFT, option_until__isnull=False, option_until__gte=oggi
    ).filter(stand__isnull=False) | contratti_ev.filter(
        status=ContractStatus.DRAFT, option_until__isnull=False, option_until__gte=oggi,
        stand_block__isnull=False))
    trattativa = _aggrega(contratti_ev.filter(status=ContractStatus.SENT))

    # Stand TOTALI dell'evento (capacita' espositiva): singoli + dentro blocchi
    n_stand_totali = Stand.objects.filter(event=ev).count()

    try:
        nome_ev = ev.get_name() if hasattr(ev, 'get_name') else str(ev)
    except Exception:
        nome_ev = str(ev)

    context = {
        **admin_site.each_context(request),
        'title': f'Cruscotto · {nome_ev}',
        'evento': ev,
        'nome_evento': nome_ev,
        'confermati': confermati,
        'opzionati': opzionati,
        'trattativa': trattativa,
        'n_stand_totali': n_stand_totali,
    }
    return render(request, 'cruscotto/evento.html', context)
