"""View del cruscotto: home con eventi in programmazione."""
from django.contrib.admin import site as admin_site
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render
import json
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from events.models import Event, EventStatus
from core.event_scope import scope_by_event, scope_generic_by_event


@staff_member_required
def cruscotto_home(request):
    """Home cruscotto: card degli eventi attivi (SELLING + LIVE)."""
    eventi = scope_by_event(request, (Event.objects
              .filter(status__in=[EventStatus.SELLING, EventStatus.LIVE])
              .order_by('start_date', 'id')), 'id')

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
        ev = scope_by_event(request, Event.objects.filter(pk=pk), 'id').get()
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
        ev = scope_by_event(request, Event.objects.filter(pk=pk), 'id').get()
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

    from django.utils import timezone as _tz
    from contracts.models import Deadline, DeadlineStatus
    _oggi = _tz.now().date()
    righe_out = []
    riepilogo = {'confermati': 0, 'opzione': 0, 'trattativa': 0}
    cat_to_key = {'confermato': 'confermati', 'opzione': 'opzione',
                  'trattativa': 'trattativa'}
    for r in righe:
        c = r.contract
        categoria = cats.get(c.id, '-')
        k = cat_to_key.get(categoria)
        if k:
            riepilogo[k] += 1
        consegne = []
        for dl in (Deadline.objects
                   .filter(contract_line=r, deadline_template__isnull=False)
                   .exclude(status=DeadlineStatus.WAIVED)):
            received = dl.status == DeadlineStatus.RECEIVED
            late = (not received) and dl.due_date and dl.due_date < _oggi
            consegne.append({
                'id': dl.id,
                'titolo': dl.title,
                'stato': 'completata' if received else ('ritardo' if late else 'dafare'),
            })
        righe_out.append({
            'contract_id': c.id,
            'contract_number': c.contract_number,
            'sponsor': str(c.sponsor) if c.sponsor_id else '(senza sponsor)',
            'sponsor_id': c.sponsor_id,
            'status_label': c.get_status_display(),
            'categoria': categoria,
            'variante': r.variant_label_snapshot,
            'quantity': r.quantity,
            'importo': r.line_total or 0,
            'consegne': consegne,
        })

    try:
        nome_serv = servizio.translated('name') if hasattr(servizio, 'translated') else servizio.code
    except Exception:
        nome_serv = servizio.code
    try:
        nome_ev = ev.get_name() if hasattr(ev, 'get_name') else str(ev)
    except Exception:
        nome_ev = str(ev)

    q_totale = sum(x['quantity'] for x in righe_out)

    context = {
        **admin_site.each_context(request),
        'title': f'Cruscotto \u00b7 {nome_ev} \u00b7 {nome_serv}',
        'evento': ev,
        'nome_evento': nome_ev,
        'servizio': servizio,
        'nome_servizio': nome_serv,
        'righe': righe_out,
        'riepilogo': riepilogo,
        'prenotazioni': righe_out,
        'q_totale': q_totale,
        'n_prenotazioni': len(righe_out),
    }
    return render(request, 'cruscotto/servizio.html', context)


@staff_member_required
def utility_home(request):
    """Pagina Utility: bottoni per scaricare template e altri strumenti."""
    risultato = request.session.pop('import_risultato', None)
    from events.models import Event
    eventi = scope_by_event(request, Event.objects.all().order_by('-start_date'), 'id')
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
def manuale(request):
    """Serve il manuale d'uso (docs/manuale_utente.html) dentro l'area admin."""
    import os
    from django.conf import settings
    from django.http import HttpResponse, Http404
    path = os.path.join(settings.BASE_DIR, 'docs', 'manuale_utente.html')
    try:
        with open(path, encoding='utf-8') as f:
            return HttpResponse(f.read())
    except FileNotFoundError:
        raise Http404("Manuale non trovato.")


@staff_member_required
def da_incassare_evento(request, pk):
    """Listato dei residui da incassare per i contratti confermati di un evento."""
    from datetime import date
    from decimal import Decimal
    from django.http import Http404
    from contracts.models import Contract, ContractStatus
    from contracts.payments import PaymentStatus

    try:
        ev = scope_by_event(request, Event.objects.filter(pk=pk), 'id').get()
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
        ev = scope_by_event(request, Event.objects.filter(slug=slug), 'id').get()
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
        ev = scope_by_event(request, Event.objects.filter(slug=slug), 'id').get()
    except Event.DoesNotExist:
        raise Http404("Evento non trovato")

    wb = export_stand_workbook(ev)
    resp = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    resp['Content-Disposition'] = f'attachment; filename="stand_{ev.slug}.xlsx"'
    wb.save(resp)
    return resp


