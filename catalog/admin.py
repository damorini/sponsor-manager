"""
Admin per Catalog (Service e DeadlineTemplate).

Service ha campi multilingua e tutti i flag ecommerce.
DeadlineTemplate inline dentro Service.
"""
from django import forms
from django.contrib import admin
from django.db import models
from django.contrib.admin.widgets import AutocompleteSelect
from core.admin_filters import evento_filter, nascondi_archiviati_filter
from django.urls import reverse
from django.utils.html import format_html

from core.admin_widgets import TranslatableJSONField, DatalistTextInput

from .models import (CatalogService, CatalogServiceVariant, DeadlineFieldTemplate, DeadlineTemplate, PricingMode, Service, ServiceCategory, ServiceInclusion, ServiceVariant)


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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 'Categoria': tendina coi valori già usati (+ le categorie gestite del
        # catalogo), per evitare errori di battitura; resta libero per nuovi.
        if 'category' in self.fields:
            usate = (Service.objects.exclude(category='')
                     .order_by('category').values_list('category', flat=True).distinct())
            gestite = ServiceCategory.objects.order_by('name').values_list('name', flat=True)
            self.fields['category'].widget = DatalistTextInput(options=[*gestite, *usate])


class DeadlineTemplateForm(forms.ModelForm):
    """'Ruoli da notificare' come caselle da spuntare (niente testo libero):
    le scelte sono i ruoli funzionali dei contatti (ContactRole), così
    coincidono con quelli assegnati alle anagrafiche dell'azienda."""
    from sponsors.models import ContactRole as _ContactRole
    notify_roles = forms.MultipleChoiceField(
        choices=_ContactRole.choices,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Ruoli da notificare",
        help_text="Chi, tra i contatti dell'azienda, riceve il promemoria di "
                  "questa scadenza. Puoi selezionarne più di uno. Se non ne "
                  "scegli nessuno, l'avviso va al contatto principale.",
    )

    event = forms.ModelChoiceField(
        queryset=None,
        required=False,
        label="Evento (filtro)",
        help_text="Scegli prima il congresso: la lista dei servizi si restringe a quelli di quell'evento.",
    )

    class Meta:
        model = DeadlineTemplate
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from events.models import Event, EventStatus
        self.fields['event'].queryset = (
            Event.objects.exclude(status=EventStatus.ARCHIVED).order_by('-start_date')
        )
        # Pre-popola evento se record già salvato
        if self.instance and self.instance.pk and self.instance.service_id:
            try:
                self.initial['event'] = self.instance.service.event_id
            except Exception:
                pass
        # 'Tipo scadenza': suggerimenti coi tipi già usati + alcuni comuni.
        if 'deadline_type' in self.fields:
            usati = (DeadlineTemplate.objects.exclude(deadline_type='')
                     .order_by('deadline_type').values_list('deadline_type', flat=True).distinct())
            comuni = ['tecnica', 'materiali', 'documentazione', 'artwork', 'logo']
            self.fields['deadline_type'].widget = DatalistTextInput(options=[*comuni, *usati])


class DeadlineTemplateInline(admin.StackedInline):
    """Template scadenze associate a un servizio, editabili inline.
    Layout verticale (stacked): con molti campi (incluso il file modello) la
    versione tabellare andava fuori schermo a destra."""
    model = DeadlineTemplate
    extra = 0
    show_change_link = True
    fields = (
        ('deadline_type', 'title'),
        ('submission_kind', 'client_template_file'),
        ('days_before_event', 'reminder_days_before', 'is_active'),
    )


class _AutocompleteServiceByEvento(AutocompleteSelect):
    """AutocompleteSelect che aggiunge ?event=<id> all'URL della
    chiamata AJAX dell'autocomplete, cosi' ServiceAdmin.get_search_results
    filtra i risultati per evento del servizio padre."""
    def __init__(self, field, admin_site, parent_event_id=None, **kwargs):
        self._parent_event_id = parent_event_id
        super().__init__(field, admin_site, **kwargs)

    def get_url(self):
        url = super().get_url()
        if self._parent_event_id:
            sep = '&' if '?' in url else '?'
            url = "%s%sevent=%s" % (url, sep, self._parent_event_id)
        return url


class ServiceInclusionInline(admin.TabularInline):
    """Servizi inclusi (accessori) di un servizio, con la quantita' inclusa.
    La tendina 'child' e' filtrata sull'evento del servizio padre."""
    model = ServiceInclusion
    fk_name = 'parent'
    extra = 0
    autocomplete_fields = ['child']
    fields = ('child', 'quantity')
    verbose_name = 'Servizio incluso'
    verbose_name_plural = 'Servizi inclusi (accessori)'

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'child':
            parent_id = None
            try:
                parent_id = request.resolver_match.kwargs.get('object_id')
            except Exception:
                pass
            if parent_id:
                try:
                    parent = Service.objects.get(pk=parent_id)
                except Service.DoesNotExist:
                    parent = None
                if parent is not None:
                    kwargs['widget'] = _AutocompleteServiceByEvento(
                        db_field, self.admin_site,
                        parent_event_id=parent.event_id,
                    )
                    kwargs['queryset'] = Service.objects.filter(
                        event_id=parent.event_id,
                    ).exclude(pk=parent.pk)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class ServiceVariantInline(admin.TabularInline):
    model = ServiceVariant
    extra = 0
    fields = ('label', 'label_en', 'code', 'base_price', 'total_available', 'is_active', 'display_order')


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    @admin.display(description='Disponibili')
    def availability_display(self, obj):
        av = obj.quantity_available()
        if av is None:
            return '∞ (illimitato)'
        comm = obj.quantity_committed()
        return f'{av} liberi / {obj.total_available} tot ({comm} assegnati)'

    @admin.display(description='Img')
    def image_badge(self, obj):
        from django.utils.html import format_html
        if obj.image:
            return format_html(
                '<span style="color:#2e7d32;font-size:16px" title="{}">&#9989;</span>',
                obj.image.name.rsplit('/', 1)[-1],
            )
        return format_html('<span style="color:#bbb;font-size:16px" title="Nessuna immagine">&#9711;</span>')

    @admin.display(description='Scadenze')
    def scadenze_badge(self, obj):
        from django.utils.html import format_html
        n = getattr(obj, '_n_deadlines', obj.deadline_templates.filter(is_active=True).count())
        if n == 0:
            return format_html('<span style="color:#999">—</span>')
        # Usa il prefetch (se disponibile) per evitare query aggiuntive
        try:
            templates = [t for t in obj.deadline_templates.all() if t.is_active]
            titoli = ', '.join(
                t.title for t in sorted(templates, key=lambda t: t.days_before_event)
            )
        except Exception:
            titoli = ''
        return format_html(
            '<span style="background:#e8f5e9;color:#2e7d32;padding:2px 7px;'
            'border-radius:10px;font-size:11px;white-space:nowrap" title="{}">'
            '✓ {} scad.</span>',
            titoli, n,
        )

    def get_queryset(self, request):
        from django.db.models import Count
        qs = super().get_queryset(request)
        qs = qs.annotate(_n_deadlines=Count(
            'deadline_templates', filter=models.Q(deadline_templates__is_active=True)
        ))
        return qs.prefetch_related('deadline_templates')

    form = ServiceAdminForm

    list_display = (
        'code', 'display_order', 'name_display', 'image_badge', 'scadenze_badge', 'event_link', 'category',
        'pricing_display', 'ecommerce_badge', 'cutoff_display', 'is_active', 'availability_display',
    )
    # "Ordine" modificabile direttamente dalla lista: cosi' si riordina come
    # appare nell'ecommerce/portale senza aprire ogni servizio (la lista e'
    # gia' ordinata per display_order).
    list_editable = ('display_order',)
    list_filter = (
        nascondi_archiviati_filter('event'),
        evento_filter('event'),
        'is_active', 'is_self_purchasable', 'pricing_mode',
        'category', 'triggers_deadlines',
    )
    search_fields = ('code', 'name', 'event__name', 'event__slug')

    def get_search_results(self, request, queryset, search_term):
        queryset, may_dup = super().get_search_results(request, queryset, search_term)
        if "/autocomplete/" in request.path:
            _ev = request.GET.get("event")
            if _ev:
                queryset = queryset.filter(event_id=_ev)
            # Servizi di eventi ARCHIVIATI: fuori dai menu a tendina.
            from events.models import EventStatus
            queryset = queryset.exclude(event__status=EventStatus.ARCHIVED)
            # Nasconde dall'autocomplete i servizi ESAURITI con la STESSA logica del
            # portale (proprieta' is_sold_out): se il portale lo grigia, qui sparisce.
            _sold = [s.pk for s in queryset if getattr(s, 'is_sold_out', False)]
            if _sold:
                queryset = queryset.exclude(pk__in=_sold)
        return queryset, may_dup

    list_select_related = ('event',)
    autocomplete_fields = ['event']
    readonly_fields = ('created_at', 'updated_at', 'image_preview')
    @admin.display(description='Anteprima immagine')
    def image_preview(self, obj):
        from django.utils.html import format_html
        if getattr(obj, 'image', None):
            try:
                return format_html(
                    '<img src="{}" style="max-height:120px; max-width:240px; '
                    'object-fit:contain; border:1px solid #ddd; border-radius:4px;">',
                    obj.image.url)
            except Exception:
                return "(immagine non disponibile)"
        return "(nessuna immagine)"

    ordering = ('event', 'display_order')
    inlines = [DeadlineTemplateInline, ServiceVariantInline, ServiceInclusionInline]

    class Media:
        # service_event_filter: filtra i "Servizi inclusi" per evento.
        # service_from_catalog: auto-compila i campi scegliendo dal Catalogo madre.
        js = ('admin/js/service_event_filter.js', 'admin/js/service_from_catalog.js')

    fieldsets = (
        ('Crea da catalogo (opzionale)', {
            'fields': ('catalog_source',),
            'description': "Scegli una voce dal Catalogo madre: codice, nome IT/EN, "
                           "descrizione, prezzo e IVA si compilano da soli. "
                           "Poi puoi modificarli per questo evento.",
        }),
        (None, {
            'fields': ('event', 'code', 'name', 'description', 'image', 'image_preview', 'category'),
        }),
        ('Pricing', {
            'fields': ('pricing_mode', 'base_price', 'pricing_tiers',
                       'vat_rate', 'vat_exemption_article'),
            'description': "Per scaglioni: pricing_tiers come JSON list di "
                           '{"min": N, "max": N, "unit_price": X}',
        }),
        ('Disponibilità', {
            'fields': ('is_active', 'max_quantity', 'total_available', 'display_order'),
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
        prezzo = f"{obj.base_price:,.2f}"
        if obj.pricing_mode == PricingMode.FIXED:
            return format_html('<strong>€ {}</strong>', prezzo)
        if obj.pricing_mode == PricingMode.QUANTITY:
            return format_html('€ {} <small>× q.tà</small>', prezzo)
        if obj.pricing_mode == PricingMode.TIERED:
            return format_html(
                '<small>scaglioni</small> <strong>€ {}+</strong>',
                prezzo
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


class DeadlineFieldTemplateInline(admin.TabularInline):
    """Campi che il cliente deve compilare, come righe."""
    model = DeadlineFieldTemplate
    extra = 0
    fields = ('display_order', 'label', 'field_type', 'required', 'help_text')


@admin.register(DeadlineTemplate)
class DeadlineTemplateAdmin(admin.ModelAdmin):
    """Admin separato per cercare template scadenze."""
    form = DeadlineTemplateForm
    inlines = [DeadlineFieldTemplateInline]
    list_display = (
        'title', 'service_link', 'deadline_type',
        'days_before_event', 'reminder_days_before', 'is_active',
    )
    list_filter = (nascondi_archiviati_filter('service__event'), evento_filter('service__event'), 'is_active', 'deadline_type')
    search_fields = ('title', 'service__name', 'service__event__name')
    list_select_related = ('service', 'service__event')
    autocomplete_fields = ['service']
    ordering = ('service', 'display_order')

    fieldsets = (
        ('Selezione evento e servizio', {
            'fields': ('event', 'service'),
            'description': "Scegli prima il congresso per restringere la lista dei servizi.",
        }),
        ('Scadenza', {
            'fields': ('deadline_type', 'title', 'description', 'submission_kind',
                       'shipping_instructions',
                       'client_template_file', 'days_before_event', 'display_order'),
        }),
        ('Notifiche', {
            'fields': ('notify_roles', 'reminder_days_before'),
        }),
        ('Stato', {
            'fields': ('is_active',),
        }),
    )

    class Media:
        js = ('admin/js/deadline_event_filter.js', 'admin/js/deadline_shipping.js')

    @admin.display(description='Servizio', ordering='service__name')
    def service_link(self, obj):
        url = reverse('admin:catalog_service_change', args=[obj.service_id])
        return format_html('<a href="{}">{}</a>', url,
                           obj.service.translated('name') if hasattr(obj.service, 'translated')
                           else obj.service.name)


# ---- Catalogo servizi ----
class CatalogServiceVariantInline(admin.TabularInline):
    model = CatalogServiceVariant
    extra = 0
    fields = ('label', 'label_en', 'code', 'base_price', 'is_active', 'display_order')


class CatalogServiceAdminForm(forms.ModelForm):
    name = TranslatableJSONField(languages=['it', 'en'], required_languages=['it'], label='Nome servizio')
    description = TranslatableJSONField(languages=['it', 'en'], required_languages=[],
                                        use_textarea=True, required=False, label='Descrizione')

    class Meta:
        model = CatalogService
        fields = '__all__'


@admin.register(CatalogService)
class CatalogServiceAdmin(admin.ModelAdmin):
    form = CatalogServiceAdminForm
    list_display = ('code', 'nome_display', 'category', 'pricing_mode', 'base_price', 'is_active')
    list_filter = ('is_active', 'category', 'pricing_mode')
    search_fields = ('code', 'name')
    inlines = [CatalogServiceVariantInline]

    @admin.display(description='Nome')
    def nome_display(self, obj):
        try:
            return obj.get_name()
        except Exception:
            return obj.code


@admin.register(ServiceVariant)
class ServiceVariantAdmin(admin.ModelAdmin):
    """Registrato per abilitare l'autocomplete della variante nelle Righe
    contratto. Le varianti si gestiscono comunque dentro il Servizio."""
    list_display = ('label', 'service', 'code', 'base_price', 'is_active')
    list_filter = (evento_filter('service__event'), 'is_active')
    search_fields = ('label', 'label_en', 'code',
                     'service__name', 'service__event__name', 'service__event__slug')
    list_select_related = ('service', 'service__event')
    autocomplete_fields = ['service']

    def get_search_results(self, request, queryset, search_term):
        queryset, may_dup = super().get_search_results(request, queryset, search_term)
        if "/autocomplete/" in request.path:
            # Solo varianti attive; filtrate per evento se passato (?event=...)
            queryset = queryset.filter(is_active=True)
            _ev = request.GET.get("event")
            if _ev:
                queryset = queryset.filter(service__event_id=_ev)
            _serv = request.GET.get("service")
            if _serv:
                queryset = queryset.filter(service_id=_serv)
        return queryset, may_dup


@admin.register(ServiceCategory)
class ServiceCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'display_order', 'is_active')
    list_editable = ('display_order', 'is_active')
    search_fields = ('name', 'code')
    prepopulated_fields = {'code': ('name',)}
