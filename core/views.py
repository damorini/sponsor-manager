"""View del cruscotto: home con eventi in programmazione."""
from django.contrib.admin import site as admin_site
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import ValidationError
from django.shortcuts import render, redirect
import json
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from events.models import Event, EventStatus
from core.event_scope import (
    SESSION_EVENT_CHOSEN, events_for_user, get_active_event_id,
    scope_by_event, scope_generic_by_event, set_active_event,
)


# Tipi di consegna che rappresentano un MATERIALE caricato dal cliente.
_MATERIAL_SUBMISSIONS = ['file', 'content', 'both']


def materiali_da_rivedere_qs():
    """Scadenze-materiale RICEVUTE dal cliente e non ancora visionate
    dall'operatore. Esclude pagamenti e opzioni. Un nuovo upload
    (completed_at successivo a materials_reviewed_at) le fa ricomparire."""
    from django.db.models import Q, F
    from contracts.models import Deadline, DeadlineStatus
    return (Deadline.objects
            .filter(status=DeadlineStatus.RECEIVED,
                    submission_kind__in=_MATERIAL_SUBMISSIONS)
            .exclude(deadline_type__startswith='pagament')
            .exclude(deadline_type='scadenza_opzione')
            .filter(Q(materials_reviewed_at__isnull=True) |
                    Q(materials_reviewed_at__lt=F('completed_at')))
            .select_related('contract', 'contract__sponsor', 'contract__event'))


def marca_materiale_rivisto(deadline):
    """Segna che l'operatore ha visionato il materiale ricevuto (toglie
    l'avviso dal cruscotto). No-op se la scadenza non e' ricevuta o se e'
    gia' stata visionata dopo l'ultimo upload."""
    from contracts.models import DeadlineStatus
    if deadline.status != DeadlineStatus.RECEIVED:
        return
    rev = deadline.materials_reviewed_at
    comp = deadline.completed_at
    if rev is None or (comp and rev < comp):
        from django.utils import timezone
        deadline.materials_reviewed_at = timezone.now()
        deadline.save(update_fields=['materials_reviewed_at', 'updated_at'])


def _evento_scelto_valido(request, scelto):
    """L'id scelto e' un evento che l'utente puo' vedere (RBAC)?
    Robusto anche a valori non-UUID forzati nel POST."""
    try:
        return events_for_user(request).filter(pk=scelto).exists()
    except (ValueError, ValidationError):
        return False


@staff_member_required
def scegli_evento(request):
    """Scelta dell'EVENTO ATTIVO: mostrata al primo accesso dello staff
    (e raggiungibile sempre dal selettore nell'header). Da qui in poi
    tutte le liste dell'admin mostrano solo i dati dell'evento scelto;
    'Tutti gli eventi' spegne il filtro."""
    if request.method == 'POST':
        scelto = (request.POST.get('event_id') or '').strip()
        if scelto and scelto != 'tutti':
            if not _evento_scelto_valido(request, scelto):
                scelto = ''
        set_active_event(request, '' if scelto in ('', 'tutti') else scelto)
        return redirect('core:cruscotto_home')

    eventi = events_for_user(request)
    cards = []
    for ev in eventi:
        try:
            nome = ev.get_name() if hasattr(ev, 'get_name') else str(ev)
        except Exception:
            nome = str(ev)
        cards.append({
            'id': ev.id,
            'nome': nome,
            'status_label': ev.get_status_display(),
            'status_code': ev.status,
            'start_date': ev.start_date,
            'end_date': getattr(ev, 'end_date', None),
            'location': getattr(ev, 'luogo_completo', '') or getattr(ev, 'location', '') or '',
        })
    return render(request, 'cruscotto/scegli_evento.html', {
        **admin_site.each_context(request),
        'title': 'Su quale evento vuoi lavorare?',
        'cards': cards,
        'evento_attivo_id': get_active_event_id(request) or '',
    })


@staff_member_required
@require_POST
def imposta_evento_attivo(request):
    """Endpoint del selettore nell'header: cambia l'evento attivo al volo."""
    scelto = (request.POST.get('event_id') or '').strip()
    if scelto and scelto != 'tutti':
        if not _evento_scelto_valido(request, scelto):
            scelto = ''
    set_active_event(request, '' if scelto in ('', 'tutti') else scelto)
    dest = request.POST.get('next') or request.META.get('HTTP_REFERER') or ''
    # solo redirect interni
    from django.utils.http import url_has_allowed_host_and_scheme
    if not dest or not url_has_allowed_host_and_scheme(dest, allowed_hosts={request.get_host()}):
        return redirect('core:cruscotto_home')
    return redirect(dest)


