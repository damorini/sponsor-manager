"""
Admin per Stand e StandBlock (spazi espositivi).

StandBlock: si compone scegliendo, tramite selettore a doppia lista, gli stand
DISPONIBILI dell'evento (non si creano qui). Stand: lista con badge di stato,
incluso 'IN BLOCCO' per gli stand che fanno parte di un blocco.
"""
from django import forms
from django.contrib import admin
from core.admin_filters import evento_filter, nascondi_archiviati_filter
from core.admin_widgets import TranslatableJSONField
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.db.models import Q
from django.urls import reverse
from django.utils.html import format_html

from .models import Stand, StandBlock, StandStatus


class StandBlockForm(forms.ModelForm):
    """Form del blocco: permette di SCEGLIERE quali stand (gia' esistenti e
    disponibili) fanno parte del blocco, tramite selettore a doppia lista."""
    stands = forms.ModelMultipleChoiceField(
        queryset=Stand.objects.none(),
        required=False,
        widget=FilteredSelectMultiple("stand", is_stacked=False),
        label="Stand del blocco",
        help_text="Solo stand DISPONIBILI di questo evento (non prenotati/"
                  "assegnati). Gli stand si creano prima (import Excel o lista "
                  "Stand); qui scegli quali raggruppare nel blocco.",
    )
    quote_description = TranslatableJSONField(
        languages=['it', 'en'], required_languages=[], required=False,
        label="Descrizione per preventivo (IT/EN)",
    )

    class Meta:
        model = StandBlock
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        inst = self.instance
        f = self.fields['stands']
        if inst and inst.pk and inst.event_id:
            # in modifica: stand disponibili-non-assegnati di QUESTO evento
            # + quelli gia' nel blocco (per poterli togliere)
            f.queryset = (Stand.objects
                .filter(event=inst.event)
                .filter(Q(stand_block__isnull=True, status=StandStatus.AVAILABLE)
                        | Q(stand_block=inst))
                .select_related('event').order_by('code'))
            f.initial = Stand.objects.filter(stand_block=inst)
        else:
            f.queryset = (Stand.objects
                .filter(stand_block__isnull=True, status=StandStatus.AVAILABLE)
                .select_related('event').order_by('event__slug', 'code'))
        # L'etichetta include il NOME dell'evento (come nella tendina Evento):
        # cosi' il filtro integrato della casella puo' restringere per evento.
        f.label_from_instance = lambda st: (
            f"{st.code} \u00b7 {st.event}"
            + (f" ({st.width_meters}\u00d7{st.depth_meters}m)"
               if st.width_meters and st.depth_meters else "")
        )

    def clean_stands(self):
        stands = self.cleaned_data.get('stands')
        event = self.cleaned_data.get('event') or (
            self.instance.event if self.instance.pk else None)
        if stands and event:
            wrong = [st.code for st in stands if st.event_id != event.id]
            if wrong:
                raise forms.ValidationError(
                    "Questi stand non appartengono all'evento del blocco: "
                    + ", ".join(wrong))
        return stands


