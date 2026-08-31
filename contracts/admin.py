"""
Admin per Contracts.

Il cuore del sistema. Contiene:
- Contract con righe e scadenze inline
- ContractLine come admin separato (per ricerche)
- Deadline come admin separato
- Payment per gestire pagamenti ecommerce
- CartSession per vedere carrelli abbandonati

Azioni admin custom:
- Marca come firmato (transizione di stato)
- Genera PDF contratto (via Celery, placeholder per ora)
- Annulla contratto
"""
import logging

from django import forms
from django.contrib import admin, messages
from django.contrib.admin import helpers
from core.admin_filters import evento_filter
from core.softdelete_admin import SoftDeleteAdminMixin, DeletedListFilter
from django.urls import reverse
from django.utils.html import format_html
from django.utils import timezone
from django.conf import settings
from django.urls import path
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponseRedirect

from .models import (
    Contract, ContractKind, ContractLine, ContractStatus,
    Deadline, DeadlineStatus,
)
from .payments import (
    CartSession, CartSessionStatus, Payment,
    PaymentMethodChoice, PaymentStatus,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Inline forms
# =============================================================================

class _VariantSelectByService(forms.Select):
    """Select per la variante: ogni opzione porta data-service=<id servizio>,
    cosi' un JS mostra solo le varianti del servizio scelto nella riga."""
    def __init__(self, *args, service_by_pk=None, **kwargs):
        self.service_by_pk = service_by_pk or {}
        super().__init__(*args, **kwargs)

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(
            name, value, label, selected, index, subindex=subindex, attrs=attrs)
        raw = getattr(value, 'value', value)
        sid = self.service_by_pk.get(str(raw))
        if sid:
            option['attrs']['data-service'] = str(sid)
        return option


class ContractLineInline(admin.TabularInline):
    """Righe contratto editabili dentro il form contratto.

    'service' vuoto = riga LIBERA (richiesta specifica del cliente non a
    catalogo): compila 'custom_description' al suo posto. Nessun controllo
    di quantita'/disponibilita' di catalogo si applica a queste righe -
    vedi ContractLine.clean()."""
    model = ContractLine
    extra = 0
    fields = (
        'service', 'custom_description', 'service_variant', 'quantity', 'unit_price',
        'discount_percent', 'discount_amount',
        'line_subtotal', 'line_vat', 'line_total',
    )
    readonly_fields = ('line_subtotal', 'line_vat', 'line_total')
    autocomplete_fields = ['service']

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        # 'service': autocomplete filtrato per evento del contratto.
        # 'service_variant': select con opzioni taggate per servizio, filtrate
        #   lato client (JS) sul servizio scelto nella riga, e per evento.
        contract = None
        if db_field.name in ('service', 'service_variant'):
            contract_id = None
            try:
                contract_id = request.resolver_match.kwargs.get('object_id')
            except Exception:
                contract_id = None
            if contract_id:
                from .models import Contract
                contract = Contract.objects.filter(pk=contract_id).first()

        if db_field.name == 'service' and contract is not None and contract.event_id:
            from catalog.admin import _AutocompleteServiceByEvento
            from catalog.models import Service
            kwargs['widget'] = _AutocompleteServiceByEvento(
                db_field, self.admin_site, parent_event_id=contract.event_id)
            kwargs['queryset'] = Service.objects.filter(event_id=contract.event_id)

        elif db_field.name == 'service_variant':
            from catalog.models import ServiceVariant
            vqs = ServiceVariant.objects.filter(is_active=True)
            if contract is not None and contract.event_id:
                vqs = vqs.filter(service__event_id=contract.event_id)
            vqs = vqs.select_related('service')
            kwargs['queryset'] = vqs
            kwargs['widget'] = _VariantSelectByService(
                service_by_pk={str(v.pk): str(v.service_id) for v in vqs})

        return super().formfield_for_foreignkey(db_field, request, **kwargs)


def _deadline_file_esempio(obj):
    """Link di download del file di esempio (modello) della scadenza, se presente."""
    tpl = getattr(obj, 'deadline_template', None)
    f = getattr(tpl, 'client_template_file', None) if tpl else None
    try:
        url = f.url if f else None
    except Exception:
        url = None
    if url:
        return format_html('<a href="{}" target="_blank" rel="noopener">⬇ Scarica</a>', url)
    from django.utils.safestring import mark_safe
    return mark_safe('<span style="color:#999;">—</span>')


_DQ_BTN = ('display:inline-block;margin:0 3px 2px 0;padding:2px 9px;'
           'border:1px solid {col};border-radius:6px;background:#fff;'
           'color:{col};font-size:11px;font-weight:600;cursor:pointer;'
           'white-space:nowrap;text-decoration:none;')


def _deadline_azioni_rapide_html(obj, next_url=None):
    """Pulsanti a UN click per la scadenza (lista admin e inline contratto).
    - scadenze normali: '✓ Ricevuta' + 'Esonera' (POST via JS, vedi
      deadline_quick_actions_v1.js);
    - scadenze di PAGAMENTO: link '💶 Registra incasso' (la registrazione
      marca da sola la scadenza) + 'Esonera'."""
    from django.utils.safestring import mark_safe as _ms
    from .models import DeadlineStatus as _DS
    if obj is None or not obj.pk:
        return '—'
    if obj.status in (_DS.RECEIVED, _DS.WAIVED):
        return _ms('<span style="color:#999;">—</span>')
    parti = []
    dtype = (obj.deadline_type or '')
    if dtype.startswith('pagamento'):
        url = reverse('core:cruscotto_registra_incasso', args=[obj.contract_id])
        if next_url:
            from urllib.parse import quote
            url += '?next=' + quote(next_url)
        parti.append(format_html(
            '<a href="{}" style="{}">💶 Registra incasso</a>',
            url, _DQ_BTN.format(col='#1d6534')))
    else:
        parti.append(format_html(
            '<button type="button" class="dq-btn" data-url="{}" style="{}" '
            'title="Segna come ricevuta (un click)">✓ Ricevuta</button>',
            reverse('admin:contracts_deadline_segna_ricevuta', args=[obj.pk]),
            _DQ_BTN.format(col='#1d6534')))
    parti.append(format_html(
        '<button type="button" class="dq-btn" data-url="{}" style="{}" '
        'data-confirm="Esonerare {}? Il cliente non riceverà più promemoria per questa scadenza." '
        'title="Esonera: la scadenza non è più dovuta">Esonera</button>',
        reverse('admin:contracts_deadline_esonera', args=[obj.pk]),
        _DQ_BTN.format(col='#9C4A1F'), obj.title))
    return _ms(''.join(parti))


class DeadlineInline(admin.TabularInline):
    """Scadenze inline nel contratto: sola lettura sui dati (generate in
    automatico) ma con azioni rapide e link di apertura."""
    model = Deadline
    extra = 0
    show_change_link = True
    fields = ('title', 'due_date', 'status', 'completed_at', 'reminder_count',
              'file_esempio', 'azioni_rapide')
    readonly_fields = ('title', 'due_date', 'completed_at', 'reminder_count',
                       'file_esempio', 'azioni_rapide')
    can_delete = False

    @admin.display(description='File di esempio')
    def file_esempio(self, obj):
        return _deadline_file_esempio(obj)

    @admin.display(description='Azioni rapide')
    def azioni_rapide(self, obj):
        # dopo l'azione si torna sulla scheda contratto (next)
        next_url = (reverse('admin:contracts_contract_change',
                            args=[obj.contract_id]) if obj and obj.pk else None)
        return _deadline_azioni_rapide_html(obj, next_url=next_url)

    def has_add_permission(self, request, obj=None):
        return False


class PaymentInline(admin.TabularInline):
    """Pagamenti ONLINE del contratto (PayPal/carta), sola lettura.
    I bonifici e gli incassi manuali stanno SOLO nell'inline 'Registra
    incasso' qui sotto: prima comparivano in entrambi e sembravano doppi."""
    model = Payment
    extra = 0
    verbose_name = "Pagamento online (PayPal/carta)"
    verbose_name_plural = "Pagamenti online (PayPal/carta)"
    fields = (
        'payment_method', 'amount_gross', 'amount_fee',
        'status', 'paypal_order_id', 'bank_transfer_reference', 'completed_at',
    )
    readonly_fields = fields
    can_delete = False
    show_change_link = True

    def get_queryset(self, request):
        from contracts.payments import PaymentMethodChoice
        return super().get_queryset(request).exclude(payment_method__in=[
            PaymentMethodChoice.BANK_TRANSFER, PaymentMethodChoice.MANUAL])

    def has_add_permission(self, request, obj=None):
        return False


class RegistraIncassoInline(admin.TabularInline):
    """Inline per REGISTRARE incassi manuali (bonifici sponsorizzazioni)."""
    model = Payment
    extra = 0
    verbose_name = "Registra incasso (manuale/bonifico)"
    verbose_name_plural = "Registra incasso (manuale/bonifico)"
    fields = (
        'payment_method', 'amount_gross', 'status',
        'completed_at', 'bank_transfer_reference', 'notes',
    )
    # mostra solo i pagamenti manuali/bonifico (i PayPal restano nell'altro inline)
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        from contracts.payments import PaymentMethodChoice
        return qs.filter(payment_method__in=[
            PaymentMethodChoice.BANK_TRANSFER, PaymentMethodChoice.MANUAL])

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        from contracts.payments import PaymentMethodChoice, PaymentStatus
        # default comodi: bonifico + completato
        formset.form.base_fields['payment_method'].initial = PaymentMethodChoice.BANK_TRANSFER
        formset.form.base_fields['status'].initial = PaymentStatus.SUCCEEDED
        return formset


# =============================================================================
# CONTRACT
# =============================================================================

class EventoFilter(admin.SimpleListFilter):
    """Filtro 'Per evento' a menu a tendina: mostra solo i contratti dell'evento scelto."""
    title = "Evento"
    parameter_name = "event"
    template = "admin/evento_dropdown_filter.html"

    def lookups(self, request, model_admin):
        from events.models import Event
        return [(str(e.pk), str(e)) for e in Event.objects.all().order_by("-created_at")]

    def queryset(self, request, queryset):
        v = self.value()
        if v:
            return queryset.filter(event_id=v)
        return queryset


class TodoFilter(admin.SimpleListFilter):
    """Scorciatoie operative: filtra i contratti per "cosa fare adesso"."""
    title = "Cose da fare"
    parameter_name = "todo"

    def lookups(self, request, model_admin):
        return (
            ('da_inviare', 'Preventivi da inviare'),
            ('in_attesa_firma', 'In attesa di firma'),
            ('senza_risposta', 'Inviati senza risposta da 7+ giorni'),
            ('confermati', 'Confermati (firmati/attivi/completati)'),
            ('opzioni_in_scadenza', 'Opzioni in scadenza (7 giorni)'),
            ('opzionati', 'Spazi opzionati (bozze con stand)'),
            ('firmati_senza_scadenze', 'Firmati senza scadenze'),
            ('carrelli', 'Carrelli abbandonati'),
        )

    def queryset(self, request, qs):
        from datetime import date, timedelta
        v = self.value()
        if v == 'da_inviare':
            return qs.filter(contract_kind=ContractKind.MAIN, status=ContractStatus.DRAFT)
        if v == 'in_attesa_firma':
            return qs.filter(status=ContractStatus.SENT)
        if v == 'senza_risposta':
            # identico all'avviso della home cruscotto: inviati fermi da 7+ gg
            from django.utils import timezone as _tz
            from datetime import timedelta as _td
            return qs.filter(
                status=ContractStatus.SENT, contract_kind=ContractKind.MAIN,
                sent_date__lt=_tz.now() - _td(days=7))
        if v == 'confermati':
            # stessa definizione delle card "Confermati" del cruscotto
            return qs.filter(status__in=[
                ContractStatus.SIGNED, ContractStatus.ACTIVE,
                ContractStatus.COMPLETED])
        if v == 'opzioni_in_scadenza':
            # identico all'avviso della home cruscotto: bozze con opzione
            # che scade tra oggi e +7 giorni
            oggi = date.today()
            return qs.filter(
                status=ContractStatus.DRAFT,
                option_until__gte=oggi,
                option_until__lte=oggi + timedelta(days=7))
        if v == 'opzionati':
            # identico alla card "Opzionati" della pagina evento: bozze con
            # uno spazio assegnato e opzione non scaduta
            from django.db.models import Q
            return qs.filter(
                status=ContractStatus.DRAFT,
                option_until__gte=date.today(),
            ).filter(Q(stand__isnull=False) | Q(stand_block__isnull=False))
        if v == 'firmati_senza_scadenze':
            return qs.filter(
                status__in=[ContractStatus.SIGNED, ContractStatus.ACTIVE],
                deadlines__isnull=True,
            ).distinct()
        if v == 'carrelli':
            return qs.filter(contract_kind=ContractKind.ADDON, status=ContractStatus.DRAFT)
        return qs


@admin.register(Contract)
class ContractAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    @admin.display(description="Numero contratto")
    def contract_number_display(self, obj):
        # Mostra il numero; sui nuovi (non salvati) avvisa che e automatico
        if obj and obj.pk and obj.contract_number:
            return obj.contract_number
        return "(generato automaticamente al salvataggio)"

    list_display = (
        'contract_number', 'sponsor_link', 'event_link',
        'kind_badge', 'status_badge', 'venue_display',
        'total_display', 'incassato_display', 'origin_badge', 'created_at_short',
    )
    list_filter = (
        TodoFilter, EventoFilter,
        'status', 'contract_kind', 'origin', 'language',
        'vat_applicable', DeletedListFilter,
    )
    search_fields = (
        'contract_number', 'sponsor__legal_name', 'sponsor__vat_number',
        'event__name', 'event__slug',
    )
    list_select_related = ('sponsor', 'event', 'stand', 'stand_block')
    autocomplete_fields = [
        'sponsor', 'event', 'stand', 'stand_block',
        'parent_contract', 'sponsor_signer_contact',
    ]
    readonly_fields = (
        'contract_number_display',
        'created_at', 'updated_at',
        'subtotal', 'vat_amount', 'total',
        'sent_date', 'cancelled_date',
        'piano_acconto_display', 'piano_saldo_display',
        'piano_scad_acconto_display', 'piano_scad_saldo_display',
    )
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)

    @property
    def inlines(self):
        from shared.admin import ContractDocumentInline
        return [ContractLineInline, DeadlineInline, PaymentInline,
                RegistraIncassoInline, ContractDocumentInline]

    def save_formset(self, request, form, formset, change):
        from shared.models import Document
        from shared.admin import _store_uploaded_document
        if formset.model is not Document:
            return super().save_formset(request, form, formset, change)
        # Inline Documenti: gestisci il file caricato e l'autore.
        instances = formset.save(commit=False)
        for obj in instances:
            frm = next((f for f in formset.forms if f.instance is obj), None)
            up = frm.cleaned_data.get('upload') if frm else None
            if not obj.object_id:
                obj.object_id = form.instance.pk
            if up:
                _store_uploaded_document(obj, up)
            if obj.uploaded_by_user_id is None:
                obj.uploaded_by_user = request.user
            obj.save()
        formset.save_m2m()
        for obj in formset.deleted_objects:
            obj.delete()

    def get_queryset(self, request):
        from django.db.models import Sum, Q
        from core.event_scope import scope_by_event
        qs = scope_by_event(request, super().get_queryset(request), 'event')
        # Incassato per contratto (somma Payment SUCCEEDED): alimenta la
        # colonna "Incassato / Residuo" senza query per riga.
        return qs.annotate(
            _incassato=Sum(
                'payments__amount_gross',
                filter=Q(payments__status='succeeded'),
            ),
        )

    def get_changeform_initial_data(self, request):
        """Pre-compila evento/sponsor da querystring (es. dal pulsante
        '+ Nuovo contratto' di una lista filtrata o della scheda Sponsor).
        In mancanza, usa l'EVENTO ATTIVO scelto nell'header: chi lavora su
        un congresso non deve risceglierlo a ogni nuovo preventivo."""
        initial = super().get_changeform_initial_data(request)
        for k in ('event', 'sponsor'):
            v = request.GET.get(k)
            if v:
                initial.setdefault(k, v)
        if 'event' not in initial:
            from core.event_scope import get_active_event_id
            active_id = get_active_event_id(request)
            if active_id:
                initial['event'] = active_id
        return initial

    def get_search_results(self, request, queryset, search_term):
        queryset, may_dup = super().get_search_results(request, queryset, search_term)
        if "/autocomplete/" in request.path:
            sp = request.GET.get('sponsor')
            if sp:
                queryset = queryset.filter(sponsor_id=sp)
            ev = request.GET.get('event')
            if ev:
                queryset = queryset.filter(event_id=ev)
            # Per il campo 'Contratto principale' mostra solo i contratti PRINCIPALI.
            if request.GET.get('field_name') == 'parent_contract':
                queryset = queryset.filter(contract_kind=ContractKind.MAIN)
        return queryset, may_dup

    def save_model(self, request, obj, form, change):
        # Legge lo stato attuale nel DB prima di sovrascriverlo.
        old_status = None
        if change:
            old_status = (
                Contract.all_objects
                .filter(pk=obj.pk)
                .values_list('status', flat=True)
                .first()
            )

        super().save_model(request, obj, form, change)

        # Se il form ha portato il contratto a SIGNED cambiando lo stato a
        # MANO (invece che con l'azione "Segna come firmato"), esegui la
        # stessa cascata di mark_as_signed: senza, non si generavano
        # scadenze di pagamento/materiali, la scadenza 'contratto firmato',
        # lo stand non passava ad Assegnato e signed_date restava vuota
        # (successo con CROMA: contratto firmato senza scadenza acconto).
        if (change
                and obj.status == ContractStatus.SIGNED
                and old_status
                and old_status in (ContractStatus.DRAFT, ContractStatus.SENT,
                                   ContractStatus.PENDING_PAYMENT)):
            if not obj.signed_date:
                obj.signed_date = timezone.now().date()
                obj.save(update_fields=['signed_date', 'updated_at'])
            obj._update_venue_status()
            obj._generate_deadlines()
            obj._generate_payment_deadlines()
            obj._generate_signed_contract_deadline()
            self.message_user(
                request,
                "Contratto firmato: scadenze generate e spazio espositivo "
                "assegnato (cascata completata come per l'azione 'Segna come "
                "firmato').")

        # Stato portato a MANO su INVIATO: stessa cascata dell'invio vero
        # (data invio + spazio riservato), altrimenti l'avviso "fermi da 7gg"
        # non parte mai e lo stand resta Disponibile.
        if (change
                and obj.status == ContractStatus.SENT
                and old_status == ContractStatus.DRAFT):
            if not obj.sent_date:
                obj.sent_date = timezone.now()
                obj.save(update_fields=['sent_date', 'updated_at'])
            obj._update_venue_status()

        # Firmatario scelto ma con anagrafica incompleta: meglio saperlo ORA
        # che alla conferma del cliente (che verrebbe bloccata).
        try:
            _signer = obj.sponsor_signer_contact
            if _signer is not None:
                _mancanti = _signer.dati_firmatario_mancanti()
                if _mancanti:
                    self.message_user(
                        request,
                        f"⚠ Il firmatario {_signer.full_name} non ha ancora: "
                        + ", ".join(_mancanti)
                        + ". Senza questi dati il contratto non potrà essere "
                        "generato alla conferma.",
                        level=messages.WARNING)
        except Exception:
            pass

        # Se il form ha portato il contratto a CANCELLED (bypassing cancel()),
        # eseguiamo la stessa cascata: libera stand/blocco e azzera scadenze aperte.
        if (change
                and obj.status == ContractStatus.CANCELLED
                and old_status
                and old_status != ContractStatus.CANCELLED):
            obj._update_venue_status()
            from .models import DeadlineStatus
            obj.deadlines.filter(
                status__in=[
                    DeadlineStatus.PENDING,
                    DeadlineStatus.REMINDER_SENT,
                    DeadlineStatus.OVERDUE,
                ]
            ).update(status=DeadlineStatus.WAIVED)

        # Genera automaticamente la riga stand/blocco se non ancora presente.
        # Solo per contratti non annullati (evita righe fantasma su contratti cancellati).
        if obj.status != ContractStatus.CANCELLED and (obj.stand_id or obj.stand_block_id):
            from .services.stand_line import (
                genera_riga_da_stand, has_stand_line, applica_override_stand,
            )
            if not has_stand_line(obj):
                esito, msg = genera_riga_da_stand(obj)
                if esito == 'creata':
                    self.message_user(request, f"Riga stand aggiunta automaticamente: {msg}")
                elif esito == 'no_prezzo':
                    self.message_user(request, f"Attenzione: {msg}", level=messages.WARNING)
            # Applica/aggiorna prezzo e sconto stand impostati sul contratto.
            if applica_override_stand(obj):
                self.message_user(
                    request, "Prezzo/sconto stand applicati alla riga.")

    # NB: delete_model / delete_queryset NON sono ridefiniti qui: li fornisce
    # SoftDeleteAdminMixin, che itera per-record (quindi Contract.delete()
    # scatta e libera stand/blocco) e, per i record GIA' nel cestino, esegue
    # l'eliminazione DEFINITIVA. Ridefinendoli qui si vinceva sul mixin e dal
    # cestino l'eliminazione non aveva alcun effetto visibile.

    class Media:
        js = ('admin/js/contract_event_filter.js', 'admin/js/contract_contact_filter.js',
              'admin/js/contractline_variant_filter.js',
              # nome con _vN: cache-busting via RINOMINA del file (il query
              # param ?v=N viene URL-encodato da static() e il file va in 404)
              'admin/js/contractline_service_picker_v3.js',
              'admin/js/deadline_quick_actions_v1.js',)

    fieldsets = (
        (None, {
            'fields': ('contract_number_display', 'event', 'sponsor', 'sponsor_signer_contact'),
            'description': "Firmatario: senza un firmatario con i dati "
                           "anagrafici completi (nascita, residenza, documento, "
                           "CF) il cliente NON può confermare il preventivo e "
                           "il contratto non si genera.",
        }),
        ('Tipo e origine', {
            'fields': ('contract_kind', 'parent_contract', 'origin', 'language'),
            'description': (
                'PRINCIPALE: segue il flusso preventivo (invio → conferma del cliente '
                '→ Domanda di ammissione + scadenze acconto/saldo). '
                'ADDON (acquisto online): pagamento immediato, NESSUN preventivo da '
                'confermare, niente Domanda né scadenze acconto/saldo; il cliente paga '
                'dal portale (PayPal, carta o bonifico) e l\'acquisto si conferma al pagamento. '
                'ADDENDUM: usa lo stesso modulo della Domanda ma intitolato '
                '«Addendum al contratto n° … del …». Il numero contratto è automatico.'
            ),
        }),
        ('Spazio espositivo', {
            'fields': ('stand', 'stand_block', 'option_until',
                       ('stand_price_override', 'stand_discount_percent', 'stand_discount_amount')),
            'description': (
                'Scegli stand singolo OPPURE blocco, non entrambi. '
                'IMPORTANTE: nella tendina digita il nome (o slug) dell\'evento '
                'di questo contratto per vedere solo gli stand/blocchi di '
                'quell\'evento. Selezionare uno spazio di un altro evento dara\' errore al salvataggio. '
                '«Spazio opzionato fino al»: finche\' questa data non e\' passata, lo stand/blocco '
                'resta RISERVATO per questo sponsor anche se il preventivo e\' ancora in bozza; '
                'oltre la data lo spazio torna disponibile per altri.'
            ),
        }),
        ('Stato', {
            'fields': ('status', 'issued_date', 'sent_date', 'signed_date',
                       'cancelled_date', 'cancellation_reason'),
        }),
        ('Importi (calcolati automaticamente)', {
            'fields': ('subtotal', 'vat_amount', 'total',
                       'vat_applicable', 'vat_exemption_reason'),
        }),
        ('Pagamento', {
            'fields': ('payment_method', 'payment_terms', 'payment_installments'),
        }),
        ('Piano pagamento (acconto/saldo)', {
            'fields': (
                'deposit_percent',
                ('deposit_due_date_override', 'balance_due_date_override'),
                'piano_acconto_display', 'piano_saldo_display',
                'piano_scad_acconto_display', 'piano_scad_saldo_display',
            ),
            'description': "Inserisci la percentuale di acconto (vuota = pagamento unico). "
                           "Le scadenze si calcolano dai giorni in Impostazioni segreteria; "
                           "compila le date manuali solo per forzare valori diversi. "
                           "Gli importi sotto sono calcolati (IVA inclusa) e si aggiornano al salvataggio.",
        }),
        ('Template e clausole', {
            'fields': ('template_used', 'special_clauses', 'requires_aifa', 'requires_svc_medtech'),
            'classes': ('collapse',),
        }),
        ('Note interne', {
            'fields': ('internal_notes',),
            'classes': ('collapse',),
        }),
        ('Sistema', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    actions = ['action_send_quote',
               'action_generate_client_summary', 'action_genera_scadenze',
               'action_mark_as_sent', 'action_mark_as_signed', 'action_cancel',
               'action_registra_bonifico',
               'action_genera_domanda_ammissione', 'action_genera_proforma',
               'action_rigenera_pdf_contratto',
               'action_convert_to_contract',
               'action_generate_stand_line',
               'action_restore']

    @admin.display(description='Sponsor', ordering='sponsor__legal_name')
    def sponsor_link(self, obj):
        url = reverse('admin:sponsors_sponsor_change', args=[obj.sponsor_id])
        return format_html('<a href="{}">{}</a>', url, obj.sponsor.legal_name)

    @admin.display(description='Evento', ordering='event__slug')
    def event_link(self, obj):
        url = reverse('admin:events_event_change', args=[obj.event_id])
        return format_html('<a href="{}">{}</a>', url, obj.event.slug)

    @admin.display(description='Tipo')
    def kind_badge(self, obj):
        colors = {
            ContractKind.MAIN: '#79aec8',
            ContractKind.ADDON: '#e6a23c',
            ContractKind.ADDENDUM: '#9c5cb6',
        }
        color = colors.get(obj.contract_kind, '#666')
        return format_html(
            '<span style="background:{}; color:white; padding:2px 8px; '
            'border-radius:3px; font-size:0.85em;">{}</span>',
            color, obj.get_contract_kind_display()
        )

    @admin.display(description='Stato')
    def status_badge(self, obj):
        # Preventivo principale in Bozza = creato ma NON inviato: avviso evidente.
        if (obj.status == ContractStatus.DRAFT
                and obj.contract_kind == ContractKind.MAIN):
            return format_html(
                '<span style="background:#ba2121; color:white; padding:2px 8px; '
                'border-radius:3px; font-size:0.85em; font-weight:700;" '
                'title="Preventivo creato ma non ancora inviato">&#9888; Bozza &middot; DA INVIARE</span>'
            )
        colors = {
            ContractStatus.DRAFT: '#999',
            ContractStatus.SENT: '#79aec8',
            ContractStatus.PENDING_PAYMENT: '#e6a23c',
            ContractStatus.SIGNED: '#41ad7c',
            ContractStatus.ACTIVE: '#41ad7c',
            ContractStatus.COMPLETED: '#666',
            ContractStatus.CANCELLED: '#ba2121',
        }
        color = colors.get(obj.status, '#666')
        return format_html(
            '<span style="background:{}; color:white; padding:2px 8px; '
            'border-radius:3px; font-size:0.85em;">{}</span>',
            color, obj.get_status_display()
        )

    @admin.display(description='Spazio')
    def venue_display(self, obj):
        if obj.stand_id:
            return format_html('<small>Stand {}</small>', obj.stand.code)
        if obj.stand_block_id:
            return format_html('<small>Blocco {}</small>', obj.stand_block.code)
        return '—'

    @admin.display(description='Totale', ordering='total')
    def total_display(self, obj):
        return format_html('<strong>€ {}</strong>', f"{obj.total:,.2f}")

    @admin.display(description='Incassato / Residuo', ordering='_incassato')
    def incassato_display(self, obj):
        """A colpo d'occhio: verde = saldato, ambra = parziale, rosso = zero.
        Solo per contratti confermati (per bozze/preventivi non ha senso)."""
        from decimal import Decimal
        if obj.status not in (ContractStatus.SIGNED, ContractStatus.ACTIVE,
                              ContractStatus.COMPLETED):
            from django.utils.safestring import mark_safe
            return mark_safe('<span style="color:#999;">—</span>')
        incassato = getattr(obj, '_incassato', None) or Decimal('0.00')
        residuo = max((obj.total or Decimal('0.00')) - incassato, Decimal('0.00'))
        if residuo <= 0:
            return format_html(
                '<span style="color:#1a7f37; font-weight:600;">✓ saldato</span>')
        colore = '#b45309' if incassato > 0 else '#b91c1c'
        return format_html(
            '<span style="color:{};">€ {} <span style="color:#999;">/ resta</span> '
            '€ {}</span>',
            colore, f"{incassato:,.2f}", f"{residuo:,.2f}")

    @admin.display(description='Origine')
    def origin_badge(self, obj):
        icons = {'manual': '✋', 'ecommerce': '🛒', 'import': '📥'}
        return format_html(
            '<span title="{}">{}</span>',
            obj.get_origin_display(), icons.get(obj.origin, '?')
        )

    @admin.display(description='Data', ordering='created_at')
    def created_at_short(self, obj):
        return obj.created_at.strftime('%d/%m/%Y')

    # ---- PREVENTIVO: URL custom per la pagina di conferma destinatari ----
    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                '<path:object_id>/anteprima-preventivo/',
                self.admin_site.admin_view(self.preview_quote_view),
                name='contracts_contract_preview_quote',
            ),
            path(
                '<path:object_id>/invia-preventivo/',
                self.admin_site.admin_view(self.send_quote_view),
                name='contracts_contract_send_quote',
            ),
            path(
                '<path:object_id>/invia-contratto/',
                self.admin_site.admin_view(self.send_contract_view),
                name='contracts_contract_send_contract',
            ),
            path(
                'servizi-per-evento/<uuid:event_id>/',
                self.admin_site.admin_view(self.servizi_per_evento_view),
                name='contracts_contract_servizi_evento',
            ),
            path(
                '<path:object_id>/servizi-json/',
                self.admin_site.admin_view(self.servizi_json_view),
                name='contracts_contract_servizi_json',
            ),
        ]
        return custom + urls

    def servizi_per_evento_view(self, request, event_id):
        """Catalogo servizi di un EVENTO in JSON: alimenta la finestra
        'Catalogo' anche in fase di stesura (contratto non ancora salvato,
        evento scelto nella tendina del form)."""
        from django.http import JsonResponse
        from events.models import Event
        event = Event.objects.filter(pk=event_id).first()
        if event is None:
            return JsonResponse({'services': []})
        return JsonResponse({'services': self._servizi_payload(event)})

    @staticmethod
    def _servizi_payload(event):
        out = []
        for s in event.services.all().order_by('category', 'code'):
            try:
                categoria = s.get_category_display()
            except Exception:
                categoria = s.category or ''
            out.append({
                'id': str(s.pk),
                'code': s.code or '',
                'name': s.translated('name', 'it') or '',
                'price': float(s.base_price or 0),
                'category': categoria,
                'active': bool(s.is_active),
            })
        return out

    def servizi_json_view(self, request, object_id):
        """Catalogo servizi dell'evento del contratto, in JSON (variante per
        contratto gia' salvato; la finestra usa di norma servizi-per-evento)."""
        from django.http import JsonResponse
        from .models import Contract
        contract = Contract.objects.filter(pk=object_id).first()
        if contract is None or not contract.event_id:
            return JsonResponse({'services': []})
        return JsonResponse({'services': self._servizi_payload(contract.event)})

    def _contact_rows(self, contract):
        """Costruisce le righe contatto per la pagina di conferma."""
        from sponsors.models import ContactRole
        role_map = dict(ContactRole.choices)
        rows = []
        contacts = contract.sponsor.contacts.filter(deleted_at__isnull=True)
        signer = contract.sponsor_signer_contact
        for c in contacts:
            if not c.email:
                continue
            labels = ", ".join(role_map.get(r, r) for r in (c.roles or []))
            preselected = bool(
                (signer and c.id == signer.id) or c.is_signer
            )
            rows.append({
                'full_name': c.full_name,
                'email': c.email,
                'role_labels': labels,
                'is_signer': c.is_signer,
                'preselected': preselected,
            })
        return rows

    def preview_quote_view(self, request, object_id):
        """Genera il PDF del preventivo SENZA inviarlo e lo apre subito.

        Non invia email e non cambia lo stato del contratto: serve a vedere
        l'anteprima di cosa si sta per mandare. Il PDF resta allegato come
        Documento (rigenerato a ogni anteprima)."""
        from .models import Contract
        from .services.pdf_generator import generate_quote_pdf_html

        contract = get_object_or_404(Contract, pk=object_id)
        try:
            document = generate_quote_pdf_html(contract)
        except Exception as e:
            self.message_user(
                request, f"Errore nella generazione dell'anteprima: {e}",
                level=messages.ERROR)
            return HttpResponseRedirect('../')
        self.message_user(
            request,
            "Anteprima del preventivo generata (non inviata). "
            "Controlla il PDF: se va bene, usa «Genera e invia preventivo».",
            level=messages.SUCCESS)
        return HttpResponseRedirect(reverse('core:documento_apri', args=[document.id]))

    def send_quote_view(self, request, object_id):
        """Pagina di conferma: scelta destinatari, poi genera PDF e invia."""
        from .models import Contract
        from .services.pdf_generator import generate_quote_pdf_html as generate_quote_pdf
        from .services.email_sender import send_email
        from django.core.files.storage import default_storage

        contract = get_object_or_404(Contract, pk=object_id)
        contacts = self._contact_rows(contract)

        if request.method == 'POST':

            # raccogli destinatari: checkbox + email extra
            recipients = list(request.POST.getlist('recipients'))
            extra = (request.POST.get('extra_emails') or '').replace(',', ' ')
            recipients += [e.strip() for e in extra.split() if e.strip()]
            # dedup mantenendo l'ordine
            seen = set()
            recipients = [r for r in recipients if not (r in seen or seen.add(r))]

            if not recipients:
                self.message_user(
                    request,
                    "Seleziona almeno un destinatario.",
                    level=messages.ERROR,
                )
                return HttpResponseRedirect(request.path)

            # 1) genera il PDF del preventivo
            try:
                document = generate_quote_pdf(contract)
            except Exception as e:
                self.message_user(
                    request, f"Errore nella generazione del PDF: {e}",
                    level=messages.ERROR,
                )
                return HttpResponseRedirect('../')

            # 2) leggi i bytes del PDF dal storage
            try:
                rel = document.storage_url.replace(settings.MEDIA_URL, '', 1)
                pdf_bytes = default_storage.open(rel).read()
            except Exception as e:
                self.message_user(
                    request, f"PDF generato ma non leggibile per l'allegato: {e}",
                    level=messages.ERROR,
                )
                return HttpResponseRedirect('../')

            # 3) invia email con allegato (in dev -> console)
            event = contract.event
            event_name = event.get_name(contract.language) if hasattr(event, 'get_name') else str(event)
            try:
                send_email(
                    template_name='quote_email',
                    context={'contract': contract, 'event': event,
                             'event_name': event_name},
                    to=recipients,
                    subject=(f"Quote {contract.contract_number} - {event_name}"
                             if (contract.language or 'it') == 'en'
                             else f"Preventivo {contract.contract_number} - {event_name}"),
                    language=contract.language or 'it',
                    attachments=[(document.file_name, pdf_bytes, 'application/pdf')],
                    related_to=contract,
                    communication_type='quote',
                    triggered_by_user=getattr(request, 'user', None),
                )
            except Exception as e:
                self.message_user(
                    request, f"PDF generato ma invio email fallito: {e}",
                    level=messages.ERROR,
                )
                return HttpResponseRedirect('../')

            # Porta il preventivo a "Inviato": cosi' compare nel portale del cliente
            # e lo stand viene riservato. Solo se era in Bozza.
            from .models import ContractStatus as _CS
            stato_ok = False
            if contract.status == _CS.DRAFT:
                try:
                    contract.mark_as_sent()
                    stato_ok = True
                except Exception as e:
                    self.message_user(
                        request,
                        f"Preventivo inviato, ma stato non aggiornato a 'Inviato': {e}",
                        level=messages.WARNING,
                    )

            self.message_user(
                request,
                f"Preventivo inviato a: {', '.join(recipients)} (PDF allegato)."
                + (" Contratto impostato su 'Inviato'." if stato_ok else ""),
                level=messages.SUCCESS,
            )
            # Promemoria operatore: senza firmatario il cliente non potra'
            # confermare (gate lato portale) e il contratto non si genera.
            self._avvisa_se_manca_firmatario(request, contract)
            return HttpResponseRedirect('../')

        # GET: mostra la pagina di conferma
        context = {
            **self.admin_site.each_context(request),
            'title': 'Genera e invia preventivo',
            'contract': contract,
            'contacts': contacts,
            'manca_firmatario': self._manca_firmatario(contract),
            'opts': self.model._meta,
        }
        return render(request, 'admin/quote_send_confirm.html', context)

    # ---- Firmatario: helper avvisi operatore ----

    def _manca_firmatario(self, contract):
        """True se il contratto non ha un firmatario utilizzabile."""
        from contracts.services.pdf_generator import _get_signer_contact
        try:
            return _get_signer_contact(contract) is None
        except Exception:
            return False

    def _avvisa_se_manca_firmatario(self, request, contract):
        """Avviso (non bloccante) all'operatore: senza legale rappresentante
        firmatario il cliente viene fermato alla conferma del preventivo."""
        if self._manca_firmatario(contract):
            self.message_user(
                request,
                f"⚠️ {contract.sponsor.legal_name}: manca il legale rappresentante "
                f"FIRMATARIO. Il cliente non potrà confermare il preventivo "
                f"{contract.contract_number} finché non lo registrate "
                "(Anagrafica di riferimento → spunta «È il legale rappresentante "
                "firmatario?» con i suoi dati).",
                level=messages.WARNING,
            )

    def send_contract_view(self, request, object_id):
        """Trasforma in contratto (mark_as_sent) e invia il PDF ai destinatari scelti."""
        from .models import Contract, ContractStatus
        from .services.email_sender import send_email
        from shared.models import Document
        from django.contrib.contenttypes.models import ContentType
        from django.core.files.storage import default_storage

        contract = get_object_or_404(Contract, pk=object_id)
        contacts = self._contact_rows(contract)

        if request.method == 'POST':
            if contract.status != ContractStatus.DRAFT:
                self.message_user(
                    request,
                    f"Il contratto non e' in Bozza (e' '{contract.get_status_display()}').",
                    level=messages.ERROR,
                )
                return HttpResponseRedirect('../')

            recipients = list(request.POST.getlist('recipients'))
            extra = (request.POST.get('extra_emails') or '').replace(',', ' ')
            recipients += [e.strip() for e in extra.split() if e.strip()]
            seen = set()
            recipients = [r for r in recipients if not (r in seen or seen.add(r))]

            if not recipients:
                self.message_user(
                    request, "Seleziona almeno un destinatario.",
                    level=messages.ERROR,
                )
                return HttpResponseRedirect(request.path)

            # 1) transizione: genera PDF contratto + prenota stand + stato SENT
            try:
                contract.mark_as_sent()
            except Exception as e:
                self.message_user(
                    request, f"Errore nella trasformazione in contratto: {e}",
                    level=messages.ERROR,
                )
                return HttpResponseRedirect('../')

            # 2) recupera il PDF contratto appena generato (Document 'contract_pdf'
            #    piu' recente legato a questo contract)
            ct = ContentType.objects.get_for_model(Contract)
            document = (
                Document.objects.filter(
                    content_type=ct, object_id=contract.id,
                    document_type='contract_pdf',
                )
                .order_by('-created_at')
                .first()
            )
            if not document:
                self.message_user(
                    request,
                    "Contratto trasformato (stato INVIATO), ma il PDF non e' stato "
                    "trovato per l'invio email. Verifica i documenti del contratto.",
                    level=messages.WARNING,
                )
                return HttpResponseRedirect('../')

            # 3) leggi i bytes del PDF
            try:
                rel = document.storage_url.replace(settings.MEDIA_URL, '', 1)
                pdf_bytes = default_storage.open(rel).read()
            except Exception as e:
                self.message_user(
                    request,
                    f"Contratto trasformato, ma PDF non leggibile per l'allegato: {e}",
                    level=messages.WARNING,
                )
                return HttpResponseRedirect('../')

            # 4) invia email col PDF contratto allegato
            event = contract.event
            event_name = event.get_name(contract.language) if hasattr(event, 'get_name') else str(event)
            try:
                send_email(
                    template_name='contract_email',
                    context={'contract': contract, 'event': event,
                             'event_name': event_name},
                    to=recipients,
                    subject=f"Contratto {contract.contract_number} - {event_name}",
                    language=contract.language or 'it',
                    attachments=[(document.file_name, pdf_bytes, 'application/pdf')],
                    related_to=contract,
                    communication_type='contract',
                    triggered_by_user=getattr(request, 'user', None),
                )
            except Exception as e:
                self.message_user(
                    request,
                    f"Contratto trasformato e PDF generato, ma invio email fallito: {e}",
                    level=messages.WARNING,
                )
                return HttpResponseRedirect('../')

            self.message_user(
                request,
                f"Contratto {contract.contract_number} creato e inviato a: "
                f"{', '.join(recipients)} (PDF allegato).",
                level=messages.SUCCESS,
            )
            return HttpResponseRedirect('../')

        # GET: pagina di conferma
        context = {
            **self.admin_site.each_context(request),
            'title': 'Trasforma in contratto e invia',
            'contract': contract,
            'contacts': contacts,
            'opts': self.model._meta,
        }
        return render(request, 'admin/contract_send_confirm.html', context)

    # ---- AZIONI (bottoni nella lista contratti) ----

    @admin.action(description='Genera e invia PREVENTIVO (scegli destinatari)')
    def action_send_quote(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(
                request,
                "Seleziona esattamente UN contratto per inviare il preventivo.",
                level=messages.WARNING,
            )
            return
        contract = queryset.first()
        return HttpResponseRedirect(
            reverse('admin:contracts_contract_send_quote', args=[contract.pk])
        )

    @admin.action(description='Trasforma PREVENTIVO in contratto (scegli destinatari)')
    def action_convert_to_contract(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(
                request,
                "Seleziona esattamente UN contratto da trasformare.",
                level=messages.WARNING,
            )
            return
        contract = queryset.first()
        return HttpResponseRedirect(
            reverse('admin:contracts_contract_send_contract', args=[contract.pk])
        )

    @admin.action(description='Genera riga dallo STAND (prezzo nel totale)')
    def action_generate_stand_line(self, request, queryset):
        from .services.stand_line import genera_riga_da_stand
        creati = gia = senza = errori = 0
        for contract in queryset:
            esito, msg = genera_riga_da_stand(contract)
            if esito == 'creata':
                creati += 1
            elif esito == 'gia_presente':
                gia += 1
                self.message_user(request, f"{contract.contract_number}: {msg}",
                                  level=messages.INFO)
            elif esito == 'no_stand':
                senza += 1
                self.message_user(request, f"{contract.contract_number}: {msg}",
                                  level=messages.WARNING)
            else:  # no_prezzo
                errori += 1
                self.message_user(request, f"{contract.contract_number}: {msg}",
                                  level=messages.ERROR)
        if creati:
            self.message_user(
                request,
                f"{creati} riga/e stand create. Totali contratto aggiornati.",
                level=messages.SUCCESS,
            )

    # ---- Piano pagamento: importi/scadenze calcolati (sola lettura) ----
    @admin.display(description='Acconto (calcolato, IVA incl.)')
    def piano_acconto_display(self, obj):
        if not obj or not obj.pk:
            return '—'
        if not obj.has_deposit:
            return 'nessun acconto (pagamento unico)'
        from .services.pdf_generator import format_percent_filter
        return f"€ {obj.deposit_amount} ({format_percent_filter(obj.deposit_percent)}%)"

    @admin.display(description='Saldo (calcolato, IVA incl.)')
    def piano_saldo_display(self, obj):
        if not obj or not obj.pk:
            return '—'
        return f"€ {obj.balance_amount}"

    @admin.display(description='Scadenza acconto (calcolata)')
    def piano_scad_acconto_display(self, obj):
        if not obj or not obj.pk:
            return '—'
        d = obj.deposit_due_date
        return d.strftime('%d/%m/%Y') if d else '— (contratto non firmato)'

    @admin.display(description='Scadenza saldo (calcolata)')
    def piano_scad_saldo_display(self, obj):
        if not obj or not obj.pk:
            return '—'
        d = obj.balance_due_date
        return d.strftime('%d/%m/%Y') if d else '— (manca data evento)'

    @admin.action(description='Genera SCHEDA CLIENTE (sponsor+evento)')
    def action_generate_client_summary(self, request, queryset):
        from .services.pdf_generator import generate_client_summary_pdf
        if queryset.count() != 1:
            self.message_user(
                request,
                "Seleziona UN solo contratto: la scheda aggrega tutti i contratti "
                "di quello sponsor per quell'evento.",
                level=messages.WARNING,
            )
            return
        contract = queryset.first()
        try:
            document = generate_client_summary_pdf(contract.sponsor, contract.event)
        except ValueError as e:
            self.message_user(request, str(e), level=messages.ERROR)
            return
        except Exception as e:
            self.message_user(request, f"Errore nella generazione della scheda: {e}",
                              level=messages.ERROR)
            return
        self.message_user(
            request,
            format_html(
                'Scheda cliente generata: <a href="{}" target="_blank">apri il PDF</a>',
                document.storage_url,
            ),
            level=messages.SUCCESS,
        )

    # Actions

    @admin.action(description='Genera DOMANDA DI AMMISSIONE / ADDENDUM (allega e mostra nel portale)')
    def action_genera_domanda_ammissione(self, request, queryset):
        from .services.pdf_generator import generate_admission_request_pdf
        ok = 0
        for contract in queryset:
            try:
                doc = generate_admission_request_pdf(contract)
            except Exception as e:
                self.message_user(
                    request,
                    f"{contract.contract_number}: documento non generato - {e}",
                    level=messages.ERROR,
                )
                continue
            if doc:
                ok += 1
        if ok:
            self.message_user(
                request,
                f"Documento generato per {ok} contratto/i (domanda di ammissione per i "
                f"principali, addendum per gli addendum). Ora e' visibile anche nel portale.",
                level=messages.SUCCESS,
            )

    @admin.action(description='Genera FATTURA PROFORMA (acconto+saldo se previsti)')
    def action_genera_proforma(self, request, queryset):
        from .services.pdf_generator import generate_proforma_pdf
        from .tasks.notifications import send_proforma_generated_notification
        tot_docs = 0
        avvisati = 0
        for contract in queryset:
            try:
                docs = generate_proforma_pdf(contract)
            except Exception as e:
                self.message_user(
                    request,
                    f"{contract.contract_number}: proforma non generata - {e}",
                    level=messages.ERROR,
                )
                continue
            tot_docs += len(docs)
            if docs:
                try:
                    send_proforma_generated_notification.delay(
                        contract.id, [d.id for d in docs])
                    avvisati += 1
                except Exception:
                    logger.exception(
                        "Errore invio notifica proforma per %s", contract.contract_number)
        if tot_docs:
            self.message_user(
                request,
                f"Generate {tot_docs} fattura/e proforma. Le trovi tra i Documenti del contratto "
                "(numerate .../1 acconto e .../2 saldo se il contratto prevede l'acconto). "
                f"Email di avviso inviata al cliente per {avvisati} contratto/i.",
                level=messages.SUCCESS,
            )

    @admin.action(description='Rigenera PDF CONTRATTO (allega e mostra nel portale)')
    def action_rigenera_pdf_contratto(self, request, queryset):
        from .services.pdf_generator import generate_contract_pdf
        ok = 0
        for contract in queryset:
            try:
                doc = generate_contract_pdf(contract)
            except Exception as e:
                self.message_user(
                    request,
                    f"{contract.contract_number}: PDF non generato - {e}",
                    level=messages.ERROR,
                )
                continue
            if doc is None:
                self.message_user(
                    request,
                    f"{contract.contract_number}: e' un contratto ADDON (ecommerce), nessun PDF previsto.",
                    level=messages.WARNING,
                )
            else:
                ok += 1
        if ok:
            self.message_user(
                request,
                f"PDF contratto generato per {ok} contratto/i. Ora e' visibile anche nel portale.",
                level=messages.SUCCESS,
            )

    @admin.action(description='Registra pagamento bonifico ricevuto')
    def action_registra_bonifico(self, request, queryset):
        from contracts.payments import Payment, PaymentMethodChoice, PaymentStatus
        from contracts.models import ContractStatus
        ok = skip = 0
        for contract in queryset:
            if contract.status in (ContractStatus.SIGNED, ContractStatus.ACTIVE, ContractStatus.COMPLETED):
                skip += 1
                continue
            if contract.status == ContractStatus.DRAFT:
                contract.mark_as_pending_payment()
            if contract.status == ContractStatus.PENDING_PAYMENT:
                payment = contract.payments.filter(status=PaymentStatus.SUCCEEDED).first()
                if payment is None:
                    payment, _ = Payment.objects.get_or_create(
                        contract=contract,
                        status=PaymentStatus.PENDING,
                        payment_method=PaymentMethodChoice.BANK_TRANSFER,
                        defaults={'amount_gross': contract.total, 'currency': 'EUR'},
                    )
                    payment.mark_succeeded()
                ok += 1
            else:
                skip += 1
        self.message_user(
            request,
            f"Bonifici registrati: {ok}. Ignorati (gia' pagati o stato non valido): {skip}.",
            level=messages.SUCCESS,
        )

    @admin.action(description='Marca come INVIATO')
    def action_mark_as_sent(self, request, queryset):
        ok = err = 0
        for contract in queryset:
            try:
                contract.mark_as_sent()
                ok += 1
                self._avvisa_se_manca_firmatario(request, contract)
            except Exception as e:
                err += 1
                self.message_user(
                    request,
                    f"Errore su {contract.contract_number}: {e}",
                    level=messages.ERROR,
                )
        if ok:
            self.message_user(
                request,
                f"{ok} contratti marcati come inviati.",
                level=messages.SUCCESS,
            )

    @admin.action(description="Genera scadenze dai template (per domande gia' firmate/attive)")
    def action_genera_scadenze(self, request, queryset):
        tot = 0
        for contract in queryset:
            before = contract.deadlines.count()
            try:
                contract._generate_deadlines()
            except Exception as e:
                self.message_user(
                    request,
                    f"Errore su {contract.contract_number}: {e}",
                    level=messages.ERROR,
                )
                continue
            tot += contract.deadlines.count() - before
        self.message_user(
            request,
            f"Scadenze generate: {tot}. (Nota: il servizio deve avere 'Genera "
            f"scadenze' attivo e almeno un Template scadenze attivo.)",
            level=messages.SUCCESS if tot else messages.WARNING,
        )

    @admin.action(description='Marca come FIRMATO')
    def action_mark_as_signed(self, request, queryset):
        from datetime import date as _date

        # Pagina intermedia: chiede la data firma prima di procedere.
        if '_firma_confermata' not in request.POST:
            return render(request, 'admin/contracts/contract/action_firma_data.html', {
                **self.admin_site.each_context(request),
                'title': 'Conferma firma contratti',
                'queryset': queryset,
                'action': 'action_mark_as_signed',
                'oggi': _date.today().isoformat(),
                'opts': self.model._meta,
                'action_checkbox_name': helpers.ACTION_CHECKBOX_NAME,
            })

        # Parsing data firma dal POST; fallback a oggi.
        raw = request.POST.get('signed_date', '').strip()
        try:
            signed_date = _date.fromisoformat(raw) if raw else _date.today()
        except ValueError:
            signed_date = _date.today()

        ok = err = 0
        for contract in queryset:
            try:
                contract.mark_as_signed(signed_date=signed_date)
                ok += 1
            except Exception as e:
                err += 1
                self.message_user(
                    request,
                    f"Errore su {contract.contract_number}: {e}",
                    level=messages.ERROR,
                )
        if ok:
            self.message_user(
                request,
                f"{ok} contratti marcati come firmati (data firma: "
                f"{signed_date.strftime('%d/%m/%Y')}). Scadenze generate, stand assegnati.",
                level=messages.SUCCESS,
            )

    @admin.action(description='Annulla domande selezionate')
    def action_cancel(self, request, queryset):
        # Pagina intermedia di conferma: l'annullamento libera stand e
        # esonera scadenze - un click sbagliato costa caro.
        if '_annulla_confermato' not in request.POST:
            return render(request, 'admin/contracts/contract/action_annulla_conferma.html', {
                **self.admin_site.each_context(request),
                'title': 'Conferma annullamento contratti',
                'queryset': queryset,
                'action': 'action_cancel',
                'opts': self.model._meta,
                'action_checkbox_name': helpers.ACTION_CHECKBOX_NAME,
            })

        reason = (request.POST.get('reason') or '').strip() or 'Annullato da admin'
        ok = 0
        for contract in queryset:
            if contract.status != ContractStatus.CANCELLED:
                contract.cancel(reason=reason)
                ok += 1
        if ok:
            self.message_user(
                request,
                f"{ok} contratti annullati.",
                level=messages.WARNING,
            )


# =============================================================================
# CONTRACT LINE (admin separato per ricerche)
# =============================================================================

@admin.register(ContractLine)
class ContractLineAdmin(admin.ModelAdmin):
    def get_queryset(self, request):
        from core.event_scope import scope_by_event, escludi_figli_di_contratti_cestinati
        qs = scope_by_event(request, super().get_queryset(request), 'contract__event')
        return escludi_figli_di_contratti_cestinati(request, qs)

    list_display = (
        'contract_link', 'service_name_snapshot', 'quantity',
        'unit_price', 'discount_display', 'line_total',
    )
    list_filter = (evento_filter('contract__event'), 'service__category')
    search_fields = (
        'contract__contract_number', 'service_name_snapshot',
        'contract__sponsor__legal_name',
    )
    list_select_related = ('contract', 'contract__sponsor', 'service')
    autocomplete_fields = ['contract', 'service']
    readonly_fields = ('line_subtotal', 'line_vat', 'line_total',
                       'created_at', 'updated_at')

    @admin.display(description='Contratto', ordering='contract__contract_number')
    def contract_link(self, obj):
        url = reverse('admin:contracts_contract_change', args=[obj.contract_id])
        return format_html('<a href="{}">{}</a>', url, obj.contract.contract_number)

    @admin.display(description='Sconto')
    def discount_display(self, obj):
        if obj.discount_percent:
            return f"{obj.discount_percent}%"
        if obj.discount_amount:
            return f"€ {obj.discount_amount:,.2f}"
        return '—'


# =============================================================================
# DEADLINE
# =============================================================================

@admin.register(Deadline)
class DeadlineAdmin(admin.ModelAdmin):
    def get_queryset(self, request):
        # Niente scadenze di contratti nel cestino: erano gia' esonerate ma
        # restavano in elenco col conto alla rovescia dei giorni.
        from core.event_scope import scope_by_event, escludi_figli_di_contratti_cestinati
        qs = scope_by_event(request, super().get_queryset(request), 'contract__event')
        return escludi_figli_di_contratti_cestinati(request, qs)

    list_display = (
        'title', 'contract_link', 'cliente', 'due_date', 'status_badge',
        'completata_da', 'days_until_due_display', 'reminder_count', 'file_esempio',
        'azioni_rapide',
    )
    list_filter = (evento_filter('contract__event'), 'status', 'deadline_type')
    search_fields = (
        'title', 'contract__contract_number',
        'contract__sponsor__legal_name',
    )
    list_select_related = ('contract', 'contract__sponsor', 'contract__event', 'deadline_template')

    @admin.display(description='File di esempio')
    def file_esempio(self, obj):
        return _deadline_file_esempio(obj)
    autocomplete_fields = ['contract', 'contract_line', 'completed_by_contact']
    date_hierarchy = 'due_date'
    readonly_fields = ('created_at', 'updated_at', 'last_reminder_sent_at',
                       'reminder_count', 'content_schema', 'submitted_content',
                       'file_esempio')
    ordering = ('due_date',)

    actions = ['action_mark_as_received', 'action_sposta_scadenze',
               'action_aggiorna_campi_da_template']

    class Media:
        js = ('admin/js/deadline_quick_actions_v1.js',)

    # ---- Azioni rapide a UN click sulla riga (senza menu "Azione") ----

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                '<path:object_id>/segna-ricevuta/',
                self.admin_site.admin_view(self.segna_ricevuta_view),
                name='contracts_deadline_segna_ricevuta',
            ),
            path(
                '<path:object_id>/esonera/',
                self.admin_site.admin_view(self.esonera_view),
                name='contracts_deadline_esonera',
            ),
        ]
        return custom + urls

    def _azione_rapida(self, request, object_id, esito):
        from django.http import Http404, HttpResponseNotAllowed, JsonResponse
        from .models import DeadlineStatus as _DS
        if request.method != 'POST':
            return HttpResponseNotAllowed(['POST'])
        deadline = self.get_object(request, object_id)
        if deadline is None or not self.has_change_permission(request, deadline):
            raise Http404
        if esito == 'ricevuta':
            deadline.mark_as_received()
            self.message_user(
                request, f"'{deadline.title}' segnata come RICEVUTA.",
                level=messages.SUCCESS)
        else:
            deadline.status = _DS.WAIVED
            deadline.save(update_fields=['status', 'updated_at'])
            self.message_user(
                request,
                f"'{deadline.title}' ESONERATA: il cliente non riceverà più promemoria.",
                level=messages.SUCCESS)
        return JsonResponse({'ok': True})

    def segna_ricevuta_view(self, request, object_id):
        return self._azione_rapida(request, object_id, 'ricevuta')

    def esonera_view(self, request, object_id):
        return self._azione_rapida(request, object_id, 'esonera')

    @admin.display(description='Azioni rapide')
    def azioni_rapide(self, obj):
        return _deadline_azioni_rapide_html(obj)

    @admin.action(description='Aggiorna i campi da compilare dal template')
    def action_aggiorna_campi_da_template(self, request, queryset):
        """Ri-fotografa sulle scadenze selezionate i 'campi da compilare'
        (etichette) definiti sul loro Template scadenza. Serve quando le
        etichette vengono definite/corrette DOPO che la scadenza e' gia'
        stata generata dalla firma del contratto."""
        aggiornate, senza_template = 0, 0
        for d in queryset:
            tpl = d.deadline_template
            if tpl is None:
                senza_template += 1
                continue
            d.submission_kind = getattr(tpl, 'submission_kind', d.submission_kind)
            d.content_schema = [
                {
                    'key': f.key,
                    'label': f.label,
                    'type': f.field_type,
                    'required': f.required,
                    'help_text': f.help_text,
                }
                for f in tpl.content_fields.all().order_by('display_order')
            ]
            d.save(update_fields=['submission_kind', 'content_schema', 'updated_at'])
            aggiornate += 1
        if aggiornate:
            self.message_user(
                request,
                f"{aggiornate} scadenza/e aggiornate coi campi del template: "
                "il cliente ora vede le etichette nel portale.",
                level=messages.SUCCESS)
        if senza_template:
            self.message_user(
                request,
                f"{senza_template} scadenza/e SENZA template collegato: non aggiornate "
                "(i campi si definiscono sul Template scadenza del servizio).",
                level=messages.WARNING)

    @admin.action(description='Sposta le scadenze selezionate (proroga)')
    def action_sposta_scadenze(self, request, queryset):
        """Sposta la data di piu' scadenze in un colpo: di N giorni oppure a
        una data fissa. Utile per proroghe concesse o cambio data evento
        (prima si modificavano una a una nel form)."""
        from datetime import date as _date, timedelta as _td

        if '_sposta_confermato' not in request.POST:
            return render(request, 'admin/contracts/deadline/action_sposta_scadenze.html', {
                **self.admin_site.each_context(request),
                'title': 'Sposta scadenze',
                'queryset': queryset,
                'action': 'action_sposta_scadenze',
                'opts': self.model._meta,
                'action_checkbox_name': helpers.ACTION_CHECKBOX_NAME,
            })

        giorni_raw = (request.POST.get('giorni') or '').strip()
        data_raw = (request.POST.get('data_fissa') or '').strip()

        nuova_data_fissa = None
        delta = None
        if data_raw:
            try:
                nuova_data_fissa = _date.fromisoformat(data_raw)
            except ValueError:
                self.message_user(request, "Data non valida.", level=messages.ERROR)
                return
        elif giorni_raw:
            try:
                delta = _td(days=int(giorni_raw))
            except ValueError:
                self.message_user(request, "Numero di giorni non valido.",
                                  level=messages.ERROR)
                return
        else:
            self.message_user(
                request, "Indica i giorni di spostamento oppure una data fissa.",
                level=messages.WARNING)
            return

        ok = 0
        for dl in queryset:
            dl.due_date = nuova_data_fissa if nuova_data_fissa else (dl.due_date + delta)
            dl.save(update_fields=['due_date', 'updated_at'])
            ok += 1
        self.message_user(
            request,
            f"{ok} scadenza/e spostate"
            + (f" al {nuova_data_fissa.strftime('%d/%m/%Y')}." if nuova_data_fissa
               else f" di {giorni_raw} giorni."),
            level=messages.SUCCESS)

    @admin.display(description='Cliente', ordering='contract__sponsor__legal_name')
    def cliente(self, obj):
        sp = obj.contract.sponsor if obj.contract_id else None
        return sp.legal_name if sp else '—'

    @admin.display(description='Completata da')
    def completata_da(self, obj):
        c = obj.completed_by_contact
        return c.full_name if c else '—'

    @admin.display(description='Dati inviati dal cliente')
    def submitted_content(self, obj):
        data = obj.content_data or {}
        if not data:
            return format_html('<em>nessun dato inviato</em>')
        from django.utils.html import format_html_join
        labels = {f.get('key'): f.get('label', f.get('key'))
                  for f in (obj.content_schema or [])}
        return format_html_join(
            '', '<div style="margin-bottom:4px;"><strong>{}:</strong> {}</div>',
            ((labels.get(k, k), v) for k, v in data.items())
        )

    @admin.display(description='Contratto', ordering='contract__contract_number')
    def contract_link(self, obj):
        url = reverse('admin:contracts_contract_change', args=[obj.contract_id])
        return format_html('<a href="{}">{}</a>', url, obj.contract.contract_number)

    @admin.display(description='Stato')
    def status_badge(self, obj):
        colors = {
            DeadlineStatus.PENDING: '#999',
            DeadlineStatus.REMINDER_SENT: '#e6a23c',
            DeadlineStatus.RECEIVED: '#41ad7c',
            DeadlineStatus.OVERDUE: '#ba2121',
            DeadlineStatus.WAIVED: '#666',
        }
        color = colors.get(obj.status, '#666')
        return format_html(
            '<span style="background:{}; color:white; padding:2px 8px; '
            'border-radius:3px; font-size:0.85em;">{}</span>',
            color, obj.get_status_display()
        )

    @admin.display(description='Giorni mancanti')
    def days_until_due_display(self, obj):
        days = obj.days_until_due
        if obj.status == DeadlineStatus.RECEIVED:
            return format_html('<small style="color:#41ad7c;">✓ ricevuto</small>')
        if days < 0:
            return format_html(
                '<strong style="color:#ba2121;">in ritardo di {} gg</strong>',
                abs(days)
            )
        if days <= 7:
            return format_html(
                '<strong style="color:#e6a23c;">tra {} gg</strong>',
                days
            )
        return f"tra {days} gg"

    @admin.action(description='Marca come RICEVUTO')
    def action_mark_as_received(self, request, queryset):
        for deadline in queryset:
            deadline.mark_as_received()
        self.message_user(
            request,
            f"{queryset.count()} scadenze marcate come ricevute.",
            level=messages.SUCCESS,
        )


