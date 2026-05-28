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
            n_servizi += c.lines.filter(service__event=ev).exclude(
                notes__startswith='stand:').exclude(
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

    # ---- Incassi (sui contratti confermati) ----
    from contracts.payments import PaymentStatus
    confermati_qs = contratti_ev.filter(status__in=CONFIRMED)
    tot_confermato = Decimal('0.00')
    incassato = Decimal('0.00')
    for c in confermati_qs:
        tot_confermato += (c.total or Decimal('0.00'))
        for p in c.payments.filter(status=PaymentStatus.SUCCEEDED):
            incassato += (p.amount_gross or Decimal('0.00'))
    da_incassare = tot_confermato - incassato
    incassi = {
        'incassato': incassato,
        'da_incassare': da_incassare,
        'tot_confermato': tot_confermato,
    }

    try:
        nome_ev = ev.get_name() if hasattr(ev, 'get_name') else str(ev)
    except Exception:
        nome_ev = str(ev)

    servizi = _servizi_riepilogo(ev)
    context = {
        **admin_site.each_context(request),
        'title': f'Cruscotto · {nome_ev}',
        'evento': ev,
        'nome_evento': nome_ev,
        'confermati': confermati,
        'opzionati': opzionati,
        'trattativa': trattativa,
        'n_stand_totali': n_stand_totali,
        'servizi': servizi,
        'incassi': incassi,
    }
    return render(request, 'cruscotto/evento.html', context)


def _categorie_per_contratto(qs_contratti):
    """Restituisce un dict {contract_id: 'confermato'|'opzione'|'trattativa'}."""
    from datetime import date
    from contracts.models import ContractStatus
    oggi = date.today()
    CONFIRMED = {ContractStatus.SIGNED, ContractStatus.ACTIVE, ContractStatus.COMPLETED}
    out = {}
    for c in qs_contratti:
        if c.status in CONFIRMED:
            out[c.id] = 'confermato'
        elif (c.status == ContractStatus.DRAFT and c.option_until
              and c.option_until >= oggi):
            out[c.id] = 'opzione'
        elif c.status == ContractStatus.SENT:
            out[c.id] = 'trattativa'
        # CANCELLED e altri stati: non incluso
    return out


def _servizi_riepilogo(ev):
    """Per ogni Service dell'evento, calcola quantita' prenotate per categoria."""
    from catalog.models import Service
    from contracts.models import Contract, ContractStatus, ContractLine

    contratti_ev = list(Contract.objects.filter(event=ev)
                        .exclude(status=ContractStatus.CANCELLED))
    cats = _categorie_per_contratto(contratti_ev)
    if not cats:
        # nessun contratto utile -> tutti i servizi a 0
        servizi = []
        for s in Service.objects.filter(event=ev, is_active=True).order_by('display_order', 'code'):
            try:
                nome = s.translated('name') if hasattr(s, 'translated') else s.code
            except Exception:
                nome = s.code
            servizi.append({
                'id': s.id, 'code': s.code, 'nome': nome,
                'q_confermato': 0, 'q_opzione': 0, 'q_trattativa': 0, 'q_totale': 0,
            })
        return servizi

    # carico le righe servizio dei contratti utili, esclusi gli stand
    righe = (ContractLine.objects
             .filter(contract_id__in=cats.keys(), service__event=ev)
             .exclude(notes__startswith='stand:')
             .exclude(notes__startswith='block:')
             .values('service_id', 'contract_id', 'quantity'))

    aggreg = {}  # service_id -> {confermato, opzione, trattativa}
    for r in righe:
        sid = r['service_id']
        cat = cats.get(r['contract_id'])
        if not cat:
            continue
        d = aggreg.setdefault(sid, {'confermato': 0, 'opzione': 0, 'trattativa': 0})
        d[cat] += (r['quantity'] or 0)

    servizi = []
    for s in Service.objects.filter(event=ev, is_active=True).order_by('display_order', 'code'):
        try:
            nome = s.translated('name') if hasattr(s, 'translated') else s.code
        except Exception:
            nome = s.code
        d = aggreg.get(s.id, {'confermato': 0, 'opzione': 0, 'trattativa': 0})
        servizi.append({
            'id': s.id,
            'code': s.code,
            'nome': nome,
            'q_confermato': d['confermato'],
            'q_opzione': d['opzione'],
            'q_trattativa': d['trattativa'],
            'q_totale': d['confermato'] + d['opzione'] + d['trattativa'],
        })
    return servizi


@staff_member_required
def servizio_dettaglio(request, pk, service_pk):
    """Pagina di dettaglio di un servizio dell'evento: lista sponsor che l'hanno preso."""
    from django.http import Http404
    from catalog.models import Service
    from contracts.models import Contract, ContractStatus, ContractLine

    try:
        ev = Event.objects.get(pk=pk)
        servizio = Service.objects.get(pk=service_pk, event=ev)
    except (Event.DoesNotExist, Service.DoesNotExist):
        raise Http404("Evento o servizio non trovato")

    contratti_ev = list(Contract.objects.filter(event=ev)
                        .exclude(status=ContractStatus.CANCELLED)
                        .select_related('sponsor'))
    cats = _categorie_per_contratto(contratti_ev)

    righe = (ContractLine.objects
             .filter(service=servizio, contract_id__in=cats.keys())
             .exclude(notes__startswith='stand:')
             .exclude(notes__startswith='block:')
             .select_related('contract', 'contract__sponsor')
             .order_by('contract__contract_number'))

    prenotazioni = []
    for r in righe:
        c = r.contract
        prenotazioni.append({
            'contract_id': c.id,
            'contract_number': c.contract_number,
            'sponsor_nome': str(c.sponsor) if c.sponsor_id else '(senza sponsor)',
            'sponsor_id': c.sponsor_id,
            'status_label': c.get_status_display(),
            'categoria': cats.get(c.id, '-'),
            'quantita': r.quantity,
            'totale_riga': r.line_total or 0,
        })

    try:
        nome_serv = servizio.translated('name') if hasattr(servizio, 'translated') else servizio.code
    except Exception:
        nome_serv = servizio.code
    try:
        nome_ev = ev.get_name() if hasattr(ev, 'get_name') else str(ev)
    except Exception:
        nome_ev = str(ev)

    q_totale = sum(p['quantita'] for p in prenotazioni)

    context = {
        **admin_site.each_context(request),
        'title': f'Cruscotto · {nome_ev} · {nome_serv}',
        'evento': ev,
        'nome_evento': nome_ev,
        'servizio': servizio,
        'nome_servizio': nome_serv,
        'prenotazioni': prenotazioni,
        'q_totale': q_totale,
        'n_prenotazioni': len(prenotazioni),
    }
    return render(request, 'cruscotto/servizio.html', context)


@staff_member_required
def utility_home(request):
    """Pagina Utility: bottoni per scaricare template e altri strumenti."""
    risultato = request.session.pop('import_risultato', None)
    from events.models import Event
    eventi = Event.objects.all().order_by('-start_date')
    context = {
        **admin_site.each_context(request),
        'title': 'Cruscotto · Utility',
        'import_risultato': risultato,
        'eventi': eventi,
    }
    return render(request, 'cruscotto/utility.html', context)


@staff_member_required
def download_template_servizi(request):
    """Genera al volo il template Excel servizi e lo serve come download."""
    from io import BytesIO
    from django.http import HttpResponse
    from catalog.utils.excel_template import build_template_servizi_workbook

    wb = build_template_servizi_workbook()
    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    resp = HttpResponse(
        buffer.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    resp['Content-Disposition'] = 'attachment; filename="template_servizi.xlsx"'
    return resp


@staff_member_required
def download_template_stand(request):
    """Genera al volo il template Excel stand e lo serve come download."""
    from io import BytesIO
    from django.http import HttpResponse
    from catalog.utils.excel_template import build_template_stand_workbook

    wb = build_template_stand_workbook()
    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    resp = HttpResponse(
        buffer.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    resp['Content-Disposition'] = 'attachment; filename="template_stand.xlsx"'
    return resp


@staff_member_required
def da_incassare_evento(request, pk):
    """Listato dei residui da incassare per i contratti confermati di un evento."""
    from datetime import date
    from decimal import Decimal
    from django.http import Http404
    from contracts.models import Contract, ContractStatus
    from contracts.payments import PaymentStatus

    try:
        ev = Event.objects.get(pk=pk)
    except Event.DoesNotExist:
        raise Http404("Evento non trovato")

    CONFIRMED = [ContractStatus.SIGNED, ContractStatus.ACTIVE, ContractStatus.COMPLETED]
    confermati = (Contract.objects
                  .filter(event=ev, status__in=CONFIRMED)
                  .select_related('sponsor')
                  .order_by('sponsor__legal_name'))

    righe = []
    tot_residuo = Decimal('0.00')
    for c in confermati:
        incassato_c = Decimal('0.00')
        for p in c.payments.filter(status=PaymentStatus.SUCCEEDED):
            incassato_c += (p.amount_gross or Decimal('0.00'))
        residuo = (c.total or Decimal('0.00')) - incassato_c
        if residuo <= 0:
            continue  # gia' saldato
        # prossima scadenza utile (acconto se non ancora coperto, sennò saldo)
        if c.has_deposit and incassato_c < (c.deposit_amount or Decimal('0.00')):
            scadenza = c.deposit_due_date
            tipo_scad = f"Acconto ({c.deposit_percent}%)"
        else:
            scadenza = c.balance_due_date
            tipo_scad = "Saldo" if c.has_deposit else "Pagamento unico"
        righe.append({
            'contract': c,
            'numero': c.contract_number,
            'cliente': c.sponsor.legal_name if c.sponsor_id else '-',
            'totale': c.total or Decimal('0.00'),
            'incassato': incassato_c,
            'residuo': residuo,
            'scadenza': scadenza,
            'tipo_scadenza': tipo_scad,
        })
        tot_residuo += residuo

    try:
        nome_ev = ev.get_name() if hasattr(ev, 'get_name') else str(ev)
    except Exception:
        nome_ev = str(ev)

    context = {
        **admin_site.each_context(request),
        'title': f'Da incassare · {nome_ev}',
        'evento': ev,
        'nome_evento': nome_ev,
        'righe': righe,
        'tot_residuo': tot_residuo,
        'oggi': date.today(),
    }
    return render(request, 'cruscotto/da_incassare.html', context)


def _esegui_import_excel(request, comando, redirect_name):
    """Helper: salva l'upload in un file temp e lancia il comando management."""
    import os
    import tempfile
    from io import StringIO
    from django.contrib import messages
    from django.core.management import call_command
    from django.shortcuts import redirect

    f = request.FILES.get('file_excel')
    if not f:
        messages.error(request, "Nessun file selezionato.")
        return redirect(redirect_name)
    if not f.name.lower().endswith(('.xlsx', '.xls')):
        messages.error(request, "Il file deve essere un Excel (.xlsx).")
        return redirect(redirect_name)

    dry = request.POST.get('dry_run') == 'on'

    # salva in file temporaneo
    tmp = tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False)
    try:
        for chunk in f.chunks():
            tmp.write(chunk)
        tmp.close()
        out = StringIO()
        try:
            if dry:
                call_command(comando, file=tmp.name, dry_run=True, stdout=out)
            else:
                call_command(comando, file=tmp.name, stdout=out)
            risultato = out.getvalue()
            etichetta = "[ANTEPRIMA] " if dry else ""
            messages.success(request, f"{etichetta}Import completato.")
            # passo il dettaglio testuale via session per mostrarlo
            request.session['import_risultato'] = risultato
        except Exception as e:
            messages.error(request, f"Errore durante l'import: {e}")
            request.session['import_risultato'] = out.getvalue()
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass
    return redirect(redirect_name)


@staff_member_required
def importa_servizi_upload(request):
    if request.method != 'POST':
        from django.shortcuts import redirect
        return redirect('core:cruscotto_utility')
    return _esegui_import_excel(request, 'importa_servizi', 'core:cruscotto_utility')


@staff_member_required
def importa_stand_upload(request):
    if request.method != 'POST':
        from django.shortcuts import redirect
        return redirect('core:cruscotto_utility')
    return _esegui_import_excel(request, 'importa_stand', 'core:cruscotto_utility')


@staff_member_required
def export_servizi(request):
    """Scarica un Excel con i servizi esistenti dell'evento scelto (?evento=slug)."""
    from django.http import HttpResponse, Http404
    from events.models import Event
    from catalog.utils.excel_template import export_servizi_workbook

    slug = request.GET.get('evento')
    if not slug:
        from django.contrib import messages
        from django.shortcuts import redirect
        messages.error(request, "Scegli un evento prima di esportare.")
        return redirect('core:cruscotto_utility')
    try:
        ev = Event.objects.get(slug=slug)
    except Event.DoesNotExist:
        raise Http404("Evento non trovato")

    wb = export_servizi_workbook(ev)
    resp = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    resp['Content-Disposition'] = f'attachment; filename="servizi_{ev.slug}.xlsx"'
    wb.save(resp)
    return resp


@staff_member_required
def export_stand(request):
    """Scarica un Excel con gli stand esistenti dell'evento scelto (?evento=slug)."""
    from django.http import HttpResponse, Http404
    from events.models import Event
    from catalog.utils.excel_template import export_stand_workbook

    slug = request.GET.get('evento')
    if not slug:
        from django.contrib import messages
        from django.shortcuts import redirect
        messages.error(request, "Scegli un evento prima di esportare.")
        return redirect('core:cruscotto_utility')
    try:
        ev = Event.objects.get(slug=slug)
    except Event.DoesNotExist:
        raise Http404("Evento non trovato")

    wb = export_stand_workbook(ev)
    resp = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    resp['Content-Disposition'] = f'attachment; filename="stand_{ev.slug}.xlsx"'
    wb.save(resp)
    return resp
