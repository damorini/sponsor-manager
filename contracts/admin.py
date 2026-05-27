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
from django.contrib import admin, messages
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


# =============================================================================
# Inline forms
# =============================================================================

class ContractLineInline(admin.TabularInline):
    """Righe contratto editabili dentro il form contratto."""
    model = ContractLine
    extra = 0
    fields = (
        'service', 'quantity', 'unit_price',
        'discount_percent', 'discount_amount',
        'line_subtotal', 'line_vat', 'line_total',
    )
    readonly_fields = ('line_subtotal', 'line_vat', 'line_total')
    autocomplete_fields = ['service']


class DeadlineInline(admin.TabularInline):
    """Scadenze viewable inline (sola lettura, perchè generate automatico)."""
    model = Deadline
    extra = 0
    fields = ('title', 'due_date', 'status', 'completed_at', 'reminder_count')
    readonly_fields = ('title', 'due_date', 'completed_at', 'reminder_count')
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class PaymentInline(admin.TabularInline):
    """Pagamenti del contratto, sola lettura."""
    model = Payment
    extra = 0
    fields = (
        'payment_method', 'amount_gross', 'amount_fee',
        'status', 'paypal_order_id', 'bank_transfer_reference', 'completed_at',
    )
    readonly_fields = fields
    can_delete = False
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False


# =============================================================================
# CONTRACT
# =============================================================================

@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    @admin.display(description="Numero contratto")
    def contract_number_display(self, obj):
        # Mostra il numero; sui nuovi (non salvati) avvisa che e automatico
        if obj and obj.pk and obj.contract_number:
            return obj.contract_number
        return "(generato automaticamente al salvataggio)"

    list_display = (
        'contract_number', 'sponsor_link', 'event_link',
        'kind_badge', 'status_badge', 'venue_display',
        'total_display', 'origin_badge', 'created_at_short',
    )
    list_filter = (
        'status', 'contract_kind', 'origin', 'language',
        'event', 'vat_applicable',
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
    inlines = [ContractLineInline, DeadlineInline, PaymentInline]

    fieldsets = (
        (None, {
            'fields': ('contract_number_display', 'event', 'sponsor', 'sponsor_signer_contact'),
        }),
        ('Tipo e origine', {
            'fields': ('contract_kind', 'parent_contract', 'origin', 'language'),
        }),
        ('Spazio espositivo', {
            'fields': ('stand', 'stand_block'),
            'description': (
                'Scegli stand singolo OPPURE blocco, non entrambi. '
                'IMPORTANTE: nella tendina digita il nome (o slug) dell\'evento '
                'di questo contratto per vedere solo gli stand/blocchi di '
                'quell\'evento. Selezionare uno spazio di un altro evento dara\' errore al salvataggio.'
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
        ('Preventivo', {
            'fields': ('letter_template', 'quote_intro_text',),
            'description': "Scegli un template lettera: la lettera di preventivo "
                           "verra' generata al volo compilando i segnaposti coi dati "
                           "di questo contratto. (quote_intro_text e' un testo libero opzionale.)",
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

    actions = ['action_send_quote', 'action_convert_to_contract',
               'action_generate_client_summary',
               'action_mark_as_sent', 'action_mark_as_signed', 'action_cancel']

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
                '<path:object_id>/invia-preventivo/',
                self.admin_site.admin_view(self.send_quote_view),
                name='contracts_contract_send_quote',
            ),
            path(
                '<path:object_id>/invia-contratto/',
                self.admin_site.admin_view(self.send_contract_view),
                name='contracts_contract_send_contract',
            ),
        ]
        return custom + urls

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

    def send_quote_view(self, request, object_id):
        """Pagina di conferma: scelta destinatari, poi genera PDF e invia."""
        from .models import Contract
        from .services.pdf_generator import generate_quote_pdf
        from .services.email_sender import send_email
        from django.core.files.storage import default_storage

        contract = get_object_or_404(Contract, pk=object_id)
        contacts = self._contact_rows(contract)

        if request.method == 'POST':
            if not contract.letter_template:
                self.message_user(
                    request,
                    "Nessun template lettera selezionato sul contratto.",
                    level=messages.ERROR,
                )
                return HttpResponseRedirect('../')

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
                    subject=f"Preventivo {contract.contract_number} - {event_name}",
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

            self.message_user(
                request,
                f"Preventivo inviato a: {', '.join(recipients)} (PDF allegato).",
                level=messages.SUCCESS,
            )
            return HttpResponseRedirect('../')

        # GET: mostra la pagina di conferma
        context = {
            **self.admin_site.each_context(request),
            'title': 'Genera e invia preventivo',
            'contract': contract,
            'contacts': contacts,
            'opts': self.model._meta,
        }
        return render(request, 'admin/quote_send_confirm.html', context)

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

    @admin.action(description='Marca come INVIATO')
    def action_mark_as_sent(self, request, queryset):
        ok = err = 0
        for contract in queryset:
            try:
                contract.mark_as_sent()
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
                f"{ok} contratti marcati come inviati.",
                level=messages.SUCCESS,
            )

    @admin.action(description='Marca come FIRMATO')
    def action_mark_as_signed(self, request, queryset):
        ok = err = 0
        for contract in queryset:
            try:
                contract.mark_as_signed()
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
                f"{ok} contratti marcati come firmati. Scadenze generate, "
                f"stand assegnati.",
                level=messages.SUCCESS,
            )

    @admin.action(description='Annulla contratti selezionati')
    def action_cancel(self, request, queryset):
        # ATTENZIONE: in produzione, mostra una conferma esplicita.
        # Qui per semplicità annulla diretto.
        ok = 0
        for contract in queryset:
            if contract.status != ContractStatus.CANCELLED:
                contract.cancel(reason='Annullato da admin')
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
    list_display = (
        'contract_link', 'service_name_snapshot', 'quantity',
        'unit_price', 'discount_display', 'line_total',
    )
    list_filter = ('contract__event', 'service__category')
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
    list_display = (
        'title', 'contract_link', 'due_date', 'status_badge',
        'days_until_due_display', 'reminder_count',
    )
    list_filter = ('status', 'deadline_type', 'contract__event')
    search_fields = (
        'title', 'contract__contract_number',
        'contract__sponsor__legal_name',
    )
    list_select_related = ('contract', 'contract__sponsor', 'contract__event')
    autocomplete_fields = ['contract', 'contract_line', 'completed_by_contact']
    date_hierarchy = 'due_date'
    readonly_fields = ('created_at', 'updated_at', 'last_reminder_sent_at',
                       'reminder_count')
    ordering = ('due_date',)

    actions = ['action_mark_as_received']

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
    list_display = (
        'contract_link', 'method_badge', 'amount_gross',
        'amount_fee', 'amount_net_display', 'status_badge',
        'reference_display', 'completed_at_short',
    )
    list_filter = ('payment_method', 'status', 'currency')
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
            payment.bank_transfer_received_at = timezone.now().date()
            payment.bank_transfer_confirmed_by_user = request.user
            payment.mark_succeeded()
            ok += 1

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
