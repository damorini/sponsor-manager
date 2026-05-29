"""
Admin per Stand e StandBlock (spazi espositivi).

Stand inline dentro StandBlock per editare un blocco e i suoi stand insieme.
"""
from django import forms
from django.contrib import admin
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.db.models import Q
from django.urls import reverse
from django.utils.html import format_html

from .models import Stand, StandBlock, StandStatus


class StandInline(admin.TabularInline):
    """Stand editabili dentro la pagina del blocco."""
    model = Stand
    extra = 1
    fields = (
        'code', 'width_meters', 'depth_meters', 'stand_type',
        'has_power', 'status', 'base_price',
    )
    show_change_link = True


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
            # nuovo blocco: evento non ancora salvato -> mostro i disponibili
            # liberi di tutti gli eventi (la validazione controlla l'evento)
            f.queryset = (Stand.objects
                .filter(stand_block__isnull=True, status=StandStatus.AVAILABLE)
                .select_related('event').order_by('event__slug', 'code'))
        f.label_from_instance = lambda st: (
            f"{st.code} \u00b7 {st.event.slug}"
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
    list_display = (
        'code', 'name_or_dash', 'event_link', 'block_type',
        'stands_count_display', 'total_area_display',
        'block_price_display', 'status_badge',
    )
    list_filter = ('status', 'block_type', 'event')
    search_fields = ('code', 'name', 'event__name', 'event__slug')
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
        return obj.name or '—'

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
            return f"{obj.total_area_sqm} m²"
        return '—'

    @admin.display(description='Prezzo')
    def block_price_display(self, obj):
        if obj.block_price is not None:
            return f"€ {obj.block_price:,.2f}"
        return '—'

    @admin.display(description='Stato')
    def status_badge(self, obj):
        return _stand_status_badge(obj.status, obj.get_status_display())


@admin.register(Stand)
class StandAdmin(admin.ModelAdmin):
    list_display = (
        'code', 'event_link', 'block_link', 'dimensions_display',
        'stand_type', 'amenities_display', 'status_badge', 'base_price_display',
    )
    list_filter = ('status', 'stand_type', 'has_power', 'has_water', 'event')
    search_fields = ('code', 'event__name', 'event__slug', 'stand_block__code')
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
            return '—'
        url = reverse('admin:venues_standblock_change', args=[obj.stand_block_id])
        return format_html('<a href="{}">{}</a>', url, obj.stand_block.code)

    @admin.display(description='Dimensioni')
    def dimensions_display(self, obj):
        if obj.width_meters and obj.depth_meters:
            return f"{obj.width_meters}×{obj.depth_meters} m ({obj.area_sqm} m²)"
        return '—'

    @admin.display(description='Area')
    def area_sqm_display(self, obj):
        return f"{obj.area_sqm} m²" if obj.area_sqm else '—'

    @admin.display(description='Dotazioni')
    def amenities_display(self, obj):
        amenities = []
        if obj.has_power:
            amenities.append('⚡')
        if obj.has_water:
            amenities.append('💧')
        if obj.has_internet:
            amenities.append('🌐')
        return ' '.join(amenities) if amenities else '—'

    @admin.display(description='Stato')
    def status_badge(self, obj):
        return _stand_status_badge(obj.status, obj.get_status_display())

    @admin.display(description='Prezzo')
    def base_price_display(self, obj):
        if obj.base_price is not None:
            return f"€ {obj.base_price:,.2f}"
        return '—'


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