@staff_member_required
def cruscotto_home(request):
    """Home cruscotto: card degli eventi attivi (SELLING + LIVE)."""
    # Primo accesso: prima si sceglie su quale evento lavorare.
    if not request.session.get(SESSION_EVENT_CHOSEN):
        return redirect('core:scegli_evento')

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
            'location': getattr(ev, 'luogo_completo', '') or getattr(ev, 'location', '') or '',
        })

    # Avviso: risposte dei clienti non ancora lette dall'operatore
    from sponsors.models import PortalMessage, MessageSender
    from django.urls import reverse as _rev
    _unread = (PortalMessage.objects
               .filter(sender=MessageSender.SPONSOR, read_at__isnull=True,
                       is_active=True, archived_at__isnull=True)
               .select_related('sponsor').order_by('-created_at'))
    _mittenti = []
    for _m in _unread[:10]:
        _nome = _m.sponsor.legal_name
        if _nome not in _mittenti:
            _mittenti.append(_nome)

    # Avviso: preventivi creati ma NON ancora inviati (contratti principali in Bozza)
    from contracts.models import Contract, ContractStatus, ContractKind
    _bozze = scope_by_event(request, (Contract.objects
              .filter(status=ContractStatus.DRAFT,
                      contract_kind=ContractKind.MAIN,
                      deleted_at__isnull=True)
              .select_related('sponsor')
              .order_by('-created_at')), 'event')
    _bozze_count = _bozze.count()
    _bozze_sponsors = []
    for _c in _bozze[:10]:
        _n = _c.sponsor.legal_name if _c.sponsor_id else '(senza cliente)'
        if _n not in _bozze_sponsors:
            _bozze_sponsors.append(_n)

    # Avviso: materiali ricevuti dal cliente e non ancora visionati dall'operatore
    _materiali = scope_by_event(request, materiali_da_rivedere_qs(), 'contract__event')
    _materiali_count = _materiali.count()
    _materiali_sponsors = []
    for _d in _materiali.order_by('-completed_at')[:10]:
        _n = (_d.contract.sponsor.legal_name
              if _d.contract and _d.contract.sponsor_id else '(senza cliente)')
        if _n not in _materiali_sponsors:
            _materiali_sponsors.append(_n)

    context = {
        **admin_site.each_context(request),
        'title': 'Cruscotto',
        'cards': cards,
        'n_eventi': len(cards),
        'unread_msg_count': _unread.count(),
        'unread_msg_senders': _mittenti,
        'unread_msg_url': _rev('admin:sponsors_portalmessage_changelist') + '?mitt=sponsor&letto=no',
        'bozze_count': _bozze_count,
        'bozze_sponsors': _bozze_sponsors,
        'bozze_url': _rev('admin:contracts_contract_changelist') + '?status__exact=draft',
        'materiali_count': _materiali_count,
        'materiali_sponsors': _materiali_sponsors,
        'materiali_url': _rev('core:cruscotto_scadenze_cliente'),
    }
    return render(request, 'cruscotto/home.html', context)


