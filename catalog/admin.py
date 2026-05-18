"""
Admin per Catalog (Service e DeadlineTemplate).

Service ha campi multilingua e tutti i flag ecommerce.
DeadlineTemplate inline dentro Service.
"""
from django import forms
from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from core.admin_widgets import TranslatableJSONField

from .models import DeadlineTemplate, PricingMode, Service


class ServiceAdminForm(forms.ModelForm):
    name = TranslatableJSONField(
        languages=['it', 'en'],
        required_languages=['it'],
        label='Nome servizio',
    )
    description = TranslatableJSONField(
        languages=['it', 'en'],
        required_languages=[],
        use_textarea=True,
        required=False,
        label='Descrizione',
    )

    class Meta:
        model = Service
        fields = '__all__'


class DeadlineTemplateInline(admin.TabularInline):
    """Template scadenze associate a un servizio, editabili inline."""
    model = DeadlineTemplate
    extra = 0
    fields = (
        'deadline_type', 'title', 'days_before_event',
        'reminder_days_before', 'is_active',
    )


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    form = ServiceAdminForm

    list_display = (
        'code', 'name_display', 'event_link', 'category', 'pricing_display',
        'ecommerce_badge', 'cutoff_display', 'is_active',
    )
    list_filter = (
        'is_active', 'is_self_purchasable', 'pricing_mode',
        'category', 'event', 'triggers_deadlines',
    )
    search_fields = ('code', 'name', 'event__name', 'event__slug')
    list_select_related = ('event',)
    autocomplete_fields = ['event']
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('event', 'display_order')
    inlines = [DeadlineTemplateInline]

    fieldsets = (
        (None, {
            'fields': ('event', 'code', 'name', 'description', 'category'),
        }),
        ('Pricing', {
            'fields': ('pricing_mode', 'base_price', 'pricing_tiers',
                       'vat_rate', 'vat_exemption_article'),
            'description': "Per scaglioni: pricing_tiers come JSON list di "
                           '{"min": N, "max": N, "unit_price": X}',
        }),
        ('Disponibilità', {
            'fields': ('is_active', 'max_quantity', 'display_order'),
        }),
        ('Ecommerce sponsor', {
            'fields': ('is_self_purchasable', 'self_purchase_cutoff_days'),
            'description': "is_self_purchasable: appare nel portale sponsor. "
                           "cutoff: NULL = sempre, 0 = fino al giorno stesso, "
                           "N = chiude N giorni prima dell'evento.",
        }),
        ('Scadenze automatiche', {
            'fields': ('triggers_deadlines',),
            'description': "Se attivato, vendere questo servizio crea le "
                           "scadenze definite nei DeadlineTemplate sotto.",
        }),
        ('Sistema', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    @admin.display(description='Nome')
    def name_display(self, obj):
        if hasattr(obj, 'translated'):
            return obj.translated('name')
        return obj.name

    @admin.display(description='Evento', ordering='event__slug')
    def event_link(self, obj):
        url = reverse('admin:events_event_change', args=[obj.event_id])
        return format_html('<a href="{}">{}</a>', url, obj.event.slug)

    @admin.display(description='Pricing')
    def pricing_display(self, obj):
        if obj.pricing_mode == PricingMode.FIXED:
            return format_html('<strong>€ {:,.2f}</strong>', obj.base_price)
        if obj.pricing_mode == PricingMode.QUANTITY:
            return format_html('€ {:,.2f} <small>× q.tà</small>', obj.base_price)
        if obj.pricing_mode == PricingMode.TIERED:
            return format_html(
                '<small>scaglioni</small> <strong>€ {:,.2f}+</strong>',
                obj.base_price
            )
        return '—'

    @admin.display(description='Shop')
    def ecommerce_badge(self, obj):
        if obj.is_self_purchasable:
            return format_html(
                '<span style="background:#41ad7c; color:white; padding:2px 8px; '
                'border-radius:3px; font-size:0.85em;">🛒 SHOP</span>'
            )
        return '—'

    @admin.display(description='Cutoff')
    def cutoff_display(self, obj):
        if not obj.is_self_purchasable:
            return '—'
        if obj.self_purchase_cutoff_days is None:
            return format_html('<small>sempre</small>')
        if obj.self_purchase_cutoff_days == 0:
            return format_html('<small>fino al giorno</small>')
        return format_html('<small>{} gg prima</small>', obj.self_purchase_cutoff_days)


@admin.register(DeadlineTemplate)
class DeadlineTemplateAdmin(admin.ModelAdmin):
    """Admin separato per cercare template scadenze."""
    list_display = (
        'title', 'service_link', 'deadline_type',
        'days_before_event', 'reminder_days_before', 'is_active',
    )
    list_filter = ('is_active', 'service__event', 'deadline_type')
    search_fields = ('title', 'service__name', 'service__event__name')
    list_select_related = ('service', 'service__event')
    autocomplete_fields = ['service']
    ordering = ('service', 'display_order')

    @admin.display(description='Servizio', ordering='service__name')
    def service_link(self, obj):
        url = reverse('admin:catalog_service_change', args=[obj.service_id])
        return format_html('<a href="{}">{}</a>', url,
                           obj.service.translated('name') if hasattr(obj.service, 'translated')
                           else obj.service.name)