@staff_member_required
@require_POST
def translate_view(request):
    # Traduce un testo (IT->EN di default) per i campi bilingue dell'admin.
    from core.translation import translate_text, TranslationError
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except Exception:
        return JsonResponse({'error': 'Richiesta non valida'}, status=400)
    text = (payload.get('text') or '').strip()
    source = (payload.get('source') or 'it')
    target = (payload.get('target') or 'en')
    is_html = bool(payload.get('html'))
    if not text:
        return JsonResponse({'error': 'Testo vuoto'}, status=400)
    try:
        return JsonResponse({'translated': translate_text(text, source=source, target=target, html=is_html)})
    except TranslationError as e:
        return JsonResponse({'error': str(e)}, status=400)
    except Exception:
        return JsonResponse({'error': 'Errore durante la traduzione'}, status=500)


@staff_member_required
def cruscotto_scadenze_cliente(request):
    """Cruscotto: scadenze a cura del cliente (generate dai template di servizio).

    Mostra totali, completate, da fare, in ritardo, con chi/quando ha consegnato.
    """
    from django.utils import timezone
    from contracts.models import Deadline, DeadlineStatus

    today = timezone.now().date()

    qs = (Deadline.objects
          .filter(deadline_template__isnull=False)
          .exclude(status=DeadlineStatus.WAIVED)
          .select_related('contract', 'contract__sponsor', 'contract__event',
                          'completed_by_contact')
          .order_by('contract__event__start_date', 'due_date'))
    qs = scope_by_event(request, qs, 'contract__event')

    event_id = request.GET.get('event') or ''
    if event_id:
        qs = qs.filter(contract__event_id=event_id)

    deadlines = list(qs)

    tipo_map = {'content': 'Testi', 'file': 'File', 'both': 'Testi + file'}
    righe = []
    completate = in_ritardo = da_fare = 0
    for d in deadlines:
        received = d.status == DeadlineStatus.RECEIVED
        late = (not received) and d.due_date and d.due_date < today
        if received:
            stato = 'completata'; completate += 1
        elif late:
            stato = 'ritardo'; in_ritardo += 1
        else:
            stato = 'dafare'; da_fare += 1
        ev = d.contract.event
        sp = d.contract.sponsor
        try:
            evnome = ev.get_name() if ev else '—'
        except Exception:
            evnome = str(ev) if ev else '—'
        righe.append({
            'evento': evnome,
            'sponsor': sp.legal_name if sp else '—',
            'titolo': d.title,
            'tipo': tipo_map.get(getattr(d, 'submission_kind', 'file'),
                                 getattr(d, 'submission_kind', '')),
            'due_date': d.due_date,
            'stato': stato,
            'completata_da': (d.completed_by_contact.full_name
                              if d.completed_by_contact else ''),
            'completata_il': d.completed_at,
            'deadline_id': d.id,
        })

    # eventi con scadenze cliente, per il filtro
    ev_ids = set(Deadline.objects
                 .filter(deadline_template__isnull=False)
                 .exclude(status=DeadlineStatus.WAIVED)
                 .values_list('contract__event_id', flat=True))
    eventi = (Event.objects.filter(id__in=[x for x in ev_ids if x])
              .order_by('start_date'))
    ev_list = []
    for e in eventi:
        try:
            n = e.get_name() if hasattr(e, 'get_name') else str(e)
        except Exception:
            n = str(e)
        ev_list.append({'id': e.id, 'nome': n})

    context = {
        **admin_site.each_context(request),
        'title': 'Scadenze cliente',
        'righe': righe,
        'tot': len(deadlines),
        'completate': completate,
        'da_fare': da_fare,
        'in_ritardo': in_ritardo,
        'eventi': ev_list,
        'event_id': event_id,
    }
    return render(request, 'cruscotto/scadenze_cliente.html', context)