@staff_member_required
def cruscotto_cerca(request):
    """Ricerca cliente globale dal cruscotto.

    Cerca per ragione sociale, P.IVA e nome/email dei contatti; esclude
    gli sponsor nel cestino (manager di default del soft-delete). Le
    anagrafiche sono visibili a tutti gli operatori (niente scope evento).
    """
    from django.db.models import Q
    from django.urls import reverse
    from sponsors.models import Sponsor

    q = (request.GET.get('q') or '').strip()
    risultati = []
    if q:
        qs = (Sponsor.objects
              .filter(Q(legal_name__icontains=q)
                      | Q(vat_number__icontains=q)
                      | Q(contacts__full_name__icontains=q)
                      | Q(contacts__email__icontains=q))
              .distinct()
              .order_by('legal_name')
              .prefetch_related('contacts'))
        for sp in qs[:50]:
            try:
                pc = sp.primary_contact or sp.contacts.first()
            except Exception:
                pc = None
            risultati.append({
                'id': sp.id,
                'nome': sp.legal_name,
                'piva': sp.vat_number or '',
                'contatto': pc.full_name if pc else '',
                'email': pc.email if pc else '',
                'admin_url': reverse('admin:sponsors_sponsor_change', args=[sp.id]),
                'nuovo_contratto_url': (reverse('admin:contracts_contract_add')
                                        + f'?sponsor={sp.id}'),
            })

    context = {
        **admin_site.each_context(request),
        'title': 'Cerca cliente',
        'q': q,
        'risultati': risultati,
    }
    return render(request, 'cruscotto/cerca.html', context)


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
    from contracts.payments import PaymentStatus, PaymentMethodChoice
    confermati_qs = contratti_ev.filter(status__in=CONFIRMED)
    tot_confermato = Decimal('0.00')
    incassato = Decimal('0.00')
    for c in confermati_qs:
        tot_confermato += (c.total or Decimal('0.00'))
        for p in c.payments.filter(status=PaymentStatus.SUCCEEDED):
            incassato += (p.amount_gross or Decimal('0.00'))
    da_incassare = tot_confermato - incassato

    # Bonifici in attesa di conferma (PENDING + method=bank_transfer)
    from contracts.payments import Payment as _Payment
    bonifici_in_attesa = _Payment.objects.filter(
        contract__event=ev,
        status=PaymentStatus.PENDING,
        payment_method=PaymentMethodChoice.BANK_TRANSFER,
    ).count()

    # Email fallite collegate ai contratti dell'evento
    from shared.models import Communication, CommunicationStatus
    from django.contrib.contenttypes.models import ContentType
    from contracts.models import Contract as _Contract
    _ct = ContentType.objects.get_for_model(_Contract)
    _contract_ids = list(contratti_ev.values_list('id', flat=True))
    email_fallite = Communication.objects.filter(
        content_type=_ct,
        object_id__in=_contract_ids,
        status=CommunicationStatus.FAILED,
    ).count()

    incassi = {
        'incassato': incassato,
        'da_incassare': da_incassare,
        'tot_confermato': tot_confermato,
        'bonifici_in_attesa': bonifici_in_attesa,
        'email_fallite': email_fallite,
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
def download_template_catalogo(request):
    """Genera al volo il template Excel del CATALOGO GENERALE e lo serve."""
    from io import BytesIO
    from django.http import HttpResponse
    from catalog.utils.excel_template import build_template_catalogo_workbook

    wb = build_template_catalogo_workbook()
    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    resp = HttpResponse(
        buffer.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    resp['Content-Disposition'] = 'attachment; filename="template_catalogo.xlsx"'
    return resp


@staff_member_required
def importa_catalogo_upload(request):
    if request.method != 'POST':
        from django.shortcuts import redirect
        return redirect('core:cruscotto_utility')
    return _esegui_import_excel(request, 'importa_catalogo', 'core:cruscotto_utility')


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
def catalog_service_data(request, pk):
    """Dati di una voce del Catalogo madre (CatalogService), per auto-compilare
    il form Servizio quando si sceglie 'dal catalogo'."""
    from django.http import JsonResponse, Http404
    from catalog.models import CatalogService
    cs = CatalogService.objects.filter(pk=pk).first()
    if not cs:
        raise Http404()

    def _t(field):
        v = getattr(cs, field, None) or {}
        if not isinstance(v, dict):
            v = {}
        return {'it': v.get('it', '') or '', 'en': v.get('en', '') or ''}

    return JsonResponse({
        'code': cs.code or '',
        'name': _t('name'),
        'description': _t('description'),
        'base_price': str(cs.base_price if cs.base_price is not None else ''),
        'vat_rate': str(cs.vat_rate if cs.vat_rate is not None else ''),
        'pricing_mode': cs.pricing_mode or '',
        'accounting_category': cs.accounting_category or '',
        'max_quantity': '' if cs.max_quantity is None else cs.max_quantity,
        'triggers_deadlines': bool(cs.triggers_deadlines),
        'is_self_purchasable': bool(cs.is_self_purchasable),
    })


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
def manuale_operativo(request):
    """Serve il MANUALE OPERATIVO COMPLETO (Markdown) reso in HTML lato client
    con marked.js (CDN). Nessuna dipendenza Python aggiuntiva."""
    import os
    from django.conf import settings
    from django.http import HttpResponse, Http404
    path = os.path.join(settings.BASE_DIR, 'docs', 'MANUALE-OPERATIVO-COMPLETO.md')
    try:
        with open(path, encoding='utf-8') as f:
            md = f.read()
    except FileNotFoundError:
        raise Http404("Manuale operativo non trovato.")
    # Embedding sicuro dentro <textarea>: spezzo eventuali sequenze di chiusura.
    md_safe = md.replace('</textarea', '<\\/textarea')
    html = """<!doctype html><html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Manuale operativo — Sponsor Manager</title>
<script src="https://cdn.jsdelivr.net/npm/marked@12.0.2/marked.min.js"></script>
<style>
  :root{ --ink:#1A1612; --terra:#7A3613; --oro:#C8A04E; --crema:#FBF7F0; }
  body{ margin:0; background:var(--crema); color:var(--ink);
        font:16px/1.6 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif; }
  .wrap{ max-width:920px; margin:0 auto; padding:28px 22px 80px; }
  .top{ position:sticky; top:0; background:var(--ink); color:#fff; margin:-28px -22px 24px;
        padding:12px 22px; display:flex; gap:12px; align-items:center; }
  .top a{ color:var(--oro); text-decoration:none; font-weight:600; font-size:14px; }
  .top button{ margin-left:auto; background:var(--terra); color:#fff; border:0;
        border-radius:8px; padding:7px 14px; font-weight:600; cursor:pointer; }
  h1,h2,h3{ line-height:1.25; }
  h1{ border-bottom:3px solid var(--oro); padding-bottom:8px; }
  h2{ margin-top:2em; border-bottom:1px solid #e6ddcd; padding-bottom:6px; color:var(--terra); }
  h3{ margin-top:1.6em; }
  table{ border-collapse:collapse; width:100%; margin:14px 0; font-size:14px; }
  th,td{ border:1px solid #ddd; padding:8px 10px; text-align:left; vertical-align:top; }
  th{ background:#f3ece0; }
  tr:nth-child(even) td{ background:#fbf8f2; }
  code{ background:#efe9dd; padding:1px 5px; border-radius:4px; font-size:.92em; }
  pre{ background:#1f1b16; color:#f4ecd8; padding:14px; border-radius:8px; overflow:auto; }
  pre code{ background:none; color:inherit; padding:0; }
  blockquote{ border-left:4px solid var(--oro); margin:14px 0; padding:6px 14px;
        background:#fff7e6; color:#5b4a2a; }
  a{ color:var(--terra); }
  @media print{ .top{ display:none; } body{ background:#fff; } }
</style></head><body>
<div class="wrap">
  <div class="top">
    <a href="/admin/">← Backoffice</a>
    <a href="/admin/cruscotto/manuale/">📖 Manuale d'uso</a>
    <button onclick="window.print()">🖨️ Stampa / PDF</button>
  </div>
  <textarea id="md" hidden>__MD__</textarea>
  <div id="content">Rendering…</div>
</div>
<script>
  var src = document.getElementById('md').value;
  document.getElementById('content').innerHTML = marked.parse(src);
</script>
</body></html>"""
    return HttpResponse(html.replace('__MD__', md_safe))


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


@staff_member_required
def registra_incasso(request, pk):
    """Registra manualmente un incasso (bonifico o altro) su un contratto."""
    from decimal import Decimal, InvalidOperation
    from django.http import Http404
    from django.contrib import messages
    from django.utils import timezone
    from contracts.models import Contract, ContractStatus
    from contracts.payments import Payment, PaymentStatus, PaymentMethodChoice

    try:
        c = Contract.objects.select_related('sponsor', 'event').get(pk=pk)
    except Contract.DoesNotExist:
        raise Http404("Contratto non trovato")

    CONFIRMED = [ContractStatus.SIGNED, ContractStatus.ACTIVE, ContractStatus.COMPLETED]
    if c.status not in CONFIRMED:
        messages.error(request, "Il contratto non è in uno stato confermato.")
        return redirect('core:cruscotto_da_incassare', pk=c.event_id)

    error = None
    if request.method == 'POST':
        try:
            amount = Decimal(request.POST.get('amount_gross', '').replace(',', '.'))
            if amount <= 0:
                raise ValueError("Importo non valido")
        except (InvalidOperation, ValueError):
            error = "Inserisci un importo valido (es. 300.00)."
        else:
            method = request.POST.get('payment_method', PaymentMethodChoice.BANK_TRANSFER)
            reference = request.POST.get('bank_transfer_reference', '')
            notes = request.POST.get('notes', '')
            payment = Payment(
                contract=c,
                payment_method=method,
                amount_gross=amount,
                status=PaymentStatus.SUCCEEDED,
                completed_at=timezone.now(),
                notes=notes,
            )
            if reference:
                payment.bank_transfer_reference = reference
                payment.bank_transfer_received_at = timezone.now().date()
            payment.save()  # triggera reconcile_payment_deadlines() in Payment.save()
            messages.success(
                request,
                f"Incasso di € {amount:.2f} registrato per {c.contract_number}."
            )
            return redirect('core:cruscotto_da_incassare', pk=c.event_id)

    try:
        nome_ev = c.event.get_name() if hasattr(c.event, 'get_name') else str(c.event)
    except Exception:
        nome_ev = str(c.event)

    method_choices = [
        (PaymentMethodChoice.BANK_TRANSFER, 'Bonifico bancario'),
        (PaymentMethodChoice.MANUAL, 'Manuale / altro'),
    ]
    context = {
        **admin_site.each_context(request),
        'title': f'Registra incasso · {c.contract_number}',
        'contratto': c,
        'nome_evento': nome_ev,
        'method_choices': method_choices,
        'error': error,
    }
    return render(request, 'cruscotto/registra_incasso.html', context)


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
def export_sponsor(request):
    """Scarica un Excel con TUTTI gli sponsor/clienti (anagrafica, non per evento)."""
    from django.http import HttpResponse
    from sponsors.models import Sponsor
    from catalog.utils.excel_template import export_sponsor_workbook

    qs = Sponsor.objects.all().order_by('legal_name').prefetch_related('contacts')
    wb = export_sponsor_workbook(qs)
    resp = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    resp['Content-Disposition'] = 'attachment; filename="sponsor_clienti.xlsx"'
    wb.save(resp)
    return resp


@staff_member_required
def export_contatti(request):
    """Scarica un Excel con TUTTI i contatti (anagrafica, non per evento)."""
    from django.http import HttpResponse
    from sponsors.models import Contact
    from catalog.utils.excel_template import export_contatti_workbook

    qs = (Contact.objects.select_related('sponsor')
          .order_by('sponsor__legal_name', 'last_name', 'full_name'))
    wb = export_contatti_workbook(qs)
    resp = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    resp['Content-Disposition'] = 'attachment; filename="contatti.xlsx"'
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
          .filter(deadline_template__isnull=False,
                  # niente scadenze di contratti nel cestino
                  contract__deleted_at__isnull=True)
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

    # Filtri di visualizzazione: i contatori dei box restano quelli globali
    # della selezione evento; stato e ricerca filtrano solo la tabella.
    stato = request.GET.get('stato') or ''
    if stato not in ('completata', 'dafare', 'ritardo'):
        stato = ''
    q = (request.GET.get('q') or '').strip()

    righe_visibili = righe
    if stato:
        righe_visibili = [r for r in righe_visibili if r['stato'] == stato]
    if q:
        ql = q.lower()
        righe_visibili = [r for r in righe_visibili
                          if ql in (r['sponsor'] or '').lower()
                          or ql in (r['titolo'] or '').lower()]

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
        'righe': righe_visibili,
        'tot': len(deadlines),
        'completate': completate,
        'da_fare': da_fare,
        'in_ritardo': in_ritardo,
        'eventi': ev_list,
        'event_id': event_id,
        'stato': stato,
        'q': q,
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

    # L'operatore sta visionando la scadenza: toglie l'avviso "materiali ricevuti".
    marca_materiale_rivisto(d)

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
def documento_apri(request, document_id):
    """Apre un Document (PDF preventivo/contratto/ecc.) INLINE nel browser.

    Streama il file dallo storage con autenticazione staff: funziona sia in
    sviluppo sia in produzione (non dipende dal serving diretto di /media/),
    e forza la visualizzazione inline invece del download.
    """
    from django.conf import settings
    from django.core.files.storage import default_storage
    from django.http import FileResponse, Http404
    from django.shortcuts import get_object_or_404
    from shared.models import Document

    document = get_object_or_404(
        scope_generic_by_event(request, Document.objects.filter(deleted_at__isnull=True)),
        id=document_id)
    relative_path = (document.storage_url or '').replace(settings.MEDIA_URL, '', 1).lstrip('/')
    if not relative_path or not default_storage.exists(relative_path):
        raise Http404("File non trovato sul server.")
    resp = FileResponse(
        default_storage.open(relative_path, 'rb'),
        as_attachment=False, filename=document.file_name)
    # Anti-cache: i PDF rigenerati (stesso path) devono essere sempre ricaricati,
    # cosi' il browser non mostra una versione vecchia gia' aperta.
    resp['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp['Pragma'] = 'no-cache'
    resp['Expires'] = '0'
    return resp


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
