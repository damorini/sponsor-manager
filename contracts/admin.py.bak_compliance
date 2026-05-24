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
        'created_at', 'updated_at',
        'subtotal', 'vat_amount', 'total',
        'sent_date', 'cancelled_date',
    )
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)
    inlines = [ContractLineInline, DeadlineInline, PaymentInline]

    fieldsets = (
        (None, {
            'fields': ('contract_number', 'event', 'sponsor', 'sponsor_signer_contact'),
        }),
        ('Tipo e origine', {
            'fields': ('contract_kind', 'parent_contract', 'origin', 'language'),
        }),
        ('Spazio espositivo', {
            'fields': ('stand', 'stand_block'),
            'description': 'Scegli stand singolo OPPURE blocco, non entrambi.',
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
        ('Template e clausole', {
            'fields': ('template_used', 'special_clauses'),
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

    actions = ['action_mark_as_sent', 'action_mark_as_signed', 'action_cancel']

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