@staff_member_required
def cruscotto_scadenza_dettaglio(request, deadline_id):
    """Dati consegnati dal cliente per una scadenza: testi + file."""
    from django.shortcuts import get_object_or_404
    from django.contrib.contenttypes.models import ContentType
    from django.utils import timezone
    from contracts.models import Deadline, DeadlineStatus
    from shared.models import Document

    d = get_object_or_404(
        scope_by_event(request, Deadline.objects.select_related(
            'contract', 'contract__sponsor', 'contract__event',
            'completed_by_contact'), 'contract__event'),
        id=deadline_id)

    schema = d.content_schema or []
    data = d.content_data or {}
    campi = [{'label': f.get('label', f.get('key')),
              'value': data.get(f.get('key'), '')} for f in schema]

    deadline_ct = ContentType.objects.get_for_model(Deadline)
    docs = (Document.objects
            .filter(content_type=deadline_ct, object_id=d.id,
                    deleted_at__isnull=True)
            .order_by('created_at'))
    files = [{'id': x.id, 'nome': x.file_name, 'size': x.file_size_bytes,
              'data': x.created_at} for x in docs]

    today = timezone.now().date()
    received = d.status == DeadlineStatus.RECEIVED
    late = (not received) and d.due_date and d.due_date < today
    stato = 'completata' if received else ('ritardo' if late else 'dafare')
    tipo_map = {'content': 'Testi', 'file': 'File', 'both': 'Testi + file'}

    ev = d.contract.event
    sp = d.contract.sponsor
    try:
        evnome = ev.get_name() if ev else '—'
    except Exception:
        evnome = str(ev) if ev else '—'

    context = {
        **admin_site.each_context(request),
        'title': 'Dati consegnati',
        'titolo': d.title,
        'evento': evnome,
        'sponsor': sp.legal_name if sp else '—',
        'tipo': tipo_map.get(getattr(d, 'submission_kind', 'file'),
                             getattr(d, 'submission_kind', '')),
        'due_date': d.due_date,
        'stato': stato,
        'completata_da': (d.completed_by_contact.full_name
                          if d.completed_by_contact else ''),
        'completata_il': d.completed_at,
        'campi': campi,
        'files': files,
        'deadline_id': d.id,
    }
    return render(request, 'cruscotto/scadenza_dettaglio.html', context)


@staff_member_required
def cruscotto_scadenza_file(request, document_id):
    """Download (staff) di un file consegnato dal cliente."""
    from django.conf import settings
    from django.core.files.storage import default_storage
    from django.http import FileResponse, Http404
    from django.shortcuts import get_object_or_404
    from shared.models import Document

    document = get_object_or_404(
        scope_generic_by_event(request, Document.objects.filter(deleted_at__isnull=True)), id=document_id)
    relative_path = (document.storage_url or '').replace(settings.MEDIA_URL, '')
    if not relative_path or not default_storage.exists(relative_path):
        raise Http404("File non trovato sul server.")
    return FileResponse(
        default_storage.open(relative_path, 'rb'),
        as_attachment=True, filename=document.file_name)

@staff_member_required
def download_template_sponsor(request):
    """Genera al volo il template Excel sponsor/clienti e lo serve come download."""
    from io import BytesIO
    from django.http import HttpResponse
    from catalog.utils.excel_template import build_template_sponsor_workbook
    wb = build_template_sponsor_workbook()
    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    resp = HttpResponse(
        buffer.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    resp['Content-Disposition'] = 'attachment; filename="template_sponsor.xlsx"'
    return resp


@staff_member_required
def importa_sponsor_upload(request):
    if request.method != 'POST':
        from django.shortcuts import redirect
        return redirect('core:cruscotto_utility')
    return _esegui_import_excel(request, 'importa_sponsor', 'core:cruscotto_utility')

@staff_member_required
def download_template_contatti(request):
    """Genera al volo il template Excel contatti e lo serve come download."""
    from io import BytesIO
    from django.http import HttpResponse
    from catalog.utils.excel_template import build_template_contatti_workbook
    wb = build_template_contatti_workbook()
    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    resp = HttpResponse(
        buffer.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    resp['Content-Disposition'] = 'attachment; filename="template_contatti.xlsx"'
    return resp


@staff_member_required
def importa_contatti_upload(request):
    if request.method != 'POST':
        from django.shortcuts import redirect
        return redirect('core:cruscotto_utility')
    return _esegui_import_excel(request, 'importa_contatti', 'core:cruscotto_utility')