# =============================================================================
# PAYMENT
# =============================================================================

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    def get_queryset(self, request):
        from core.event_scope import scope_by_event, escludi_figli_di_contratti_cestinati
        qs = scope_by_event(request, super().get_queryset(request), 'contract__event')
        return escludi_figli_di_contratti_cestinati(request, qs)

    list_display = (
        'contract_link', 'sponsor_display', 'method_badge', 'amount_gross',
        'amount_fee', 'amount_net_display', 'status_badge',
        'reference_display', 'completed_at_short',
    )
    list_filter = (evento_filter('contract__event'), 'payment_method', 'status', 'currency')
    search_fields = (
        'contract__contract_number', 'paypal_order_id',
        'bank_transfer_reference', 'paypal_payer_email',
        'contract__sponsor__legal_name',
    )
    list_select_related = ('contract', 'contract__sponsor')
    autocomplete_fields = ['contract', 'bank_transfer_confirmed_by_user']
    readonly_fields = (
        'created_at', 'updated_at', 'initiated_at', 'completed_at',
        'failed_at', 'last_webhook_event_id',
        'paypal_order_id', 'paypal_capture_id', 'paypal_payer_email',
        'paypal_payer_id', 'paypal_response',
    )
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'

    fieldsets = (
        (None, {
            'fields': ('contract', 'payment_method', 'status'),
        }),
        ('Importi', {
            'fields': ('amount_gross', 'amount_fee', 'currency'),
        }),
        ('Riferimenti PayPal', {
            'fields': ('paypal_order_id', 'paypal_capture_id',
                       'paypal_payer_email', 'paypal_payer_id',
                       'paypal_response', 'last_webhook_event_id'),
            'classes': ('collapse',),
        }),
        ('Riferimenti bonifico', {
            'fields': ('bank_transfer_reference', 'bank_transfer_received_at',
                       'bank_transfer_confirmed_by_user'),
            'classes': ('collapse',),
        }),
        ('Date', {
            'fields': ('initiated_at', 'completed_at', 'failed_at',
                       'failure_reason'),
        }),
        ('Note', {
            'fields': ('notes',),
            'classes': ('collapse',),
        }),
        ('Sistema', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    actions = ['action_confirm_bank_transfer']

    @admin.display(description='Contratto', ordering='contract__contract_number')
    def contract_link(self, obj):
        url = reverse('admin:contracts_contract_change', args=[obj.contract_id])
        return format_html('<a href="{}">{}</a>', url, obj.contract.contract_number)

    @admin.display(description='Cliente', ordering='contract__sponsor__legal_name')
    def sponsor_display(self, obj):
        sponsor = getattr(obj.contract, 'sponsor', None)
        return sponsor.legal_name if sponsor else '—'

    @admin.display(description='Metodo')
    def method_badge(self, obj):
        icons = {'paypal': '🅿️', 'bank_transfer': '🏦', 'manual': '✋'}
        return format_html(
            '{} {}',
            icons.get(obj.payment_method, ''),
            obj.get_payment_method_display()
        )

    @admin.display(description='Netto')
    def amount_net_display(self, obj):
        return format_html('<strong>€ {}</strong>', f"{obj.amount_net:,.2f}")

    @admin.display(description='Stato')
    def status_badge(self, obj):
        colors = {
            PaymentStatus.PENDING: '#999',
            PaymentStatus.PROCESSING: '#79aec8',
            PaymentStatus.SUCCEEDED: '#41ad7c',
            PaymentStatus.FAILED: '#ba2121',
            PaymentStatus.REFUNDED: '#666',
            PaymentStatus.PARTIAL_REFUND: '#e6a23c',
        }
        color = colors.get(obj.status, '#666')
        return format_html(
            '<span style="background:{}; color:white; padding:2px 8px; '
            'border-radius:3px; font-size:0.85em;">{}</span>',
            color, obj.get_status_display()
        )

    @admin.display(description='Riferimento')
    def reference_display(self, obj):
        if obj.paypal_order_id:
            return format_html(
                '<small style="font-family:monospace;">{}</small>',
                obj.paypal_order_id[:20]
            )
        if obj.bank_transfer_reference:
            return format_html(
                '<small style="font-family:monospace;">{}</small>',
                obj.bank_transfer_reference
            )
        return '—'

    @admin.display(description='Completato', ordering='completed_at')
    def completed_at_short(self, obj):
        if obj.completed_at:
            return obj.completed_at.strftime('%d/%m/%Y %H:%M')
        return '—'

    @admin.action(description='Conferma bonifico ricevuto')
    def action_confirm_bank_transfer(self, request, queryset):
        # Solo per pagamenti bonifico in pending
        eligible = queryset.filter(
            payment_method=PaymentMethodChoice.BANK_TRANSFER,
            status=PaymentStatus.PENDING,
        )
        ok = 0
        for payment in eligible:
            # Per-pagamento: un errore su uno non deve bloccare gli altri
            # ne' lasciare Payment salvati a meta' con una pagina 500.
            try:
                payment.bank_transfer_received_at = timezone.now().date()
                payment.bank_transfer_confirmed_by_user = request.user
                payment.mark_succeeded()
                ok += 1
            except Exception as e:
                logger.exception(
                    "Conferma bonifico fallita per payment %s", payment.id)
                self.message_user(
                    request,
                    f"Pagamento {payment.contract.contract_number}: errore "
                    f"nella conferma - {e}",
                    level=messages.ERROR,
                )

        if ok:
            self.message_user(
                request,
                f"{ok} bonifici confermati. Contratti firmati automaticamente.",
                level=messages.SUCCESS,
            )

        skipped = queryset.count() - ok
        if skipped:
            self.message_user(
                request,
                f"{skipped} pagamenti saltati (non bonifici in pending).",
                level=messages.WARNING,
            )


# =============================================================================
# CART SESSION
# =============================================================================

@admin.register(CartSession)
class CartSessionAdmin(admin.ModelAdmin):
    def get_queryset(self, request):
        from core.event_scope import (
            escludi_figli_di_contratti_cestinati, scope_lista_evento_attivo)
        qs = scope_lista_evento_attivo(
            request, super().get_queryset(request), 'contract__event')
        return escludi_figli_di_contratti_cestinati(request, qs)

    list_display = (
        'contact_display', 'contract_link', 'status_badge',
        'last_activity_short', 'abandoned_email_sent',
    )
    list_filter = ('status',)
    search_fields = (
        'contact__full_name', 'contact__email',
        'contract__contract_number',
    )
    list_select_related = ('contact', 'contact__sponsor', 'contract')
    readonly_fields = ('created_at', 'updated_at', 'last_activity_at',
                       'completed_at', 'abandoned_email_sent_at')
    ordering = ('-last_activity_at',)

    @admin.display(description='Contatto')
    def contact_display(self, obj):
        return f"{obj.contact.full_name} ({obj.contact.sponsor.legal_name})"

    @admin.display(description='Carrello', ordering='contract__contract_number')
    def contract_link(self, obj):
        url = reverse('admin:contracts_contract_change', args=[obj.contract_id])
        return format_html('<a href="{}">€ {}</a>', url, f"{obj.contract.total:,.2f}")

    @admin.display(description='Stato')
    def status_badge(self, obj):
        colors = {
            CartSessionStatus.ACTIVE: '#41ad7c',
            CartSessionStatus.ABANDONED: '#e6a23c',
            CartSessionStatus.COMPLETED: '#79aec8',
            CartSessionStatus.EXPIRED: '#999',
        }
        color = colors.get(obj.status, '#666')
        return format_html(
            '<span style="background:{}; color:white; padding:2px 8px; '
            'border-radius:3px; font-size:0.85em;">{}</span>',
            color, obj.get_status_display()
        )

    @admin.display(description='Ultima attività', ordering='last_activity_at')
    def last_activity_short(self, obj):
        return obj.last_activity_at.strftime('%d/%m/%Y %H:%M')

    @admin.display(description='Recovery inviata', boolean=True)
    def abandoned_email_sent(self, obj):
        return obj.abandoned_email_sent_at is not None
