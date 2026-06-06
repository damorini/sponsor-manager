"""
Admin per Events.

Usa il widget multilingua custom per name e description.
"""
from django import forms
from catalog.models import CatalogService, Service
from django.contrib import admin
from django.db.models import Count, Sum, Q
from django.utils.html import format_html
from django.urls import reverse

from core.admin_widgets import TranslatableJSONField

from .models import Event, EventStatus


class EventAdminForm(forms.ModelForm):
    name = TranslatableJSONField(
        languages=['it', 'en'],
        required_languages=['it'],
        label='Nome evento',
    )
    description = TranslatableJSONField(
        languages=['it', 'en'],
        required_languages=[],
        use_textarea=True,
        required=False,
        label='Descrizione',
    )

    catalog_services = forms.ModelMultipleChoiceField(
        queryset=CatalogService.objects.filter(is_active=True).order_by('display_order', 'code'),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Servizi disponibili (dal catalogo)",
        help_text="Spunta i servizi del catalogo da offrire in questo evento.",
    )

    class Meta:
        model = Event
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        inst = getattr(self, 'instance', None)
        if inst and inst.pk:
            ids = list(
                Service.objects.filter(
                    event=inst, catalog_source__isnull=False, is_active=True
                ).values_list('catalog_source_id', flat=True)
            )
            self.fields['catalog_services'].initial = ids


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    form = EventAdminForm

    list_display = (
        'name_display', 'event_type', 'start_date', 'status_badge',
        'sponsors_count', 'revenue_display', 'languages_display',
    )
    list_filter = ('status', 'event_type', 'default_language', 'start_date')
    search_fields = ('slug', 'name', 'location')
    date_hierarchy = 'start_date'
    ordering = ('-start_date',)
    readonly_fields = ('created_at', 'updated_at', 'sponsor_dashboard')
    actions = ['action_archivia', 'action_riattiva']

    @admin.action(description='Archivia eventi selezionati (spariscono dal portale, niente acquisti)')
    def action_archivia(self, request, queryset):
        from events.models import EventStatus
        n = queryset.update(status=EventStatus.ARCHIVED)
        self.message_user(request, f"{n} evento/i archiviato/i. Non sono più visibili né acquistabili nel portale (restano in 'Archivio eventi').")

    @admin.action(description='Riattiva eventi selezionati (vendita aperta)')
    def action_riattiva(self, request, queryset):
        from events.models import EventStatus
        n = queryset.update(status=EventStatus.SELLING)
        self.message_user(request, f"{n} evento/i riattivato/i (stato: Vendita aperta).")

    fieldsets = (
        (None, {
            'fields': ('slug', 'code', 'email_header_image', 'name', 'description', 'event_type', 'status'),
        }),
        ('Date e luogo', {
            'fields': ('start_date', 'end_date', 'location', 'venue_name', 'venue_address'),
        }),
        ('Lingue supportate', {
            'fields': ('supported_languages', 'default_language'),
            'description': "Quali lingue sono supportate per questo evento. "
                           "La lingua di default è obbligatoria nei campi multilingua.",
        }),
        ('Dati per contratti', {
            'fields': ('scientific_director', 'ecm_id', 'aifa_reference', 'medtech_svc_reference', 'organizer_legal_name', 'contract_signing_location'),
            'classes': ('collapse',),
        }),
        ("Servizi dell'evento (dal catalogo)", {
            'fields': ('catalog_services',),
            'description': "Spunta i servizi del catalogo da rendere disponibili. "
                           "Al salvataggio i servizi spuntati vengono creati/riattivati e "
                           "quelli tolti disattivati. Quantita' e prezzi si regolano nella sezione Servizi.",
        }),
        ('Note interne', {
            'fields': ('notes',),
            'classes': ('collapse',),
        }),
        ('Dashboard', {
            'fields': ('sponsor_dashboard',),
            'classes': ('collapse',),
        }),
        ('Sistema', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    def get_queryset(self, request):
        from core.event_scope import scope_by_event
        qs = scope_by_event(request, super().get_queryset(request), 'id')
        return qs.annotate(
            _sponsors_count=Count(
                'contracts__sponsor',
                filter=Q(contracts__deleted_at__isnull=True) &
                       ~Q(contracts__status__in=['cancelled', 'draft']),
                distinct=True,
            ),
            _revenue=Sum(
                'contracts__total',
                filter=Q(contracts__deleted_at__isnull=True) &
                       ~Q(contracts__status__in=['cancelled', 'draft']),
            ),
        )

    @admin.display(description='Nome', ordering='slug')
    def name_display(self, obj):
        return obj.get_name() if hasattr(obj, 'get_name') else obj.slug

    @admin.display(description='Stato')
    def status_badge(self, obj):
        colors = {
            EventStatus.PLANNING: '#999',
            EventStatus.SELLING: '#41ad7c',
            EventStatus.CLOSED_SALES: '#79aec8',
            EventStatus.LIVE: '#e6a23c',
            EventStatus.ARCHIVED: '#666',
        }
        color = colors.get(obj.status, '#666')
        return format_html(
            '<span style="background:{}; color:white; padding:2px 8px; '
            'border-radius:3px; font-size:0.85em;">{}</span>',
            color, obj.get_status_display()
        )

    @admin.display(description='Sponsor', ordering='_sponsors_count')
    def sponsors_count(self, obj):
        count = getattr(obj, '_sponsors_count', None)
        if count is None:
            return '—'
        return count

    @admin.display(description='Fatturato', ordering='_revenue')
    def revenue_display(self, obj):
        revenue = getattr(obj, '_revenue', None)
        if revenue is None:
            return '—'
        return format_html('<strong>€ {}</strong>', f"{revenue:,.2f}")

    @admin.display(description='Lingue')
    def languages_display(self, obj):
        if not obj.supported_languages:
            return '—'
        badges = ''.join([
            format_html(
                '<span style="background:#79aec8; color:white; padding:1px 6px; '
                'border-radius:3px; font-size:0.75em; margin-right:2px;">{}</span>',
                lang.upper()
            )
            for lang in obj.supported_languages
        ])
        return format_html(badges)

    @admin.display(description='Riepilogo evento')
    def sponsor_dashboard(self, obj):
        if not obj.pk:
            return '—'

        contracts_url = reverse('admin:contracts_contract_changelist') + f'?event__id__exact={obj.pk}'
        services_url = reverse('admin:catalog_service_changelist') + f'?event__id__exact={obj.pk}'
        stands_url = reverse('admin:venues_stand_changelist') + f'?event__id__exact={obj.pk}'

        return format_html(
            '<div style="line-height: 1.8;">'
            '<a href="{}" class="button">Vedi contratti</a> '
            '<a href="{}" class="button">Vedi servizi</a> '
            '<a href="{}" class="button">Vedi stand</a>'
            '</div>',
            contracts_url, services_url, stands_url,
        )

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        try:
            _sincronizza_servizi_catalogo(request, form.instance, form.cleaned_data.get('catalog_services'))
        except Exception as exc:
            from django.contrib import messages
            messages.warning(request, f"Servizi dal catalogo non sincronizzati: {exc}")


def _sincronizza_servizi_catalogo(request, event, selezionati):
    from django.contrib import messages
    from catalog.models import Service
    if selezionati is None:
        return
    selezionati = list(selezionati)
    sel_ids = {c.pk for c in selezionati}
    esistenti = {
        s.catalog_source_id: s
        for s in Service.objects.filter(event=event, catalog_source__isnull=False)
    }
    creati = riattivati = disattivati = 0
    for cat in selezionati:
        svc = esistenti.get(cat.pk)
        if svc is None:
            _crea_servizio_da_catalogo(cat, event)
            creati += 1
        elif not svc.is_active:
            svc.is_active = True
            svc.save(update_fields=['is_active'])
            riattivati += 1
    for cat_id, svc in esistenti.items():
        if cat_id not in sel_ids and svc.is_active:
            svc.is_active = False
            svc.save(update_fields=['is_active'])
            disattivati += 1
    if creati or riattivati or disattivati:
        messages.info(
            request,
            f"Catalogo -> evento: {creati} creati, {riattivati} riattivati, {disattivati} disattivati."
        )


def _crea_servizio_da_catalogo(cat, event):
    from catalog.models import Service, ServiceVariant
    code = cat.code
    base = code
    i = 2
    while Service.objects.filter(event=event, code=code).exists():
        code = f"{base}_{i}"
        i += 1
    svc = Service.objects.create(
        event=event,
        code=code,
        name=cat.name,
        description=cat.description,
        category=(cat.category.name if cat.category_id else ''),
        accounting_category=cat.accounting_category,
        pricing_mode=cat.pricing_mode,
        base_price=cat.base_price,
        pricing_tiers=cat.pricing_tiers,
        is_active=True,
        max_quantity=cat.max_quantity,
        total_available=None,
        triggers_deadlines=cat.triggers_deadlines,
        is_self_purchasable=cat.is_self_purchasable,
        self_purchase_cutoff_days=cat.self_purchase_cutoff_days,
        vat_rate=cat.vat_rate,
        vat_exemption_article=cat.vat_exemption_article,
        display_order=cat.display_order,
        catalog_source=cat,
    )
    if getattr(cat, 'image', None):
        try:
            from django.core.files.base import ContentFile
            import os as _os
            # Legge i byte dell'immagine del catalogo (senza modificarla)
            cat.image.open('rb')
            try:
                _data = cat.image.read()
            finally:
                cat.image.close()
            _base = _os.path.basename(cat.image.name) or 'img'
            # Salva una COPIA indipendente del file sul servizio
            # (services/images/). save=True fa scattare la
            # neutralizzazione/ottimizzazione lato Service. L'originale
            # del catalogo NON viene mai toccato.
            svc.image.save(_base, ContentFile(_data), save=True)
        except Exception:
            pass
    for cv in cat.variants.all():
        ServiceVariant.objects.create(
            service=svc, label=cv.label, label_en=cv.label_en, code=cv.code,
            base_price=cv.base_price, total_available=None,
            is_active=cv.is_active, display_order=cv.display_order,
        )
    return svc