@admin.register(StandBlock)
class StandBlockAdmin(admin.ModelAdmin):
    def get_queryset(self, request):
        from core.event_scope import scope_by_event
        return scope_by_event(request, super().get_queryset(request), 'event')

    list_display = (
        'code', 'name_or_dash', 'event_link', 'block_type',
        'stands_count_display', 'total_area_display',
        'block_price_display', 'status_badge',
    )
    list_filter = (nascondi_archiviati_filter('event'), evento_filter('event'), 'status', 'block_type')
    search_fields = ('code', 'name', 'event__name', 'event__slug')

    def get_search_results(self, request, queryset, search_term):
        # AUTOCOMPLETE_SOLO_DISPONIBILI: nella tendina autocomplete (selezione spazio nel contratto)
        # mostra solo gli stand/blocchi DISPONIBILI, nascondendo quelli
        # Riservati (opzionati), Assegnati (venduti) o Non disponibili.
        queryset, may_dup = super().get_search_results(
            request, queryset, search_term)
        if "/autocomplete/" in request.path:
            queryset = queryset.filter(status=StandStatus.AVAILABLE)
            _ev = request.GET.get("event")
            if _ev:
                queryset = queryset.filter(event_id=_ev)
        return queryset, may_dup

    list_select_related = ('event',)
    autocomplete_fields = ['event']
    readonly_fields = ('created_at', 'updated_at')
    form = StandBlockForm

    fieldsets = (
        (None, {
            'fields': ('event', 'code', 'name', 'block_type', 'status'),
        }),
        ('Stand del blocco', {
            'fields': ('stands',),
        }),
        ('Descrizione per il preventivo', {
            'fields': ('quote_description',),
            'description': "Questo testo compare SOLO nel preventivo del cliente.",
        }),
        ('Dimensioni e prezzo', {
            'fields': ('total_area_sqm', 'block_price'),
            'description': "Prezzo blocco: lascialo VUOTO per usare in automatico "
                           "la somma dei prezzi degli stand inclusi. Inseriscilo "
                           "solo se vuoi forzare un prezzo diverso.",
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

    class Media:
        # Filtra la casella "Stand del blocco" per l'evento scelto nel form.
        js = ('admin/js/standblock_event_filter.js',)

    def get_fieldsets(self, request, obj=None):
        # In CREAZIONE mostro gia' il selettore stand: la casella elenca tutti
        # gli stand DISPONIBILI e, scegliendo l'evento, si filtra in automatico
        # su quel congresso (vedi standblock_event_filter.js). La validazione
        # (clean_stands) impedisce comunque di legare stand di un altro evento.
        if obj is None:
            return (
                (None, {
                    'fields': ('event', 'code', 'name', 'block_type', 'status'),
                    'description': "Scegli prima il congresso: la casella qui sotto "
                                   "mostrera' solo gli stand disponibili di QUEL congresso.",
                }),
                ('Stand del blocco', {
                    'fields': ('stands',),
                    'description': "Sposta a destra gli stand da includere nel blocco. "
                                   "Sono elencati solo gli stand DISPONIBILI.",
                }),
                ('Descrizione per il preventivo', {
                    'fields': ('quote_description',),
                }),
                ('Dimensioni e prezzo', {
                    'fields': ('total_area_sqm', 'block_price'),
                    'description': "Prezzo blocco: lascialo VUOTO per usare la somma "
                                   "dei prezzi degli stand. Inseriscilo solo per "
                                   "forzare un prezzo diverso.",
                }),
                ('Note', {
                    'fields': ('notes',),
                    'classes': ('collapse',),
                }),
            )
        return super().get_fieldsets(request, obj)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        block = form.instance
        selected = form.cleaned_data.get('stands')
        if selected is None:
            return
        current = set(Stand.objects.filter(stand_block=block)
                      .values_list('id', flat=True))
        chosen = set(st.id for st in selected)
        to_remove = current - chosen
        to_add = chosen - current
        if to_remove:
            Stand.objects.filter(id__in=to_remove).update(stand_block=None)
        if to_add:
            Stand.objects.filter(id__in=to_add).update(stand_block=block)

    @admin.display(description='Nome')
    def name_or_dash(self, obj):
        return obj.name or '\u2014'

    @admin.display(description='Evento', ordering='event__slug')
    def event_link(self, obj):
        url = reverse('admin:events_event_change', args=[obj.event_id])
        return format_html('<a href="{}">{}</a>', url, obj.event.slug)

    @admin.display(description='Stand')
    def stands_count_display(self, obj):
        return obj.stands_count

    @admin.display(description='Area totale')
    def total_area_display(self, obj):
        if obj.total_area_sqm:
            return f"{obj.total_area_sqm} m\u00b2"
        return '\u2014'

    @admin.display(description='Prezzo')
    def block_price_display(self, obj):
        if obj.block_price is not None:
            return format_html('\u20ac {}', f"{obj.block_price:,.2f}")
        # Nessun prezzo a mano: mostra la somma degli stand (calcolata).
        somma = obj.stands_price_sum
        return format_html(
            '<span title="Somma prezzi stand (nessun prezzo blocco impostato)">'
            '\u20ac {} <small style="color:#8a7a66;">(somma stand)</small></span>',
            f"{somma:,.2f}")

    @admin.display(description='Stato')
    def status_badge(self, obj):
        return _stand_status_badge(obj.status, obj.get_status_display())


class StandAdminForm(forms.ModelForm):
    """Form Stand con descrizione preventivo bilingue (IT/EN)."""
    quote_description = TranslatableJSONField(
        languages=['it', 'en'], required_languages=[], required=False,
        label="Descrizione per preventivo (IT/EN)",
    )

    class Meta:
        model = Stand
        fields = '__all__'


@admin.register(Stand)
class StandAdmin(admin.ModelAdmin):
    form = StandAdminForm

    def get_queryset(self, request):
        from core.event_scope import scope_by_event
        from django.db.models import Prefetch
        from contracts.models import Contract, ContractStatus
        qs = super().get_queryset(request)
        # Prefetch dei contratti (non bozza/annullati) che occupano lo stand,
        # con lo sponsor, per mostrare chi ha acquistato/opzionato senza N+1.
        rel = (Contract.objects
               .filter(deleted_at__isnull=True)
               .exclude(status__in=[ContractStatus.DRAFT, ContractStatus.CANCELLED])
               .select_related('sponsor')
               .order_by('-created_at'))
        qs = qs.prefetch_related(
            Prefetch('contracts', queryset=rel, to_attr='occupanti'))
        return scope_by_event(request, qs, 'event')

    list_display = (
        'code', 'event_link', 'block_link', 'dimensions_display',
        'stand_type', 'amenities_display', 'status_badge', 'sponsor_display',
        'base_price_display',
    )
    list_filter = (nascondi_archiviati_filter('event'), evento_filter('event'), 'status', 'stand_type', 'has_power', 'has_water')
    search_fields = ('code', 'event__name', 'event__slug', 'stand_block__code')

    def get_search_results(self, request, queryset, search_term):
        # AUTOCOMPLETE_SOLO_DISPONIBILI: nella tendina autocomplete (selezione spazio nel contratto)
        # mostra solo gli stand/blocchi DISPONIBILI, nascondendo quelli
        # Riservati (opzionati), Assegnati (venduti) o Non disponibili.
        queryset, may_dup = super().get_search_results(
            request, queryset, search_term)
        if "/autocomplete/" in request.path:
            queryset = queryset.filter(status=StandStatus.AVAILABLE, stand_block__isnull=True)
            _ev = request.GET.get("event")
            if _ev:
                queryset = queryset.filter(event_id=_ev)
        return queryset, may_dup

    list_select_related = ('event', 'stand_block')
    autocomplete_fields = ['event', 'stand_block']
    readonly_fields = ('created_at', 'updated_at', 'area_sqm_display')
    ordering = ('event', 'code')

    fieldsets = (
        (None, {
            'fields': ('event', 'stand_block', 'code', 'stand_type', 'status'),
        }),
        ('Dimensioni', {
            'fields': (
                ('width_meters', 'depth_meters'),
                'area_sqm_display',
                'max_height_meters',
            ),
        }),
        ('Dotazioni', {
            'fields': (
                ('has_power', 'power_kw'),
                'has_water',
                'has_internet',
            ),
        }),
        ('Posizionamento', {
            'fields': (('map_x', 'map_y'),),
            'classes': ('collapse',),
        }),
        ('Prezzo', {
            'fields': ('base_price',),
        }),
        ('Descrizione per il preventivo', {
            'fields': ('quote_description',),
            'description': "Compare SOLO nel preventivo del cliente. "
                           "L'inglese si compila da solo al salvataggio.",
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

    @admin.display(description='Evento', ordering='event__slug')
    def event_link(self, obj):
        url = reverse('admin:events_event_change', args=[obj.event_id])
        return format_html('<a href="{}">{}</a>', url, obj.event.slug)

    @admin.display(description='Blocco')
    def block_link(self, obj):
        if not obj.stand_block_id:
            return '\u2014'
        url = reverse('admin:venues_standblock_change', args=[obj.stand_block_id])
        return format_html('<a href="{}">{}</a>', url, obj.stand_block.code)

    @admin.display(description='Dimensioni')
    def dimensions_display(self, obj):
        if obj.width_meters and obj.depth_meters:
            return f"{obj.width_meters}\u00d7{obj.depth_meters} m ({obj.area_sqm} m\u00b2)"
        return '\u2014'

    @admin.display(description='Area')
    def area_sqm_display(self, obj):
        return f"{obj.area_sqm} m\u00b2" if obj.area_sqm else '\u2014'

    @admin.display(description='Dotazioni')
    def amenities_display(self, obj):
        amenities = []
        if obj.has_power:
            amenities.append('\u26a1')
        if obj.has_water:
            amenities.append('\U0001f4a7')
        if obj.has_internet:
            amenities.append('\U0001f310')
        return ' '.join(amenities) if amenities else '\u2014'

    @admin.display(description='Stato')
    def status_badge(self, obj):
        # Stand dentro un blocco: spazio bloccato, non vendibile singolarmente
        if obj.stand_block_id and obj.status == StandStatus.AVAILABLE:
            return format_html(
                '<span style="background:{}; color:white; padding:2px 8px; '
                'border-radius:3px; font-size:0.85em; font-weight:700; '
                'letter-spacing:0.3px;">IN BLOCCO</span>',
                '#8e44ad'
            )
        return _stand_status_badge(obj.status, obj.get_status_display())

    @admin.display(description='Prezzo')
    def base_price_display(self, obj):
        if obj.base_price is not None:
            return f"\u20ac {obj.base_price:,.2f}"
        return '\u2014'

    @admin.display(description='Sponsor')
    def sponsor_display(self, obj):
        """Sponsor che ha acquistato (o opzionato) lo stand.
        Prima cerca un contratto sullo stand singolo, poi sul blocco."""
        from contracts.models import ContractStatus
        occ = list(getattr(obj, 'occupanti', None) or [])
        # Fallback: stand dentro un blocco venduto/opzionato -> contratto sul blocco
        if not occ and obj.stand_block_id:
            occ = list(obj.stand_block.contracts
                       .filter(deleted_at__isnull=True)
                       .exclude(status__in=[ContractStatus.DRAFT, ContractStatus.CANCELLED])
                       .select_related('sponsor')
                       .order_by('-created_at'))
        if not occ:
            return '\u2014'
        firmati = [ContractStatus.SIGNED, ContractStatus.ACTIVE, ContractStatus.COMPLETED]
        attivi = [c for c in occ if c.status in firmati]
        c = attivi[0] if attivi else occ[0]
        if not c.sponsor_id:
            return '\u2014'
        url = reverse('admin:sponsors_sponsor_change', args=[c.sponsor_id])
        label = c.sponsor.display_name or c.sponsor.legal_name
        opzione = c.status in [ContractStatus.SENT, ContractStatus.PENDING_PAYMENT]
        if opzione:
            return format_html(
                '<a href="{}">{}</a> <small style="color:#e6a23c;">(opzione)</small>',
                url, label)
        return format_html('<a href="{}">{}</a>', url, label)


# Helper condiviso per badge stato
def _stand_status_badge(status, label):
    colors = {
        StandStatus.AVAILABLE: '#41ad7c',
        StandStatus.RESERVED: '#e6a23c',
        StandStatus.ASSIGNED: '#79aec8',
        StandStatus.UNAVAILABLE: '#999',
    }
    color = colors.get(status, '#666')
    return format_html(
        '<span style="background:{}; color:white; padding:2px 8px; '
        'border-radius:3px; font-size:0.85em;">{}</span>',
        color, label
    )
